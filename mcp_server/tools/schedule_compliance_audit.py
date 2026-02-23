# Copyright (c) 2025-2026 OptimNow. All Rights Reserved.
# Licensed under the Apache License, Version 2.0.
# See LICENSE file in the project root for full license information.

"""MCP tool for scheduling recurring compliance audits."""

import logging
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Valid schedule types
VALID_SCHEDULE_TYPES = {"daily", "weekly", "monthly"}

# Valid notification formats
VALID_FORMATS = {"email", "slack", "both"}


class AuditScheduleConfig(BaseModel):
    """Configuration for a scheduled compliance audit."""

    schedule_id: str = Field(..., description="Unique schedule identifier")
    schedule_type: str = Field(..., description="Schedule frequency: daily, weekly, or monthly")
    time: str = Field(..., description="Time of day in HH:MM format (24-hour)")
    timezone: str = Field("UTC", description="Timezone (e.g., 'America/New_York', 'UTC')")
    resource_types: list[str] = Field(
        default_factory=list, description="Resource types to audit"
    )
    notification_format: str = Field(
        "email", description="Notification format: email, slack, or both"
    )
    recipients: list[str] = Field(
        default_factory=list, description="Notification recipients"
    )


class ScheduleComplianceAuditResult(BaseModel):
    """Result from the schedule_compliance_audit tool."""

    schedule_id: str = Field(..., description="Unique schedule identifier")
    status: str = Field(..., description="Schedule status: 'active', 'created', or 'error'")
    schedule_type: str = Field(..., description="Schedule frequency")
    time: str = Field(..., description="Scheduled time in HH:MM format")
    timezone: str = Field(..., description="Timezone for the schedule")
    resource_types: list[str] = Field(
        default_factory=list, description="Resource types to audit"
    )
    next_run: str = Field(..., description="Next scheduled run (ISO 8601)")
    notification_format: str = Field(..., description="Notification delivery method")
    recipients: list[str] = Field(
        default_factory=list, description="Who receives notifications"
    )
    cron_expression: str = Field(..., description="Generated cron expression")
    message: str = Field(..., description="Human-readable confirmation message")


