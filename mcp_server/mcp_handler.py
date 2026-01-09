# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""MCP Protocol Handler for FinOps Tag Compliance Server.

This module implements the Model Context Protocol (MCP) handler that exposes
all 8 compliance tools to AI assistants like Claude.

Requirements: 14.5, 15.3, 15.4, 15.5, 16.4
"""

import json
import logging
from datetime import datetime
from typing import Any, Callable, Optional
from pydantic import BaseModel

from .models import (
    ComplianceResult,
    UntaggedResourcesResult,
    ValidateResourceTagsResult,
    CostAttributionGapResult,
    BudgetExhaustedResponse,
)
from .models.audit import AuditStatus
from .models.loop_detection import LoopDetectedResponse
from .tools import (
    check_tag_compliance,
    find_untagged_resources,
    validate_resource_tags,
    get_cost_attribution_gap,
    suggest_tags,
    get_tagging_policy,
    generate_compliance_report,
    get_violation_history,
    SuggestTagsResult,
    GetTaggingPolicyResult,
    GenerateComplianceReportResult,
    GetViolationHistoryResult,
)
from .services import (
    PolicyService,
    ComplianceService,
    AuditService,
    HistoryService,
    get_security_service,
)
from .clients.aws_client import AWSClient
from .clients.cache import RedisCache
from .middleware.budget_middleware import (
    BudgetTracker,
    BudgetExhaustedError,
    get_budget_tracker,
)
from .utils.correlation import get_correlation_id
from .utils.loop_detection import (
    LoopDetector,
    LoopDetectedError,
    get_loop_detector,
)
from .utils.input_validation import InputValidator, ValidationError, SecurityViolationError

logger = logging.getLogger(__name__)


class MCPToolDefinition(BaseModel):
    """Definition of an MCP tool."""
    name: str
    description: str
    input_schema: dict


class MCPToolResult(BaseModel):
    """Result from an MCP tool invocation."""
    content: list[dict]
    is_error: bool = False


class MCPHandler:
    """
    MCP Protocol Handler for the FinOps Tag Compliance Server.
    
    This handler manages the registration and invocation of all 8 MCP tools:
    1. check_tag_compliance - Scan resources and return compliance score
    2. find_untagged_resources - Find resources missing tags
    3. validate_resource_tags - Validate specific resources by ARN
    4. get_cost_attribution_gap - Calculate financial impact of tagging gaps
    5. suggest_tags - Suggest tag values for a resource
    6. get_tagging_policy - Return the policy configuration
    7. generate_compliance_report - Generate formatted reports
    8. get_violation_history - Return historical compliance data
    
    Requirements: 14.5
    """
    
    def __init__(
        self,
        aws_client: Optional[AWSClient] = None,
        policy_service: Optional[PolicyService] = None,
        compliance_service: Optional[ComplianceService] = None,
        redis_cache: Optional[RedisCache] = None,
        audit_service: Optional[AuditService] = None,
        history_service: Optional["HistoryService"] = None,
    ):
        """
        Initialize the MCP handler with required services.
        
        Args:
            aws_client: AWSClient for AWS API calls
            policy_service: PolicyService for policy management
            compliance_service: ComplianceService for compliance checks
            redis_cache: RedisCache for caching
            audit_service: AuditService for audit logging
            history_service: HistoryService for storing compliance history
        """
        self.aws_client = aws_client
        self.policy_service = policy_service
        self.compliance_service = compliance_service
        self.redis_cache = redis_cache
        self.audit_service = audit_service
        self.history_service = history_service
        
        # Register all tools
        self._tools: dict[str, Callable] = {}
        self._tool_definitions: dict[str, MCPToolDefinition] = {}
        self._register_tools()
    
    def _register_tools(self) -> None:
        """Register all 8 MCP tools with their definitions."""
        
        # Tool 1: check_tag_compliance
        self._register_tool(
            name="check_tag_compliance",
            handler=self._handle_check_tag_compliance,
            description=(
                "Check tag compliance for AWS resources. Scans specified resource types "
                "and validates them against the organization's tagging policy. Returns "
                "a compliance score along with detailed violation information. "
                "Use 'all' to scan all tagged resources including Bedrock, OpenSearch, etc."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "resource_types": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "all",
                                "ec2:instance",
                                "rds:db",
                                "s3:bucket",
                                "lambda:function",
                                "ecs:service",
                                "opensearch:domain",
                            ],
                            "minLength": 1,
                            "maxLength": 50,
                        },
                        "minItems": 1,
                        "maxItems": 10,
                        "uniqueItems": True,
                        "description": (
                            "List of resource types to check. "
                            "Use 'all' to scan all tagged resources (Bedrock, OpenSearch, etc.). "
                            "Valid types: all, ec2:instance, rds:db, s3:bucket, lambda:function, ecs:service, opensearch:domain. "
                            "Maximum 10 types per request."
                        ),
                    },
                    "filters": {
                        "type": "object",
                        "description": "Optional filters for region, account_id",
                        "properties": {
                            "region": {
                                "type": "string",
                                "pattern": "^[a-z]{2}-[a-z]+-\\d{1}$",
                                "minLength": 9,
                                "maxLength": 15,
                                "description": "AWS region code (e.g., us-east-1)",
                            },
                            "account_id": {
                                "type": "string",
                                "pattern": "^\\d{12}$",
                                "minLength": 12,
                                "maxLength": 12,
                                "description": "12-digit AWS account ID",
                            },
                        },
                        "additionalProperties": False,
                        "maxProperties": 2,
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["all", "errors_only", "warnings_only"],
                        "default": "all",
                        "description": "Filter results by severity level",
                    },
                    "store_snapshot": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "If true, store this compliance result in the history database "
                            "for trend tracking. Use this for full compliance audits, not "
                            "ad-hoc queries. Defaults to false to prevent partial scans "
                            "from affecting historical averages."
                        ),
                    },
                    "force_refresh": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "If true, bypass cache and force a fresh scan from AWS. "
                            "Use this when you need real-time data or suspect the cache "
                            "is stale. Defaults to false to use cached results when available."
                        ),
                    },
                },
                "required": ["resource_types"],
                "additionalProperties": False,
            },
        )
        
        # Tool 2: find_untagged_resources
        self._register_tool(
            name="find_untagged_resources",
            handler=self._handle_find_untagged_resources,
            description=(
                "Find resources with no tags or missing required tags. "
                "Returns resource details and age to help prioritize remediation. "
                "Cost estimates are only included when explicitly requested via include_costs=true. "
                "Use 'all' to scan all tagged resources including Bedrock, OpenSearch, etc."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "resource_types": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "all",
                                "ec2:instance",
                                "rds:db",
                                "s3:bucket",
                                "lambda:function",
                                "ecs:service",
                                "opensearch:domain",
                            ],
                            "minLength": 1,
                            "maxLength": 50,
                        },
                        "minItems": 1,
                        "maxItems": 10,
                        "uniqueItems": True,
                        "description": "List of resource types to search. Use 'all' for all tagged resources. Maximum 10 types per request.",
                    },
                    "regions": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "pattern": "^[a-z]{2}-[a-z]+-\\d{1}$",
                            "minLength": 9,
                            "maxLength": 15,
                        },
                        "minItems": 1,
                        "maxItems": 20,
                        "uniqueItems": True,
                        "description": "Optional list of AWS regions to search. Maximum 20 regions per request.",
                    },
                    "include_costs": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Whether to include cost estimates. Only set to true when user explicitly "
                            "asks about costs or cost impact. EC2/RDS costs are accurate (from Cost Explorer). "
                            "S3/Lambda/ECS costs are rough estimates (service total / resource count)."
                        ),
                    },
                    "min_cost_threshold": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1000000,
                        "description": (
                            "Optional minimum monthly cost threshold in USD (0-1,000,000). "
                            "Implies include_costs=true."
                        ),
                    },
                },
                "required": ["resource_types"],
                "additionalProperties": False,
            },
        )
        
        # Tool 3: validate_resource_tags
        self._register_tool(
            name="validate_resource_tags",
            handler=self._handle_validate_resource_tags,
            description=(
                "Validate specific resources against the tagging policy. "
                "Returns detailed violation information including missing tags, "
                "invalid values, and format violations."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "resource_arns": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "pattern": "^arn:aws:[a-z0-9\\-]+:[a-z0-9\\-]*(:\\d{12}|::)[a-z0-9\\-/:._]+$",
                            "minLength": 20,
                            "maxLength": 1024,
                        },
                        "minItems": 1,
                        "maxItems": 100,
                        "uniqueItems": True,
                        "description": "List of AWS resource ARNs to validate. Maximum 100 ARNs per request.",
                    },
                },
                "required": ["resource_arns"],
                "additionalProperties": False,
            },
        )
        
        # Tool 4: get_cost_attribution_gap
        self._register_tool(
            name="get_cost_attribution_gap",
            handler=self._handle_get_cost_attribution_gap,
            description=(
                "Calculate the cost attribution gap - the financial impact of tagging gaps. "
                "Shows how much cloud spend cannot be allocated to teams/projects due to "
                "missing or invalid resource tags. "
                "Use 'all' to analyze all tagged resources including Bedrock, OpenSearch, etc."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "resource_types": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "all",
                                "ec2:instance",
                                "rds:db",
                                "s3:bucket",
                                "lambda:function",
                                "ecs:service",
                                "opensearch:domain",
                            ],
                            "minLength": 1,
                            "maxLength": 50,
                        },
                        "minItems": 1,
                        "maxItems": 10,
                        "uniqueItems": True,
                        "description": "List of resource types to analyze. Use 'all' for all tagged resources. Maximum 10 types per request.",
                    },
                    "time_period": {
                        "type": "object",
                        "description": "Time period for cost analysis (max 365 days)",
                        "properties": {
                            "Start": {
                                "type": "string",
                                "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
                                "minLength": 10,
                                "maxLength": 10,
                                "description": "Start date in YYYY-MM-DD format",
                            },
                            "End": {
                                "type": "string",
                                "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
                                "minLength": 10,
                                "maxLength": 10,
                                "description": "End date in YYYY-MM-DD format (must be after Start)",
                            },
                        },
                        "required": ["Start", "End"],
                        "additionalProperties": False,
                    },
                    "group_by": {
                        "type": "string",
                        "enum": ["resource_type", "region", "account"],
                        "description": "Optional grouping dimension for breakdown",
                    },
                    "filters": {
                        "type": "object",
                        "description": "Optional filters for region or account_id",
                        "properties": {
                            "region": {
                                "type": "string",
                                "pattern": "^[a-z]{2}-[a-z]+-\\d{1}$",
                                "minLength": 9,
                                "maxLength": 15,
                                "description": "AWS region code",
                            },
                            "account_id": {
                                "type": "string",
                                "pattern": "^\\d{12}$",
                                "minLength": 12,
                                "maxLength": 12,
                                "description": "12-digit AWS account ID",
                            },
                        },
                        "additionalProperties": False,
                        "maxProperties": 2,
                    },
                },
                "required": ["resource_types"],
                "additionalProperties": False,
            },
        )
        
        # Tool 5: suggest_tags
        self._register_tool(
            name="suggest_tags",
            handler=self._handle_suggest_tags,
            description=(
                "Suggest appropriate tags for an AWS resource. Analyzes patterns "
                "like VPC naming, IAM roles, and similar resources to recommend "
                "tag values with confidence scores and reasoning."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "resource_arn": {
                        "type": "string",
                        "pattern": "^arn:aws:[a-z0-9\\-]+:[a-z0-9\\-]*(:\\d{12}|::)[a-z0-9\\-/:._]+$",
                        "minLength": 20,
                        "maxLength": 1024,
                        "description": "AWS ARN of the resource to suggest tags for",
                    },
                },
                "required": ["resource_arn"],
                "additionalProperties": False,
            },
        )
        
        # Tool 6: get_tagging_policy
        self._register_tool(
            name="get_tagging_policy",
            handler=self._handle_get_tagging_policy,
            description=(
                "Retrieve the complete tagging policy configuration. "
                "Returns required tags, optional tags, validation rules, "
                "and which resource types each tag applies to."
            ),
            input_schema={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        )
        
        # Tool 7: generate_compliance_report
        self._register_tool(
            name="generate_compliance_report",
            handler=self._handle_generate_compliance_report,
            description=(
                "Generate a comprehensive compliance report. "
                "Includes overall compliance summary, top violations ranked by "
                "count and cost impact, and actionable recommendations. "
                "Use 'all' to include all tagged resources including Bedrock, OpenSearch, etc."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "resource_types": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "all",
                                "ec2:instance",
                                "rds:db",
                                "s3:bucket",
                                "lambda:function",
                                "ecs:service",
                                "opensearch:domain",
                            ],
                            "minLength": 1,
                            "maxLength": 50,
                        },
                        "minItems": 1,
                        "maxItems": 10,
                        "uniqueItems": True,
                        "description": "List of resource types to include in the report. Use 'all' for all tagged resources. Maximum 10 types per request.",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["json", "csv", "markdown"],
                        "default": "json",
                        "description": "Output format for the report",
                    },
                    "include_recommendations": {
                        "type": "boolean",
                        "default": True,
                        "description": "Whether to include actionable recommendations",
                    },
                },
                "required": ["resource_types"],
                "additionalProperties": False,
            },
        )
        
        # Tool 8: get_violation_history
        self._register_tool(
            name="get_violation_history",
            handler=self._handle_get_violation_history,
            description=(
                "Retrieve historical compliance data with trend analysis. "
                "Shows how compliance has changed over time to track progress "
                "and measure remediation effectiveness."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "days_back": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 90,
                        "default": 30,
                        "description": "Number of days to look back (1-90)",
                    },
                    "group_by": {
                        "type": "string",
                        "enum": ["day", "week", "month"],
                        "default": "day",
                        "description": "How to group the historical data",
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
        )
        
        logger.info(f"Registered {len(self._tools)} MCP tools")
    
    def _register_tool(
        self,
        name: str,
        handler: Callable,
        description: str,
        input_schema: dict,
    ) -> None:
        """Register a single MCP tool."""
        self._tools[name] = handler
        self._tool_definitions[name] = MCPToolDefinition(
            name=name,
            description=description,
            input_schema=input_schema,
        )
    
    def get_tool_definitions(self) -> list[dict]:
        """
        Get all tool definitions for MCP protocol.
        
        Returns:
            List of tool definitions with name, description, and input schema
        """
        return [
            {
                "name": defn.name,
                "description": defn.description,
                "inputSchema": defn.input_schema,
            }
            for defn in self._tool_definitions.values()
        ]
    
    def _validate_tool_inputs(self, tool_name: str, arguments: dict) -> None:
        """
        Validate tool inputs against their schemas with detailed field-level feedback.
        
        Args:
            tool_name: Name of the tool being invoked
            arguments: Tool arguments to validate
        
        Raises:
            ValidationError: If validation fails with detailed field-level error
        
        Requirements: 16.3
        """
        try:
            if tool_name == "check_tag_compliance":
                InputValidator.validate_resource_types(
                    arguments.get("resource_types"),
                    required=True,
                )
                InputValidator.validate_filters(
                    arguments.get("filters"),
                    required=False,
                )
                InputValidator.validate_severity(
                    arguments.get("severity", "all"),
                    required=False,
                )
                InputValidator.validate_boolean(
                    arguments.get("store_snapshot", False),
                    field_name="store_snapshot",
                    required=False,
                )
                InputValidator.validate_boolean(
                    arguments.get("force_refresh", False),
                    field_name="force_refresh",
                    required=False,
                )
            
            elif tool_name == "find_untagged_resources":
                InputValidator.validate_resource_types(
                    arguments.get("resource_types"),
                    required=True,
                )
                InputValidator.validate_regions(
                    arguments.get("regions"),
                    required=False,
                )
                InputValidator.validate_boolean(
                    arguments.get("include_costs", False),
                    field_name="include_costs",
                    required=False,
                )
                InputValidator.validate_min_cost_threshold(
                    arguments.get("min_cost_threshold"),
                    required=False,
                )
            
            elif tool_name == "validate_resource_tags":
                InputValidator.validate_resource_arns(
                    arguments.get("resource_arns"),
                    required=True,
                )
            
            elif tool_name == "get_cost_attribution_gap":
                InputValidator.validate_resource_types(
                    arguments.get("resource_types"),
                    required=True,
                )
                InputValidator.validate_time_period(
                    arguments.get("time_period"),
                    required=False,
                )
                InputValidator.validate_group_by(
                    arguments.get("group_by"),
                    required=False,
                    valid_options=InputValidator.VALID_GROUP_BY_OPTIONS,
                )
                InputValidator.validate_filters(
                    arguments.get("filters"),
                    required=False,
                )
            
            elif tool_name == "suggest_tags":
                InputValidator.validate_string(
                    arguments.get("resource_arn"),
                    field_name="resource_arn",
                    required=True,
                    max_length=InputValidator.MAX_STRING_LENGTH,
                    pattern=InputValidator.ARN_PATTERN,
                )
            
            elif tool_name == "get_tagging_policy":
                # No parameters to validate
                pass
            
            elif tool_name == "generate_compliance_report":
                InputValidator.validate_resource_types(
                    arguments.get("resource_types"),
                    required=True,
                )
                InputValidator.validate_format(
                    arguments.get("format", "json"),
                    required=False,
                )
                InputValidator.validate_boolean(
                    arguments.get("include_recommendations", True),
                    field_name="include_recommendations",
                    required=False,
                )
            
            elif tool_name == "get_violation_history":
                InputValidator.validate_integer(
                    arguments.get("days_back", 30),
                    field_name="days_back",
                    required=False,
                    minimum=1,
                    maximum=90,
                )
                InputValidator.validate_group_by(
                    arguments.get("group_by", "day"),
                    field_name="group_by",
                    required=False,
                    valid_options=InputValidator.VALID_HISTORY_GROUP_BY,
                )
            
            logger.debug(f"Input validation passed for tool: {tool_name}")
        
        except ValidationError as e:
            # Re-raise with tool context
            logger.warning(
                f"Input validation failed for tool '{tool_name}': "
                f"field='{e.field}', message='{e.message}'"
            )
            raise
    
    async def invoke_tool(self, name: str, arguments: dict) -> MCPToolResult:
        """
        Invoke an MCP tool by name with the given arguments.
        
        Args:
            name: Name of the tool to invoke
            arguments: Tool arguments as a dictionary
        
        Returns:
            MCPToolResult with the tool output
        
        Raises:
            ValueError: If the tool name is not recognized
        
        Requirements: 14.5, 15.3, 15.4, 15.5, 16.3, 16.4
        """
        session_id = get_correlation_id()
        security_service = get_security_service()
        
        # Check if tool is registered (Requirement 16.4)
        if name not in self._tools:
            # Log unknown tool attempt for security monitoring
            logger.warning(
                f"Attempt to invoke unknown tool: {name}",
                extra={
                    "tool_name": name,
                    "session_id": session_id,
                    "correlation_id": session_id,
                }
            )
            
            # Log to security service
            if security_service:
                await security_service.log_unknown_tool_attempt(
                    tool_name=name,
                    session_id=session_id,
                    parameters=arguments,
                )
                
                # Check rate limit for unknown tool attempts (Requirement 16.4)
                is_blocked, current_count, max_attempts = await security_service.check_unknown_tool_rate_limit(
                    session_id=session_id,
                    tool_name=name,
                )
                
                if is_blocked:
                    # Rate limit exceeded - block the request
                    logger.error(
                        f"Rate limit exceeded for unknown tool attempts: "
                        f"session={session_id}, count={current_count}/{max_attempts}",
                        extra={
                            "session_id": session_id,
                            "tool_name": name,
                            "attempts": current_count,
                            "max_attempts": max_attempts,
                        }
                    )
                    
                    # Log to audit service
                    if self.audit_service:
                        self.audit_service.log_invocation(
                            tool_name=name,
                            parameters={"_rate_limited": True},
                            status=AuditStatus.FAILURE,
                            error_message=f"Rate limit exceeded: {current_count}/{max_attempts} unknown tool attempts",
                        )
                    
                    return MCPToolResult(
                        content=[{
                            "type": "text",
                            "text": json.dumps({
                                "error": "Rate limit exceeded",
                                "message": "Too many attempts to invoke unknown tools. Please verify the tool name and try again later.",
                                "details": {
                                    "attempts": current_count,
                                    "max_attempts": max_attempts,
                                    "window_seconds": security_service.window_seconds,
                                },
                            }),
                        }],
                        is_error=True,
                    )
            
            # Log to audit service
            if self.audit_service:
                self.audit_service.log_invocation(
                    tool_name=name,
                    parameters=arguments,
                    status=AuditStatus.FAILURE,
                    error_message=f"Unknown tool: {name}",
                )
            
            # Return explicit rejection (Requirement 16.4)
            return MCPToolResult(
                content=[{
                    "type": "text",
                    "text": json.dumps({
                        "error": "Unknown tool",
                        "message": f"Tool '{name}' is not registered in this MCP server.",
                        "details": "Please check the tool name and ensure it is one of the registered tools.",
                        "registered_tools": list(self._tools.keys()),
                    }),
                }],
                is_error=True,
            )
        
        # Check parameter size limits before validation (Requirement 16.3)
        try:
            InputValidator.check_parameter_size_limits(arguments, "arguments")
        except SecurityViolationError as e:
            # Log security violation
            error_message = f"Security violation ({e.violation_type}): {e.message}"
            logger.error(
                f"Security violation detected for tool '{name}': {error_message}",
                extra={
                    "tool_name": name,
                    "violation_type": e.violation_type,
                    "correlation_id": session_id,
                }
            )
            
            # Log to security service (Requirement 16.4)
            if security_service:
                await security_service.log_validation_bypass_attempt(
                    tool_name=name,
                    violation_type=e.violation_type,
                    session_id=session_id,
                )
            
            if self.audit_service:
                self.audit_service.log_invocation(
                    tool_name=name,
                    parameters={"_security_violation": e.violation_type},  # Don't log full params
                    status=AuditStatus.FAILURE,
                    error_message=error_message,
                )
            
            return MCPToolResult(
                content=[{
                    "type": "text",
                    "text": json.dumps({
                        "error": "Security violation detected",
                        "message": "Request rejected due to security policy violation",
                        "details": "The request contains parameters that exceed security limits or contain suspicious patterns.",
                    }),
                }],
                is_error=True,
            )
        
        # Validate inputs before execution (Requirement 16.3)
        try:
            self._validate_tool_inputs(name, arguments)
        except SecurityViolationError as e:
            # Log security violation (injection attempt detected during validation)
            error_message = f"Security violation ({e.violation_type}): {e.message}"
            logger.error(
                f"Security violation detected for tool '{name}': {error_message}",
                extra={
                    "tool_name": name,
                    "violation_type": e.violation_type,
                    "correlation_id": session_id,
                }
            )
            
            # Log to security service (Requirement 16.4)
            if security_service:
                await security_service.log_injection_attempt(
                    tool_name=name,
                    violation_type=e.violation_type,
                    field_name="unknown",  # Field name not available in this context
                    session_id=session_id,
                )
            
            if self.audit_service:
                self.audit_service.log_invocation(
                    tool_name=name,
                    parameters={"_security_violation": e.violation_type},  # Don't log full params
                    status=AuditStatus.FAILURE,
                    error_message=error_message,
                )
            
            return MCPToolResult(
                content=[{
                    "type": "text",
                    "text": json.dumps({
                        "error": "Security violation detected",
                        "message": "Request rejected due to security policy violation",
                        "details": "The request contains potentially malicious content or injection attempts.",
                    }),
                }],
                is_error=True,
            )
        except ValidationError as e:
            # Return detailed validation error with field-level feedback
            error_message = f"Validation error for '{e.field}': {e.message}"
            logger.warning(f"Input validation failed for tool '{name}': {error_message}")
            
            if self.audit_service:
                self.audit_service.log_invocation(
                    tool_name=name,
                    parameters=arguments,
                    status=AuditStatus.FAILURE,
                    error_message=error_message,
                )
            
            return MCPToolResult(
                content=[{
                    "type": "text",
                    "text": json.dumps({
                        "error": "Input validation failed",
                        "field": e.field,
                        "message": e.message,
                        "details": "Please check the input schema and ensure all parameters are valid.",
                    }),
                }],
                is_error=True,
            )
        
        # Check budget before executing tool (Requirement 15.3)
        budget_tracker = get_budget_tracker()
        session_id = get_correlation_id()
        
        if budget_tracker and session_id:
            try:
                success, current_count, max_calls = await budget_tracker.consume_budget(session_id)
                logger.debug(
                    f"Budget consumed for session {session_id}: "
                    f"{current_count}/{max_calls} calls"
                )
            except BudgetExhaustedError as e:
                # Return graceful degradation response (Requirement 15.5)
                logger.warning(
                    f"Budget exhausted for session {e.session_id}: "
                    f"{e.current_count}/{e.max_calls} calls"
                )
                
                # Log budget exhaustion event
                if self.audit_service:
                    self.audit_service.log_invocation(
                        tool_name=name,
                        parameters=arguments,
                        status=AuditStatus.FAILURE,
                        error_message=f"Budget exhausted: {e.current_count}/{e.max_calls}",
                    )
                
                # Create graceful degradation response
                response = BudgetExhaustedResponse.create(
                    session_id=e.session_id,
                    current_usage=e.current_count,
                    limit=e.max_calls,
                    retry_after_seconds=budget_tracker.session_ttl_seconds,
                )
                
                return MCPToolResult(
                    content=response.to_mcp_content(),
                    is_error=False,  # Not an error, graceful degradation
                )
        
        # Check for loops before executing tool (Requirement 15.4)
        loop_detector = get_loop_detector()
        
        if loop_detector and session_id:
            try:
                loop_detected, call_count = await loop_detector.record_call(
                    session_id=session_id,
                    tool_name=name,
                    parameters=arguments,
                )
                logger.debug(
                    f"Loop check for session {session_id}: "
                    f"Tool '{name}' count={call_count}/{loop_detector.max_identical_calls}"
                )
            except LoopDetectedError as e:
                # Return structured response explaining the loop (Requirement 15.4)
                logger.warning(
                    f"Loop detected for session {session_id}: "
                    f"Tool '{e.tool_name}' called {e.call_count} times "
                    f"(max: {e.max_calls}), signature={e.call_signature}"
                )
                
                # Log loop detection event with detailed information
                if self.audit_service:
                    self.audit_service.log_invocation(
                        tool_name=name,
                        parameters=arguments,
                        status=AuditStatus.FAILURE,
                        error_message=(
                            f"Loop detected: {e.call_count}/{e.max_calls} identical calls, "
                            f"signature={e.call_signature}"
                        ),
                    )
                
                # Create structured response
                response = LoopDetectedResponse.create(
                    tool_name=e.tool_name,
                    call_count=e.call_count,
                    max_calls=e.max_calls,
                )
                
                return MCPToolResult(
                    content=response.to_mcp_content(),
                    is_error=False,  # Not an error, structured message
                )
        
        handler = self._tools[name]
        
        try:
            # Invoke the tool handler
            result = await handler(arguments)
            
            # Log success
            if self.audit_service:
                self.audit_service.log_invocation(
                    tool_name=name,
                    parameters=arguments,
                    status=AuditStatus.SUCCESS,
                )
            
            return MCPToolResult(
                content=[{"type": "text", "text": json.dumps(result, default=str)}],
                is_error=False,
            )
        
        except Exception as e:
            # Sanitize error before returning to client (Requirement 16.5)
            from .utils.error_sanitization import sanitize_exception, log_error_safely
            
            # Log full error internally
            log_error_safely(
                e,
                context={
                    "tool_name": name,
                    "session_id": session_id,
                },
                logger_instance=logger,
            )
            
            # Sanitize for client response
            sanitized = sanitize_exception(e)
            
            # Log failure with sanitized message
            if self.audit_service:
                self.audit_service.log_invocation(
                    tool_name=name,
                    parameters=arguments,
                    status=AuditStatus.FAILURE,
                    error_message=sanitized.internal_message,  # Use internal message for audit
                )
            
            return MCPToolResult(
                content=[{
                    "type": "text",
                    "text": json.dumps({
                        "error": sanitized.error_code,
                        "message": sanitized.user_message,
                    }),
                }],
                is_error=True,
            )
    
    # Tool handlers
    
    async def _handle_check_tag_compliance(self, arguments: dict) -> dict:
        """Handle check_tag_compliance tool invocation."""
        if not self.compliance_service:
            raise ValueError("ComplianceService not initialized")
        
        # Only pass history_service if store_snapshot is True
        store_snapshot = arguments.get("store_snapshot", False)
        force_refresh = arguments.get("force_refresh", False)
        
        result = await check_tag_compliance(
            compliance_service=self.compliance_service,
            resource_types=arguments["resource_types"],
            filters=arguments.get("filters"),
            severity=arguments.get("severity", "all"),
            history_service=self.history_service,
            store_snapshot=store_snapshot,
            force_refresh=force_refresh,
        )
        
        return {
            "compliance_score": result.compliance_score,
            "total_resources": result.total_resources,
            "compliant_resources": result.compliant_resources,
            "violations": [
                {
                    "resource_id": v.resource_id,
                    "resource_type": v.resource_type,
                    "region": v.region,
                    "violation_type": v.violation_type.value,
                    "tag_name": v.tag_name,
                    "severity": v.severity.value,
                    "current_value": v.current_value,
                    "allowed_values": v.allowed_values,
                    "cost_impact_monthly": v.cost_impact_monthly,
                }
                for v in result.violations
            ],
            "cost_attribution_gap": result.cost_attribution_gap,
            "scan_timestamp": result.scan_timestamp.isoformat(),
            "stored_in_history": store_snapshot,
        }
    
    async def _handle_find_untagged_resources(self, arguments: dict) -> dict:
        """Handle find_untagged_resources tool invocation."""
        if not self.aws_client or not self.policy_service:
            raise ValueError("AWSClient or PolicyService not initialized")
        
        include_costs = arguments.get("include_costs", False)
        
        result = await find_untagged_resources(
            aws_client=self.aws_client,
            policy_service=self.policy_service,
            resource_types=arguments["resource_types"],
            regions=arguments.get("regions"),
            min_cost_threshold=arguments.get("min_cost_threshold"),
            include_costs=include_costs,
        )
        
        # Build resource list - only include cost fields if costs were requested
        resources = []
        for r in result.resources:
            resource_data = {
                "resource_id": r.resource_id,
                "resource_type": r.resource_type,
                "region": r.region,
                "arn": r.arn,
                "current_tags": r.current_tags,
                "missing_required_tags": r.missing_required_tags,
                "age_days": r.age_days,
            }
            # Only include cost fields if costs were requested and available
            if include_costs and r.monthly_cost_estimate is not None:
                resource_data["monthly_cost_estimate"] = r.monthly_cost_estimate
                resource_data["cost_source"] = r.cost_source
            resources.append(resource_data)
        
        response = {
            "total_untagged": result.total_untagged,
            "resources": resources,
            "scan_timestamp": result.scan_timestamp.isoformat(),
        }
        
        # Only include cost summary if costs were requested
        if include_costs:
            response["total_monthly_cost"] = result.total_monthly_cost
            if result.cost_data_note:
                response["cost_data_note"] = result.cost_data_note
        
        return response
    
    async def _handle_validate_resource_tags(self, arguments: dict) -> dict:
        """Handle validate_resource_tags tool invocation."""
        if not self.aws_client or not self.policy_service:
            raise ValueError("AWSClient or PolicyService not initialized")
        
        result = await validate_resource_tags(
            aws_client=self.aws_client,
            policy_service=self.policy_service,
            resource_arns=arguments["resource_arns"],
        )
        
        return {
            "total_resources": result.total_resources,
            "compliant_resources": result.compliant_resources,
            "non_compliant_resources": result.non_compliant_resources,
            "results": [
                {
                    "resource_arn": r.resource_arn,
                    "resource_id": r.resource_id,
                    "resource_type": r.resource_type,
                    "region": r.region,
                    "is_compliant": r.is_compliant,
                    "violations": [
                        {
                            "resource_id": v.resource_id,
                            "violation_type": v.violation_type.value,
                            "tag_name": v.tag_name,
                            "severity": v.severity.value,
                            "current_value": v.current_value,
                            "allowed_values": v.allowed_values,
                        }
                        for v in r.violations
                    ],
                    "current_tags": r.current_tags,
                }
                for r in result.results
            ],
            "validation_timestamp": result.validation_timestamp.isoformat(),
        }
    
    async def _handle_get_cost_attribution_gap(self, arguments: dict) -> dict:
        """Handle get_cost_attribution_gap tool invocation."""
        if not self.aws_client or not self.policy_service:
            raise ValueError("AWSClient or PolicyService not initialized")
        
        result = await get_cost_attribution_gap(
            aws_client=self.aws_client,
            policy_service=self.policy_service,
            resource_types=arguments["resource_types"],
            time_period=arguments.get("time_period"),
            group_by=arguments.get("group_by"),
            filters=arguments.get("filters"),
        )
        
        breakdown = None
        if result.breakdown:
            breakdown = {
                key: {
                    "total": value.total,
                    "attributable": value.attributable,
                    "gap": value.gap,
                }
                for key, value in result.breakdown.items()
            }
        
        return {
            "total_spend": result.total_spend,
            "attributable_spend": result.attributable_spend,
            "attribution_gap": result.attribution_gap,
            "attribution_gap_percentage": result.attribution_gap_percentage,
            "time_period": result.time_period,
            "breakdown": breakdown,
            "scan_timestamp": result.scan_timestamp.isoformat(),
        }
    
    async def _handle_suggest_tags(self, arguments: dict) -> dict:
        """Handle suggest_tags tool invocation."""
        if not self.aws_client or not self.policy_service:
            raise ValueError("AWSClient or PolicyService not initialized")
        
        result = await suggest_tags(
            aws_client=self.aws_client,
            policy_service=self.policy_service,
            resource_arn=arguments["resource_arn"],
        )
        
        return result.to_dict()
    
    async def _handle_get_tagging_policy(self, arguments: dict) -> dict:
        """Handle get_tagging_policy tool invocation."""
        if not self.policy_service:
            raise ValueError("PolicyService not initialized")
        
        result = await get_tagging_policy(
            policy_service=self.policy_service,
        )
        
        return result.to_dict()
    
    async def _handle_generate_compliance_report(self, arguments: dict) -> dict:
        """Handle generate_compliance_report tool invocation."""
        if not self.compliance_service:
            raise ValueError("ComplianceService not initialized")
        
        # First, run a compliance check to get the data
        compliance_result = await check_tag_compliance(
            compliance_service=self.compliance_service,
            resource_types=arguments["resource_types"],
            filters=arguments.get("filters"),
            severity="all",
            history_service=self.history_service,
        )
        
        # Get actual cost attribution gap from cost service
        # The compliance service doesn't have per-resource cost data, so we need
        # to call the cost service to get the real cost attribution gap
        if self.aws_client and self.policy_service:
            try:
                from .services.cost_service import CostService
                cost_service = CostService(
                    aws_client=self.aws_client,
                    policy_service=self.policy_service
                )
                cost_result = await cost_service.calculate_attribution_gap(
                    resource_types=arguments["resource_types"],
                    filters=arguments.get("filters"),
                )
                # Update the compliance result with the actual cost attribution gap
                compliance_result.cost_attribution_gap = cost_result.attribution_gap
                logger.info(f"Updated cost_attribution_gap from cost service: ${cost_result.attribution_gap:.2f}")
            except Exception as e:
                # Log but don't fail - report can still be generated without cost data
                logger.warning(f"Failed to get cost attribution gap: {str(e)}")
        
        # Then generate the report
        result = await generate_compliance_report(
            compliance_result=compliance_result,
            format=arguments.get("format", "json"),
            include_recommendations=arguments.get("include_recommendations", True),
        )
        
        return result.to_dict()
    
    async def _handle_get_violation_history(self, arguments: dict) -> dict:
        """Handle get_violation_history tool invocation."""
        # Use the history_service's db_path if available, otherwise use default
        db_path = "compliance_history.db"
        if self.history_service:
            db_path = self.history_service.db_path
            logger.debug(f"Using history_service db_path: {db_path}")
        else:
            logger.warning("history_service is None, using default db_path")
        
        logger.info(f"get_violation_history using db_path: {db_path}")
        
        result = await get_violation_history(
            days_back=arguments.get("days_back", 30),
            group_by=arguments.get("group_by", "day"),
            db_path=db_path,
        )
        
        return result.to_dict()
