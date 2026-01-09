# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Input validation utilities for MCP tools.

This module provides comprehensive JSON schema validation with detailed
field-level error messages for all MCP tool inputs. Includes detection
of validation bypass attempts and malicious payload injection.

Requirements: 16.3
"""

import re
from typing import Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SecurityViolationError(Exception):
    """Raised when a potential security violation is detected."""
    
    def __init__(self, violation_type: str, message: str, value: Any = None):
        """
        Initialize security violation error.
        
        Args:
            violation_type: Type of security violation detected
            message: Human-readable error message
            value: The suspicious value (optional, for logging)
        """
        self.violation_type = violation_type
        self.message = message
        self.value = value
        super().__init__(f"Security violation ({violation_type}): {message}")


class ValidationError(Exception):
    """Raised when input validation fails."""
    
    def __init__(self, field: str, message: str, value: Any = None):
        """
        Initialize validation error.
        
        Args:
            field: The field that failed validation
            message: Human-readable error message
            value: The invalid value (optional, for logging)
        """
        self.field = field
        self.message = message
        self.value = value
        super().__init__(f"Validation error for '{field}': {message}")


class InputValidator:
    """
    Comprehensive input validator for MCP tools.
    
    Provides strict validation with detailed field-level feedback to prevent
    malformed inputs and potential security issues. Includes detection of
    validation bypass attempts, injection attacks, and malicious payloads.
    
    Requirements: 16.3
    """
    
    # Valid resource types
    # "all" uses Resource Groups Tagging API to scan all tagged resources
    VALID_RESOURCE_TYPES = {
        "all",
        "ec2:instance",
        "rds:db",
        "s3:bucket",
        "lambda:function",
        "ecs:service",
        "opensearch:domain",
    }
    
    # Valid severity levels
    VALID_SEVERITIES = {"all", "errors_only", "warnings_only"}
    
    # Valid report formats
    VALID_REPORT_FORMATS = {"json", "csv", "markdown"}
    
    # Valid grouping options
    VALID_GROUP_BY_OPTIONS = {"resource_type", "region", "account", "service"}
    
    # Valid history grouping options
    VALID_HISTORY_GROUP_BY = {"day", "week", "month"}
    
    # Valid AWS regions (subset for validation)
    VALID_AWS_REGIONS = {
        "us-east-1", "us-east-2", "us-west-1", "us-west-2",
        "eu-west-1", "eu-west-2", "eu-west-3", "eu-central-1",
        "ap-southeast-1", "ap-southeast-2", "ap-northeast-1",
        "ap-south-1", "sa-east-1", "ca-central-1",
    }
    
    # Maximum parameter sizes (security limits)
    MAX_RESOURCE_TYPES = 10
    MAX_RESOURCE_ARNS = 100
    MAX_REGIONS = 20
    MAX_STRING_LENGTH = 1024
    MAX_ARRAY_LENGTH = 1000
    MAX_DICT_KEYS = 50
    MAX_NESTED_DEPTH = 5
    
    # Suspicious patterns that may indicate injection attempts
    SUSPICIOUS_PATTERNS = [
        re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL),  # XSS
        re.compile(r'javascript:', re.IGNORECASE),  # JavaScript protocol
        re.compile(r'on\w+\s*=', re.IGNORECASE),  # Event handlers
        re.compile(r'eval\s*\(', re.IGNORECASE),  # eval() calls
        re.compile(r'exec\s*\(', re.IGNORECASE),  # exec() calls
        re.compile(r'__import__', re.IGNORECASE),  # Python imports
        re.compile(r'\$\{.*?\}'),  # Template injection
        re.compile(r'\{\{.*?\}\}'),  # Template injection (Jinja2/Handlebars)
        re.compile(r'\.\./', re.IGNORECASE),  # Path traversal
        re.compile(r'\.\.\\', re.IGNORECASE),  # Path traversal (Windows)
        re.compile(r'/etc/passwd', re.IGNORECASE),  # System file access
        re.compile(r'cmd\.exe', re.IGNORECASE),  # Command execution
        re.compile(r'/bin/(ba)?sh', re.IGNORECASE),  # Shell access
        re.compile(r';\s*(rm|del|drop|truncate)', re.IGNORECASE),  # Destructive commands
    ]
    
    # ==========================================================================
    # ARN Pattern Validation
    # ==========================================================================
    # AWS ARN Format: arn:partition:service:region:account-id:resource
    #
    # Different AWS services have different ARN formats:
    #
    # 1. STANDARD FORMAT (most services):
    #    arn:aws:service:region:account-id:resource-type/resource-id
    #    Example: arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0
    #
    # 2. GLOBAL SERVICES (no region):
    #    arn:aws:service::account-id:resource
    #    Examples:
    #    - IAM: arn:aws:iam::123456789012:user/johndoe
    #    - IAM: arn:aws:iam::123456789012:role/admin-role
    #    - IAM: arn:aws:iam::123456789012:policy/my-policy
    #    - Route53: arn:aws:route53::123456789012:hostedzone/Z1234567890
    #    - CloudFront: arn:aws:cloudfront::123456789012:distribution/E1234567890
    #
    # 3. S3 BUCKETS (no region, no account):
    #    arn:aws:s3:::bucket-name
    #    arn:aws:s3:::bucket-name/key-name
    #    Note: S3 bucket ARNs have empty region AND account fields
    #
    # 4. S3 ACCESS POINTS (with region and account):
    #    arn:aws:s3:us-east-1:123456789012:accesspoint/my-access-point
    #
    # 5. LAMBDA FUNCTIONS:
    #    arn:aws:lambda:region:account-id:function:function-name
    #    arn:aws:lambda:region:account-id:function:function-name:alias
    #    arn:aws:lambda:region:account-id:function:function-name:$LATEST
    #
    # 6. RDS RESOURCES:
    #    arn:aws:rds:region:account-id:db:db-instance-id
    #    arn:aws:rds:region:account-id:cluster:cluster-id
    #    arn:aws:rds:region:account-id:snapshot:snapshot-id
    #
    # 7. ECS RESOURCES:
    #    arn:aws:ecs:region:account-id:cluster/cluster-name
    #    arn:aws:ecs:region:account-id:service/cluster-name/service-name
    #    arn:aws:ecs:region:account-id:task/cluster-name/task-id
    #
    # 8. OPENSEARCH/ELASTICSEARCH:
    #    arn:aws:es:region:account-id:domain/domain-name
    #    arn:aws:opensearch:region:account-id:domain/domain-name
    #
    # 9. SNS/SQS:
    #    arn:aws:sns:region:account-id:topic-name
    #    arn:aws:sqs:region:account-id:queue-name
    #
    # 10. DYNAMODB:
    #     arn:aws:dynamodb:region:account-id:table/table-name
    #
    # 11. KINESIS:
    #     arn:aws:kinesis:region:account-id:stream/stream-name
    #
    # 12. SECRETS MANAGER:
    #     arn:aws:secretsmanager:region:account-id:secret:secret-name
    #
    # 13. KMS:
    #     arn:aws:kms:region:account-id:key/key-id
    #     arn:aws:kms:region:account-id:alias/alias-name
    #
    # 14. STEP FUNCTIONS:
    #     arn:aws:states:region:account-id:stateMachine:state-machine-name
    #
    # 15. API GATEWAY:
    #     arn:aws:apigateway:region::/restapis/api-id
    #     arn:aws:execute-api:region:account-id:api-id/stage/method/resource
    #
    # 16. CLOUDWATCH:
    #     arn:aws:logs:region:account-id:log-group:log-group-name
    #     arn:aws:cloudwatch:region:account-id:alarm:alarm-name
    #
    # 17. ELASTIC LOAD BALANCING:
    #     arn:aws:elasticloadbalancing:region:account-id:loadbalancer/app/name/id
    #     arn:aws:elasticloadbalancing:region:account-id:targetgroup/name/id
    #
    # 18. ELASTICACHE:
    #     arn:aws:elasticache:region:account-id:cluster:cluster-id
    #     arn:aws:elasticache:region:account-id:replicationgroup:group-id
    #
    # 19. REDSHIFT:
    #     arn:aws:redshift:region:account-id:cluster:cluster-id
    #
    # 20. GLUE:
    #     arn:aws:glue:region:account-id:database/database-name
    #     arn:aws:glue:region:account-id:table/database-name/table-name
    #
    # ==========================================================================
    #
    # Comprehensive ARN pattern that handles:
    # - Standard services with region and account (ec2, rds, lambda, etc.)
    # - Global services with no region (iam, route53, cloudfront)
    # - S3 buckets with no region AND no account
    # - Various resource naming conventions (slashes, colons, dots, underscores)
    # - AWS partitions (aws, aws-cn, aws-us-gov)
    #
    ARN_PATTERN = re.compile(
        r'^arn:'                           # ARN prefix
        r'(aws|aws-cn|aws-us-gov):'        # Partition (aws, aws-cn for China, aws-us-gov for GovCloud)
        r'[a-z0-9\-]+:'                    # Service name (ec2, s3, iam, lambda, etc.)
        r'[a-z0-9\-]*:'                    # Region (can be empty for global services like IAM, S3)
        r'(\d{12}|):'                      # Account ID (12 digits, or empty for S3 buckets)
        r'[a-zA-Z0-9\-/:._*$@+=]+$'
    )
    
    # Date pattern validation (YYYY-MM-DD)
    DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    
    @classmethod
    def detect_injection_attempt(cls, value: str, field_name: str) -> None:
        """
        Detect potential injection attempts in string values.
        
        Args:
            value: String value to check
            field_name: Name of the field being validated
        
        Raises:
            SecurityViolationError: If suspicious patterns are detected
        
        Requirements: 16.3
        """
        if not isinstance(value, str):
            return
        
        for pattern in cls.SUSPICIOUS_PATTERNS:
            if pattern.search(value):
                logger.warning(
                    f"Potential injection attempt detected in field '{field_name}': "
                    f"pattern={pattern.pattern}, value_preview={value[:100]}"
                )
                raise SecurityViolationError(
                    violation_type="injection_attempt",
                    message=f"Suspicious pattern detected in field '{field_name}'. "
                    f"Input appears to contain potentially malicious content.",
                    value=value[:100],  # Only log preview for security
                )
    
    @classmethod
    def check_parameter_size_limits(cls, data: Any, field_name: str = "root", depth: int = 0) -> None:
        """
        Recursively check parameter size limits to prevent resource exhaustion.
        
        Args:
            data: Data structure to check
            field_name: Name of the current field
            depth: Current nesting depth
        
        Raises:
            SecurityViolationError: If size limits are exceeded
        
        Requirements: 16.3
        """
        # Check nesting depth
        if depth > cls.MAX_NESTED_DEPTH:
            logger.warning(
                f"Excessive nesting depth detected in field '{field_name}': "
                f"depth={depth}, max={cls.MAX_NESTED_DEPTH}"
            )
            raise SecurityViolationError(
                violation_type="excessive_nesting",
                message=f"Parameter nesting too deep (max: {cls.MAX_NESTED_DEPTH} levels)",
                value=depth,
            )
        
        if isinstance(data, dict):
            # Check number of keys
            if len(data) > cls.MAX_DICT_KEYS:
                logger.warning(
                    f"Excessive dictionary keys in field '{field_name}': "
                    f"keys={len(data)}, max={cls.MAX_DICT_KEYS}"
                )
                raise SecurityViolationError(
                    violation_type="excessive_keys",
                    message=f"Too many dictionary keys (max: {cls.MAX_DICT_KEYS})",
                    value=len(data),
                )
            
            # Recursively check nested values
            for key, value in data.items():
                # Check key length
                if isinstance(key, str) and len(key) > cls.MAX_STRING_LENGTH:
                    raise SecurityViolationError(
                        violation_type="excessive_key_length",
                        message=f"Dictionary key too long (max: {cls.MAX_STRING_LENGTH} chars)",
                        value=len(key),
                    )
                
                cls.check_parameter_size_limits(value, f"{field_name}.{key}", depth + 1)
        
        elif isinstance(data, list):
            # Check array length
            if len(data) > cls.MAX_ARRAY_LENGTH:
                logger.warning(
                    f"Excessive array length in field '{field_name}': "
                    f"length={len(data)}, max={cls.MAX_ARRAY_LENGTH}"
                )
                raise SecurityViolationError(
                    violation_type="excessive_array_length",
                    message=f"Array too long (max: {cls.MAX_ARRAY_LENGTH} items)",
                    value=len(data),
                )
            
            # Recursively check nested values
            for i, item in enumerate(data):
                cls.check_parameter_size_limits(item, f"{field_name}[{i}]", depth + 1)
        
        elif isinstance(data, str):
            # Check string length
            if len(data) > cls.MAX_STRING_LENGTH:
                logger.warning(
                    f"Excessive string length in field '{field_name}': "
                    f"length={len(data)}, max={cls.MAX_STRING_LENGTH}"
                )
                raise SecurityViolationError(
                    violation_type="excessive_string_length",
                    message=f"String too long (max: {cls.MAX_STRING_LENGTH} chars)",
                    value=len(data),
                )
    
    @classmethod
    def sanitize_string(cls, value: str, max_length: int = MAX_STRING_LENGTH, field_name: str = "string") -> str:
        """
        Sanitize string input to prevent injection attacks.
        
        Args:
            value: String to sanitize
            max_length: Maximum allowed length
            field_name: Name of the field being sanitized
        
        Returns:
            Sanitized string
        
        Raises:
            ValidationError: If string is too long or contains dangerous characters
            SecurityViolationError: If injection attempt is detected
        """
        if not isinstance(value, str):
            return value
        
        # Check for injection attempts first
        cls.detect_injection_attempt(value, field_name)
        
        # Truncate to max length
        if len(value) > max_length:
            raise ValidationError(
                field_name,
                f"String too long (max: {max_length} chars, got: {len(value)})",
                len(value),
            )
        
        # Check for null bytes (potential injection)
        if '\x00' in value:
            logger.warning(
                f"Null byte detected in field '{field_name}' - potential injection attempt"
            )
            raise SecurityViolationError(
                violation_type="null_byte_injection",
                message="String contains null bytes (potential injection attempt)",
                value=value[:100],
            )
        
        # Check for control characters (except newline, tab, carriage return)
        dangerous_chars = [chr(i) for i in range(32) if i not in (9, 10, 13)]
        for char in dangerous_chars:
            if char in value:
                logger.warning(
                    f"Control character detected in field '{field_name}': {repr(char)}"
                )
                raise SecurityViolationError(
                    violation_type="control_character",
                    message=f"String contains dangerous control character: {repr(char)}",
                    value=value[:100],
                )
        
        return value
    
    @classmethod
    def validate_resource_types(
        cls,
        resource_types: Any,
        field_name: str = "resource_types",
        required: bool = True,
    ) -> list[str]:
        """
        Validate resource_types parameter.
        
        Args:
            resource_types: The value to validate
            field_name: Name of the field (for error messages)
            required: Whether the field is required
        
        Returns:
            Validated list of resource types
        
        Raises:
            ValidationError: If validation fails
        """
        if resource_types is None:
            if required:
                raise ValidationError(field_name, "Field is required")
            return []
        
        if not isinstance(resource_types, list):
            raise ValidationError(
                field_name,
                f"Must be an array, got {type(resource_types).__name__}",
                resource_types,
            )
        
        if not resource_types:
            raise ValidationError(field_name, "Cannot be empty")
        
        if len(resource_types) > cls.MAX_RESOURCE_TYPES:
            raise ValidationError(
                field_name,
                f"Too many resource types (max: {cls.MAX_RESOURCE_TYPES})",
                len(resource_types),
            )
        
        # Check for duplicates
        if len(resource_types) != len(set(resource_types)):
            raise ValidationError(field_name, "Contains duplicate values")
        
        # Validate each resource type
        invalid_types = []
        for rt in resource_types:
            if not isinstance(rt, str):
                raise ValidationError(
                    field_name,
                    f"All items must be strings, got {type(rt).__name__}",
                )
            
            if rt not in cls.VALID_RESOURCE_TYPES:
                invalid_types.append(rt)
        
        if invalid_types:
            raise ValidationError(
                field_name,
                f"Invalid resource types: {invalid_types}. "
                f"Valid types: {sorted(cls.VALID_RESOURCE_TYPES)}",
                invalid_types,
            )
        
        return resource_types
    
    @classmethod
    def validate_resource_arns(
        cls,
        resource_arns: Any,
        field_name: str = "resource_arns",
        required: bool = True,
    ) -> list[str]:
        """
        Validate resource_arns parameter.
        
        Args:
            resource_arns: The value to validate
            field_name: Name of the field (for error messages)
            required: Whether the field is required
        
        Returns:
            Validated list of ARNs
        
        Raises:
            ValidationError: If validation fails
        """
        if resource_arns is None:
            if required:
                raise ValidationError(field_name, "Field is required")
            return []
        
        if not isinstance(resource_arns, list):
            raise ValidationError(
                field_name,
                f"Must be an array, got {type(resource_arns).__name__}",
            )
        
        if not resource_arns:
            raise ValidationError(field_name, "Cannot be empty")
        
        if len(resource_arns) > cls.MAX_RESOURCE_ARNS:
            raise ValidationError(
                field_name,
                f"Too many ARNs (max: {cls.MAX_RESOURCE_ARNS})",
                len(resource_arns),
            )
        
        # Validate each ARN
        invalid_arns = []
        for arn in resource_arns:
            if not isinstance(arn, str):
                raise ValidationError(
                    field_name,
                    f"All ARNs must be strings, got {type(arn).__name__}",
                )
            
            # Sanitize the ARN (includes injection detection)
            try:
                arn = cls.sanitize_string(arn, cls.MAX_STRING_LENGTH, field_name)
            except (ValidationError, SecurityViolationError) as e:
                if isinstance(e, ValidationError):
                    raise ValidationError(
                        field_name,
                        f"ARN sanitization failed: {e.message}",
                        arn,
                    )
                # Re-raise SecurityViolationError as-is
                raise
            
            if len(arn) > cls.MAX_STRING_LENGTH:
                raise ValidationError(
                    field_name,
                    f"ARN too long (max: {cls.MAX_STRING_LENGTH} chars)",
                    len(arn),
                )
            
            if not cls.ARN_PATTERN.match(arn):
                invalid_arns.append(arn)
        
        if invalid_arns:
            raise ValidationError(
                field_name,
                f"Invalid ARN format. ARNs must match pattern: "
                f"arn:aws:service:region:account:resource. "
                f"Invalid ARNs: {invalid_arns[:3]}{'...' if len(invalid_arns) > 3 else ''}",
                invalid_arns,
            )
        
        return resource_arns
    
    @classmethod
    def validate_regions(
        cls,
        regions: Any,
        field_name: str = "regions",
        required: bool = False,
    ) -> Optional[list[str]]:
        """
        Validate regions parameter.
        
        Args:
            regions: The value to validate
            field_name: Name of the field (for error messages)
            required: Whether the field is required
        
        Returns:
            Validated list of regions or None
        
        Raises:
            ValidationError: If validation fails
        """
        if regions is None:
            if required:
                raise ValidationError(field_name, "Field is required")
            return None
        
        if not isinstance(regions, list):
            raise ValidationError(
                field_name,
                f"Must be an array, got {type(regions).__name__}",
            )
        
        if len(regions) > cls.MAX_REGIONS:
            raise ValidationError(
                field_name,
                f"Too many regions (max: {cls.MAX_REGIONS})",
                len(regions),
            )
        
        # Validate each region
        invalid_regions = []
        for region in regions:
            if not isinstance(region, str):
                raise ValidationError(
                    field_name,
                    f"All regions must be strings, got {type(region).__name__}",
                )
            
            if region not in cls.VALID_AWS_REGIONS:
                invalid_regions.append(region)
        
        if invalid_regions:
            raise ValidationError(
                field_name,
                f"Invalid AWS regions: {invalid_regions}. "
                f"Valid regions include: {sorted(list(cls.VALID_AWS_REGIONS)[:5])}...",
                invalid_regions,
            )
        
        return regions
    
    @classmethod
    def validate_filters(
        cls,
        filters: Any,
        field_name: str = "filters",
        required: bool = False,
    ) -> Optional[dict]:
        """
        Validate filters parameter.
        
        Args:
            filters: The value to validate
            field_name: Name of the field (for error messages)
            required: Whether the field is required
        
        Returns:
            Validated filters dict or None
        
        Raises:
            ValidationError: If validation fails
        """
        if filters is None:
            if required:
                raise ValidationError(field_name, "Field is required")
            return None
        
        if not isinstance(filters, dict):
            raise ValidationError(
                field_name,
                f"Must be an object, got {type(filters).__name__}",
            )
        
        # Validate allowed filter keys
        allowed_keys = {"region", "account_id"}
        invalid_keys = set(filters.keys()) - allowed_keys
        if invalid_keys:
            raise ValidationError(
                field_name,
                f"Invalid filter keys: {invalid_keys}. "
                f"Allowed keys: {sorted(allowed_keys)}",
                invalid_keys,
            )
        
        # Validate region filter
        if "region" in filters:
            region = filters["region"]
            if not isinstance(region, str):
                raise ValidationError(
                    f"{field_name}.region",
                    f"Must be a string, got {type(region).__name__}",
                )
            
            if region not in cls.VALID_AWS_REGIONS:
                raise ValidationError(
                    f"{field_name}.region",
                    f"Invalid AWS region: {region}",
                    region,
                )
        
        # Validate account_id filter
        if "account_id" in filters:
            account_id = filters["account_id"]
            if not isinstance(account_id, str):
                raise ValidationError(
                    f"{field_name}.account_id",
                    f"Must be a string, got {type(account_id).__name__}",
                )
            
            if not re.match(r'^\d{12}$', account_id):
                raise ValidationError(
                    f"{field_name}.account_id",
                    "Must be a 12-digit AWS account ID",
                    account_id,
                )
        
        return filters
    
    @classmethod
    def validate_severity(
        cls,
        severity: Any,
        field_name: str = "severity",
        required: bool = False,
        default: str = "all",
    ) -> str:
        """
        Validate severity parameter.
        
        Args:
            severity: The value to validate
            field_name: Name of the field (for error messages)
            required: Whether the field is required
            default: Default value if not provided
        
        Returns:
            Validated severity value
        
        Raises:
            ValidationError: If validation fails
        """
        if severity is None:
            if required:
                raise ValidationError(field_name, "Field is required")
            return default
        
        # Handle case where AI agent wraps value in array (common mistake)
        # Extract first element if it's a single-element array of strings
        if isinstance(severity, list):
            if len(severity) == 1 and isinstance(severity[0], str):
                logger.debug(f"Auto-unwrapping single-element array for {field_name}: {severity}")
                severity = severity[0]
            else:
                raise ValidationError(
                    field_name,
                    f"Must be a string, got {type(severity).__name__}. "
                    f"Valid values: {sorted(cls.VALID_SEVERITIES)}",
                )
        
        if not isinstance(severity, str):
            raise ValidationError(
                field_name,
                f"Must be a string, got {type(severity).__name__}",
            )
        
        if severity not in cls.VALID_SEVERITIES:
            raise ValidationError(
                field_name,
                f"Invalid severity: {severity}. "
                f"Valid values: {sorted(cls.VALID_SEVERITIES)}",
                severity,
            )
        
        return severity
    
    @classmethod
    def validate_min_cost_threshold(
        cls,
        min_cost_threshold: Any,
        field_name: str = "min_cost_threshold",
        required: bool = False,
    ) -> Optional[float]:
        """
        Validate min_cost_threshold parameter.
        
        Args:
            min_cost_threshold: The value to validate
            field_name: Name of the field (for error messages)
            required: Whether the field is required
        
        Returns:
            Validated cost threshold or None
        
        Raises:
            ValidationError: If validation fails
        """
        if min_cost_threshold is None:
            if required:
                raise ValidationError(field_name, "Field is required")
            return None
        
        if not isinstance(min_cost_threshold, (int, float)):
            raise ValidationError(
                field_name,
                f"Must be a number, got {type(min_cost_threshold).__name__}",
            )
        
        if min_cost_threshold < 0:
            raise ValidationError(
                field_name,
                "Must be non-negative",
                min_cost_threshold,
            )
        
        if min_cost_threshold > 1_000_000:
            raise ValidationError(
                field_name,
                "Unreasonably large threshold (max: $1,000,000)",
                min_cost_threshold,
            )
        
        return float(min_cost_threshold)
    
    @classmethod
    def validate_time_period(
        cls,
        time_period: Any,
        field_name: str = "time_period",
        required: bool = False,
    ) -> Optional[dict]:
        """
        Validate time_period parameter.
        
        Args:
            time_period: The value to validate
            field_name: Name of the field (for error messages)
            required: Whether the field is required
        
        Returns:
            Validated time period dict or None
        
        Raises:
            ValidationError: If validation fails
        """
        if time_period is None:
            if required:
                raise ValidationError(field_name, "Field is required")
            return None
        
        if not isinstance(time_period, dict):
            raise ValidationError(
                field_name,
                f"Must be an object, got {type(time_period).__name__}",
            )
        
        # Validate required keys
        required_keys = {"Start", "End"}
        missing_keys = required_keys - set(time_period.keys())
        if missing_keys:
            raise ValidationError(
                field_name,
                f"Missing required keys: {sorted(missing_keys)}",
            )
        
        # Validate Start date
        start = time_period["Start"]
        if not isinstance(start, str):
            raise ValidationError(
                f"{field_name}.Start",
                f"Must be a string, got {type(start).__name__}",
            )
        
        if not cls.DATE_PATTERN.match(start):
            raise ValidationError(
                f"{field_name}.Start",
                "Must be in YYYY-MM-DD format",
                start,
            )
        
        try:
            start_date = datetime.strptime(start, "%Y-%m-%d")
        except ValueError as e:
            raise ValidationError(
                f"{field_name}.Start",
                f"Invalid date: {e}",
                start,
            )
        
        # Validate End date
        end = time_period["End"]
        if not isinstance(end, str):
            raise ValidationError(
                f"{field_name}.End",
                f"Must be a string, got {type(end).__name__}",
            )
        
        if not cls.DATE_PATTERN.match(end):
            raise ValidationError(
                f"{field_name}.End",
                "Must be in YYYY-MM-DD format",
                end,
            )
        
        try:
            end_date = datetime.strptime(end, "%Y-%m-%d")
        except ValueError as e:
            raise ValidationError(
                f"{field_name}.End",
                f"Invalid date: {e}",
                end,
            )
        
        # Validate date range
        if end_date < start_date:
            raise ValidationError(
                field_name,
                "End date must be after Start date",
                {"Start": start, "End": end},
            )
        
        # Validate range is not too large (max 1 year)
        days_diff = (end_date - start_date).days
        if days_diff > 365:
            raise ValidationError(
                field_name,
                f"Date range too large (max: 365 days, got: {days_diff} days)",
                days_diff,
            )
        
        return time_period
    
    @classmethod
    def validate_group_by(
        cls,
        group_by: Any,
        field_name: str = "group_by",
        required: bool = False,
        valid_options: Optional[set[str]] = None,
    ) -> Optional[str]:
        """
        Validate group_by parameter.
        
        Args:
            group_by: The value to validate
            field_name: Name of the field (for error messages)
            required: Whether the field is required
            valid_options: Set of valid options (defaults to VALID_GROUP_BY_OPTIONS)
        
        Returns:
            Validated group_by value or None
        
        Raises:
            ValidationError: If validation fails
        """
        if group_by is None:
            if required:
                raise ValidationError(field_name, "Field is required")
            return None
        
        valid_opts = valid_options or cls.VALID_GROUP_BY_OPTIONS
        
        # Handle case where AI agent wraps value in array (common mistake)
        # Extract first element if it's a single-element array of strings
        if isinstance(group_by, list):
            if len(group_by) == 1 and isinstance(group_by[0], str):
                logger.debug(f"Auto-unwrapping single-element array for {field_name}: {group_by}")
                group_by = group_by[0]
            else:
                raise ValidationError(
                    field_name,
                    f"Must be a string, got {type(group_by).__name__}. "
                    f"Valid values: {sorted(valid_opts)}",
                )
        
        if not isinstance(group_by, str):
            raise ValidationError(
                field_name,
                f"Must be a string, got {type(group_by).__name__}",
            )
        
        if group_by not in valid_opts:
            raise ValidationError(
                field_name,
                f"Invalid value: {group_by}. Valid values: {sorted(valid_opts)}",
                group_by,
            )
        
        return group_by
    
    @classmethod
    def validate_format(
        cls,
        format: Any,
        field_name: str = "format",
        required: bool = False,
        default: str = "json",
    ) -> str:
        """
        Validate format parameter.
        
        Args:
            format: The value to validate
            field_name: Name of the field (for error messages)
            required: Whether the field is required
            default: Default value if not provided
        
        Returns:
            Validated format value
        
        Raises:
            ValidationError: If validation fails
        """
        if format is None:
            if required:
                raise ValidationError(field_name, "Field is required")
            return default
        
        if not isinstance(format, str):
            raise ValidationError(
                field_name,
                f"Must be a string, got {type(format).__name__}",
            )
        
        if format not in cls.VALID_REPORT_FORMATS:
            raise ValidationError(
                field_name,
                f"Invalid format: {format}. "
                f"Valid formats: {sorted(cls.VALID_REPORT_FORMATS)}",
                format,
            )
        
        return format
    
    @classmethod
    def validate_boolean(
        cls,
        value: Any,
        field_name: str,
        required: bool = False,
        default: bool = True,
    ) -> bool:
        """
        Validate boolean parameter.
        
        Args:
            value: The value to validate
            field_name: Name of the field (for error messages)
            required: Whether the field is required
            default: Default value if not provided
        
        Returns:
            Validated boolean value
        
        Raises:
            ValidationError: If validation fails
        """
        if value is None:
            if required:
                raise ValidationError(field_name, "Field is required")
            return default
        
        if not isinstance(value, bool):
            raise ValidationError(
                field_name,
                f"Must be a boolean, got {type(value).__name__}",
            )
        
        return value
    
    @classmethod
    def validate_integer(
        cls,
        value: Any,
        field_name: str,
        required: bool = False,
        default: Optional[int] = None,
        minimum: Optional[int] = None,
        maximum: Optional[int] = None,
    ) -> Optional[int]:
        """
        Validate integer parameter.
        
        Args:
            value: The value to validate
            field_name: Name of the field (for error messages)
            required: Whether the field is required
            default: Default value if not provided
            minimum: Minimum allowed value (inclusive)
            maximum: Maximum allowed value (inclusive)
        
        Returns:
            Validated integer value or None
        
        Raises:
            ValidationError: If validation fails
        """
        if value is None:
            if required:
                raise ValidationError(field_name, "Field is required")
            return default
        
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValidationError(
                field_name,
                f"Must be an integer, got {type(value).__name__}",
            )
        
        if minimum is not None and value < minimum:
            raise ValidationError(
                field_name,
                f"Must be at least {minimum}, got {value}",
                value,
            )
        
        if maximum is not None and value > maximum:
            raise ValidationError(
                field_name,
                f"Must be at most {maximum}, got {value}",
                value,
            )
        
        return value
    
    @classmethod
    def validate_string(
        cls,
        value: Any,
        field_name: str,
        required: bool = False,
        max_length: Optional[int] = None,
        pattern: Optional[re.Pattern] = None,
    ) -> Optional[str]:
        """
        Validate string parameter with sanitization.
        
        Args:
            value: The value to validate
            field_name: Name of the field (for error messages)
            required: Whether the field is required
            max_length: Maximum allowed length
            pattern: Regex pattern to match
        
        Returns:
            Validated and sanitized string value or None
        
        Raises:
            ValidationError: If validation fails
            SecurityViolationError: If injection attempt is detected
        """
        if value is None:
            if required:
                raise ValidationError(field_name, "Field is required")
            return None
        
        if not isinstance(value, str):
            raise ValidationError(
                field_name,
                f"Must be a string, got {type(value).__name__}",
            )
        
        # Sanitize the string first (includes injection detection)
        try:
            value = cls.sanitize_string(value, max_length or cls.MAX_STRING_LENGTH, field_name)
        except (ValidationError, SecurityViolationError) as e:
            # Re-raise with proper field name if not already set
            if isinstance(e, ValidationError) and e.field != field_name:
                raise ValidationError(field_name, e.message, e.value)
            raise
        
        if max_length is not None and len(value) > max_length:
            raise ValidationError(
                field_name,
                f"Too long (max: {max_length} chars, got: {len(value)})",
                len(value),
            )
        
        if pattern is not None and not pattern.match(value):
            raise ValidationError(
                field_name,
                f"Does not match required pattern",
                value,
            )
        
        return value
