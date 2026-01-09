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
        # Resource Groups Tagging API - discovers all taggable resources
        self.resourcegroupstaggingapi = boto3.client('resourcegroupstaggingapi', config=config)
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
            # Compute
            "ec2:instance": "Amazon Elastic Compute Cloud - Compute",
            "lambda:function": "AWS Lambda",
            "ecs:service": "Amazon Elastic Container Service",
            # Database
            "rds:db": "Amazon Relational Database Service",
            "dynamodb:table": "Amazon DynamoDB",
            # Storage
            "s3:bucket": "Amazon Simple Storage Service",
            # Analytics & AI/ML
            "opensearch:domain": "Amazon OpenSearch Service",
            "glue:crawler": "AWS Glue",
            "glue:job": "AWS Glue",
            "glue:database": "AWS Glue",
            "athena:workgroup": "Amazon Athena",
            "bedrock:agent": "Amazon Bedrock",
            "bedrock:knowledge-base": "Amazon Bedrock",
            # Identity & Security
            "cognito-idp:userpool": "Amazon Cognito",
            "secretsmanager:secret": "AWS Secrets Manager",
            "kms:key": "AWS Key Management Service",
            # Monitoring & Logging
            "logs:log-group": "Amazon CloudWatch",
            "cloudwatch:alarm": "Amazon CloudWatch",
            # Networking
            "elasticloadbalancing:loadbalancer": "Elastic Load Balancing",
            "elasticloadbalancing:targetgroup": "Elastic Load Balancing",
            # Messaging
            "sns:topic": "Amazon Simple Notification Service",
            "sqs:queue": "Amazon Simple Queue Service",
            # Containers
            "ecr:repository": "Amazon EC2 Container Registry (ECR)",
        }
        return service_map.get(resource_type, "")

    async def get_all_tagged_resources(
        self,
        resource_type_filters: list[str] | None = None,
        tag_filters: list[dict[str, Any]] | None = None,
        include_compliance_details: bool = False
    ) -> list[dict[str, Any]]:
        """
        Fetch all taggable resources using AWS Resource Groups Tagging API.
        
        This method provides a unified way to discover resources across 50+ AWS services
        without needing individual service API calls. It handles pagination automatically.
        
        Args:
            resource_type_filters: Optional list of resource type filters 
                (e.g., ["ec2:instance", "rds:db", "s3", "lambda:function"])
                If None, returns all taggable resources.
            tag_filters: Optional list of tag filters in format:
                [{"Key": "Environment", "Values": ["production", "staging"]}]
            include_compliance_details: If True, includes ComplianceDetails in response
        
        Returns:
            List of resources with their tags, ARNs, and resource types
        
        Example response:
            [
                {
                    "resource_id": "i-1234567890abcdef0",
                    "resource_type": "ec2:instance",
                    "region": "us-east-1",
                    "tags": {"Environment": "production", "Owner": "team@example.com"},
                    "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"
                },
                ...
            ]
        """
        try:
            resources = []
            pagination_token = None
            
            # Build request parameters
            request_params: dict[str, Any] = {}
            
            if resource_type_filters:
                # Convert our resource type format to AWS format
                aws_resource_types = self._convert_resource_types_to_aws_format(resource_type_filters)
                if aws_resource_types:
                    request_params["ResourceTypeFilters"] = aws_resource_types
            
            if tag_filters:
                request_params["TagFilters"] = tag_filters
            
            if include_compliance_details:
                request_params["IncludeComplianceDetails"] = True
                request_params["ExcludeCompliantResources"] = False
            
            # Paginate through all results
            while True:
                if pagination_token:
                    request_params["PaginationToken"] = pagination_token
                
                response = await self._call_with_backoff(
                    "resourcegroupstaggingapi",
                    self.resourcegroupstaggingapi.get_resources,
                    **request_params
                )
                
                # Process resources from this page
                for resource_mapping in response.get("ResourceTagMappingList", []):
                    arn = resource_mapping.get("ResourceARN", "")
                    tags = self._extract_tags(resource_mapping.get("Tags", []))
                    
                    # Parse ARN to extract resource details
                    parsed = self._parse_arn(arn)
                    
                    resource_entry = {
                        "resource_id": parsed["resource_id"],
                        "resource_type": parsed["resource_type"],
                        "region": parsed["region"] or self.region,
                        "tags": tags,
                        "arn": arn,
                        "created_at": None  # Resource Groups Tagging API doesn't provide creation date
                    }
                    
                    # Include compliance details if requested
                    if include_compliance_details and "ComplianceDetails" in resource_mapping:
                        resource_entry["compliance_details"] = resource_mapping["ComplianceDetails"]
                    
                    resources.append(resource_entry)
                
                # Check for more pages
                pagination_token = response.get("PaginationToken")
                if not pagination_token:
                    break
            
            return resources
        
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch resources via Resource Groups Tagging API: {str(e)}") from e
    
    def _convert_resource_types_to_aws_format(self, resource_types: list[str]) -> list[str]:
        """
        Convert our internal resource type format to AWS Resource Groups Tagging API format.
        
        Our format: "ec2:instance", "rds:db", "s3:bucket"
        AWS format: "ec2:instance", "rds:db", "s3", "lambda:function"
        
        Args:
            resource_types: List of resource types in our format
        
        Returns:
            List of resource types in AWS format
        """
        # Mapping from our format to AWS Resource Groups Tagging API format
        type_mapping = {
            # Compute
            "ec2:instance": "ec2:instance",
            "lambda:function": "lambda:function",
            "ecs:service": "ecs:service",
            # Database
            "rds:db": "rds:db",
            "dynamodb:table": "dynamodb:table",
            # Storage
            "s3:bucket": "s3",  # S3 uses just "s3" in the API
            # Analytics & AI/ML
            "opensearch:domain": "es:domain",  # OpenSearch uses "es" prefix
            "glue:crawler": "glue:crawler",
            "glue:job": "glue:job",
            "glue:database": "glue:database",
            "athena:workgroup": "athena:workgroup",
            "bedrock:agent": "bedrock:agent",
            "bedrock:knowledge-base": "bedrock:knowledge-base",
            # Identity & Security
            "cognito-idp:userpool": "cognito-idp:userpool",
            "secretsmanager:secret": "secretsmanager:secret",
            "kms:key": "kms:key",
            # Monitoring & Logging
            "logs:log-group": "logs:log-group",
            "cloudwatch:alarm": "cloudwatch:alarm",
            # Networking
            "elasticloadbalancing:loadbalancer": "elasticloadbalancing:loadbalancer",
            "elasticloadbalancing:targetgroup": "elasticloadbalancing:targetgroup",
            # Messaging
            "sns:topic": "sns",
            "sqs:queue": "sqs",
            # Containers
            "ecr:repository": "ecr:repository",
            # Additional common resource types
            "elasticache:cluster": "elasticache:cluster",
            "efs:file-system": "elasticfilesystem:file-system",
            "apigateway:restapi": "apigateway",
            "cloudfront:distribution": "cloudfront:distribution",
            "route53:hostedzone": "route53:hostedzone",
            "kinesis:stream": "kinesis:stream",
            "glue:table": "glue:table",
            "redshift:cluster": "redshift:cluster",
            "emr:cluster": "elasticmapreduce:cluster",
            "stepfunctions:statemachine": "states:stateMachine",
            "codebuild:project": "codebuild:project",
            "codepipeline:pipeline": "codepipeline",
        }
        
        aws_types = []
        for rt in resource_types:
            if rt == "all":
                # Return empty list to get all resources
                return []
            
            aws_type = type_mapping.get(rt, rt)
            if aws_type not in aws_types:
                aws_types.append(aws_type)
        
        return aws_types
    
    def _parse_arn(self, arn: str) -> dict[str, str]:
        """
        Parse an AWS ARN to extract resource details.
        
        ARN format: arn:partition:service:region:account:resource
        
        Args:
            arn: AWS ARN string
        
        Returns:
            Dictionary with parsed ARN components:
            - service: AWS service name
            - region: AWS region (may be empty for global services)
            - account: AWS account ID (may be empty for some services)
            - resource_type: Our internal resource type format
            - resource_id: Resource identifier
        """
        parts = arn.split(":")
        
        if len(parts) < 6:
            return {
                "service": "",
                "region": "",
                "account": "",
                "resource_type": "unknown",
                "resource_id": arn
            }
        
        service = parts[2]
        region = parts[3]
        account = parts[4]
        resource_part = ":".join(parts[5:])  # Handle resources with colons
        
        # Parse resource type and ID based on service
        resource_type, resource_id = self._parse_resource_part(service, resource_part)
        
        return {
            "service": service,
            "region": region,
            "account": account,
            "resource_type": resource_type,
            "resource_id": resource_id
        }
    
    def _parse_resource_part(self, service: str, resource_part: str) -> tuple[str, str]:
        """
        Parse the resource part of an ARN to extract type and ID.
        
        Args:
            service: AWS service name from ARN
            resource_part: Resource portion of ARN (everything after account)
        
        Returns:
            Tuple of (resource_type, resource_id)
        """
        # Service-specific parsing rules
        if service == "ec2":
            if resource_part.startswith("instance/"):
                return "ec2:instance", resource_part.split("/")[1]
            elif resource_part.startswith("volume/"):
                return "ec2:volume", resource_part.split("/")[1]
            elif resource_part.startswith("vpc/"):
                return "ec2:vpc", resource_part.split("/")[1]
            elif resource_part.startswith("subnet/"):
                return "ec2:subnet", resource_part.split("/")[1]
            elif resource_part.startswith("security-group/"):
                return "ec2:security-group", resource_part.split("/")[1]
            elif resource_part.startswith("snapshot/"):
                return "ec2:snapshot", resource_part.split("/")[1]
            elif resource_part.startswith("image/"):
                return "ec2:image", resource_part.split("/")[1]
            else:
                return f"ec2:{resource_part.split('/')[0]}", resource_part.split("/")[-1]
        
        elif service == "rds":
            if resource_part.startswith("db:"):
                return "rds:db", resource_part.split(":")[1]
            elif resource_part.startswith("cluster:"):
                return "rds:cluster", resource_part.split(":")[1]
            elif resource_part.startswith("snapshot:"):
                return "rds:snapshot", resource_part.split(":")[1]
            else:
                return f"rds:{resource_part.split(':')[0]}", resource_part.split(":")[-1]
        
        elif service == "s3":
            # S3 ARNs: arn:aws:s3:::bucket-name or arn:aws:s3:::bucket-name/key
            return "s3:bucket", resource_part.split("/")[0]
        
        elif service == "lambda":
            if resource_part.startswith("function:"):
                func_name = resource_part.split(":")[1]
                # Remove version/alias if present
                if ":" in func_name:
                    func_name = func_name.split(":")[0]
                return "lambda:function", func_name
            else:
                return "lambda:function", resource_part
        
        elif service == "ecs":
            if "/service/" in resource_part:
                # Format: cluster/cluster-name/service/service-name
                parts = resource_part.split("/")
                return "ecs:service", parts[-1]
            elif resource_part.startswith("cluster/"):
                return "ecs:cluster", resource_part.split("/")[1]
            elif resource_part.startswith("task/"):
                return "ecs:task", resource_part.split("/")[-1]
            else:
                return f"ecs:{resource_part.split('/')[0]}", resource_part.split("/")[-1]
        
        elif service == "es" or service == "opensearch":
            if resource_part.startswith("domain/"):
                return "opensearch:domain", resource_part.split("/")[1]
            else:
                return "opensearch:domain", resource_part
        
        elif service == "dynamodb":
            if resource_part.startswith("table/"):
                return "dynamodb:table", resource_part.split("/")[1]
            else:
                return f"dynamodb:{resource_part.split('/')[0]}", resource_part.split("/")[-1]
        
        elif service == "sns":
            return "sns:topic", resource_part
        
        elif service == "sqs":
            return "sqs:queue", resource_part.split("/")[-1]
        
        elif service == "elasticache":
            if resource_part.startswith("cluster:"):
                return "elasticache:cluster", resource_part.split(":")[1]
            elif resource_part.startswith("replicationgroup:"):
                return "elasticache:replicationgroup", resource_part.split(":")[1]
            else:
                return f"elasticache:{resource_part.split(':')[0]}", resource_part.split(":")[-1]
        
        elif service == "secretsmanager":
            if resource_part.startswith("secret:"):
                return "secretsmanager:secret", resource_part.split(":")[1]
            else:
                return "secretsmanager:secret", resource_part
        
        elif service == "kms":
            if resource_part.startswith("key/"):
                return "kms:key", resource_part.split("/")[1]
            elif resource_part.startswith("alias/"):
                return "kms:alias", resource_part.split("/")[1]
            else:
                return f"kms:{resource_part.split('/')[0]}", resource_part.split("/")[-1]
        
        elif service == "ecr":
            if resource_part.startswith("repository/"):
                return "ecr:repository", resource_part.split("/")[1]
            else:
                return "ecr:repository", resource_part
        
        elif service == "elasticfilesystem":
            if resource_part.startswith("file-system/"):
                return "efs:file-system", resource_part.split("/")[1]
            else:
                return "efs:file-system", resource_part
        
        elif service == "elasticloadbalancing":
            if resource_part.startswith("loadbalancer/"):
                return "elasticloadbalancing:loadbalancer", resource_part.split("/")[-1]
            elif resource_part.startswith("targetgroup/"):
                return "elasticloadbalancing:targetgroup", resource_part.split("/")[-1]
            else:
                return f"elasticloadbalancing:{resource_part.split('/')[0]}", resource_part.split("/")[-1]
        
        elif service == "apigateway":
            if resource_part.startswith("/restapis/"):
                return "apigateway:restapi", resource_part.split("/")[2]
            else:
                return "apigateway:restapi", resource_part
        
        elif service == "cloudfront":
            if resource_part.startswith("distribution/"):
                return "cloudfront:distribution", resource_part.split("/")[1]
            else:
                return "cloudfront:distribution", resource_part
        
        elif service == "route53":
            if resource_part.startswith("hostedzone/"):
                return "route53:hostedzone", resource_part.split("/")[1]
            else:
                return "route53:hostedzone", resource_part
        
        elif service == "kinesis":
            if resource_part.startswith("stream/"):
                return "kinesis:stream", resource_part.split("/")[1]
            else:
                return "kinesis:stream", resource_part
        
        elif service == "glue":
            if resource_part.startswith("database/"):
                return "glue:database", resource_part.split("/")[1]
            elif resource_part.startswith("table/"):
                return "glue:table", resource_part.split("/")[-1]
            else:
                return f"glue:{resource_part.split('/')[0]}", resource_part.split("/")[-1]
        
        elif service == "athena":
            if resource_part.startswith("workgroup/"):
                return "athena:workgroup", resource_part.split("/")[1]
            else:
                return "athena:workgroup", resource_part
        
        elif service == "redshift":
            if resource_part.startswith("cluster:"):
                return "redshift:cluster", resource_part.split(":")[1]
            else:
                return "redshift:cluster", resource_part
        
        elif service == "elasticmapreduce":
            if resource_part.startswith("cluster/"):
                return "emr:cluster", resource_part.split("/")[1]
            else:
                return "emr:cluster", resource_part
        
        elif service == "states":
            if resource_part.startswith("stateMachine:"):
                return "stepfunctions:statemachine", resource_part.split(":")[1]
            else:
                return "stepfunctions:statemachine", resource_part
        
        elif service == "codebuild":
            if resource_part.startswith("project/"):
                return "codebuild:project", resource_part.split("/")[1]
            else:
                return "codebuild:project", resource_part
        
        elif service == "codepipeline":
            return "codepipeline:pipeline", resource_part
        
        elif service == "logs":
            if resource_part.startswith("log-group:"):
                return "logs:log-group", resource_part.split(":")[1]
            else:
                return "logs:log-group", resource_part
        
        elif service == "cloudwatch":
            if resource_part.startswith("alarm:"):
                return "cloudwatch:alarm", resource_part.split(":")[1]
            else:
                return f"cloudwatch:{resource_part.split(':')[0]}", resource_part.split(":")[-1]
        
        elif service == "bedrock":
            # Bedrock ARNs: arn:aws:bedrock:region:account:agent/agent-id
            # or arn:aws:bedrock:region:account:knowledge-base/kb-id
            if resource_part.startswith("agent/"):
                return "bedrock:agent", resource_part.split("/")[1]
            elif resource_part.startswith("knowledge-base/"):
                return "bedrock:knowledge-base", resource_part.split("/")[1]
            else:
                return f"bedrock:{resource_part.split('/')[0]}", resource_part.split("/")[-1]
        
        elif service == "cognito-idp":
            # Cognito User Pool ARNs: arn:aws:cognito-idp:region:account:userpool/pool-id
            if resource_part.startswith("userpool/"):
                return "cognito-idp:userpool", resource_part.split("/")[1]
            else:
                return f"cognito-idp:{resource_part.split('/')[0]}", resource_part.split("/")[-1]
        
        elif service == "cognito-identity":
            # Cognito Identity Pool ARNs: arn:aws:cognito-identity:region:account:identitypool/pool-id
            if resource_part.startswith("identitypool/"):
                return "cognito-identity:identitypool", resource_part.split("/")[1]
            else:
                return f"cognito-identity:{resource_part.split('/')[0]}", resource_part.split("/")[-1]
        
        # Default: use service name and full resource part
        return f"{service}:resource", resource_part

    async def get_total_account_spend(
        self,
        time_period: dict[str, str] | None = None,
    ) -> tuple[float, dict[str, float]]:
        """
        Get total account spend from AWS Cost Explorer across ALL services.
        
        This method retrieves the total cloud spend for the account without
        filtering by specific services, capturing costs from ALL AWS services
        including Bedrock, CloudWatch, Data Transfer, Support, etc.
        
        Args:
            time_period: Time period for cost data (e.g., {"Start": "2025-01-01", "End": "2025-01-31"})
        
        Returns:
            Tuple of:
            - total_spend: Total account spend for the period
            - service_breakdown: Dict mapping service names to their costs
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
            # Get total cost grouped by service
            response = await self._call_with_backoff(
                "ce",
                self.ce.get_cost_and_usage,
                TimePeriod=time_period,
                Granularity="MONTHLY",
                Metrics=["UnblendedCost"],
                GroupBy=[
                    {"Type": "DIMENSION", "Key": "SERVICE"}
                ]
            )
            
            total_spend = 0.0
            service_breakdown: dict[str, float] = {}
            
            for result in response.get("ResultsByTime", []):
                for group in result.get("Groups", []):
                    service = group.get("Keys", [""])[0]
                    amount = float(group.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", 0))
                    service_breakdown[service] = service_breakdown.get(service, 0) + amount
                    total_spend += amount
            
            return total_spend, service_breakdown
        
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch total account spend: {str(e)}") from e