async def schedule_compliance_audit(
    schedule: str = "daily",
    time: str = "09:00",
    timezone_str: str = "UTC",
    resource_types: list[str] | None = None,
    recipients: list[str] | None = None,
    notification_format: str = "email",
) -> ScheduleComplianceAuditResult:
    """
    Schedule a recurring compliance audit.

    Configures automated compliance scans that run on a schedule and
    deliver results via email, Slack, or both. Scheduled scans are
    stored in the compliance history with a "scheduled" flag for
    accurate trend tracking.

    Note: This tool generates the schedule configuration. The actual
    execution requires a scheduler service (e.g., APScheduler, AWS
    EventBridge) to be configured separately.

    Args:
        schedule: Frequency of the audit: "daily", "weekly", or "monthly".
            Default: "daily"
        time: Time of day to run in HH:MM format (24-hour).
            Default: "09:00"
        timezone_str: Timezone for the schedule.
            Default: "UTC"
        resource_types: Resource types to audit.
            Default: ["all"] (comprehensive scan)
        recipients: Email addresses or Slack channels for notifications.
            Default: empty list
        notification_format: How to deliver results: "email", "slack", or "both".
            Default: "email"

    Returns:
        ScheduleComplianceAuditResult containing:
        - schedule_id: Unique identifier for this schedule
        - status: Current status ("created")
        - schedule_type: The schedule frequency
        - time: Scheduled time
        - timezone: Timezone used
        - resource_types: What will be audited
        - next_run: When the next audit will run
        - cron_expression: The generated cron expression
        - message: Human-readable confirmation

    Raises:
        ValueError: If schedule, time, or notification_format is invalid

    Example:
        >>> result = await schedule_compliance_audit(
        ...     schedule="daily",
        ...     time="09:00",
        ...     timezone_str="America/New_York",
        ...     resource_types=["ec2:instance", "rds:db"],
        ...     recipients=["finops@company.com"],
        ... )
        >>> print(f"Scheduled: {result.schedule_id}")
        >>> print(f"Next run: {result.next_run}")
    """
    # Validate schedule type
    if schedule not in VALID_SCHEDULE_TYPES:
        raise ValueError(
            f"Invalid schedule '{schedule}'. Must be one of: {VALID_SCHEDULE_TYPES}"
        )

    # Validate time format
    try:
        parts = time.split(":")
        if len(parts) != 2:
            raise ValueError()
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError()
    except (ValueError, IndexError):
        raise ValueError(
            f"Invalid time '{time}'. Must be in HH:MM format (24-hour), e.g., '09:00'"
        )

    # Validate notification format
    if notification_format not in VALID_FORMATS:
        raise ValueError(
            f"Invalid notification_format '{notification_format}'. "
            f"Must be one of: {VALID_FORMATS}"
        )

    if resource_types is None:
        resource_types = ["all"]

    if recipients is None:
        recipients = []

    logger.info(
        f"Creating compliance audit schedule: {schedule} at {time} {timezone_str}, "
        f"resource_types={resource_types}"
    )

    # Generate schedule ID
    schedule_id = f"audit-sched-{uuid.uuid4().hex[:8]}"

    # Generate cron expression
    cron_expression = _generate_cron(schedule, hour, minute)

    # Calculate next run time (approximate - actual scheduling done by scheduler service)
    now = datetime.now(timezone.utc)
    next_run = _estimate_next_run(schedule, hour, minute, now)

    message = (
        f"Compliance audit scheduled: {schedule} at {time} {timezone_str}. "
        f"Auditing {', '.join(resource_types)} resources."
    )
    if recipients:
        message += f" Notifications will be sent to {', '.join(recipients)}."

    logger.info(f"Schedule created: {schedule_id}, next_run={next_run.isoformat()}")

    return ScheduleComplianceAuditResult(
        schedule_id=schedule_id,
        status="created",
        schedule_type=schedule,
        time=time,
        timezone=timezone_str,
        resource_types=resource_types,
        next_run=next_run.isoformat(),
        notification_format=notification_format,
        recipients=recipients,
        cron_expression=cron_expression,
        message=message,
    )


def _generate_cron(schedule: str, hour: int, minute: int) -> str:
    """Generate a cron expression from schedule parameters.

    Args:
        schedule: "daily", "weekly", or "monthly"
        hour: Hour (0-23)
        minute: Minute (0-59)

    Returns:
        Cron expression string
    """
    if schedule == "daily":
        return f"{minute} {hour} * * *"
    elif schedule == "weekly":
        return f"{minute} {hour} * * MON"
    elif schedule == "monthly":
        return f"{minute} {hour} 1 * *"
    else:
        return f"{minute} {hour} * * *"


def _estimate_next_run(
    schedule: str, hour: int, minute: int, now: datetime
) -> datetime:
    """Estimate the next run time.

    This is an approximation - the actual scheduler service handles
    precise timezone-aware scheduling.

    Args:
        schedule: "daily", "weekly", or "monthly"
        hour: Hour (0-23)
        minute: Minute (0-59)
        now: Current UTC time

    Returns:
        Estimated next run datetime (UTC)
    """
    from datetime import timedelta

    # Simple estimate: next occurrence of the specified time
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if next_run <= now:
        if schedule == "daily":
            next_run += timedelta(days=1)
        elif schedule == "weekly":
            days_ahead = 7 - now.weekday()  # Monday is 0
            if days_ahead == 0:
                days_ahead = 7
            next_run = now.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            ) + timedelta(days=days_ahead)
        elif schedule == "monthly":
            # Move to the 1st of next month
            if now.month == 12:
                next_run = now.replace(
                    year=now.year + 1,
                    month=1,
                    day=1,
                    hour=hour,
                    minute=minute,
                    second=0,
                    microsecond=0,
                )
            else:
                next_run = now.replace(
                    month=now.month + 1,
                    day=1,
                    hour=hour,
                    minute=minute,
                    second=0,
                    microsecond=0,
                )

    return next_run
