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

    IMPORTANT: The 'all' mode scans 42 resource types across all AWS regions,
    which may take several minutes. For faster results, specify resource types
    explicitly: ["ec2:instance", "s3:bucket", "lambda:function", "rds:db"]

    Args:
        resource_types: List of resource types to check. Examples:
            - ["ec2:instance", "s3:bucket"] - specific types (faster)
            - ["all"] - comprehensive scan (slower, may timeout)
        filters: Optional filters for region or account_id
        severity: Filter results by severity: "all", "errors_only", or "warnings_only"
        store_snapshot: If true, store result in history for trend tracking
        force_refresh: If true, bypass cache and force fresh scan
    """
    _ensure_initialized()
    from .tools import check_tag_compliance as _check

    try:
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
    except asyncio.TimeoutError as e:
        error_msg = str(e)
        logger.error(f"Timeout during compliance check: {error_msg}")
        # Return helpful error with suggestion
        return json.dumps({
            "error": "timeout",
            "message": f"Scan timed out: {error_msg}",
            "suggestion": "Try scanning specific resource types instead of 'all'. "
                         "Example: ['ec2:instance', 's3:bucket', 'lambda:function', 'rds:db']",
        })
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error during compliance check: {error_msg}")
        return json.dumps({
            "error": "scan_failed",
            "message": error_msg,
            "suggestion": "If using 'all' mode, try specific resource types instead.",
        })

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
        response["regional_breakdown"] = [
            {
                "region": summary.region,
                "compliance_score": summary.compliance_score,
                "total_resources": summary.total_resources,
                "compliant_resources": summary.compliant_resources,
                "violation_count": summary.violation_count,
                "cost_attribution_gap": summary.cost_attribution_gap,
            }
            for region, summary in result.regional_breakdown.items()
        ]

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
# Tool 9: generate_custodian_policy
# ---------------------------------------------------------------------------
@mcp.tool()
async def generate_custodian_policy(
    resource_types: list[str] | None = None,
    violation_types: list[str] | None = None,
    target_tags: list[str] | None = None,
    dry_run: bool = True,
) -> str:
    """Generate Cloud Custodian YAML policies from the tagging policy.

    Creates enforceable Cloud Custodian policies based on the current tagging
    policy. Policies can target specific resource types, violation types, and
    tags. Use dry_run=True (default) to generate notify-only policies.

    Args:
        resource_types: Resource types to generate policies for (e.g. ["ec2:instance"]).
            If None, generates for all resource types in the tagging policy.
        violation_types: Types of violations to enforce: "missing_tag", "invalid_value".
            If None, enforces all violation types.
        target_tags: Specific tag names to enforce (e.g. ["Environment", "Owner"]).
            If None, enforces all required tags from the policy.
        dry_run: If True (default), generates notify-only policies. If False,
            generates auto-remediation policies.
    """
    _ensure_initialized()
    from .tools import generate_custodian_policy as _custodian

    result = await _custodian(
        policy_service=_container.policy_service,
        resource_types=resource_types,
        violation_types=violation_types,
        target_tags=target_tags,
        dry_run=dry_run,
        compliance_service=_container.compliance_service,
    )

    return json.dumps(result.model_dump(mode="json"), default=str)


# ---------------------------------------------------------------------------
# Tool 10: generate_openops_workflow
# ---------------------------------------------------------------------------
@mcp.tool()
async def generate_openops_workflow(
    resource_types: list[str] | None = None,
    remediation_strategy: str = "notify",
    threshold: float | None = None,
    target_tags: list[str] | None = None,
    schedule: str = "daily",
) -> str:
    """Generate an OpenOps automation workflow for tag remediation.

    Creates an OpenOps-compatible YAML workflow that automates tag compliance
    enforcement. Supports notification, auto-tagging, and reporting strategies.

    Args:
        resource_types: Resource types to include (e.g. ["ec2:instance"]).
            If None, includes all resource types from the policy.
        remediation_strategy: Strategy to use: "notify" (send alerts),
            "auto_tag" (apply missing tags), or "report" (generate reports).
        threshold: Compliance score threshold (0.0-1.0) that triggers the workflow.
            If None, no threshold filter is applied.
        target_tags: Specific tag names to target (e.g. ["Environment"]).
            If None, targets all required tags.
        schedule: How often to run: "daily", "weekly", or "monthly".
    """
    _ensure_initialized()
    from .tools import generate_openops_workflow as _openops

    result = await _openops(
        policy_service=_container.policy_service,
        resource_types=resource_types or ["all"],
        remediation_strategy=remediation_strategy,
        threshold=threshold if threshold is not None else 0.8,
        target_tags=target_tags,
        schedule=schedule,
        compliance_service=_container.compliance_service,
    )

    return json.dumps(result.model_dump(mode="json"), default=str)


# ---------------------------------------------------------------------------
# Tool 11: schedule_compliance_audit
# ---------------------------------------------------------------------------
@mcp.tool()
async def schedule_compliance_audit(
    schedule: str = "daily",
    time: str = "09:00",
    timezone_str: str = "UTC",
    resource_types: list[str] | None = None,
    recipients: list[str] | None = None,
    notification_format: str = "email",
    # Alternate parameter names AI agents commonly send
    schedule_type: str | None = None,
    time_of_day: str | None = None,
    timezone: str | None = None,
) -> str:
    """Create a compliance audit schedule configuration.

    Generates a schedule configuration for recurring compliance audits,
    including cron expression and next estimated run time. This creates
    the configuration — actual scheduling requires an external scheduler.

    Args:
        schedule: Frequency: "daily", "weekly", or "monthly"
        time: Time of day in HH:MM format (24-hour)
        timezone_str: Timezone (e.g. "UTC", "US/Eastern", "Europe/London")
        resource_types: Resource types to audit. If None, audits all types.
        recipients: Email addresses for notifications
        notification_format: Notification method: "email", "slack", or "both"
        schedule_type: Alias for schedule
        time_of_day: Alias for time
        timezone: Alias for timezone_str
    """
    _ensure_initialized()
    from .tools import schedule_compliance_audit as _schedule

    # Accept alternate parameter names as fallbacks
    effective_schedule = schedule_type if schedule_type and schedule == "daily" else schedule
    effective_time = time_of_day if time_of_day and time == "09:00" else time
    effective_tz = timezone if timezone and timezone_str == "UTC" else timezone_str

    result = await _schedule(
        schedule=effective_schedule,
        time=effective_time,
        timezone_str=effective_tz,
        resource_types=resource_types,
        recipients=recipients,
        notification_format=notification_format,
    )

    return json.dumps(result.model_dump(mode="json"), default=str)


# ---------------------------------------------------------------------------
# Tool 12: detect_tag_drift
# ---------------------------------------------------------------------------
@mcp.tool()
async def detect_tag_drift(
    resource_types: list[str] | None = None,
    tag_keys: list[str] | None = None,
    lookback_days: int = 7,
) -> str:
    """Detect unexpected tag changes since the last compliance scan.

    Compares current resource tags against expected state from the tagging
    policy to identify missing required tags and invalid tag values.
    Classifies drift by severity: critical (required tag removed),
    warning (value changed), or info (optional tag changed).

    Args:
        resource_types: Resource types to check (e.g. ["ec2:instance"]).
            Default: ["ec2:instance", "s3:bucket", "rds:db"]
        tag_keys: Specific tag keys to monitor. If None, monitors all
            required tags from the policy.
        lookback_days: Number of days to look back for baseline (1-90, default 7)
    """
    _ensure_initialized()
    from .tools import detect_tag_drift as _drift

    result = await _drift(
        aws_client=_container.aws_client,
        policy_service=_container.policy_service,
        resource_types=resource_types,
        tag_keys=tag_keys,
        lookback_days=lookback_days,
        history_service=_container.history_service,
        compliance_service=_container.compliance_service,
        multi_region_scanner=_container.multi_region_scanner,
    )

    return json.dumps(result.model_dump(mode="json"), default=str)


# ---------------------------------------------------------------------------
# Tool 13: export_violations_csv
# ---------------------------------------------------------------------------
@mcp.tool()
async def export_violations_csv(
    resource_types: list[str] | None = None,
    severity: str = "all",
    columns: list[str] | None = None,
) -> str:
    """Export compliance violations as CSV data.

    Runs a compliance scan and exports violations in CSV format for
    spreadsheet analysis, reporting, or integration with other tools.

    Args:
        resource_types: Resource types to scan (e.g. ["ec2:instance"]).
            If None, scans all resource types.
        severity: Filter by severity: "all", "errors_only", or "warnings_only"
        columns: CSV columns to include. Available: resource_id, resource_type,
            region, violation_type, tag_name, severity, current_value,
            allowed_values, cost_impact, arn.
            Default: resource_id, resource_type, region, violation_type,
            tag_name, severity.
    """
    _ensure_initialized()
    from .tools import export_violations_csv as _export

    result = await _export(
        compliance_service=_container.compliance_service,
        resource_types=resource_types,
        severity=severity,
        columns=columns,
        multi_region_scanner=_container.multi_region_scanner,
    )

    return json.dumps(result.model_dump(mode="json"), default=str)


# ---------------------------------------------------------------------------
# Tool 14: import_aws_tag_policy
# ---------------------------------------------------------------------------
@mcp.tool()
async def import_aws_tag_policy(
    policy_id: str | None = None,
    save_to_file: bool = True,
    output_path: str = "policies/tagging_policy.json",
) -> str:
    """Import and convert an AWS Organizations tag policy to MCP format.

    Connects to AWS Organizations to retrieve tag policies and converts
    them to the MCP server's tagging policy format. If no policy_id is
    provided, lists all available tag policies.

    Args:
        policy_id: AWS Organizations policy ID (e.g. "p-xxxxxxxx").
            If None, lists all available tag policies instead of importing.
        save_to_file: Whether to save the converted policy to a file (default True)
        output_path: File path to save the converted policy
            (default "policies/tagging_policy.json")
    """
    _ensure_initialized()
    from .tools import import_aws_tag_policy as _import

    result = await _import(
        aws_client=_container.aws_client,
        policy_id=policy_id,
        save_to_file=save_to_file,
        output_path=output_path,
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
