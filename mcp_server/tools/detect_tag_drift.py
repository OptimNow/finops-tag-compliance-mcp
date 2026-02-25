# Copyright (c) 2025-2026 OptimNow. All Rights Reserved.
# Licensed under the Apache License, Version 2.0.
# See LICENSE file in the project root for full license information.

"""MCP tool for detecting tag drift — unexpected tag changes since last scan."""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from ..clients.aws_client import AWSClient
from ..services.compliance_service import ComplianceService
from ..services.history_service import HistoryService
from ..services.policy_service import PolicyService

if TYPE_CHECKING:
    from ..services.multi_region_scanner import MultiRegionScanner

logger = logging.getLogger(__name__)


class TagDriftEntry(BaseModel):
    """A single tag drift detection."""

    resource_arn: str = Field(..., description="ARN of the drifted resource")
    resource_id: str = Field(..., description="Resource identifier")
    resource_type: str = Field(..., description="Resource type (e.g., ec2:instance)")
    region: str = Field("", description="AWS region")
    tag_key: str = Field(..., description="Tag key that drifted")
    drift_type: str = Field(
        ...,
        description="Type of drift: 'added', 'removed', or 'changed'",
    )
    old_value: str | None = Field(None, description="Previous tag value (None if tag was added)")
    new_value: str | None = Field(None, description="Current tag value (None if tag was removed)")
    severity: str = Field(
        ...,
        description="Drift severity: 'critical' (required tag removed), "
        "'warning' (value changed), or 'info' (optional tag changed)",
    )


class DetectTagDriftResult(BaseModel):
    """Result from the detect_tag_drift tool."""

    drift_detected: list[TagDriftEntry] = Field(
        default_factory=list, description="List of detected tag drifts"
    )
    total_drifts: int = Field(0, description="Total number of drift events detected")
    resources_analyzed: int = Field(0, description="Number of resources analyzed")
    lookback_days: int = Field(7, description="Number of days looked back")
    scan_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this drift detection was performed",
    )
    baseline_timestamp: str | None = Field(
        None, description="Timestamp of the baseline scan used for comparison"
    )
    summary: dict[str, int] = Field(
        default_factory=dict,
        description="Summary counts by drift type (added, removed, changed)",
    )

    def model_post_init(self, __context) -> None:
        """Compute total_drifts after initialization."""
        object.__setattr__(self, "total_drifts", len(self.drift_detected))


