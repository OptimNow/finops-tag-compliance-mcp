"""MCP Protocol Handler for FinOps Tag Compliance Server.

This module implements the Model Context Protocol (MCP) handler that exposes
all 8 compliance tools to AI assistants like Claude.

Requirements: 14.5
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
)
from .models.audit import AuditStatus
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
)
from .clients.aws_client import AWSClient
from .clients.cache import RedisCache

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
    ):
        """
        Initialize the MCP handler with required services.
        
        Args:
            aws_client: AWSClient for AWS API calls
            policy_service: PolicyService for policy management
            compliance_service: ComplianceService for compliance checks
            redis_cache: RedisCache for caching
            audit_service: AuditService for audit logging
        """
        self.aws_client = aws_client
        self.policy_service = policy_service
        self.compliance_service = compliance_service
        self.redis_cache = redis_cache
        self.audit_service = audit_service
        
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
                "a compliance score along with detailed violation information."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "resource_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of resource types to check. "
                            "Valid types: ec2:instance, rds:db, s3:bucket, lambda:function, ecs:service"
                        ),
                    },
                    "filters": {
                        "type": "object",
                        "description": "Optional filters for region, account_id",
                        "properties": {
                            "region": {"type": "string"},
                            "account_id": {"type": "string"},
                        },
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["all", "errors_only", "warnings_only"],
                        "default": "all",
                        "description": "Filter results by severity level",
                    },
                },
                "required": ["resource_types"],
            },
        )
        
        # Tool 2: find_untagged_resources
        self._register_tool(
            name="find_untagged_resources",
            handler=self._handle_find_untagged_resources,
            description=(
                "Find resources with no tags or missing required tags. "
                "Includes cost estimates and resource age to help prioritize remediation."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "resource_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of resource types to search",
                    },
                    "regions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of AWS regions to search",
                    },
                    "min_cost_threshold": {
                        "type": "number",
                        "description": "Optional minimum monthly cost threshold in USD",
                    },
                },
                "required": ["resource_types"],
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
                        "items": {"type": "string"},
                        "description": "List of AWS resource ARNs to validate",
                    },
                },
                "required": ["resource_arns"],
            },
        )
        
        # Tool 4: get_cost_attribution_gap
        self._register_tool(
            name="get_cost_attribution_gap",
            handler=self._handle_get_cost_attribution_gap,
            description=(
                "Calculate the cost attribution gap - the financial impact of tagging gaps. "
                "Shows how much cloud spend cannot be allocated to teams/projects due to "
                "missing or invalid resource tags."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "resource_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of resource types to analyze",
                    },
                    "time_period": {
                        "type": "object",
                        "description": "Time period for cost analysis",
                        "properties": {
                            "Start": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                            "End": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                        },
                    },
                    "group_by": {
                        "type": "string",
                        "enum": ["resource_type", "region", "account"],
                        "description": "Optional grouping dimension for breakdown",
                    },
                    "filters": {
                        "type": "object",
                        "description": "Optional filters for region or account_id",
                    },
                },
                "required": ["resource_types"],
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
                        "description": "AWS ARN of the resource to suggest tags for",
                    },
                },
                "required": ["resource_arn"],
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
            },
        )
        
        # Tool 7: generate_compliance_report
        self._register_tool(
            name="generate_compliance_report",
            handler=self._handle_generate_compliance_report,
            description=(
                "Generate a comprehensive compliance report. "
                "Includes overall compliance summary, top violations ranked by "
                "count and cost impact, and actionable recommendations."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "resource_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of resource types to include in the report",
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
        """
        if name not in self._tools:
            return MCPToolResult(
                content=[{"type": "text", "text": f"Unknown tool: {name}"}],
                is_error=True,
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
            logger.error(f"Error invoking tool {name}: {str(e)}")
            
            # Log failure
            if self.audit_service:
                self.audit_service.log_invocation(
                    tool_name=name,
                    parameters=arguments,
                    status=AuditStatus.FAILURE,
                    error_message=str(e),
                )
            
            return MCPToolResult(
                content=[{"type": "text", "text": f"Error: {str(e)}"}],
                is_error=True,
            )
    
    # Tool handlers
    
    async def _handle_check_tag_compliance(self, arguments: dict) -> dict:
        """Handle check_tag_compliance tool invocation."""
        if not self.compliance_service:
            raise ValueError("ComplianceService not initialized")
        
        result = await check_tag_compliance(
            compliance_service=self.compliance_service,
            resource_types=arguments["resource_types"],
            filters=arguments.get("filters"),
            severity=arguments.get("severity", "all"),
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
        }
    
    async def _handle_find_untagged_resources(self, arguments: dict) -> dict:
        """Handle find_untagged_resources tool invocation."""
        if not self.aws_client or not self.policy_service:
            raise ValueError("AWSClient or PolicyService not initialized")
        
        result = await find_untagged_resources(
            aws_client=self.aws_client,
            policy_service=self.policy_service,
            resource_types=arguments["resource_types"],
            regions=arguments.get("regions"),
            min_cost_threshold=arguments.get("min_cost_threshold"),
        )
        
        return {
            "total_untagged": result.total_untagged,
            "resources": [
                {
                    "resource_id": r.resource_id,
                    "resource_type": r.resource_type,
                    "region": r.region,
                    "arn": r.arn,
                    "current_tags": r.current_tags,
                    "missing_required_tags": r.missing_required_tags,
                    "monthly_cost_estimate": r.monthly_cost_estimate,
                    "age_days": r.age_days,
                }
                for r in result.resources
            ],
            "total_monthly_cost": result.total_monthly_cost,
            "scan_timestamp": result.scan_timestamp.isoformat(),
        }
    
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
        )
        
        # Then generate the report
        result = await generate_compliance_report(
            compliance_result=compliance_result,
            format=arguments.get("format", "json"),
            include_recommendations=arguments.get("include_recommendations", True),
        )
        
        return result.to_dict()
    
    async def _handle_get_violation_history(self, arguments: dict) -> dict:
        """Handle get_violation_history tool invocation."""
        result = await get_violation_history(
            days_back=arguments.get("days_back", 30),
            group_by=arguments.get("group_by", "day"),
        )
        
        return result.to_dict()
