# Copyright (c) 2025-2026 OptimNow. All Rights Reserved.
# Licensed under the Apache License, Version 2.0.
# See LICENSE file in the project root for full license information.

"""AWS client wrapper with rate limiting and backoff."""

import asyncio
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


class AWSAPIError(Exception):
    """Raised when AWS API calls fail."""

    pass


class AWSClient:
    """
    Wrapper around boto3 clients with rate limiting and exponential backoff.

    Uses IAM instance profile for authentication - no hardcoded credentials.
    Implements exponential backoff for rate limit errors.
    """

    def __init__(self, region: str = "us-east-1", boto_config: Config | None = None):
        """
        Initialize AWS clients.

        Args:
            region: AWS region to use for regional services
            boto_config: Optional botocore Config to use for all clients.
                        If not provided, a default config with adaptive retries is used.
                        This ensures consistent retry/timeout behavior when creating
                        clients for multiple regions via RegionalClientFactory.
        """
        # Use provided config or create default with retries
        if boto_config is not None:
            # Merge region into provided config
            config = boto_config.merge(Config(region_name=region))
        else:
            config = Config(region_name=region, retries={"max_attempts": 3, "mode": "adaptive"})

        # Initialize clients - uses IAM instance profile automatically
        self.region = region
        self._boto_config = config  # Store for introspection
        self.ec2 = boto3.client("ec2", config=config)
        self.rds = boto3.client("rds", config=config)
        self.s3 = boto3.client("s3", config=config)
        self.lambda_client = boto3.client("lambda", config=config)
        self.ecs = boto3.client("ecs", config=config)
        self.sts = boto3.client("sts", config=config)
        self.opensearch = boto3.client("opensearch", config=config)
        # Resource Groups Tagging API - discovers all taggable resources
        self.resourcegroupstaggingapi = boto3.client("resourcegroupstaggingapi", config=config)
        # Cost Explorer is always us-east-1
        self.ce = boto3.client("ce", region_name="us-east-1")

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

    async def _call_with_backoff(self, service_name: str, func: Callable, *args, **kwargs) -> Any:
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
                response = await loop.run_in_executor(None, lambda: func(*args, **kwargs))
                return response

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")

                # Retry on throttling errors
                if error_code in ["Throttling", "ThrottlingException", "RequestLimitExceeded"]:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2**attempt)
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
            response = await self._call_with_backoff("sts", self.sts.get_caller_identity)
            self._account_id = response.get("Account", "")
            if not self._account_id:
                raise AWSAPIError("Account ID not found in STS response")
            return self._account_id

        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to get account ID: {str(e)}") from e

    def _get_client(self, service_name: str) -> Any:
        """
        Lazily initialize and cache a boto3 client for a given service.

        Avoids creating 30+ boto3 clients at startup when only a few
        resource types may be scanned.

        Args:
            service_name: boto3 service name (e.g., "dynamodb", "eks")

        Returns:
            boto3 client for the service
        """
        cache_attr = f"_lazy_{service_name.replace('-', '_')}"
        if not hasattr(self, cache_attr):
            setattr(self, cache_attr, boto3.client(service_name, config=self._boto_config))
        return getattr(self, cache_attr)

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

    async def get_tags_for_arns(self, arns: list[str]) -> dict[str, dict[str, str]]:
        """
        Efficiently fetch tags for specific resources by their ARNs.

        Uses the Resource Groups Tagging API with ResourceARNList parameter
        to fetch tags for multiple ARNs in a single API call, avoiding the
        need to list all resources of a type.

        Args:
            arns: List of AWS ARNs to fetch tags for

        Returns:
            Dictionary mapping ARN to tag dictionary.
            Example: {"arn:aws:ec2:...": {"Environment": "prod", "Owner": "team@example.com"}}

        Note:
            - Maximum 100 ARNs per request (AWS API limit)
            - ARNs not found will not appear in the result
        """
        if not arns:
            return {}

        try:
            result: dict[str, dict[str, str]] = {}

            # Process in batches of 100 (AWS API limit)
            batch_size = 100
            for i in range(0, len(arns), batch_size):
                batch = arns[i : i + batch_size]

                response = await self._call_with_backoff(
                    "resourcegroupstaggingapi",
                    self.resourcegroupstaggingapi.get_resources,
                    ResourceARNList=batch,
                )

                for resource_mapping in response.get("ResourceTagMappingList", []):
                    arn = resource_mapping.get("ResourceARN", "")
                    tags = self._extract_tags(resource_mapping.get("Tags", []))
                    result[arn] = tags

            return result

        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch tags for ARNs: {str(e)}") from e

    async def get_ec2_instances(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
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

        # Exclude terminated and shutting-down instances at the API level.
        # These are no longer actionable and inflate compliance violation counts.
        ec2_filters.append({
            "Name": "instance-state-name",
            "Values": ["pending", "running", "stopping", "stopped"],
        })

        if "region" in filters and filters["region"] != self.region:
            # Would need to create a new client for different region
            # For now, only support current region
            return []

        try:
            # Get account ID for ARN construction
            account_id = await self._get_account_id()

            response = await self._call_with_backoff(
                "ec2", self.ec2.describe_instances, Filters=ec2_filters
            )

            resources = []
            for reservation in response.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    instance_id = instance.get("InstanceId")
                    tags = self._extract_tags(instance.get("Tags", []))
                    launch_time = instance.get("LaunchTime")

                    # Extract instance metadata for state-aware cost attribution
                    state = instance.get("State", {}).get("Name", "unknown")
                    instance_type = instance.get("InstanceType", "unknown")

                    resources.append(
                        {
                            "resource_id": instance_id,
                            "resource_type": "ec2:instance",
                            "region": self.region,
                            "tags": tags,
                            "created_at": launch_time,
                            "arn": f"arn:aws:ec2:{self.region}:{account_id}:instance/{instance_id}",
                            "instance_state": state,
                            "instance_type": instance_type,
                        }
                    )

            return resources

        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch EC2 instances: {str(e)}") from e

    async def get_elastic_ips(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        Fetch Elastic IPs with their tags.

        Elastic IPs cost ~$3.65/month if not attached to a running instance.
        This is a significant cost that's often overlooked.

        Args:
            filters: Optional filters for the query

        Returns:
            List of Elastic IP resources with tags
        """
        filters = filters or {}

        try:
            # Get account ID for ARN construction
            account_id = await self._get_account_id()

            response = await self._call_with_backoff("ec2", self.ec2.describe_addresses)

            resources = []
            for address in response.get("Addresses", []):
                allocation_id = address.get("AllocationId")
                public_ip = address.get("PublicIp")
                tags = self._extract_tags(address.get("Tags", []))

                # Check if attached to an instance
                instance_id = address.get("InstanceId")
                association_id = address.get("AssociationId")
                is_attached = bool(instance_id or association_id)

                # Use allocation ID as resource ID (more stable than public IP)
                resource_id = allocation_id or public_ip

                resources.append(
                    {
                        "resource_id": resource_id,
                        "resource_type": "ec2:elastic-ip",
                        "region": self.region,
                        "tags": tags,
                        "created_at": None,  # EC2 doesn't provide creation date for EIPs
                        "arn": f"arn:aws:ec2:{self.region}:{account_id}:elastic-ip/{allocation_id}",
                        "public_ip": public_ip,
                        "is_attached": is_attached,
                        "attached_instance": instance_id,
                    }
                )

            return resources

        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch Elastic IPs: {str(e)}") from e

    async def get_ebs_snapshots(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """
        Fetch EBS snapshots with their tags.

        Snapshots cost per GB stored (~$0.05/GB/month).
        Old/orphaned snapshots can accumulate significant costs.

        Args:
            filters: Optional filters for the query

        Returns:
            List of EBS snapshot resources with tags
        """
        filters = filters or {}

        try:
            # Get account ID for ARN construction
            account_id = await self._get_account_id()

            # Only get snapshots owned by this account (not public AMI snapshots)
            response = await self._call_with_backoff(
                "ec2", self.ec2.describe_snapshots, OwnerIds=["self"]
            )

            resources = []
            for snapshot in response.get("Snapshots", []):
                snapshot_id = snapshot.get("SnapshotId")
                tags = self._extract_tags(snapshot.get("Tags", []))
                start_time = snapshot.get("StartTime")
                volume_size = snapshot.get("VolumeSize", 0)

                resources.append(
                    {
                        "resource_id": snapshot_id,
                        "resource_type": "ec2:snapshot",
                        "region": self.region,
                        "tags": tags,
                        "created_at": start_time,
                        "arn": f"arn:aws:ec2:{self.region}:{account_id}:snapshot/{snapshot_id}",
                        "volume_size_gb": volume_size,
                        "state": snapshot.get("State", "unknown"),
                    }
                )

            return resources

        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch EBS snapshots: {str(e)}") from e

    async def get_ebs_volumes(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        Fetch EBS volumes with their tags.

        EBS volumes cost per GB provisioned.
        Unattached volumes still incur costs.

        Args:
            filters: Optional filters for the query

        Returns:
            List of EBS volume resources with tags
        """
        filters = filters or {}

        try:
            # Get account ID for ARN construction
            account_id = await self._get_account_id()

            response = await self._call_with_backoff("ec2", self.ec2.describe_volumes)

            resources = []
            for volume in response.get("Volumes", []):
                volume_id = volume.get("VolumeId")
                tags = self._extract_tags(volume.get("Tags", []))
                create_time = volume.get("CreateTime")
                size = volume.get("Size", 0)
                state = volume.get("State", "unknown")

                # Check if attached
                attachments = volume.get("Attachments", [])
                is_attached = len(attachments) > 0
                attached_instance = attachments[0].get("InstanceId") if attachments else None

                resources.append(
                    {
                        "resource_id": volume_id,
                        "resource_type": "ec2:volume",
                        "region": self.region,
                        "tags": tags,
                        "created_at": create_time,
                        "arn": f"arn:aws:ec2:{self.region}:{account_id}:volume/{volume_id}",
                        "size_gb": size,
                        "state": state,
                        "is_attached": is_attached,
                        "attached_instance": attached_instance,
                        "volume_type": volume.get("VolumeType", "unknown"),
                    }
                )

            return resources

        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch EBS volumes: {str(e)}") from e

    async def get_rds_instances(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """
        Fetch RDS instances with their tags.

        Args:
            filters: Optional filters for the query

        Returns:
            List of RDS instance resources with tags
        """
        filters = filters or {}

        try:
            response = await self._call_with_backoff("rds", self.rds.describe_db_instances)

            resources = []
            for db_instance in response.get("DBInstances", []):
                db_arn = db_instance.get("DBInstanceArn")
                db_id = db_instance.get("DBInstanceIdentifier")
                created_at = db_instance.get("InstanceCreateTime")

                # Fetch tags for this RDS instance
                tags_response = await self._call_with_backoff(
                    "rds", self.rds.list_tags_for_resource, ResourceName=db_arn
                )

                tags = self._extract_tags(tags_response.get("TagList", []))

                resources.append(
                    {
                        "resource_id": db_id,
                        "resource_type": "rds:db",
                        "region": self.region,
                        "tags": tags,
                        "created_at": created_at,
                        "arn": db_arn,
                    }
                )

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
            response = await self._call_with_backoff("s3", self.s3.list_buckets)

            resources = []
            for bucket in response.get("Buckets", []):
                bucket_name = bucket.get("Name")
                created_at = bucket.get("CreationDate")

                # Fetch tags for this bucket
                try:
                    tags_response = await self._call_with_backoff(
                        "s3", self.s3.get_bucket_tagging, Bucket=bucket_name
                    )
                    tags = self._extract_tags(tags_response.get("TagSet", []))
                except AWSAPIError:
                    # Bucket might not have tags
                    tags = {}

                resources.append(
                    {
                        "resource_id": bucket_name,
                        "resource_type": "s3:bucket",
                        "region": "global",  # S3 buckets are global
                        "tags": tags,
                        "created_at": created_at,
                        "arn": f"arn:aws:s3:::{bucket_name}",
                    }
                )

            return resources

        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch S3 buckets: {str(e)}") from e

    async def get_lambda_functions(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """
        Fetch Lambda functions with their tags.

        Args:
            filters: Optional filters for the query

        Returns:
            List of Lambda function resources with tags
        """
        filters = filters or {}

        try:
            response = await self._call_with_backoff("lambda", self.lambda_client.list_functions)

            resources = []
            for function in response.get("Functions", []):
                function_name = function.get("FunctionName")
                function_arn = function.get("FunctionArn")
                last_modified = function.get("LastModified")

                # Fetch tags for this function
                try:
                    tags_response = await self._call_with_backoff(
                        "lambda", self.lambda_client.list_tags, Resource=function_arn
                    )
                    tags = tags_response.get("Tags", {})
                except AWSAPIError:
                    tags = {}

                resources.append(
                    {
                        "resource_id": function_name,
                        "resource_type": "lambda:function",
                        "region": self.region,
                        "tags": tags,
                        "created_at": last_modified,
                        "arn": function_arn,
                    }
                )

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
            clusters_response = await self._call_with_backoff("ecs", self.ecs.list_clusters)

            resources = []
            for cluster_arn in clusters_response.get("clusterArns", []):
                # List services in this cluster
                services_response = await self._call_with_backoff(
                    "ecs", self.ecs.list_services, cluster=cluster_arn
                )

                if not services_response.get("serviceArns"):
                    continue

                # Describe services to get details
                describe_response = await self._call_with_backoff(
                    "ecs",
                    self.ecs.describe_services,
                    cluster=cluster_arn,
                    services=services_response.get("serviceArns", []),
                    include=["TAGS"],
                )

                for service in describe_response.get("services", []):
                    service_name = service.get("serviceName")
                    service_arn = service.get("serviceArn")
                    created_at = service.get("createdAt")

                    tags = self._extract_tags(service.get("tags", []))

                    resources.append(
                        {
                            "resource_id": service_name,
                            "resource_type": "ecs:service",
                            "region": self.region,
                            "tags": tags,
                            "created_at": created_at,
                            "arn": service_arn,
                        }
                    )

            return resources

        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch ECS services: {str(e)}") from e

    async def get_opensearch_domains(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
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
                "opensearch", self.opensearch.list_domain_names
            )

            resources = []
            for domain_info in list_response.get("DomainNames", []):
                domain_name = domain_info.get("DomainName")

                if not domain_name:
                    continue

                # Get domain details
                try:
                    describe_response = await self._call_with_backoff(
                        "opensearch", self.opensearch.describe_domain, DomainName=domain_name
                    )

                    domain_status = describe_response.get("DomainStatus", {})
                    domain_arn = domain_status.get(
                        "ARN", f"arn:aws:es:{self.region}:{account_id}:domain/{domain_name}"
                    )
                    created_at = domain_status.get("Created")

                    # Fetch tags for this domain
                    try:
                        tags_response = await self._call_with_backoff(
                            "opensearch", self.opensearch.list_tags, ARN=domain_arn
                        )
                        tags = self._extract_tags(tags_response.get("TagList", []))
                    except AWSAPIError:
                        tags = {}

                    resources.append(
                        {
                            "resource_id": domain_name,
                            "resource_type": "opensearch:domain",
                            "region": self.region,
                            "tags": tags,
                            "created_at": created_at,
                            "arn": domain_arn,
                        }
                    )

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

    # ================================================================
    # EC2: NAT Gateways
    # ================================================================

    async def get_nat_gateways(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Fetch NAT Gateways with their tags."""
        filters = filters or {}
        try:
            account_id = await self._get_account_id()
            response = await self._call_with_backoff(
                "ec2", self.ec2.describe_nat_gateways,
                Filter=[{"Name": "state", "Values": ["available", "pending"]}],
            )
            resources = []
            for nat in response.get("NatGateways", []):
                nat_id = nat.get("NatGatewayId")
                tags = self._extract_tags(nat.get("Tags", []))
                resources.append({
                    "resource_id": nat_id,
                    "resource_type": "ec2:natgateway",
                    "region": self.region,
                    "tags": tags,
                    "created_at": nat.get("CreateTime"),
                    "arn": f"arn:aws:ec2:{self.region}:{account_id}:natgateway/{nat_id}",
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch NAT Gateways: {str(e)}") from e

    # ================================================================
    # ECS: Clusters, Task Definitions
    # ================================================================

    async def get_ecs_clusters(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Fetch ECS clusters with their tags."""
        filters = filters or {}
        try:
            list_response = await self._call_with_backoff("ecs", self.ecs.list_clusters)
            cluster_arns = list_response.get("clusterArns", [])
            if not cluster_arns:
                return []
            describe_response = await self._call_with_backoff(
                "ecs", self.ecs.describe_clusters,
                clusters=cluster_arns, include=["TAGS"],
            )
            resources = []
            for cluster in describe_response.get("clusters", []):
                tags = self._extract_tags(cluster.get("tags", []))
                resources.append({
                    "resource_id": cluster.get("clusterName"),
                    "resource_type": "ecs:cluster",
                    "region": self.region,
                    "tags": tags,
                    "created_at": None,
                    "arn": cluster.get("clusterArn"),
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch ECS clusters: {str(e)}") from e

    async def get_ecs_task_definitions(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch active ECS task definition families with their tags."""
        filters = filters or {}
        try:
            list_response = await self._call_with_backoff(
                "ecs", self.ecs.list_task_definition_families, status="ACTIVE",
            )
            resources = []
            for family in list_response.get("families", []):
                try:
                    desc = await self._call_with_backoff(
                        "ecs", self.ecs.describe_task_definition,
                        taskDefinition=family, include=["TAGS"],
                    )
                    td = desc.get("taskDefinition", {})
                    tags = self._extract_tags(desc.get("tags", []))
                    resources.append({
                        "resource_id": family,
                        "resource_type": "ecs:task-definition",
                        "region": self.region,
                        "tags": tags,
                        "created_at": td.get("registeredAt"),
                        "arn": td.get("taskDefinitionArn", ""),
                    })
                except AWSAPIError:
                    continue
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch ECS task definitions: {str(e)}") from e

    # ================================================================
    # EKS: Clusters, Node Groups
    # ================================================================

    async def get_eks_clusters(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Fetch EKS clusters with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("eks")
            list_response = await self._call_with_backoff("eks", client.list_clusters)
            resources = []
            for name in list_response.get("clusters", []):
                try:
                    desc = await self._call_with_backoff("eks", client.describe_cluster, name=name)
                    cluster = desc.get("cluster", {})
                    resources.append({
                        "resource_id": name,
                        "resource_type": "eks:cluster",
                        "region": self.region,
                        "tags": cluster.get("tags", {}),
                        "created_at": cluster.get("createdAt"),
                        "arn": cluster.get("arn", ""),
                    })
                except AWSAPIError:
                    continue
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch EKS clusters: {str(e)}") from e

    async def get_eks_nodegroups(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Fetch EKS node groups with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("eks")
            list_clusters = await self._call_with_backoff("eks", client.list_clusters)
            resources = []
            for cluster_name in list_clusters.get("clusters", []):
                try:
                    ng_response = await self._call_with_backoff(
                        "eks", client.list_nodegroups, clusterName=cluster_name,
                    )
                    for ng_name in ng_response.get("nodegroups", []):
                        try:
                            desc = await self._call_with_backoff(
                                "eks", client.describe_nodegroup,
                                clusterName=cluster_name, nodegroupName=ng_name,
                            )
                            ng = desc.get("nodegroup", {})
                            resources.append({
                                "resource_id": ng_name,
                                "resource_type": "eks:nodegroup",
                                "region": self.region,
                                "tags": ng.get("tags", {}),
                                "created_at": ng.get("createdAt"),
                                "arn": ng.get("nodegroupArn", ""),
                            })
                        except AWSAPIError:
                            continue
                except AWSAPIError:
                    continue
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch EKS node groups: {str(e)}") from e

    # ================================================================
    # Storage: EFS, FSx
    # ================================================================

    async def get_efs_file_systems(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch EFS file systems with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("efs")
            response = await self._call_with_backoff("efs", client.describe_file_systems)
            resources = []
            for fs in response.get("FileSystems", []):
                tags = self._extract_tags(fs.get("Tags", []))
                resources.append({
                    "resource_id": fs.get("FileSystemId"),
                    "resource_type": "elasticfilesystem:file-system",
                    "region": self.region,
                    "tags": tags,
                    "created_at": fs.get("CreationTime"),
                    "arn": fs.get("FileSystemArn", ""),
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch EFS file systems: {str(e)}") from e

    async def get_fsx_file_systems(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch FSx file systems with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("fsx")
            response = await self._call_with_backoff("fsx", client.describe_file_systems)
            resources = []
            for fs in response.get("FileSystems", []):
                tags = self._extract_tags(fs.get("Tags", []))
                resources.append({
                    "resource_id": fs.get("FileSystemId"),
                    "resource_type": "fsx:file-system",
                    "region": self.region,
                    "tags": tags,
                    "created_at": fs.get("CreationTime"),
                    "arn": fs.get("ResourceARN", ""),
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch FSx file systems: {str(e)}") from e

    # ================================================================
    # Database: RDS Clusters, DynamoDB, ElastiCache, Redshift
    # ================================================================

    async def get_rds_clusters(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Fetch RDS Aurora clusters with their tags."""
        filters = filters or {}
        try:
            response = await self._call_with_backoff("rds", self.rds.describe_db_clusters)
            resources = []
            for cluster in response.get("DBClusters", []):
                cluster_arn = cluster.get("DBClusterArn")
                tags_response = await self._call_with_backoff(
                    "rds", self.rds.list_tags_for_resource, ResourceName=cluster_arn,
                )
                tags = self._extract_tags(tags_response.get("TagList", []))
                resources.append({
                    "resource_id": cluster.get("DBClusterIdentifier"),
                    "resource_type": "rds:cluster",
                    "region": self.region,
                    "tags": tags,
                    "created_at": cluster.get("ClusterCreateTime"),
                    "arn": cluster_arn,
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch RDS clusters: {str(e)}") from e

    async def get_dynamodb_tables(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch DynamoDB tables with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("dynamodb")
            list_response = await self._call_with_backoff("dynamodb", client.list_tables)
            resources = []
            for table_name in list_response.get("TableNames", []):
                try:
                    desc = await self._call_with_backoff(
                        "dynamodb", client.describe_table, TableName=table_name,
                    )
                    table = desc.get("Table", {})
                    table_arn = table.get("TableArn", "")
                    try:
                        tags_resp = await self._call_with_backoff(
                            "dynamodb", client.list_tags_of_resource, ResourceArn=table_arn,
                        )
                        tags = self._extract_tags(tags_resp.get("Tags", []))
                    except AWSAPIError:
                        tags = {}
                    resources.append({
                        "resource_id": table_name,
                        "resource_type": "dynamodb:table",
                        "region": self.region,
                        "tags": tags,
                        "created_at": table.get("CreationDateTime"),
                        "arn": table_arn,
                    })
                except AWSAPIError:
                    continue
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch DynamoDB tables: {str(e)}") from e

    async def get_elasticache_clusters(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch ElastiCache clusters with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("elasticache")
            response = await self._call_with_backoff(
                "elasticache", client.describe_cache_clusters, ShowCacheNodeInfo=False,
            )
            resources = []
            for cluster in response.get("CacheClusters", []):
                arn = cluster.get("ARN", "")
                try:
                    tags_resp = await self._call_with_backoff(
                        "elasticache", client.list_tags_for_resource, ResourceName=arn,
                    )
                    tags = self._extract_tags(tags_resp.get("TagList", []))
                except AWSAPIError:
                    tags = {}
                resources.append({
                    "resource_id": cluster.get("CacheClusterId"),
                    "resource_type": "elasticache:cluster",
                    "region": self.region,
                    "tags": tags,
                    "created_at": cluster.get("CacheClusterCreateTime"),
                    "arn": arn,
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch ElastiCache clusters: {str(e)}") from e

    async def get_elasticache_replication_groups(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch ElastiCache replication groups with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("elasticache")
            response = await self._call_with_backoff(
                "elasticache", client.describe_replication_groups,
            )
            resources = []
            for rg in response.get("ReplicationGroups", []):
                arn = rg.get("ARN", "")
                try:
                    tags_resp = await self._call_with_backoff(
                        "elasticache", client.list_tags_for_resource, ResourceName=arn,
                    )
                    tags = self._extract_tags(tags_resp.get("TagList", []))
                except AWSAPIError:
                    tags = {}
                resources.append({
                    "resource_id": rg.get("ReplicationGroupId"),
                    "resource_type": "elasticache:replicationgroup",
                    "region": self.region,
                    "tags": tags,
                    "created_at": None,
                    "arn": arn,
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch ElastiCache replication groups: {str(e)}") from e

    async def get_redshift_clusters(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch Redshift clusters with their tags (inline)."""
        filters = filters or {}
        try:
            client = self._get_client("redshift")
            account_id = await self._get_account_id()
            response = await self._call_with_backoff("redshift", client.describe_clusters)
            resources = []
            for cluster in response.get("Clusters", []):
                cluster_id = cluster.get("ClusterIdentifier")
                tags = self._extract_tags(cluster.get("Tags", []))
                resources.append({
                    "resource_id": cluster_id,
                    "resource_type": "redshift:cluster",
                    "region": self.region,
                    "tags": tags,
                    "created_at": cluster.get("ClusterCreateTime"),
                    "arn": f"arn:aws:redshift:{self.region}:{account_id}:cluster:{cluster_id}",
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch Redshift clusters: {str(e)}") from e

    # ================================================================
    # AI/ML: SageMaker, Bedrock
    # ================================================================

    async def get_sagemaker_endpoints(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch SageMaker endpoints with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("sagemaker")
            response = await self._call_with_backoff("sagemaker", client.list_endpoints)
            resources = []
            for ep in response.get("Endpoints", []):
                ep_arn = ep.get("EndpointArn", "")
                try:
                    tags_resp = await self._call_with_backoff(
                        "sagemaker", client.list_tags, ResourceArn=ep_arn,
                    )
                    tags = self._extract_tags(tags_resp.get("Tags", []))
                except AWSAPIError:
                    tags = {}
                resources.append({
                    "resource_id": ep.get("EndpointName"),
                    "resource_type": "sagemaker:endpoint",
                    "region": self.region,
                    "tags": tags,
                    "created_at": ep.get("CreationTime"),
                    "arn": ep_arn,
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch SageMaker endpoints: {str(e)}") from e

    async def get_sagemaker_notebooks(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch SageMaker notebook instances with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("sagemaker")
            response = await self._call_with_backoff("sagemaker", client.list_notebook_instances)
            resources = []
            for nb in response.get("NotebookInstances", []):
                nb_arn = nb.get("NotebookInstanceArn", "")
                try:
                    tags_resp = await self._call_with_backoff(
                        "sagemaker", client.list_tags, ResourceArn=nb_arn,
                    )
                    tags = self._extract_tags(tags_resp.get("Tags", []))
                except AWSAPIError:
                    tags = {}
                resources.append({
                    "resource_id": nb.get("NotebookInstanceName"),
                    "resource_type": "sagemaker:notebook-instance",
                    "region": self.region,
                    "tags": tags,
                    "created_at": nb.get("CreationTime"),
                    "arn": nb_arn,
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch SageMaker notebooks: {str(e)}") from e

    async def get_bedrock_agents(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch Bedrock agents with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("bedrock-agent")
            account_id = await self._get_account_id()
            response = await self._call_with_backoff("bedrock-agent", client.list_agents)
            resources = []
            for agent_summary in response.get("agentSummaries", []):
                agent_id = agent_summary.get("agentId")
                arn = f"arn:aws:bedrock:{self.region}:{account_id}:agent/{agent_id}"
                try:
                    tags_resp = await self._call_with_backoff(
                        "bedrock-agent", client.list_tags_for_resource, resourceArn=arn,
                    )
                    tags = tags_resp.get("tags", {})
                except AWSAPIError:
                    tags = {}
                resources.append({
                    "resource_id": agent_id,
                    "resource_type": "bedrock:agent",
                    "region": self.region,
                    "tags": tags,
                    "created_at": agent_summary.get("updatedAt"),
                    "arn": arn,
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch Bedrock agents: {str(e)}") from e

    async def get_bedrock_knowledge_bases(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch Bedrock knowledge bases with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("bedrock-agent")
            account_id = await self._get_account_id()
            response = await self._call_with_backoff(
                "bedrock-agent", client.list_knowledge_bases,
            )
            resources = []
            for kb in response.get("knowledgeBaseSummaries", []):
                kb_id = kb.get("knowledgeBaseId")
                arn = f"arn:aws:bedrock:{self.region}:{account_id}:knowledge-base/{kb_id}"
                try:
                    tags_resp = await self._call_with_backoff(
                        "bedrock-agent", client.list_tags_for_resource, resourceArn=arn,
                    )
                    tags = tags_resp.get("tags", {})
                except AWSAPIError:
                    tags = {}
                resources.append({
                    "resource_id": kb_id,
                    "resource_type": "bedrock:knowledge-base",
                    "region": self.region,
                    "tags": tags,
                    "created_at": kb.get("updatedAt"),
                    "arn": arn,
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch Bedrock knowledge bases: {str(e)}") from e

    # ================================================================
    # Networking: Load Balancers, Target Groups
    # ================================================================

    async def get_load_balancers(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch ALB/NLB load balancers with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("elbv2")
            response = await self._call_with_backoff("elbv2", client.describe_load_balancers)
            lbs = response.get("LoadBalancers", [])
            if not lbs:
                return []
            # Batch fetch tags (ELBv2 supports up to 20 ARNs per call)
            lb_arns = [lb.get("LoadBalancerArn", "") for lb in lbs]
            tags_map: dict[str, dict[str, str]] = {}
            for i in range(0, len(lb_arns), 20):
                batch = lb_arns[i : i + 20]
                tags_response = await self._call_with_backoff(
                    "elbv2", client.describe_tags, ResourceArns=batch,
                )
                for td in tags_response.get("TagDescriptions", []):
                    tags_map[td["ResourceArn"]] = self._extract_tags(td.get("Tags", []))
            resources = []
            for lb in lbs:
                lb_arn = lb.get("LoadBalancerArn", "")
                resources.append({
                    "resource_id": lb.get("LoadBalancerName"),
                    "resource_type": "elasticloadbalancing:loadbalancer",
                    "region": self.region,
                    "tags": tags_map.get(lb_arn, {}),
                    "created_at": lb.get("CreatedTime"),
                    "arn": lb_arn,
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch load balancers: {str(e)}") from e

    async def get_target_groups(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch ELB target groups with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("elbv2")
            response = await self._call_with_backoff("elbv2", client.describe_target_groups)
            tgs = response.get("TargetGroups", [])
            if not tgs:
                return []
            tg_arns = [tg.get("TargetGroupArn", "") for tg in tgs]
            tags_map: dict[str, dict[str, str]] = {}
            for i in range(0, len(tg_arns), 20):
                batch = tg_arns[i : i + 20]
                tags_response = await self._call_with_backoff(
                    "elbv2", client.describe_tags, ResourceArns=batch,
                )
                for td in tags_response.get("TagDescriptions", []):
                    tags_map[td["ResourceArn"]] = self._extract_tags(td.get("Tags", []))
            resources = []
            for tg in tgs:
                tg_arn = tg.get("TargetGroupArn", "")
                resources.append({
                    "resource_id": tg.get("TargetGroupName"),
                    "resource_type": "elasticloadbalancing:targetgroup",
                    "region": self.region,
                    "tags": tags_map.get(tg_arn, {}),
                    "created_at": None,
                    "arn": tg_arn,
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch target groups: {str(e)}") from e

    # ================================================================
    # Analytics: Kinesis, Glue, EMR
    # ================================================================

    async def get_kinesis_streams(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch Kinesis data streams with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("kinesis")
            account_id = await self._get_account_id()
            response = await self._call_with_backoff("kinesis", client.list_streams)
            resources = []
            for stream_name in response.get("StreamNames", []):
                arn = f"arn:aws:kinesis:{self.region}:{account_id}:stream/{stream_name}"
                try:
                    tags_resp = await self._call_with_backoff(
                        "kinesis", client.list_tags_for_stream, StreamName=stream_name,
                    )
                    tags = self._extract_tags(tags_resp.get("Tags", []))
                except AWSAPIError:
                    tags = {}
                resources.append({
                    "resource_id": stream_name,
                    "resource_type": "kinesis:stream",
                    "region": self.region,
                    "tags": tags,
                    "created_at": None,
                    "arn": arn,
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch Kinesis streams: {str(e)}") from e

    async def get_glue_jobs(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Fetch Glue jobs with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("glue")
            account_id = await self._get_account_id()
            response = await self._call_with_backoff("glue", client.get_jobs)
            resources = []
            for job in response.get("Jobs", []):
                job_name = job.get("Name")
                arn = f"arn:aws:glue:{self.region}:{account_id}:job/{job_name}"
                try:
                    tags_resp = await self._call_with_backoff(
                        "glue", client.get_tags, ResourceArn=arn,
                    )
                    tags = tags_resp.get("Tags", {})
                except AWSAPIError:
                    tags = {}
                resources.append({
                    "resource_id": job_name,
                    "resource_type": "glue:job",
                    "region": self.region,
                    "tags": tags,
                    "created_at": job.get("CreatedOn"),
                    "arn": arn,
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch Glue jobs: {str(e)}") from e

    async def get_glue_crawlers(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch Glue crawlers with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("glue")
            account_id = await self._get_account_id()
            response = await self._call_with_backoff("glue", client.get_crawlers)
            resources = []
            for crawler in response.get("Crawlers", []):
                name = crawler.get("Name")
                arn = f"arn:aws:glue:{self.region}:{account_id}:crawler/{name}"
                try:
                    tags_resp = await self._call_with_backoff(
                        "glue", client.get_tags, ResourceArn=arn,
                    )
                    tags = tags_resp.get("Tags", {})
                except AWSAPIError:
                    tags = {}
                resources.append({
                    "resource_id": name,
                    "resource_type": "glue:crawler",
                    "region": self.region,
                    "tags": tags,
                    "created_at": crawler.get("CreationTime"),
                    "arn": arn,
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch Glue crawlers: {str(e)}") from e

    async def get_glue_tables(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch Glue catalog tables with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("glue")
            account_id = await self._get_account_id()
            db_response = await self._call_with_backoff("glue", client.get_databases)
            resources = []
            for db in db_response.get("DatabaseList", []):
                db_name = db.get("Name")
                try:
                    tables_resp = await self._call_with_backoff(
                        "glue", client.get_tables, DatabaseName=db_name,
                    )
                    for table in tables_resp.get("TableList", []):
                        table_name = table.get("Name")
                        arn = f"arn:aws:glue:{self.region}:{account_id}:table/{db_name}/{table_name}"
                        try:
                            tags_resp = await self._call_with_backoff(
                                "glue", client.get_tags, ResourceArn=arn,
                            )
                            tags = tags_resp.get("Tags", {})
                        except AWSAPIError:
                            tags = {}
                        resources.append({
                            "resource_id": f"{db_name}/{table_name}",
                            "resource_type": "glue:table",
                            "region": self.region,
                            "tags": tags,
                            "created_at": table.get("CreateTime"),
                            "arn": arn,
                        })
                except AWSAPIError:
                    continue
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch Glue tables: {str(e)}") from e

    async def get_emr_clusters(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch active EMR clusters with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("emr")
            response = await self._call_with_backoff(
                "emr", client.list_clusters,
                ClusterStates=["STARTING", "BOOTSTRAPPING", "RUNNING", "WAITING"],
            )
            resources = []
            for cs in response.get("Clusters", []):
                cluster_id = cs.get("Id")
                try:
                    desc = await self._call_with_backoff(
                        "emr", client.describe_cluster, ClusterId=cluster_id,
                    )
                    cluster = desc.get("Cluster", {})
                    tags = self._extract_tags(cluster.get("Tags", []))
                    created = cs.get("Status", {}).get("Timeline", {}).get("CreationDateTime")
                    resources.append({
                        "resource_id": cluster_id,
                        "resource_type": "emr:cluster",
                        "region": self.region,
                        "tags": tags,
                        "created_at": created,
                        "arn": cluster.get("ClusterArn", ""),
                    })
                except AWSAPIError:
                    continue
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch EMR clusters: {str(e)}") from e

    # ================================================================
    # Security: Cognito, Secrets Manager, KMS
    # ================================================================

    async def get_cognito_user_pools(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch Cognito user pools with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("cognito-idp")
            response = await self._call_with_backoff(
                "cognito-idp", client.list_user_pools, MaxResults=60,
            )
            resources = []
            for pool in response.get("UserPools", []):
                pool_id = pool.get("Id")
                try:
                    desc = await self._call_with_backoff(
                        "cognito-idp", client.describe_user_pool, UserPoolId=pool_id,
                    )
                    detail = desc.get("UserPool", {})
                    resources.append({
                        "resource_id": pool_id,
                        "resource_type": "cognito-idp:userpool",
                        "region": self.region,
                        "tags": detail.get("UserPoolTags", {}),
                        "created_at": detail.get("CreationDate"),
                        "arn": detail.get("Arn", ""),
                    })
                except AWSAPIError:
                    continue
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch Cognito user pools: {str(e)}") from e

    async def get_cognito_identity_pools(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch Cognito identity pools with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("cognito-identity")
            account_id = await self._get_account_id()
            response = await self._call_with_backoff(
                "cognito-identity", client.list_identity_pools, MaxResults=60,
            )
            resources = []
            for pool in response.get("IdentityPools", []):
                pool_id = pool.get("IdentityPoolId")
                arn = f"arn:aws:cognito-identity:{self.region}:{account_id}:identitypool/{pool_id}"
                try:
                    desc = await self._call_with_backoff(
                        "cognito-identity", client.describe_identity_pool,
                        IdentityPoolId=pool_id,
                    )
                    tags = desc.get("IdentityPoolTags", {})
                except AWSAPIError:
                    tags = {}
                resources.append({
                    "resource_id": pool_id,
                    "resource_type": "cognito-identity:identitypool",
                    "region": self.region,
                    "tags": tags,
                    "created_at": None,
                    "arn": arn,
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch Cognito identity pools: {str(e)}") from e

    async def get_secrets(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Fetch Secrets Manager secrets with their tags (inline)."""
        filters = filters or {}
        try:
            client = self._get_client("secretsmanager")
            response = await self._call_with_backoff("secretsmanager", client.list_secrets)
            resources = []
            for secret in response.get("SecretList", []):
                tags = self._extract_tags(secret.get("Tags", []))
                resources.append({
                    "resource_id": secret.get("Name"),
                    "resource_type": "secretsmanager:secret",
                    "region": self.region,
                    "tags": tags,
                    "created_at": secret.get("CreatedDate"),
                    "arn": secret.get("ARN", ""),
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch secrets: {str(e)}") from e

    async def get_kms_keys(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Fetch customer-managed KMS keys with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("kms")
            response = await self._call_with_backoff("kms", client.list_keys)
            resources = []
            for key in response.get("Keys", []):
                key_id = key.get("KeyId")
                key_arn = key.get("KeyArn", "")
                try:
                    desc = await self._call_with_backoff("kms", client.describe_key, KeyId=key_id)
                    meta = desc.get("KeyMetadata", {})
                    if meta.get("KeyManager") != "CUSTOMER":
                        continue
                    tags_resp = await self._call_with_backoff(
                        "kms", client.list_resource_tags, KeyId=key_id,
                    )
                    tags = self._extract_tags(tags_resp.get("Tags", []))
                    resources.append({
                        "resource_id": key_id,
                        "resource_type": "kms:key",
                        "region": self.region,
                        "tags": tags,
                        "created_at": meta.get("CreationDate"),
                        "arn": key_arn,
                    })
                except AWSAPIError:
                    continue
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch KMS keys: {str(e)}") from e

    # ================================================================
    # Application: API Gateway, CloudFront, Route53, Step Functions,
    #              CodeBuild, CodePipeline
    # ================================================================

    async def get_api_gateways(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch API Gateway REST APIs with their tags (inline)."""
        filters = filters or {}
        try:
            client = self._get_client("apigateway")
            response = await self._call_with_backoff("apigateway", client.get_rest_apis)
            resources = []
            for api in response.get("items", []):
                api_id = api.get("id")
                arn = f"arn:aws:apigateway:{self.region}::/restapis/{api_id}"
                resources.append({
                    "resource_id": api_id,
                    "resource_type": "apigateway:restapi",
                    "region": self.region,
                    "tags": api.get("tags", {}),
                    "created_at": api.get("createdDate"),
                    "arn": arn,
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch API Gateways: {str(e)}") from e

    async def get_cloudfront_distributions(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch CloudFront distributions with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("cloudfront")
            response = await self._call_with_backoff("cloudfront", client.list_distributions)
            dist_list = response.get("DistributionList", {})
            resources = []
            for dist in dist_list.get("Items", []):
                dist_arn = dist.get("ARN", "")
                try:
                    tags_resp = await self._call_with_backoff(
                        "cloudfront", client.list_tags_for_resource, Resource=dist_arn,
                    )
                    tag_items = tags_resp.get("Tags", {}).get("Items", [])
                    tags = self._extract_tags(tag_items)
                except AWSAPIError:
                    tags = {}
                resources.append({
                    "resource_id": dist.get("Id"),
                    "resource_type": "cloudfront:distribution",
                    "region": "global",
                    "tags": tags,
                    "created_at": dist.get("LastModifiedTime"),
                    "arn": dist_arn,
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch CloudFront distributions: {str(e)}") from e

    async def get_route53_hosted_zones(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch Route 53 hosted zones with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("route53")
            response = await self._call_with_backoff("route53", client.list_hosted_zones)
            resources = []
            for zone in response.get("HostedZones", []):
                zone_id = zone.get("Id", "").split("/")[-1]
                arn = f"arn:aws:route53:::hostedzone/{zone_id}"
                try:
                    tags_resp = await self._call_with_backoff(
                        "route53", client.list_tags_for_resource,
                        ResourceType="hostedzone", ResourceId=zone_id,
                    )
                    tag_set = tags_resp.get("ResourceTagSet", {})
                    tags = self._extract_tags(tag_set.get("Tags", []))
                except AWSAPIError:
                    tags = {}
                resources.append({
                    "resource_id": zone_id,
                    "resource_type": "route53:hostedzone",
                    "region": "global",
                    "tags": tags,
                    "created_at": None,
                    "arn": arn,
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch Route 53 hosted zones: {str(e)}") from e

    async def get_step_functions(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch Step Functions state machines with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("stepfunctions")
            response = await self._call_with_backoff("stepfunctions", client.list_state_machines)
            resources = []
            for sm in response.get("stateMachines", []):
                sm_arn = sm.get("stateMachineArn", "")
                try:
                    tags_resp = await self._call_with_backoff(
                        "stepfunctions", client.list_tags_for_resource, resourceArn=sm_arn,
                    )
                    tags = self._extract_tags(tags_resp.get("tags", []))
                except AWSAPIError:
                    tags = {}
                resources.append({
                    "resource_id": sm.get("name"),
                    "resource_type": "stepfunctions:statemachine",
                    "region": self.region,
                    "tags": tags,
                    "created_at": sm.get("creationDate"),
                    "arn": sm_arn,
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch Step Functions: {str(e)}") from e

    async def get_codebuild_projects(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch CodeBuild projects with their tags (via batch_get)."""
        filters = filters or {}
        try:
            client = self._get_client("codebuild")
            list_resp = await self._call_with_backoff("codebuild", client.list_projects)
            names = list_resp.get("projects", [])
            if not names:
                return []
            desc = await self._call_with_backoff(
                "codebuild", client.batch_get_projects, names=names,
            )
            resources = []
            for project in desc.get("projects", []):
                tags = self._extract_tags(project.get("tags", []))
                resources.append({
                    "resource_id": project.get("name"),
                    "resource_type": "codebuild:project",
                    "region": self.region,
                    "tags": tags,
                    "created_at": project.get("created"),
                    "arn": project.get("arn", ""),
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch CodeBuild projects: {str(e)}") from e

    async def get_codepipeline_pipelines(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch CodePipeline pipelines with their tags."""
        filters = filters or {}
        try:
            client = self._get_client("codepipeline")
            account_id = await self._get_account_id()
            response = await self._call_with_backoff("codepipeline", client.list_pipelines)
            resources = []
            for pipeline in response.get("pipelines", []):
                name = pipeline.get("name")
                arn = f"arn:aws:codepipeline:{self.region}:{account_id}:{name}"
                try:
                    tags_resp = await self._call_with_backoff(
                        "codepipeline", client.list_tags_for_resource, resourceArn=arn,
                    )
                    tags = self._extract_tags(tags_resp.get("tags", []))
                except AWSAPIError:
                    tags = {}
                resources.append({
                    "resource_id": name,
                    "resource_type": "codepipeline:pipeline",
                    "region": self.region,
                    "tags": tags,
                    "created_at": pipeline.get("created"),
                    "arn": arn,
                })
            return resources
        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch CodePipeline pipelines: {str(e)}") from e

    async def get_cost_data(
        self,
        resource_ids: list[str] | None = None,
        time_period: dict[str, str] | None = None,
        granularity: str = "MONTHLY",
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
                "End": end_date.strftime("%Y-%m-%d"),
            }

        try:
            # Get cost and usage data
            response = await self._call_with_backoff(
                "ce",
                self.ce.get_cost_and_usage,
                TimePeriod=time_period,
                Granularity=granularity,
                Metrics=["UnblendedCost"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
            )

            # Parse cost data
            cost_by_service = {}
            for result in response.get("ResultsByTime", []):
                for group in result.get("Groups", []):
                    service = group.get("Keys", [""])[0]
                    amount = float(
                        group.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", 0)
                    )

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
    ) -> tuple[dict[str, float], dict[str, float], dict[str, float], str]:
        """
        Fetch cost data from AWS Cost Explorer with per-resource granularity where available.

        This method attempts to get actual per-resource costs for EC2 using the Name tag
        (since RESOURCE_ID dimension is not available in standard Cost Explorer).
        For other services (S3, Lambda, ECS), it returns service-level totals.

        Args:
            time_period: Time period for cost data (e.g., {"Start": "2025-01-01", "End": "2025-01-31"})

        Returns:
            Tuple of:
            - resource_costs: Dict mapping resource IDs to actual costs (EC2/RDS)
            - service_costs: Dict mapping service names to total costs
            - costs_by_name: Dict mapping Name tag values to costs (for EC2)
            - cost_source: "actual" if per-resource data available, "service_average" otherwise
        """
        # Default to last 30 days if no time period specified
        if not time_period:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            time_period = {
                "Start": start_date.strftime("%Y-%m-%d"),
                "End": end_date.strftime("%Y-%m-%d"),
            }

        resource_costs: dict[str, float] = {}
        service_costs: dict[str, float] = {}
        costs_by_name: dict[str, float] = {}
        cost_source = "estimated"

        try:
            # First, get service-level costs (always works)
            service_response = await self._call_with_backoff(
                "ce",
                self.ce.get_cost_and_usage,
                TimePeriod=time_period,
                Granularity="MONTHLY",
                Metrics=["UnblendedCost"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
            )

            for result in service_response.get("ResultsByTime", []):
                for group in result.get("Groups", []):
                    service = group.get("Keys", [""])[0]
                    amount = float(
                        group.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", 0)
                    )
                    service_costs[service] = service_costs.get(service, 0) + amount

            cost_source = "service_average"

            # Get per-resource costs for EC2 using Name tag (Cost Allocation Tag)
            # RESOURCE_ID dimension is not available in standard Cost Explorer
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
                            "Values": ["Amazon Elastic Compute Cloud - Compute"],
                        }
                    },
                    GroupBy=[{"Type": "TAG", "Key": "Name"}],
                )

                for result in ec2_response.get("ResultsByTime", []):
                    for group in result.get("Groups", []):
                        # Tag key format is "Name$value" or just the value
                        tag_key = group.get("Keys", [""])[0]
                        # Extract the actual name value (remove "Name$" prefix if present)
                        if tag_key.startswith("Name$"):
                            name_value = tag_key[5:]  # Remove "Name$" prefix
                        else:
                            name_value = tag_key

                        amount = float(
                            group.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", 0)
                        )
                        if name_value and amount > 0:
                            # Aggregate costs by name (same instance may appear multiple times)
                            costs_by_name[name_value] = costs_by_name.get(name_value, 0) + amount

                if costs_by_name:
                    cost_source = "actual_by_name"

            except Exception as e:
                # Per-resource costs not available, continue with service-level
                import logging

                logging.getLogger(__name__).debug(
                    f"Per-resource EC2 costs by Name tag not available: {e}"
                )

            # Try to get per-resource costs for RDS using Name tag
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
                            "Values": ["Amazon Relational Database Service"],
                        }
                    },
                    GroupBy=[{"Type": "TAG", "Key": "Name"}],
                )

                for result in rds_response.get("ResultsByTime", []):
                    for group in result.get("Groups", []):
                        tag_key = group.get("Keys", [""])[0]
                        # Extract the actual name value (remove "Name$" prefix if present)
                        if tag_key.startswith("Name$"):
                            name_value = tag_key[5:]
                        else:
                            name_value = tag_key

                        amount = float(
                            group.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", 0)
                        )
                        if name_value and amount > 0:
                            # Store RDS costs by name as well
                            costs_by_name[name_value] = costs_by_name.get(name_value, 0) + amount

            except Exception as e:
                import logging

                logging.getLogger(__name__).debug(f"Per-resource RDS costs not available: {e}")

            return resource_costs, service_costs, costs_by_name, cost_source

        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch cost data: {str(e)}") from e

    def get_service_name_for_resource_type(self, resource_type: str) -> str:
        """
        Map resource type to AWS Cost Explorer service name.

        Service name mapping is loaded from config/resource_types.json.
        Falls back to hardcoded mapping if config not available.

        Args:
            resource_type: Resource type (e.g., "ec2:instance")

        Returns:
            AWS service name as it appears in Cost Explorer, or empty string if free/unknown
        """
        # Try to load from config first
        try:
            from ..utils.resource_type_config import get_service_name_for_resource_type

            return get_service_name_for_resource_type(resource_type)
        except ImportError:
            pass

        # Fallback to hardcoded mapping if config service not available
        service_map = {
            "ec2:instance": "Amazon Elastic Compute Cloud - Compute",
            "ec2:volume": "Amazon Elastic Compute Cloud - Compute",
            "ec2:elastic-ip": "EC2 - Other",
            "ec2:snapshot": "EC2 - Other",
            "ec2:natgateway": "EC2 - Other",
            "ec2:vpc": "",
            "ec2:subnet": "",
            "ec2:security-group": "",
            "lambda:function": "AWS Lambda",
            "s3:bucket": "Amazon Simple Storage Service",
            "rds:db": "Amazon Relational Database Service",
            "dynamodb:table": "Amazon DynamoDB",
        }
        return service_map.get(resource_type, "")

    async def get_all_tagged_resources(
        self,
        resource_type_filters: list[str] | None = None,
        tag_filters: list[dict[str, Any]] | None = None,
        include_compliance_details: bool = False,
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
                aws_resource_types = self._convert_resource_types_to_aws_format(
                    resource_type_filters
                )
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
                    **request_params,
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
                        "created_at": None,  # Resource Groups Tagging API doesn't provide creation date
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
            raise AWSAPIError(
                f"Failed to fetch resources via Resource Groups Tagging API: {str(e)}"
            ) from e

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
            # Compute (40-60% of typical spend)
            "ec2:instance": "ec2:instance",
            "ec2:volume": "ec2:volume",
            "ec2:natgateway": "ec2:natgateway",
            "ec2:vpc": "ec2:vpc",
            "ec2:subnet": "ec2:subnet",
            "ec2:security-group": "ec2:security-group",
            "lambda:function": "lambda:function",
            "ecs:cluster": "ecs:cluster",
            "ecs:service": "ecs:service",
            "ecs:task-definition": "ecs:task-definition",
            "eks:cluster": "eks:cluster",
            "eks:nodegroup": "eks:nodegroup",
            # Storage (10-20% of typical spend)
            "s3:bucket": "s3",  # S3 uses just "s3" in the API
            "elasticfilesystem:file-system": "elasticfilesystem:file-system",
            "fsx:file-system": "fsx:file-system",
            # Database (15-25% of typical spend)
            "rds:db": "rds:db",
            "dynamodb:table": "dynamodb:table",
            "elasticache:cluster": "elasticache:cluster",
            "redshift:cluster": "redshift:cluster",
            # AI/ML (Growing rapidly)
            "sagemaker:endpoint": "sagemaker:endpoint",
            "sagemaker:notebook-instance": "sagemaker:notebook-instance",
            "bedrock:agent": "bedrock:agent",
            "bedrock:knowledge-base": "bedrock:knowledge-base",
            # Networking (Often overlooked)
            "elasticloadbalancing:loadbalancer": "elasticloadbalancing:loadbalancer",
            "elasticloadbalancing:targetgroup": "elasticloadbalancing:targetgroup",
            # Analytics (Data & streaming)
            "kinesis:stream": "kinesis:stream",
            "glue:job": "glue:job",
            "glue:crawler": "glue:crawler",
            "glue:database": "glue:database",
            "athena:workgroup": "athena:workgroup",
            "opensearch:domain": "es:domain",  # OpenSearch uses "es" prefix
            # Identity & Security
            "cognito-idp:userpool": "cognito-idp:userpool",
            "secretsmanager:secret": "secretsmanager:secret",
            "kms:key": "kms:key",
            # Monitoring & Logging
            "logs:log-group": "logs:log-group",
            "cloudwatch:alarm": "cloudwatch:alarm",
            # Messaging
            "sns:topic": "sns",
            "sqs:queue": "sqs",
            # Containers
            "ecr:repository": "ecr:repository",
            # Additional common resource types (legacy mappings)
            "efs:file-system": "elasticfilesystem:file-system",
            "apigateway:restapi": "apigateway",
            "cloudfront:distribution": "cloudfront:distribution",
            "route53:hostedzone": "route53:hostedzone",
            "glue:table": "glue:table",
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
                "resource_id": arn,
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
            "resource_id": resource_id,
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
            elif resource_part.startswith("natgateway/"):
                return "ec2:natgateway", resource_part.split("/")[1]
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
            elif resource_part.startswith("task-definition/"):
                return "ecs:task-definition", resource_part.split("/")[1].split(":")[0]
            else:
                return f"ecs:{resource_part.split('/')[0]}", resource_part.split("/")[-1]

        elif service == "eks":
            if resource_part.startswith("cluster/"):
                return "eks:cluster", resource_part.split("/")[1]
            elif resource_part.startswith("nodegroup/"):
                # Format: nodegroup/cluster-name/nodegroup-name/id
                parts = resource_part.split("/")
                return "eks:nodegroup", parts[2] if len(parts) > 2 else parts[-1]
            else:
                return f"eks:{resource_part.split('/')[0]}", resource_part.split("/")[-1]

        elif service == "sagemaker":
            if resource_part.startswith("endpoint/"):
                return "sagemaker:endpoint", resource_part.split("/")[1]
            elif resource_part.startswith("notebook-instance/"):
                return "sagemaker:notebook-instance", resource_part.split("/")[1]
            elif resource_part.startswith("training-job/"):
                return "sagemaker:training-job", resource_part.split("/")[1]
            elif resource_part.startswith("model/"):
                return "sagemaker:model", resource_part.split("/")[1]
            else:
                return f"sagemaker:{resource_part.split('/')[0]}", resource_part.split("/")[-1]

        elif service == "fsx":
            if resource_part.startswith("file-system/"):
                return "fsx:file-system", resource_part.split("/")[1]
            elif resource_part.startswith("backup/"):
                return "fsx:backup", resource_part.split("/")[1]
            else:
                return f"fsx:{resource_part.split('/')[0]}", resource_part.split("/")[-1]

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
                return "elasticfilesystem:file-system", resource_part.split("/")[1]
            else:
                return "elasticfilesystem:file-system", resource_part

        elif service == "elasticloadbalancing":
            if resource_part.startswith("loadbalancer/"):
                return "elasticloadbalancing:loadbalancer", resource_part.split("/")[-1]
            elif resource_part.startswith("targetgroup/"):
                return "elasticloadbalancing:targetgroup", resource_part.split("/")[-1]
            else:
                return (
                    f"elasticloadbalancing:{resource_part.split('/')[0]}",
                    resource_part.split("/")[-1],
                )

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
                return (
                    f"cognito-identity:{resource_part.split('/')[0]}",
                    resource_part.split("/")[-1],
                )

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
                "End": end_date.strftime("%Y-%m-%d"),
            }

        try:
            # Get total cost grouped by service
            response = await self._call_with_backoff(
                "ce",
                self.ce.get_cost_and_usage,
                TimePeriod=time_period,
                Granularity="MONTHLY",
                Metrics=["UnblendedCost"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
            )

            total_spend = 0.0
            service_breakdown: dict[str, float] = {}

            for result in response.get("ResultsByTime", []):
                for group in result.get("Groups", []):
                    service = group.get("Keys", [""])[0]
                    amount = float(
                        group.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", 0)
                    )
                    service_breakdown[service] = service_breakdown.get(service, 0) + amount
                    total_spend += amount

            return total_spend, service_breakdown

        except AWSAPIError:
            raise
        except Exception as e:
            raise AWSAPIError(f"Failed to fetch total account spend: {str(e)}") from e
