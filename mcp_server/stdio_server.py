# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Stdio MCP server using FastMCP from the mcp Python SDK.

This module creates a standard MCP server that speaks the JSON-RPC
protocol over stdio, making it compatible with:
- Claude Desktop (claude_desktop_config.json)
- MCP Inspector (npx @modelcontextprotocol/inspector)
- Any MCP client that uses the stdio transport

It is a thin wrapper: all business logic lives in the service layer.
The ServiceContainer handles initialization and dependency wiring.

Usage::

    # Run directly (stdio transport):
    python -m mcp_server.stdio_server

    # Test with MCP Inspector:
    npx @modelcontextprotocol/inspector python -m mcp_server.stdio_server

Phase 1.9 Step 7.
"""

import asyncio
import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from .container import ServiceContainer

logger = logging.getLogger(__name__)

# Create the FastMCP server instance
mcp = FastMCP("FinOps Tag Compliance")

# Module-level container (initialized in lifespan)
_container: ServiceContainer | None = None


# ---------------------------------------------------------------------------
# Tool 1: check_tag_compliance
# ---------------------------------------------------------------------------
@mcp.tool()
async def check_tag_compliance(
    resource_types: list[str],
    filters: dict[str, str] | None = None,
    severity: str = "all",
    store_snapshot: bool = False,
    force_refresh: bool = False,
) -> str:
    """Check tag compliance for AWS resources.

    Scans specified resource types and validates them against the
    organization's tagging policy. Returns a compliance score along
    with detailed violation information.
    Use 'all' to scan all tagged resources including Bedrock, OpenSearch, etc.

    Args:
        resource_types: List of resource types to check (e.g. ["ec2:instance", "s3:bucket"] or ["all"])
        filters: Optional filters for region or account_id
        severity: Filter results by severity: "all", "errors_only", or "warnings_only"
        store_snapshot: If true, store result in history for trend tracking
        force_refresh: If true, bypass cache and force fresh scan
    """
    _ensure_initialized()
    from .tools import check_tag_compliance as _check

    result = await _check(
        compliance_service=_container.compliance_service,
        resource_types=resource_types,
        filters=filters,
        severity=severity,
        history_service=_container.history_service,
        store_snapshot=store_snapshot,
        force_refresh=force_refresh,
        multi_region_scanner=_container.multi_region_scanner,
    )

    # Try to get actual cost attribution gap from CostService
    # The compliance service doesn't fetch cost data, so we need to call CostService separately
    cost_attribution_gap = result.cost_attribution_gap
    if _container.aws_client and _container.policy_service:
        try:
            from .services.cost_service import CostService

            cost_service = CostService(
                aws_client=_container.aws_client,
                policy_service=_container.policy_service,
                multi_region_scanner=_container.multi_region_scanner,
            )
            cost_result = await cost_service.calculate_attribution_gap(
                resource_types=resource_types,
                filters=filters,
            )
            cost_attribution_gap = cost_result.attribution_gap
            logger.info(f"Cost attribution gap calculated: ${cost_attribution_gap:.2f}")
        except Exception as e:
            logger.warning(f"Failed to get cost attribution gap: {e}")

    # Build base response (common to both ComplianceResult and MultiRegionComplianceResult)
    response: dict[str, Any] = {
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
        "cost_attribution_gap": cost_attribution_gap,
        "scan_timestamp": result.scan_timestamp.isoformat(),
        "stored_in_history": store_snapshot,
    }

    # Add multi-region fields if this is a MultiRegionComplianceResult
    if hasattr(result, "region_metadata"):
        response["region_metadata"] = {
            "total_regions": result.region_metadata.total_regions,
            "successful_regions": result.region_metadata.successful_regions,
            "failed_regions": result.region_metadata.failed_regions,
            "skipped_regions": result.region_metadata.skipped_regions,
        }
        response["regional_breakdown"] = {
            region: {
                "region": summary.region,
                "total_resources": summary.total_resources,
                "compliant_resources": summary.compliant_resources,
                "compliance_score": summary.compliance_score,
                "violation_count": summary.violation_count,
                "cost_attribution_gap": summary.cost_attribution_gap,
            }
            for region, summary in result.regional_breakdown.items()
        }

    return json.dumps(response, default=str)


# ---------------------------------------------------------------------------
# Tool 2: find_untagged_resources
# ---------------------------------------------------------------------------
@mcp.tool()
async def find_untagged_resources(
    resource_types: list[str],
    regions: list[str] | None = None,
    include_costs: bool = False,
    min_cost_threshold: float | None = None,
) -> str:
    """Find resources with no tags or missing required tags.

    Returns resource details and age to help prioritize remediation.
    Cost estimates are only included when explicitly requested via include_costs=true.

    Args:
        resource_types: List of resource types to search (e.g. ["ec2:instance"] or ["all"])
        regions: Optional list of AWS regions to search
        include_costs: Whether to include cost estimates (default false)
        min_cost_threshold: Optional minimum monthly cost threshold in USD
    """
    _ensure_initialized()
    from .tools import find_untagged_resources as _find

    result = await _find(
        aws_client=_container.aws_client,
        policy_service=_container.policy_service,
        resource_types=resource_types,
        regions=regions,
        min_cost_threshold=min_cost_threshold,
        include_costs=include_costs,
        multi_region_scanner=_container.multi_region_scanner,
    )

    resources = []
    for r in result.resources:
        resource_data = {
            "resource_id": r.resource_id,
            "resource_type": r.resource_type,
            "region": r.region,
            "arn": r.arn,
            "current_tags": r.current_tags,
            "missing_required_tags": r.missing_required_tags,
        }
        if r.age_days is not None:
            resource_data["age_days"] = r.age_days
        if include_costs and r.monthly_cost_estimate is not None:
            resource_data["monthly_cost_estimate"] = r.monthly_cost_estimate
            resource_data["cost_source"] = r.cost_source
        resources.append(resource_data)

    response: dict[str, Any] = {
        "total_untagged": result.total_untagged,
        "resources": resources,
        "scan_timestamp": result.scan_timestamp.isoformat(),
    }
    if include_costs:
        response["total_monthly_cost"] = result.total_monthly_cost
        if result.cost_data_note:
            response["cost_data_note"] = result.cost_data_note

    return json.dumps(response, default=str)


# ---------------------------------------------------------------------------
# Tool 3: validate_resource_tags
# ---------------------------------------------------------------------------
@mcp.tool()
async def validate_resource_tags(
    resource_arns: list[str],
) -> str:
    """Validate specific resources against the tagging policy.

    Returns detailed violation information including missing tags,
    invalid values, and format violations.

    Args:
        resource_arns: List of AWS resource ARNs to validate (max 100)
    """
    _ensure_initialized()
    from .tools import validate_resource_tags as _validate

    result = await _validate(
        aws_client=_container.aws_client,
        policy_service=_container.policy_service,
        resource_arns=resource_arns,
        multi_region_scanner=_container.multi_region_scanner,
    )

    return json.dumps(
        {
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
        },
        default=str,
    )


# ---------------------------------------------------------------------------
# Tool 4: get_cost_attribution_gap
# ---------------------------------------------------------------------------
@mcp.tool()
async def get_cost_attribution_gap(
    resource_types: list[str],
    time_period: dict[str, str] | None = None,
    group_by: str | None = None,
    filters: dict[str, str] | None = None,
) -> str:
    """Calculate the cost attribution gap — the financial impact of tagging gaps.

    Shows how much cloud spend cannot be allocated to teams/projects due to
    missing or invalid resource tags.

    Args:
        resource_types: List of resource types to analyze (e.g. ["ec2:instance"] or ["all"])
        time_period: Time period with Start and End dates in YYYY-MM-DD format
        group_by: Optional grouping dimension: "resource_type", "region", or "account"
        filters: Optional filters for region or account_id
    """
    _ensure_initialized()
    from .tools import get_cost_attribution_gap as _gap

    result = await _gap(
        aws_client=_container.aws_client,
        policy_service=_container.policy_service,
        resource_types=resource_types,
        time_period=time_period,
        group_by=group_by,
        filters=filters,
        multi_region_scanner=_container.multi_region_scanner,
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

    return json.dumps(
        {
            "total_spend": result.total_spend,
            "attributable_spend": result.attributable_spend,
            "attribution_gap": result.attribution_gap,
            "attribution_gap_percentage": result.attribution_gap_percentage,
            "time_period": result.time_period,
            "breakdown": breakdown,
            "scan_timestamp": result.scan_timestamp.isoformat(),
        },
        default=str,
    )


# ---------------------------------------------------------------------------
# Tool 5: suggest_tags
# ---------------------------------------------------------------------------
@mcp.tool()
async def suggest_tags(
    resource_arn: str,
) -> str:
    """Suggest appropriate tags for an AWS resource.

    Analyzes patterns like VPC naming, IAM roles, and similar resources
    to recommend tag values with confidence scores and reasoning.

    Args:
        resource_arn: AWS ARN of the resource to suggest tags for
    """
    _ensure_initialized()
    from .tools import suggest_tags as _suggest

    result = await _suggest(
        aws_client=_container.aws_client,
        policy_service=_container.policy_service,
        resource_arn=resource_arn,
        multi_region_scanner=_container.multi_region_scanner,
    )

    return json.dumps(result.model_dump(mode="json"), default=str)


# ---------------------------------------------------------------------------
# Tool 6: get_tagging_policy
# ---------------------------------------------------------------------------
@mcp.tool()
async def get_tagging_policy() -> str:
    """Retrieve the complete tagging policy configuration.

    Returns required tags, optional tags, validation rules,
    and which resource types each tag applies to.
    """
    _ensure_initialized()
    from .tools import get_tagging_policy as _policy

    result = await _policy(
        policy_service=_container.policy_service,
    )

    return json.dumps(result.model_dump(mode="json"), default=str)


# ---------------------------------------------------------------------------
# Tool 7: generate_compliance_report
# ---------------------------------------------------------------------------
@mcp.tool()
async def generate_compliance_report(
    resource_types: list[str],
    format: str = "json",
    include_recommendations: bool = True,
) -> str:
    """Generate a comprehensive compliance report.

    Includes overall compliance summary, top violations ranked by
    count and cost impact, and actionable recommendations.

    Args:
        resource_types: List of resource types to include (e.g. ["ec2:instance"] or ["all"])
        format: Output format: "json", "csv", or "markdown"
        include_recommendations: Whether to include actionable recommendations
    """
    _ensure_initialized()
    from .tools import check_tag_compliance as _check
    from .tools import generate_compliance_report as _report

    compliance_result = await _check(
        compliance_service=_container.compliance_service,
        resource_types=resource_types,
        severity="all",
        history_service=_container.history_service,
        multi_region_scanner=_container.multi_region_scanner,
    )

    # Try to get actual cost attribution gap
    if _container.aws_client and _container.policy_service:
        try:
            from .services.cost_service import CostService

            cost_service = CostService(
                aws_client=_container.aws_client,
                policy_service=_container.policy_service,
            )
            cost_result = await cost_service.calculate_attribution_gap(
                resource_types=resource_types,
            )
            compliance_result.cost_attribution_gap = cost_result.attribution_gap
        except Exception as e:
            logger.warning(f"Failed to get cost attribution gap: {e}")

    result = await _report(
        compliance_result=compliance_result,
        format=format,
        include_recommendations=include_recommendations,
    )

    return json.dumps(result.model_dump(mode="json"), default=str)


# ---------------------------------------------------------------------------
# Tool 8: get_violation_history
# ---------------------------------------------------------------------------
@mcp.tool()
async def get_violation_history(
    days_back: int = 30,
    group_by: str = "day",
) -> str:
    """Retrieve historical compliance data with trend analysis.

    Shows how compliance has changed over time to track progress
    and measure remediation effectiveness.

    Args:
        days_back: Number of days to look back (1-90, default 30)
        group_by: How to group historical data: "day", "week", or "month"
    """
    _ensure_initialized()
    from .tools import get_violation_history as _history

    db_path = "compliance_history.db"
    if _container.history_service:
        db_path = _container.history_service.db_path

    result = await _history(
        days_back=days_back,
        group_by=group_by,
        db_path=db_path,
    )

    return json.dumps(result.model_dump(mode="json"), default=str)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_initialized() -> None:
    """Raise if the container hasn't been initialized yet."""
    if _container is None or not _container.initialized:
        raise RuntimeError(
            "ServiceContainer not initialized. "
            "Call initialize_container() before using tools."
        )
    if not _container.compliance_service:
        raise RuntimeError("ComplianceService not available. Check AWS configuration.")


async def initialize_container() -> ServiceContainer:
    """Initialize the ServiceContainer for the stdio server."""
    global _container
    from .config import CoreSettings

    _container = ServiceContainer(settings=CoreSettings())
    await _container.initialize()
    return _container


async def shutdown_container() -> None:
    """Shut down the ServiceContainer."""
    global _container
    if _container:
        await _container.shutdown()
        _container = None


def main() -> None:
    """Entry point for the stdio MCP server."""
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,  # MCP uses stdout for JSON-RPC; logs go to stderr
    )

    logger.info("Starting FinOps Tag Compliance MCP Server (stdio transport)")

    async def _run() -> None:
        await initialize_container()
        try:
            await mcp.run_stdio_async()
        finally:
            await shutdown_container()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
