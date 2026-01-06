# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""AWS client wrapper with rate limiting and backoff."""

import asyncio
import time
from typing import Any, Callable
from datetime import datetime, timedelta

import boto3
from botocore.exceptions import ClientError, BotoCoreError
from botocore.config import Config


class AWSAPIError(Exception):
    """Raised when AWS API calls fail."""
    pass


class AWSClient:
    """
    Wrapper around boto3 clients with rate limiting and exponential backoff.
    
    Uses IAM instance profile for authentication - no hardcoded credentials.
    Implements exponential backoff for rate limit errors.
    """
    
    def __init__(self, region: str = "us-east-1"):
        """
        Initialize AWS clients.
        
        Args:
            region: AWS region to use for regional services
        """
        # Configure boto3 with retries
        config = Config(
            region_name=region,
            retries={
                'max_attempts': 3,
                'mode': 'adaptive'
            }
        )
        
        # Initialize clients - uses IAM instance profile automatically
        self.region = region
        self.ec2 = boto3.client('ec2', config=config)
        self.rds = boto3.client('rds', config=config)
        self.s3 = boto3.client('s3', config=config)
        self.lambda_client = boto3.client('lambda', config=config)
        self.ecs = boto3.client('ecs', config=config)
        self.sts = boto3.client('sts', config=config)
        self.opensearch = boto3.client('opensearch', config=config)
        # Cost Explorer is always us-east-1
        self.ce = boto3.client('ce', region_name='us-east-1')
        
        # Cache account ID to avoid repeated STS calls
        self._account_id: str | None = None
        
        # Rate limiting state
        self._last_call_time: dict[str, float] = {}
        self._min_call_interval = 0.1  # 100ms between calls to same service
    
    async def _rate_limit(self, service_name: str) -> None:
        """
        Implement basic rate limiting between calls to the same service.
        
        Args:
            service_name: Name of the AWS service
        """
        if service_name in self._last_call_time:
            elapsed = time.time() - self._last_call_time[service_name]
            if elapsed < self._min_call_interval:
                await asyncio.sleep(self._min_call_interval - elapsed)
        
        self._last_call_time[service_name] = time.time()
    
    async def _call_with_backoff(
        self,
        service_name: str,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Call AWS API with exponential backoff on rate limit errors.
        
        Args:
            service_name: Name of the AWS service
            func: Boto3 client method to call
            *args: Positional arguments for the method
            **kwargs: Keyword arguments for the method
        
        Returns:
            Response from AWS API
        
        Raises:
            AWSAPIError: If the API call fails after retries
        """
        await self._rate_limit(service_name)
        
        max_retries = 5
        base_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                # Run boto3 call in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: func(*args, **kwargs)
                )
                return response
            
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', '')
                
                # Retry on throttling errors
                if error_code in ['Throttling', 'ThrottlingException', 'RequestLimitExceeded']:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        await asyncio.sleep(delay)
                        continue
                
                # Don't retry other errors
                raise AWSAPIError(f"AWS API error: {error_code} - {str(e)}") from e
            
            except BotoCoreError as e:
                raise AWSAPIError(f"Boto3 error: {str(e)}") from e
        
        raise AWSAPIError(f"Max retries exceeded for {service_name}")
    
    async def _get_account_id(self) -> str:
        """
        Get the AWS account ID using STS GetCallerIdentity.
        
        Returns:
            AWS account ID
        
        Raises:
            AWSAPIError: If unable to get account ID
        """
        if self._account_id is not None:
            return self._account_id
        
        try:
            response = await self._call_with_backoff(
                "sts",
                self.sts.get_caller_identity
            )
            self._account_id = response.get("Account", "")
            if not self._account_id:
                raise AWSAPIError("Account ID not found in STS response")
            return self._account_id
        
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to get account ID: {str(e)}") from e
    
    def _extract_tags(self, tag_list: list[dict[str, str]]) -> dict[str, str]:
        """
        Convert AWS tag list format to dictionary.
        
        Args:
            tag_list: List of tags in AWS format [{"Key": "...", "Value": "..."}]
                     or ECS format [{"key": "...", "value": "..."}]
        
        Returns:
            Dictionary of tag key-value pairs
        """
        if not tag_list:
            return {}
        
        result = {}
        for tag in tag_list:
            # Handle both uppercase (EC2, RDS, S3, Lambda) and lowercase (ECS) keys
            key = tag.get("Key") or tag.get("key", "")
            value = tag.get("Value") or tag.get("value", "")
            if key:  # Only add if key is not empty
                result[key] = value
        
        return result
    
    async def get_ec2_instances(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        Fetch EC2 instances with their tags.
        
        Args:
            filters: Optional filters for the query (e.g., {"region": "us-east-1"})
        
        Returns:
            List of EC2 instance resources with tags
        """
        filters = filters or {}
        
        # Build EC2 filters
        ec2_filters = []
        if "region" in filters and filters["region"] != self.region:
            # Would need to create a new client for different region
            # For now, only support current region
            return []
        
        try:
            # Get account ID for ARN construction
            account_id = await self._get_account_id()
            
            response = await self._call_with_backoff(
                "ec2",
                self.ec2.describe_instances,
                Filters=ec2_filters
            )
            
            resources = []
            for reservation in response.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    instance_id = instance.get("InstanceId")
                    tags = self._extract_tags(instance.get("Tags", []))
                    launch_time = instance.get("LaunchTime")
                    
                    resources.append({
                        "resource_id": instance_id,
                        "resource_type": "ec2:instance",
                        "region": self.region,
                        "tags": tags,
                        "created_at": launch_time,
                        "arn": f"arn:aws:ec2:{self.region}:{account_id}:instance/{instance_id}"
                    })
            
            return resources
        
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch EC2 instances: {str(e)}") from e
    
    async def get_rds_instances(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        Fetch RDS instances with their tags.
        
        Args:
            filters: Optional filters for the query
        
        Returns:
            List of RDS instance resources with tags
        """
        filters = filters or {}
        
        try:
            response = await self._call_with_backoff(
                "rds",
                self.rds.describe_db_instances
            )
            
            resources = []
            for db_instance in response.get("DBInstances", []):
                db_arn = db_instance.get("DBInstanceArn")
                db_id = db_instance.get("DBInstanceIdentifier")
                created_at = db_instance.get("InstanceCreateTime")
                
                # Fetch tags for this RDS instance
                tags_response = await self._call_with_backoff(
                    "rds",
                    self.rds.list_tags_for_resource,
                    ResourceName=db_arn
                )
                
                tags = self._extract_tags(tags_response.get("TagList", []))
                
                resources.append({
                    "resource_id": db_id,
                    "resource_type": "rds:db",
                    "region": self.region,
                    "tags": tags,
                    "created_at": created_at,
                    "arn": db_arn
                })
            
            return resources
        
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch RDS instances: {str(e)}") from e
    
    async def get_s3_buckets(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        Fetch S3 buckets with their tags.
        
        Args:
            filters: Optional filters for the query
        
        Returns:
            List of S3 bucket resources with tags
        """
        filters = filters or {}
        
        try:
            response = await self._call_with_backoff(
                "s3",
                self.s3.list_buckets
            )
            
            resources = []
            for bucket in response.get("Buckets", []):
                bucket_name = bucket.get("Name")
                created_at = bucket.get("CreationDate")
                
                # Fetch tags for this bucket
                try:
                    tags_response = await self._call_with_backoff(
                        "s3",
                        self.s3.get_bucket_tagging,
                        Bucket=bucket_name
                    )
                    tags = self._extract_tags(tags_response.get("TagSet", []))
                except AWSAPIError:
                    # Bucket might not have tags
                    tags = {}
                
                resources.append({
                    "resource_id": bucket_name,
                    "resource_type": "s3:bucket",
                    "region": "global",  # S3 buckets are global
                    "tags": tags,
                    "created_at": created_at,
                    "arn": f"arn:aws:s3:::{bucket_name}"
                })
            
            return resources
        
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch S3 buckets: {str(e)}") from e
    
    async def get_lambda_functions(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        Fetch Lambda functions with their tags.
        
        Args:
            filters: Optional filters for the query
        
        Returns:
            List of Lambda function resources with tags
        """
        filters = filters or {}
        
        try:
            response = await self._call_with_backoff(
                "lambda",
                self.lambda_client.list_functions
            )
            
            resources = []
            for function in response.get("Functions", []):
                function_name = function.get("FunctionName")
                function_arn = function.get("FunctionArn")
                last_modified = function.get("LastModified")
                
                # Fetch tags for this function
                try:
                    tags_response = await self._call_with_backoff(
                        "lambda",
                        self.lambda_client.list_tags,
                        Resource=function_arn
                    )
                    tags = tags_response.get("Tags", {})
                except AWSAPIError:
                    tags = {}
                
                resources.append({
                    "resource_id": function_name,
                    "resource_type": "lambda:function",
                    "region": self.region,
                    "tags": tags,
                    "created_at": last_modified,
                    "arn": function_arn
                })
            
            return resources
        
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch Lambda functions: {str(e)}") from e
    
    async def get_ecs_services(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        Fetch ECS services with their tags.
        
        Args:
            filters: Optional filters for the query
        
        Returns:
            List of ECS service resources with tags
        """
        filters = filters or {}
        
        try:
            # First, list all clusters
            clusters_response = await self._call_with_backoff(
                "ecs",
                self.ecs.list_clusters
            )
            
            resources = []
            for cluster_arn in clusters_response.get("clusterArns", []):
                # List services in this cluster
                services_response = await self._call_with_backoff(
                    "ecs",
                    self.ecs.list_services,
                    cluster=cluster_arn
                )
                
                if not services_response.get("serviceArns"):
                    continue
                
                # Describe services to get details
                describe_response = await self._call_with_backoff(
                    "ecs",
                    self.ecs.describe_services,
                    cluster=cluster_arn,
                    services=services_response.get("serviceArns", []),
                    include=["TAGS"]
                )
                
                for service in describe_response.get("services", []):
                    service_name = service.get("serviceName")
                    service_arn = service.get("serviceArn")
                    created_at = service.get("createdAt")
                    
                    tags = self._extract_tags(service.get("tags", []))
                    
                    resources.append({
                        "resource_id": service_name,
                        "resource_type": "ecs:service",
                        "region": self.region,
                        "tags": tags,
                        "created_at": created_at,
                        "arn": service_arn
                    })
            
            return resources
        
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch ECS services: {str(e)}") from e
    
    async def get_opensearch_domains(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        Fetch OpenSearch domains with their tags.
        
        Args:
            filters: Optional filters for the query
        
        Returns:
            List of OpenSearch domain resources with tags
        """
        filters = filters or {}
        
        try:
            # Get account ID for ARN construction
            account_id = await self._get_account_id()
            
            # List all domain names
            list_response = await self._call_with_backoff(
                "opensearch",
                self.opensearch.list_domain_names
            )
            
            resources = []
            for domain_info in list_response.get("DomainNames", []):
                domain_name = domain_info.get("DomainName")
                
                if not domain_name:
                    continue
                
                # Get domain details
                try:
                    describe_response = await self._call_with_backoff(
                        "opensearch",
                        self.opensearch.describe_domain,
                        DomainName=domain_name
                    )
                    
                    domain_status = describe_response.get("DomainStatus", {})
                    domain_arn = domain_status.get("ARN", f"arn:aws:es:{self.region}:{account_id}:domain/{domain_name}")
                    created_at = domain_status.get("Created")
                    
                    # Fetch tags for this domain
                    try:
                        tags_response = await self._call_with_backoff(
                            "opensearch",
                            self.opensearch.list_tags,
                            ARN=domain_arn
                        )
                        tags = self._extract_tags(tags_response.get("TagList", []))
                    except AWSAPIError:
                        tags = {}
                    
                    resources.append({
                        "resource_id": domain_name,
                        "resource_type": "opensearch:domain",
                        "region": self.region,
                        "tags": tags,
                        "created_at": created_at,
                        "arn": domain_arn
                    })
                
                except AWSAPIError as e:
                    # Log but continue with other domains
                    import logging
                    logging.getLogger(__name__).warning(
                        f"Failed to describe OpenSearch domain {domain_name}: {str(e)}"
                    )
                    continue
            
            return resources
        
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch OpenSearch domains: {str(e)}") from e
    
    async def get_cost_data(
        self,
        resource_ids: list[str] | None = None,
        time_period: dict[str, str] | None = None,
        granularity: str = "MONTHLY"
    ) -> dict[str, float]:
        """
        Fetch cost data from AWS Cost Explorer.
        
        Args:
            resource_ids: Optional list of resource IDs to filter costs
            time_period: Time period for cost data (e.g., {"Start": "2025-01-01", "End": "2025-01-31"})
            granularity: Cost granularity (DAILY, MONTHLY, HOURLY)
        
        Returns:
            Dictionary mapping resource IDs to their monthly costs
        """
        # Default to last 30 days if no time period specified
        if not time_period:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            time_period = {
                "Start": start_date.strftime("%Y-%m-%d"),
                "End": end_date.strftime("%Y-%m-%d")
            }
        
        try:
            # Get cost and usage data
            response = await self._call_with_backoff(
                "ce",
                self.ce.get_cost_and_usage,
                TimePeriod=time_period,
                Granularity=granularity,
                Metrics=["UnblendedCost"],
                GroupBy=[
                    {
                        "Type": "DIMENSION",
                        "Key": "SERVICE"
                    }
                ]
            )
            
            # Parse cost data
            cost_by_service = {}
            for result in response.get("ResultsByTime", []):
                for group in result.get("Groups", []):
                    service = group.get("Keys", [""])[0]
                    amount = float(group.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", 0))
                    
                    if service in cost_by_service:
                        cost_by_service[service] += amount
                    else:
                        cost_by_service[service] = amount
            
            # If specific resource IDs provided, try to estimate their costs
            # This is a simplified approach - real implementation would need resource-level cost allocation
            if resource_ids:
                resource_costs = {}
                total_cost = sum(cost_by_service.values())
                
                # Distribute costs evenly among resources (simplified)
                if resource_ids and total_cost > 0:
                    cost_per_resource = total_cost / len(resource_ids)
                    for resource_id in resource_ids:
                        resource_costs[resource_id] = cost_per_resource
                
                return resource_costs
            
            return cost_by_service
        
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch cost data: {str(e)}") from e


    async def get_cost_data_by_resource(
        self,
        time_period: dict[str, str] | None = None,
    ) -> tuple[dict[str, float], dict[str, float], str]:
        """
        Fetch cost data from AWS Cost Explorer with per-resource granularity where available.
        
        This method attempts to get actual per-resource costs for EC2 and RDS using
        the RESOURCE_ID dimension. For other services (S3, Lambda, ECS), it returns
        service-level totals that can be distributed among resources.
        
        Args:
            time_period: Time period for cost data (e.g., {"Start": "2025-01-01", "End": "2025-01-31"})
        
        Returns:
            Tuple of:
            - resource_costs: Dict mapping resource IDs to actual costs (EC2/RDS)
            - service_costs: Dict mapping service names to total costs
            - cost_source: "actual" if per-resource data available, "service_average" otherwise
        """
        # Default to last 30 days if no time period specified
        if not time_period:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            time_period = {
                "Start": start_date.strftime("%Y-%m-%d"),
                "End": end_date.strftime("%Y-%m-%d")
            }
        
        resource_costs: dict[str, float] = {}
        service_costs: dict[str, float] = {}
        cost_source = "estimated"
        
        try:
            # First, get service-level costs (always works)
            service_response = await self._call_with_backoff(
                "ce",
                self.ce.get_cost_and_usage,
                TimePeriod=time_period,
                Granularity="MONTHLY",
                Metrics=["UnblendedCost"],
                GroupBy=[
                    {"Type": "DIMENSION", "Key": "SERVICE"}
                ]
            )
            
            for result in service_response.get("ResultsByTime", []):
                for group in result.get("Groups", []):
                    service = group.get("Keys", [""])[0]
                    amount = float(group.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", 0))
                    service_costs[service] = service_costs.get(service, 0) + amount
            
            cost_source = "service_average"
            
            # Try to get per-resource costs for EC2 (uses RESOURCE_ID dimension)
            try:
                ec2_response = await self._call_with_backoff(
                    "ce",
                    self.ce.get_cost_and_usage,
                    TimePeriod=time_period,
                    Granularity="MONTHLY",
                    Metrics=["UnblendedCost"],
                    Filter={
                        "Dimensions": {
                            "Key": "SERVICE",
                            "Values": ["Amazon Elastic Compute Cloud - Compute"]
                        }
                    },
                    GroupBy=[
                        {"Type": "DIMENSION", "Key": "RESOURCE_ID"}
                    ]
                )
                
                for result in ec2_response.get("ResultsByTime", []):
                    for group in result.get("Groups", []):
                        resource_id = group.get("Keys", [""])[0]
                        if resource_id and resource_id.startswith("i-"):
                            amount = float(group.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", 0))
                            resource_costs[resource_id] = resource_costs.get(resource_id, 0) + amount
                
                if resource_costs:
                    cost_source = "actual"
                    
            except Exception as e:
                # Per-resource costs not available, continue with service-level
                import logging
                logging.getLogger(__name__).debug(f"Per-resource EC2 costs not available: {e}")
            
            # Try to get per-resource costs for RDS
            try:
                rds_response = await self._call_with_backoff(
                    "ce",
                    self.ce.get_cost_and_usage,
                    TimePeriod=time_period,
                    Granularity="MONTHLY",
                    Metrics=["UnblendedCost"],
                    Filter={
                        "Dimensions": {
                            "Key": "SERVICE",
                            "Values": ["Amazon Relational Database Service"]
                        }
                    },
                    GroupBy=[
                        {"Type": "DIMENSION", "Key": "RESOURCE_ID"}
                    ]
                )
                
                for result in rds_response.get("ResultsByTime", []):
                    for group in result.get("Groups", []):
                        resource_id = group.get("Keys", [""])[0]
                        if resource_id:
                            # RDS resource IDs in Cost Explorer are ARNs
                            # Extract the DB identifier
                            if ":db:" in resource_id:
                                db_id = resource_id.split(":db:")[-1]
                                amount = float(group.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", 0))
                                resource_costs[db_id] = resource_costs.get(db_id, 0) + amount
                
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug(f"Per-resource RDS costs not available: {e}")
            
            return resource_costs, service_costs, cost_source
        
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch cost data: {str(e)}") from e
    
    def get_service_name_for_resource_type(self, resource_type: str) -> str:
        """
        Map resource type to AWS Cost Explorer service name.
        
        Args:
            resource_type: Resource type (e.g., "ec2:instance")
        
        Returns:
            AWS service name as it appears in Cost Explorer
        """
        service_map = {
            "ec2:instance": "Amazon Elastic Compute Cloud - Compute",
            "rds:db": "Amazon Relational Database Service",
            "s3:bucket": "Amazon Simple Storage Service",
            "lambda:function": "AWS Lambda",
            "ecs:service": "Amazon Elastic Container Service",
            "opensearch:domain": "Amazon OpenSearch Service",
        }
        return service_map.get(resource_type, "")
