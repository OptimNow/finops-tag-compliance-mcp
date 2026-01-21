# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""
Configuration loader for AWS resource types.

Loads resource types from external JSON configuration file for easy maintenance.
This module is in utils/ to avoid circular imports with services/.
"""

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default config path - can be overridden via environment variable
DEFAULT_CONFIG_PATH = "config/resource_types.json"


class ResourceTypeConfig:
    """
    Configuration for AWS resource types.
    
    Manages three categories of resources:
    1. Cost-generating resources: Scanned for compliance and cost attribution
    2. Free resources: Taggable but no direct cost (excluded from compliance by default)
    3. Unattributable services: Have costs but no taggable resources (Bedrock API, Tax, etc.)
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize resource type configuration.
        
        Args:
            config_path: Path to JSON config file. If None, uses DEFAULT_CONFIG_PATH
                        or RESOURCE_TYPES_CONFIG_PATH environment variable.
        """
        self.config_path = config_path or os.environ.get(
            "RESOURCE_TYPES_CONFIG_PATH",
            DEFAULT_CONFIG_PATH
        )
        self._config: Optional[dict] = None
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from JSON file."""
        try:
            # Try multiple paths for flexibility
            paths_to_try = [
                Path(self.config_path),
                Path(__file__).parent.parent.parent / self.config_path,
                Path("/app") / self.config_path,  # Docker container path
            ]
            
            for path in paths_to_try:
                if path.exists():
                    with open(path, "r", encoding="utf-8") as f:
                        self._config = json.load(f)
                    logger.info(f"Loaded resource type config from {path}")
                    return
            
            logger.warning(
                f"Resource type config not found at {self.config_path}, using defaults"
            )
            self._config = self._get_default_config()
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in resource type config: {e}")
            self._config = self._get_default_config()
        except Exception as e:
            logger.error(f"Failed to load resource type config: {e}")
            self._config = self._get_default_config()
    
    def _get_default_config(self) -> dict:
        """Return default configuration if file not found."""
        return {
            "cost_generating_resources": {
                "compute": [
                    "ec2:instance", "ec2:volume", "ec2:elastic-ip", "ec2:snapshot",
                    "ec2:natgateway", "lambda:function", "ecs:cluster", "ecs:service",
                    "ecs:task-definition", "eks:cluster", "eks:nodegroup"
                ],
                "storage": ["s3:bucket", "elasticfilesystem:file-system", "fsx:file-system"],
                "database": [
                    "rds:db", "rds:cluster", "dynamodb:table", "elasticache:cluster",
                    "elasticache:replicationgroup", "redshift:cluster"
                ],
                "ai_ml": [
                    "sagemaker:endpoint", "sagemaker:notebook-instance",
                    "bedrock:agent", "bedrock:knowledge-base"
                ],
                "networking": [
                    "elasticloadbalancing:loadbalancer", "elasticloadbalancing:targetgroup"
                ],
                "analytics": [
                    "kinesis:stream", "glue:job", "glue:crawler", "glue:table",
                    "opensearch:domain", "emr:cluster"
                ],
                "security": [
                    "cognito-idp:userpool", "cognito-identity:identitypool",
                    "secretsmanager:secret", "kms:key"
                ],
                "application": [
                    "apigateway:restapi", "cloudfront:distribution", "route53:hostedzone",
                    "stepfunctions:statemachine", "codebuild:project", "codepipeline:pipeline"
                ]
            },
            "free_resources": {
                "networking": ["ec2:vpc", "ec2:subnet", "ec2:security-group"],
                "monitoring": ["logs:log-group", "cloudwatch:alarm"],
                "messaging": ["sns:topic", "sqs:queue"],
                "containers": ["ecr:repository"],
                "analytics": ["glue:database", "athena:workgroup"]
            },
            "unattributable_services": {
                "ai_ml_api_usage": [
                    "Claude 3.5 Sonnet (Amazon Bedrock Edition)",
                    "Amazon Bedrock"
                ],
                "aws_fees": ["Tax", "AWS Cost Explorer"]
            },
            "service_name_mapping": {
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
                "rds:cluster": "Amazon Relational Database Service",
                "dynamodb:table": "Amazon DynamoDB",
                "ecs:cluster": "Amazon Elastic Container Service",
                "ecs:service": "Amazon Elastic Container Service",
                "ecs:task-definition": "Amazon Elastic Container Service",
                "eks:cluster": "Amazon Elastic Kubernetes Service",
                "eks:nodegroup": "Amazon Elastic Kubernetes Service",
                "elasticfilesystem:file-system": "Amazon Elastic File System",
                "fsx:file-system": "Amazon FSx",
                "elasticache:cluster": "Amazon ElastiCache",
                "elasticache:replicationgroup": "Amazon ElastiCache",
                "redshift:cluster": "Amazon Redshift",
                "sagemaker:endpoint": "Amazon SageMaker",
                "sagemaker:notebook-instance": "Amazon SageMaker",
                "bedrock:agent": "Amazon Bedrock",
                "bedrock:knowledge-base": "Amazon Bedrock",
                "elasticloadbalancing:loadbalancer": "Elastic Load Balancing",
                "elasticloadbalancing:targetgroup": "Elastic Load Balancing",
                "kinesis:stream": "Amazon Kinesis",
                "glue:job": "AWS Glue",
                "glue:crawler": "AWS Glue",
                "glue:table": "AWS Glue",
                "glue:database": "",
                "athena:workgroup": "",
                "opensearch:domain": "Amazon OpenSearch Service",
                "emr:cluster": "Amazon EMR",
                "cognito-idp:userpool": "Amazon Cognito",
                "cognito-identity:identitypool": "Amazon Cognito",
                "secretsmanager:secret": "AWS Secrets Manager",
                "kms:key": "AWS Key Management Service",
                "logs:log-group": "",
                "cloudwatch:alarm": "",
                "sns:topic": "",
                "sqs:queue": "",
                "ecr:repository": "",
                "apigateway:restapi": "Amazon API Gateway",
                "cloudfront:distribution": "Amazon CloudFront",
                "route53:hostedzone": "Amazon Route 53",
                "stepfunctions:statemachine": "AWS Step Functions",
                "codebuild:project": "AWS CodeBuild",
                "codepipeline:pipeline": "AWS CodePipeline"
            }
        }
    
    def get_cost_generating_resources(self) -> list[str]:
        """
        Get list of resource types that generate direct costs.
        
        These are the resources scanned for compliance and cost attribution.
        
        Returns:
            Flat list of resource type strings
        """
        resources = []
        cost_gen = self._config.get("cost_generating_resources", {})
        
        for category, types in cost_gen.items():
            if category.startswith("_"):  # Skip metadata fields
                continue
            if isinstance(types, list):
                resources.extend(types)
        
        return resources
    
    def get_free_resources(self) -> list[str]:
        """
        Get list of resource types that are taggable but free.
        
        These are excluded from compliance scans by default.
        
        Returns:
            Flat list of resource type strings
        """
        resources = []
        free = self._config.get("free_resources", {})
        
        for category, types in free.items():
            if category.startswith("_"):
                continue
            if isinstance(types, list):
                resources.extend(types)
        
        return resources
    
    def get_all_taggable_resources(self) -> list[str]:
        """
        Get all taggable resource types (cost-generating + free).
        
        Returns:
            Combined list of all taggable resource types
        """
        return self.get_cost_generating_resources() + self.get_free_resources()
    
    def get_unattributable_services(self) -> list[str]:
        """
        Get list of service names that have costs but no taggable resources.
        
        These are excluded from attribution gap calculation.
        
        Returns:
            Flat list of Cost Explorer service names
        """
        services = []
        unattr = self._config.get("unattributable_services", {})
        
        for category, names in unattr.items():
            if category.startswith("_"):
                continue
            if isinstance(names, list):
                services.extend(names)
        
        return services
    
    def get_service_name(self, resource_type: str) -> str:
        """
        Get Cost Explorer service name for a resource type.
        
        Args:
            resource_type: Resource type (e.g., "ec2:instance")
        
        Returns:
            Service name as it appears in Cost Explorer, or empty string if free/unknown
        """
        mapping = self._config.get("service_name_mapping", {})
        return mapping.get(resource_type, "")
    
    def is_cost_generating(self, resource_type: str) -> bool:
        """Check if a resource type generates direct costs."""
        return resource_type in self.get_cost_generating_resources()
    
    def is_free_resource(self, resource_type: str) -> bool:
        """Check if a resource type is free (no direct cost)."""
        return resource_type in self.get_free_resources()
    
    def reload(self) -> None:
        """Reload configuration from file."""
        self._load_config()
        # Clear cached instance
        get_resource_type_config.cache_clear()


@lru_cache(maxsize=1)
def get_resource_type_config() -> ResourceTypeConfig:
    """
    Get singleton instance of ResourceTypeConfig.
    
    Uses LRU cache to ensure single instance across the application.
    
    Returns:
        ResourceTypeConfig instance
    """
    return ResourceTypeConfig()


# Convenience functions
def get_supported_resource_types() -> list[str]:
    """Get cost-generating resource types (for compliance scans)."""
    return get_resource_type_config().get_cost_generating_resources()


def get_tagging_api_resource_types() -> list[str]:
    """Get all taggable resource types (for Resource Groups Tagging API)."""
    return get_resource_type_config().get_cost_generating_resources()


def get_unattributable_services() -> list[str]:
    """Get services with costs but no taggable resources."""
    return get_resource_type_config().get_unattributable_services()


def get_service_name_for_resource_type(resource_type: str) -> str:
    """Get Cost Explorer service name for a resource type."""
    return get_resource_type_config().get_service_name(resource_type)