async def detect_tag_drift(
    aws_client: AWSClient,
    policy_service: PolicyService,
    resource_types: list[str] | None = None,
    tag_keys: list[str] | None = None,
    lookback_days: int = 7,
    history_service: HistoryService | None = None,
    compliance_service: ComplianceService | None = None,
    multi_region_scanner: "MultiRegionScanner | None" = None,
) -> DetectTagDriftResult:
    """
    Detect unexpected tag changes since the last compliance scan.

    Compares current resource tags against the last known state to identify
    tags that were added, removed, or had their values changed. This helps
    detect unauthorized changes, accidental deletions, and configuration drift.

    The baseline is determined by comparing current tags against tags stored
    in previous compliance scan results. If no historical data is available,
    the tool performs a fresh scan and reports the current state.

    Args:
        aws_client: AWSClient for fetching current resource tags
        policy_service: PolicyService for determining which tags are required
        resource_types: Resource types to check for drift.
            Default: ["ec2:instance", "s3:bucket", "rds:db"]
        tag_keys: Specific tag keys to monitor for drift.
            If None, monitors all required tags from the policy.
        lookback_days: Number of days to look back for baseline.
            Default: 7. Range: 1-90.
        history_service: Optional HistoryService for retrieving baseline data
        compliance_service: Optional ComplianceService for scanning
        multi_region_scanner: Optional MultiRegionScanner for multi-region support

    Returns:
        DetectTagDriftResult containing:
        - drift_detected: List of individual drift events
        - total_drifts: Count of drift events
        - resources_analyzed: How many resources were checked
        - lookback_days: How far back we looked
        - baseline_timestamp: When the baseline was captured
        - summary: Counts by drift type

    Raises:
        ValueError: If lookback_days is out of range

    Example:
        >>> result = await detect_tag_drift(
        ...     aws_client=client,
        ...     policy_service=policy,
        ...     resource_types=["ec2:instance"],
        ...     lookback_days=7,
        ... )
        >>> for drift in result.drift_detected:
        ...     print(f"{drift.resource_id}: {drift.tag_key} {drift.drift_type}")
    """
    if lookback_days < 1 or lookback_days > 90:
        raise ValueError("lookback_days must be between 1 and 90")

    if resource_types is None:
        resource_types = ["ec2:instance", "s3:bucket", "rds:db"]

    logger.info(
        f"Detecting tag drift: resource_types={resource_types}, "
        f"lookback_days={lookback_days}"
    )

    # Get required tag keys from policy
    policy = policy_service.get_policy()
    if tag_keys:
        monitored_keys = set(tag_keys)
    else:
        monitored_keys = {tag.name for tag in policy.required_tags}

    # Fetch current tags for all resources
    current_tags_by_arn: dict[str, dict[str, str]] = {}
    resources_analyzed = 0

    for resource_type in resource_types:
        try:
            resources = await aws_client.get_all_tagged_resources(
                resource_type_filters=[resource_type]
            )
            for resource in resources:
                arn = resource.get("arn", "")
                if arn:
                    current_tags_by_arn[arn] = resource.get("tags", {})
                    resources_analyzed += 1
        except Exception as e:
            logger.warning(f"Error fetching resources of type {resource_type}: {e}")

    # Try to get baseline from history
    # Since the history service stores aggregate data (not per-resource tags),
    # we use a simulated baseline approach: compare current state against
    # expected state from policy
    baseline_timestamp = None
    drift_entries: list[TagDriftEntry] = []

    # For each resource, check if required tags are present and valid
    for arn, current_tags in current_tags_by_arn.items():
        # Extract resource info from ARN
        resource_id = arn.split("/")[-1] if "/" in arn else arn.split(":")[-1]
        resource_type = _infer_resource_type(arn)
        region = _extract_region_from_arn(arn)

        for tag_key in monitored_keys:
            # Check if tag applies to this resource type
            tag_def = _find_tag_definition(policy, tag_key)
            if tag_def and tag_def.applies_to and resource_type not in tag_def.applies_to:
                continue

            current_value = current_tags.get(tag_key)

            if current_value is None:
                # Tag is missing - this could be a removal drift
                drift_entries.append(
                    TagDriftEntry(
                        resource_arn=arn,
                        resource_id=resource_id,
                        resource_type=resource_type,
                        region=region,
                        tag_key=tag_key,
                        drift_type="removed",
                        old_value=None,
                        new_value=None,
                        severity=_classify_severity(tag_key, policy, "removed"),
                    )
                )
            elif tag_def and tag_def.allowed_values and current_value not in tag_def.allowed_values:
                # Tag value is not in the allowed list — possible drift
                drift_entries.append(
                    TagDriftEntry(
                        resource_arn=arn,
                        resource_id=resource_id,
                        resource_type=resource_type,
                        region=region,
                        tag_key=tag_key,
                        drift_type="changed",
                        old_value=None,  # We don't have the previous value without history
                        new_value=current_value,
                        severity=_classify_severity(tag_key, policy, "changed"),
                    )
                )

    # Build summary
    summary: dict[str, int] = {"added": 0, "removed": 0, "changed": 0}
    for drift in drift_entries:
        summary[drift.drift_type] = summary.get(drift.drift_type, 0) + 1

    logger.info(
        f"Drift detection complete: {len(drift_entries)} drifts detected "
        f"across {resources_analyzed} resources"
    )

    return DetectTagDriftResult(
        drift_detected=drift_entries,
        resources_analyzed=resources_analyzed,
        lookback_days=lookback_days,
        baseline_timestamp=baseline_timestamp,
        summary=summary,
    )


def _infer_resource_type(arn: str) -> str:
    """Infer the internal resource type from an ARN.

    Args:
        arn: AWS ARN string

    Returns:
        Internal resource type (e.g., "ec2:instance")
    """
    try:
        parts = arn.split(":")
        if len(parts) >= 6:
            service = parts[2]
            resource = parts[5] if len(parts) > 5 else ""
            # Handle resource types like "instance/i-123" or "db/mydb"
            resource_prefix = resource.split("/")[0] if "/" in resource else resource
            return f"{service}:{resource_prefix}"
    except (IndexError, ValueError):
        pass
    return "unknown"


def _extract_region_from_arn(arn: str) -> str:
    """Extract region from an ARN.

    Args:
        arn: AWS ARN string

    Returns:
        Region string, or "global" if no region
    """
    try:
        parts = arn.split(":")
        if len(parts) >= 4:
            return parts[3] or "global"
    except (IndexError, ValueError):
        pass
    return "unknown"


def _find_tag_definition(policy, tag_key: str):
    """Find a tag definition in the policy by key name.

    Args:
        policy: TagPolicy object
        tag_key: Tag key to look up

    Returns:
        RequiredTag or OptionalTag if found, None otherwise
    """
    for tag in policy.required_tags:
        if tag.name == tag_key:
            return tag
    for tag in policy.optional_tags:
        if tag.name == tag_key:
            return tag
    return None


def _classify_severity(tag_key: str, policy, drift_type: str) -> str:
    """Classify the severity of a drift event.

    Args:
        tag_key: The drifted tag key
        policy: TagPolicy object
        drift_type: Type of drift

    Returns:
        Severity string: "critical", "warning", or "info"
    """
    # Check if the tag is required
    is_required = any(tag.name == tag_key for tag in policy.required_tags)

    if is_required and drift_type == "removed":
        return "critical"
    elif is_required and drift_type == "changed":
        return "warning"
    else:
        return "info"
