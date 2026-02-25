# Copyright (c) 2025-2026 OptimNow. All Rights Reserved.
# Licensed under the Apache License, Version 2.0.
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
# Anti-hallucination: data quality metadata
# ---------------------------------------------------------------------------
def _build_data_quality(result: Any) -> dict:
    """Build a data_quality block that tells LLMs whether results are complete.

    This metadata is included in every scan response so that LLMs know whether
    the data covers all regions and resource types, or is partial/incomplete.
    LLMs MUST report partial data honestly rather than presenting it as complete.
    """
    quality: dict[str, Any] = {"status": "complete"}

    if not hasattr(result, "region_metadata"):
        return quality

    meta = result.region_metadata
    failed = meta.failed_regions or []
    total = meta.total_regions or 0

    if meta.discovery_failed:
        quality["status"] = "partial"
        quality["warning"] = (
            "Region discovery failed. Results are from the default region only "
            "and DO NOT represent the full AWS account. "
            "Do not present these numbers as account-wide totals."
        )
        if meta.discovery_error:
            quality["discovery_error"] = meta.discovery_error
    elif failed:
        quality["status"] = "partial"
        quality["warning"] = (
            f"{len(failed)} of {total} regions failed to scan. "
            f"Results are incomplete and DO NOT cover: {', '.join(failed)}. "
            "Do not present these numbers as account-wide totals."
        )
        quality["failed_regions"] = failed
    else:
        quality["status"] = "complete"
        quality["note"] = f"All {total} regions scanned successfully."

    return quality


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

    REQUIRED WORKFLOW — do NOT guess resource types:
    1. FIRST call get_tagging_policy to retrieve the policy and extract ALL
       resource types from the "applies_to" fields across all required tags.
    2. THEN call this tool with those resource types — either in one call or
       in batches of 4-6 types to avoid timeouts.
    Do NOT pick resource types from memory (e.g., "EC2, S3, Lambda"). The
    policy may include Bedrock, DynamoDB, ECS, EKS, SageMaker, and others
    that you would miss. Always read the policy first.

    TIMEOUT WARNING: MCP clients (e.g., Claude Desktop) may have a 60-second
    response timeout. Scanning many resource types across all regions can
    take 2-5 minutes and will silently timeout on the client side. To avoid
    this, scan in batches of 4-6 resource types per call and aggregate the
    results yourself. Only use ["all"] if the client supports long timeouts.

    CRITICAL — data accuracy: Always check the "data_quality" field in the
    response. If data_quality.status is "partial", some regions failed to scan
    and the results are INCOMPLETE. You MUST disclose this to the user — do NOT
    present partial data as if it were a complete account-wide picture. Never
    estimate, extrapolate, or fabricate values for regions that failed.

    Args:
        resource_types: List of resource types to check. Examples:
            - ["ec2:instance", "s3:bucket", "lambda:function", "rds:db"] — batch (recommended)
            - ["all"] — comprehensive scan (WARNING: will likely timeout on Claude Desktop)
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

    # Add data quality metadata (anti-hallucination guard)
    response["data_quality"] = _build_data_quality(result)

    # Add multi-region fields if this is a MultiRegionComplianceResult
    if hasattr(result, "region_metadata"):
        response["region_metadata"] = {
            "total_regions": result.region_metadata.total_regions,
            "successful_regions": result.region_metadata.successful_regions,
            "failed_regions": result.region_metadata.failed_regions,
            "skipped_regions": result.region_metadata.skipped_regions,
            "discovery_failed": result.region_metadata.discovery_failed,
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

    REQUIRED WORKFLOW — do NOT guess resource types:
    Call get_tagging_policy first to get ALL resource types from the policy.
    Then pass those types here — in batches of 4-6 to avoid client timeouts.
    Do NOT pick types from memory; the policy may include types you'd miss.

    TIMEOUT WARNING: MCP clients may timeout after 60 seconds. Scan in batches
    of 4-6 resource types per call rather than using ["all"].

    CRITICAL — data accuracy: Always check the "data_quality" field in the
    response. If data_quality.status is "partial", some regions failed and the
    results are INCOMPLETE. You MUST tell the user which regions are missing.
    Never estimate or fabricate resource counts for failed regions.

    Args:
        resource_types: List of resource types to search. Get these from get_tagging_policy.
            - ["ec2:instance", "s3:bucket", "lambda:function", "rds:db"] — batch (recommended)
            - ["all"] — comprehensive scan (WARNING: will likely timeout on Claude Desktop)
        regions: Optional list of AWS regions to search
        include_costs: Whether to include cost estimates (default false)
        min_cost_threshold: Optional minimum monthly cost threshold in USD
    """
    _ensure_initialized()
    from .tools import find_untagged_resources as _find

    try:
        result = await _find(
            aws_client=_container.aws_client,
            policy_service=_container.policy_service,
            resource_types=resource_types,
            regions=regions,
            min_cost_threshold=min_cost_threshold,
            include_costs=include_costs,
            multi_region_scanner=_container.multi_region_scanner,
        )
    except asyncio.TimeoutError as e:
        error_msg = str(e)
        logger.error(f"Timeout during find_untagged_resources: {error_msg}")
        return json.dumps({
            "error": "timeout",
            "message": f"Scan timed out: {error_msg}",
            "suggestion": "Try scanning specific resource types instead of 'all'. "
                         "Example: ['ec2:instance', 's3:bucket', 'lambda:function', 'rds:db']",
        })
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error during find_untagged_resources: {error_msg}")
        return json.dumps({
            "error": "scan_failed",
            "message": error_msg,
            "suggestion": "If using 'all' mode, try specific resource types instead.",
        })

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
        "data_quality": _build_data_quality(result),
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

    REQUIRED WORKFLOW — do NOT guess resource types:
    Call get_tagging_policy first to get ALL resource types from the policy.
    Then pass those types here — in batches of 4-6 to avoid client timeouts.

    TIMEOUT WARNING: This is the SLOWEST tool (3-5 minutes with "all"). MCP
    clients like Claude Desktop timeout after 60 seconds. ALWAYS scan in small
    batches of 3-4 cost-generating resource types per call.

    CRITICAL — data accuracy: If this tool returns an error or timeout, report
    the error to the user exactly as received. Never estimate, extrapolate, or
    fabricate dollar amounts. If the tool succeeds, check the "data_quality"
    field — if status is "partial", clearly disclose which data is missing.

    Args:
        resource_types: List of resource types to analyze. Get these from get_tagging_policy.
            - ["ec2:instance", "rds:db", "lambda:function"] — batch (recommended)
            - ["all"] — comprehensive (WARNING: will timeout on Claude Desktop)
        time_period: Time period with Start and End dates in YYYY-MM-DD format
        group_by: Optional grouping dimension: "resource_type", "region", or "account"
        filters: Optional filters for region or account_id
    """
    _ensure_initialized()
    from .tools import get_cost_attribution_gap as _gap

    try:
        result = await _gap(
            aws_client=_container.aws_client,
            policy_service=_container.policy_service,
            resource_types=resource_types,
            time_period=time_period,
            group_by=group_by,
            filters=filters,
            multi_region_scanner=_container.multi_region_scanner,
        )
    except asyncio.TimeoutError as e:
        error_msg = str(e)
        logger.error(f"Timeout during cost attribution gap: {error_msg}")
        return json.dumps({
            "error": "timeout",
            "message": f"Cost attribution analysis timed out: {error_msg}",
            "suggestion": "Try analyzing specific resource types instead of 'all'. "
                         "Example: ['ec2:instance', 's3:bucket', 'lambda:function', 'rds:db']",
        })
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error during cost attribution gap: {error_msg}")
        return json.dumps({
            "error": "analysis_failed",
            "message": error_msg,
            "suggestion": "If using 'all' mode, try specific resource types instead.",
        })

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
            "data_quality": _build_data_quality(result),
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

    IMPORTANT: This is the starting point for all compliance workflows.
    Call this FIRST before calling check_tag_compliance, find_untagged_resources,
    get_cost_attribution_gap, or generate_compliance_report. The response includes
    an "all_applicable_resource_types" field — a deduplicated list of every
    resource type referenced in the policy. Use that list (in batches of 4-6)
    as the resource_types parameter for scanning tools. NEVER guess or pick
    resource types from memory.
    """
    _ensure_initialized()
    from .tools import get_tagging_policy as _policy

    result = await _policy(
        policy_service=_container.policy_service,
    )

    # Build response with helper field for LLM workflows
    response = result.model_dump(mode="json")

    # Extract all unique resource types from the policy for easy LLM consumption
    all_types: set[str] = set()
    for tag in response.get("required_tags", []):
        for rt in tag.get("applies_to", []):
            all_types.add(rt)
    for tag in response.get("optional_tags", []):
        for rt in tag.get("applies_to", []):
            all_types.add(rt)
    response["all_applicable_resource_types"] = sorted(all_types)

    return json.dumps(response, default=str)


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

    REQUIRED WORKFLOW — do NOT guess resource types:
    Call get_tagging_policy first to get ALL resource types from the policy.
    Then pass those types here — in batches of 4-6 to avoid client timeouts.

    TIMEOUT WARNING: MCP clients may timeout after 60 seconds. Scan in batches
    of 4-6 resource types per call rather than using ["all"].

    CRITICAL — data accuracy: Always check the "data_quality" field. If status
    is "partial", clearly state which regions or data are missing. Never present
    partial scan results as a complete compliance report.

    Args:
        resource_types: List of resource types to include. Get these from get_tagging_policy.
            - ["ec2:instance", "s3:bucket", "lambda:function", "rds:db"] — batch (recommended)
            - ["all"] — comprehensive (WARNING: will likely timeout on Claude Desktop)
        format: Output format: "json", "csv", or "markdown"
        include_recommendations: Whether to include actionable recommendations
    """
    _ensure_initialized()
    from .tools import check_tag_compliance as _check
    from .tools import generate_compliance_report as _report

    try:
        compliance_result = await _check(
            compliance_service=_container.compliance_service,
            resource_types=resource_types,
            severity="all",
            history_service=_container.history_service,
            multi_region_scanner=_container.multi_region_scanner,
        )
    except asyncio.TimeoutError as e:
        error_msg = str(e)
        logger.error(f"Timeout during compliance report scan: {error_msg}")
        return json.dumps({
            "error": "timeout",
            "message": f"Scan timed out: {error_msg}",
            "suggestion": "Try generating a report for specific resource types instead of 'all'. "
                         "Example: ['ec2:instance', 's3:bucket', 'lambda:function', 'rds:db']",
        })
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error during compliance report scan: {error_msg}")
        return json.dumps({
            "error": "scan_failed",
            "message": error_msg,
            "suggestion": "If using 'all' mode, try specific resource types instead.",
        })

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

    report_data = result.model_dump(mode="json")
    report_data["data_quality"] = _build_data_quality(compliance_result)
    return json.dumps(report_data, default=str)


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

    RECOMMENDED: Call get_tagging_policy first to know which resource types
    are in scope, then pass them here rather than relying on defaults.

    CRITICAL — data accuracy: If the result contains a "data_quality" field
    with status "partial", tell the user which regions were not scanned.
    Never fabricate drift data for regions that failed.

    Args:
        resource_types: Resource types to check. Get these from get_tagging_policy.
            Default: ["ec2:instance", "s3:bucket", "rds:db"]
        tag_keys: Specific tag keys to monitor. If None, monitors all
            required tags from the policy.
        lookback_days: Number of days to look back for baseline (1-90, default 7)
    """
    _ensure_initialized()
    from .tools import detect_tag_drift as _drift

    try:
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
    except asyncio.TimeoutError as e:
        error_msg = str(e)
        logger.error(f"Timeout during tag drift detection: {error_msg}")
        return json.dumps({
            "error": "timeout",
            "message": f"Tag drift detection timed out: {error_msg}",
            "suggestion": "Try checking specific resource types instead of scanning all. "
                         "Example: ['ec2:instance', 's3:bucket', 'rds:db']",
        })
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error during tag drift detection: {error_msg}")
        return json.dumps({
            "error": "drift_detection_failed",
            "message": error_msg,
        })

    drift_data = result.model_dump(mode="json")
    drift_data["data_quality"] = _build_data_quality(result)
    return json.dumps(drift_data, default=str)


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

    RECOMMENDED: Call get_tagging_policy first to know which resource types
    are in scope, then pass them here rather than guessing.

    TIMEOUT WARNING: MCP clients may timeout after 60 seconds. Scan in batches
    of 4-6 resource types per call rather than using ["all"] or None.

    CRITICAL — data accuracy: Check "data_quality" in the response. If status
    is "partial", note it in the export and tell the user which regions are missing.

    Args:
        resource_types: Resource types to scan. Get these from get_tagging_policy.
            If None, scans all resource types (WARNING: may timeout).
        severity: Filter by severity: "all", "errors_only", or "warnings_only"
        columns: CSV columns to include. Available: resource_id, resource_type,
            region, violation_type, tag_name, severity, current_value,
            allowed_values, cost_impact, arn.
            Default: resource_id, resource_type, region, violation_type,
            tag_name, severity.
    """
    _ensure_initialized()
    from .tools import export_violations_csv as _export

    try:
        result = await _export(
            compliance_service=_container.compliance_service,
            resource_types=resource_types,
            severity=severity,
            columns=columns,
            multi_region_scanner=_container.multi_region_scanner,
        )
    except asyncio.TimeoutError as e:
        error_msg = str(e)
        logger.error(f"Timeout during violations export: {error_msg}")
        return json.dumps({
            "error": "timeout",
            "message": f"Export timed out: {error_msg}",
            "suggestion": "Try exporting specific resource types instead of all. "
                         "Example: ['ec2:instance', 's3:bucket', 'lambda:function', 'rds:db']",
        })
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error during violations export: {error_msg}")
        return json.dumps({
            "error": "export_failed",
            "message": error_msg,
        })

    export_data = result.model_dump(mode="json")
    export_data["data_quality"] = _build_data_quality(result)
    return json.dumps(export_data, default=str)


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
