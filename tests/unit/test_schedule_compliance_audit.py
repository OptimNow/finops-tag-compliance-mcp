"""Unit tests for schedule_compliance_audit tool."""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from mcp_server.tools.schedule_compliance_audit import (
    AuditScheduleConfig,
    ScheduleComplianceAuditResult,
    schedule_compliance_audit,
    _generate_cron,
    _estimate_next_run,
    VALID_SCHEDULE_TYPES,
    VALID_FORMATS,
)


# =============================================================================
# Tests for AuditScheduleConfig model
# =============================================================================


class TestAuditScheduleConfig:
    """Test AuditScheduleConfig Pydantic model."""

    def test_model_required_fields(self):
        """Test that schedule_id and schedule_type are required."""
        config = AuditScheduleConfig(
            schedule_id="audit-sched-abc12345",
            schedule_type="daily",
            time="09:00",
        )
        assert config.schedule_id == "audit-sched-abc12345"
        assert config.schedule_type == "daily"
        assert config.time == "09:00"

    def test_model_defaults(self):
        """Test default values for optional fields."""
        config = AuditScheduleConfig(
            schedule_id="audit-sched-abc12345",
            schedule_type="daily",
            time="09:00",
        )
        assert config.timezone == "UTC"
        assert config.resource_types == []
        assert config.notification_format == "email"
        assert config.recipients == []

    def test_model_custom_values(self):
        """Test model with all custom values."""
        config = AuditScheduleConfig(
            schedule_id="audit-sched-abc12345",
            schedule_type="weekly",
            time="14:30",
            timezone="America/New_York",
            resource_types=["ec2:instance", "rds:db"],
            notification_format="slack",
            recipients=["#finops-alerts"],
        )
        assert config.schedule_type == "weekly"
        assert config.time == "14:30"
        assert config.timezone == "America/New_York"
        assert config.resource_types == ["ec2:instance", "rds:db"]
        assert config.notification_format == "slack"
        assert config.recipients == ["#finops-alerts"]


# =============================================================================
# Tests for ScheduleComplianceAuditResult model
# =============================================================================


class TestScheduleComplianceAuditResult:
    """Test ScheduleComplianceAuditResult Pydantic model."""

    def test_result_fields_present(self):
        """Test that all expected fields are present on the result model."""
        result = ScheduleComplianceAuditResult(
            schedule_id="audit-sched-abc12345",
            status="created",
            schedule_type="daily",
            time="09:00",
            timezone="UTC",
            resource_types=["all"],
            next_run="2026-02-14T09:00:00+00:00",
            notification_format="email",
            recipients=[],
            cron_expression="0 9 * * *",
            message="Compliance audit scheduled.",
        )
        assert result.schedule_id == "audit-sched-abc12345"
        assert result.status == "created"
        assert result.schedule_type == "daily"
        assert result.time == "09:00"
        assert result.timezone == "UTC"
        assert result.resource_types == ["all"]
        assert result.next_run == "2026-02-14T09:00:00+00:00"
        assert result.notification_format == "email"
        assert result.recipients == []
        assert result.cron_expression == "0 9 * * *"
        assert result.message == "Compliance audit scheduled."

    def test_result_serialization(self):
        """Test that the result model serializes to dict correctly."""
        result = ScheduleComplianceAuditResult(
            schedule_id="audit-sched-abc12345",
            status="created",
            schedule_type="daily",
            time="09:00",
            timezone="UTC",
            resource_types=["all"],
            next_run="2026-02-14T09:00:00+00:00",
            notification_format="email",
            recipients=["admin@example.com"],
            cron_expression="0 9 * * *",
            message="Scheduled.",
        )
        result_dict = result.model_dump()
        assert result_dict["schedule_id"] == "audit-sched-abc12345"
        assert result_dict["recipients"] == ["admin@example.com"]

    def test_result_with_multiple_recipients(self):
        """Test result with multiple recipients."""
        result = ScheduleComplianceAuditResult(
            schedule_id="audit-sched-abc12345",
            status="created",
            schedule_type="weekly",
            time="10:00",
            timezone="UTC",
            resource_types=["ec2:instance"],
            next_run="2026-02-16T10:00:00+00:00",
            notification_format="both",
            recipients=["admin@example.com", "#finops-alerts", "cto@example.com"],
            cron_expression="0 10 * * MON",
            message="Scheduled.",
        )
        assert len(result.recipients) == 3


# =============================================================================
# Tests for _generate_cron helper
# =============================================================================


class TestGenerateCron:
    """Test _generate_cron helper function."""

    def test_daily_cron(self):
        """Test cron expression for daily schedule."""
        cron = _generate_cron("daily", 9, 0)
        assert cron == "0 9 * * *"

    def test_daily_cron_afternoon(self):
        """Test cron expression for daily schedule in the afternoon."""
        cron = _generate_cron("daily", 14, 30)
        assert cron == "30 14 * * *"

    def test_weekly_cron(self):
        """Test cron expression for weekly schedule (runs on Monday)."""
        cron = _generate_cron("weekly", 9, 0)
        assert cron == "0 9 * * MON"

    def test_monthly_cron(self):
        """Test cron expression for monthly schedule (runs on 1st of month)."""
        cron = _generate_cron("monthly", 9, 0)
        assert cron == "0 9 1 * *"

    def test_daily_midnight(self):
        """Test cron expression for daily schedule at midnight."""
        cron = _generate_cron("daily", 0, 0)
        assert cron == "0 0 * * *"

    def test_daily_end_of_day(self):
        """Test cron expression for daily schedule at 23:59."""
        cron = _generate_cron("daily", 23, 59)
        assert cron == "59 23 * * *"

    def test_unknown_schedule_defaults_to_daily(self):
        """Test that unknown schedule type falls back to daily cron pattern."""
        cron = _generate_cron("unknown", 9, 0)
        assert cron == "0 9 * * *"


# =============================================================================
# Tests for _estimate_next_run helper
# =============================================================================


class TestEstimateNextRun:
    """Test _estimate_next_run helper function."""

    def test_daily_next_run_future(self):
        """Test that daily next_run is in the future."""
        now = datetime(2026, 2, 13, 8, 0, 0, tzinfo=timezone.utc)
        next_run = _estimate_next_run("daily", 9, 0, now)
        # 09:00 is in the future relative to 08:00
        assert next_run > now
        assert next_run.hour == 9
        assert next_run.minute == 0

    def test_daily_next_run_wraps_to_tomorrow(self):
        """Test that daily next_run wraps to next day if time already passed."""
        now = datetime(2026, 2, 13, 10, 0, 0, tzinfo=timezone.utc)
        next_run = _estimate_next_run("daily", 9, 0, now)
        # 09:00 already passed, should be tomorrow
        assert next_run.day == 14
        assert next_run.hour == 9

    def test_weekly_next_run(self):
        """Test that weekly next_run advances to next week."""
        # Thursday at 10:00
        now = datetime(2026, 2, 12, 10, 0, 0, tzinfo=timezone.utc)
        next_run = _estimate_next_run("weekly", 9, 0, now)
        # Should advance to next Monday
        assert next_run > now
        assert next_run.weekday() == 0  # Monday

    def test_monthly_next_run_wraps_to_next_month(self):
        """Test that monthly next_run wraps to next month."""
        # February 13 at 10:00 (past the 1st)
        now = datetime(2026, 2, 13, 10, 0, 0, tzinfo=timezone.utc)
        next_run = _estimate_next_run("monthly", 9, 0, now)
        # Should wrap to March 1st
        assert next_run.month == 3
        assert next_run.day == 1
        assert next_run.hour == 9

    def test_monthly_next_run_december_wraps_to_january(self):
        """Test that monthly next_run wraps from December to January."""
        now = datetime(2026, 12, 15, 10, 0, 0, tzinfo=timezone.utc)
        next_run = _estimate_next_run("monthly", 9, 0, now)
        assert next_run.year == 2027
        assert next_run.month == 1
        assert next_run.day == 1

    def test_next_run_is_always_in_future(self):
        """Test that next_run is always after now for all schedule types."""
        now = datetime(2026, 2, 13, 12, 0, 0, tzinfo=timezone.utc)
        for schedule_type in ["daily", "weekly", "monthly"]:
            next_run = _estimate_next_run(schedule_type, 9, 0, now)
            assert next_run > now, f"next_run for {schedule_type} should be in the future"


# =============================================================================
# Tests for schedule_compliance_audit tool function
# =============================================================================


class TestScheduleComplianceAuditTool:
    """Test the schedule_compliance_audit async tool function."""

    @pytest.mark.asyncio
    async def test_default_parameters(self):
        """Test schedule_compliance_audit with all default parameters."""
        result = await schedule_compliance_audit()

        assert isinstance(result, ScheduleComplianceAuditResult)
        assert result.status == "created"
        assert result.schedule_type == "daily"
        assert result.time == "09:00"
        assert result.timezone == "UTC"
        assert result.resource_types == ["all"]
        assert result.recipients == []
        assert result.notification_format == "email"

    @pytest.mark.asyncio
    async def test_schedule_id_format(self):
        """Test that schedule_id follows the expected format."""
        result = await schedule_compliance_audit()

        assert result.schedule_id.startswith("audit-sched-")
        # 'audit-sched-' prefix + 8 hex chars = 20 chars
        assert len(result.schedule_id) == 20

    @pytest.mark.asyncio
    async def test_schedule_id_unique(self):
        """Test that each call generates a unique schedule_id."""
        result1 = await schedule_compliance_audit()
        result2 = await schedule_compliance_audit()

        assert result1.schedule_id != result2.schedule_id

    @pytest.mark.asyncio
    async def test_daily_schedule(self):
        """Test creating a daily schedule."""
        result = await schedule_compliance_audit(schedule="daily", time="08:00")

        assert result.schedule_type == "daily"
        assert result.cron_expression == "0 8 * * *"

    @pytest.mark.asyncio
    async def test_weekly_schedule(self):
        """Test creating a weekly schedule."""
        result = await schedule_compliance_audit(schedule="weekly", time="10:30")

        assert result.schedule_type == "weekly"
        assert result.cron_expression == "30 10 * * MON"

    @pytest.mark.asyncio
    async def test_monthly_schedule(self):
        """Test creating a monthly schedule."""
        result = await schedule_compliance_audit(schedule="monthly", time="14:00")

        assert result.schedule_type == "monthly"
        assert result.cron_expression == "0 14 1 * *"

    @pytest.mark.asyncio
    async def test_custom_time(self):
        """Test custom time parameter."""
        result = await schedule_compliance_audit(time="23:45")

        assert result.time == "23:45"
        assert result.cron_expression == "45 23 * * *"

    @pytest.mark.asyncio
    async def test_custom_timezone(self):
        """Test custom timezone parameter."""
        result = await schedule_compliance_audit(timezone_str="America/New_York")

        assert result.timezone == "America/New_York"

    @pytest.mark.asyncio
    async def test_custom_resource_types(self):
        """Test custom resource_types parameter."""
        resource_types = ["ec2:instance", "rds:db", "s3:bucket"]
        result = await schedule_compliance_audit(resource_types=resource_types)

        assert result.resource_types == resource_types

    @pytest.mark.asyncio
    async def test_default_resource_types_is_all(self):
        """Test that default resource_types is ['all']."""
        result = await schedule_compliance_audit()

        assert result.resource_types == ["all"]

    @pytest.mark.asyncio
    async def test_recipients_list(self):
        """Test recipients parameter."""
        recipients = ["admin@example.com", "finops@example.com"]
        result = await schedule_compliance_audit(recipients=recipients)

        assert result.recipients == recipients

    @pytest.mark.asyncio
    async def test_empty_recipients_default(self):
        """Test that default recipients is empty list."""
        result = await schedule_compliance_audit()

        assert result.recipients == []

    @pytest.mark.asyncio
    async def test_notification_format_email(self):
        """Test email notification format."""
        result = await schedule_compliance_audit(notification_format="email")

        assert result.notification_format == "email"

    @pytest.mark.asyncio
    async def test_notification_format_slack(self):
        """Test slack notification format."""
        result = await schedule_compliance_audit(notification_format="slack")

        assert result.notification_format == "slack"

    @pytest.mark.asyncio
    async def test_notification_format_both(self):
        """Test both notification format."""
        result = await schedule_compliance_audit(notification_format="both")

        assert result.notification_format == "both"

    @pytest.mark.asyncio
    async def test_next_run_is_iso_format(self):
        """Test that next_run is a valid ISO 8601 string."""
        result = await schedule_compliance_audit()

        # Should be parseable as datetime
        parsed = datetime.fromisoformat(result.next_run)
        assert isinstance(parsed, datetime)

    @pytest.mark.asyncio
    async def test_next_run_is_in_the_future(self):
        """Test that next_run is in the future."""
        result = await schedule_compliance_audit()

        next_run = datetime.fromisoformat(result.next_run)
        # Make both timezone-aware for comparison
        now = datetime.now(timezone.utc)
        if next_run.tzinfo is None:
            next_run = next_run.replace(tzinfo=timezone.utc)
        assert next_run > now or (next_run - now).total_seconds() > -60

    @pytest.mark.asyncio
    async def test_message_contains_schedule_info(self):
        """Test that the message contains schedule information."""
        result = await schedule_compliance_audit(
            schedule="weekly",
            time="10:00",
            timezone_str="UTC",
        )

        assert "weekly" in result.message
        assert "10:00" in result.message
        assert "UTC" in result.message

    @pytest.mark.asyncio
    async def test_message_contains_recipients(self):
        """Test that message mentions recipients when provided."""
        result = await schedule_compliance_audit(
            recipients=["admin@example.com"],
        )

        assert "admin@example.com" in result.message

    @pytest.mark.asyncio
    async def test_message_no_recipients_mention_when_empty(self):
        """Test that message does not mention notifications when recipients empty."""
        result = await schedule_compliance_audit(recipients=[])

        assert "Notifications will be sent" not in result.message

    # =========================================================================
    # Validation tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_invalid_schedule_raises_value_error(self):
        """Test that invalid schedule value raises ValueError."""
        with pytest.raises(ValueError, match="Invalid schedule"):
            await schedule_compliance_audit(schedule="biweekly")

    @pytest.mark.asyncio
    async def test_invalid_schedule_hourly_raises_value_error(self):
        """Test that 'hourly' schedule raises ValueError."""
        with pytest.raises(ValueError, match="Invalid schedule"):
            await schedule_compliance_audit(schedule="hourly")

    @pytest.mark.asyncio
    async def test_invalid_time_format_raises_value_error(self):
        """Test that invalid time format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid time"):
            await schedule_compliance_audit(time="9am")

    @pytest.mark.asyncio
    async def test_invalid_time_no_colon_raises_value_error(self):
        """Test that time without colon raises ValueError."""
        with pytest.raises(ValueError, match="Invalid time"):
            await schedule_compliance_audit(time="0900")

    @pytest.mark.asyncio
    async def test_invalid_time_out_of_range_hour(self):
        """Test that hour > 23 raises ValueError."""
        with pytest.raises(ValueError, match="Invalid time"):
            await schedule_compliance_audit(time="25:00")

    @pytest.mark.asyncio
    async def test_invalid_time_out_of_range_minute(self):
        """Test that minute > 59 raises ValueError."""
        with pytest.raises(ValueError, match="Invalid time"):
            await schedule_compliance_audit(time="09:60")

    @pytest.mark.asyncio
    async def test_invalid_time_negative_hour(self):
        """Test that negative hour raises ValueError."""
        with pytest.raises(ValueError, match="Invalid time"):
            await schedule_compliance_audit(time="-1:00")

    @pytest.mark.asyncio
    async def test_invalid_time_extra_parts(self):
        """Test that time with extra parts raises ValueError."""
        with pytest.raises(ValueError, match="Invalid time"):
            await schedule_compliance_audit(time="09:00:00")

    @pytest.mark.asyncio
    async def test_invalid_time_non_numeric(self):
        """Test that non-numeric time raises ValueError."""
        with pytest.raises(ValueError, match="Invalid time"):
            await schedule_compliance_audit(time="ab:cd")

    @pytest.mark.asyncio
    async def test_invalid_notification_format_raises_value_error(self):
        """Test that invalid notification_format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid notification_format"):
            await schedule_compliance_audit(notification_format="sms")

    @pytest.mark.asyncio
    async def test_boundary_time_midnight(self):
        """Test time at midnight (00:00) is valid."""
        result = await schedule_compliance_audit(time="00:00")
        assert result.time == "00:00"

    @pytest.mark.asyncio
    async def test_boundary_time_end_of_day(self):
        """Test time at 23:59 is valid."""
        result = await schedule_compliance_audit(time="23:59")
        assert result.time == "23:59"

    # =========================================================================
    # Constants / valid values tests
    # =========================================================================

    def test_valid_schedule_types_contains_expected(self):
        """Test that VALID_SCHEDULE_TYPES contains daily, weekly, monthly."""
        assert "daily" in VALID_SCHEDULE_TYPES
        assert "weekly" in VALID_SCHEDULE_TYPES
        assert "monthly" in VALID_SCHEDULE_TYPES

    def test_valid_formats_contains_expected(self):
        """Test that VALID_FORMATS contains email, slack, both."""
        assert "email" in VALID_FORMATS
        assert "slack" in VALID_FORMATS
        assert "both" in VALID_FORMATS

    # =========================================================================
    # Full integration-style test with all parameters
    # =========================================================================

    @pytest.mark.asyncio
    async def test_full_configuration(self):
        """Test schedule_compliance_audit with all parameters set."""
        result = await schedule_compliance_audit(
            schedule="weekly",
            time="14:30",
            timezone_str="Europe/London",
            resource_types=["ec2:instance", "s3:bucket"],
            recipients=["admin@example.com", "#slack-channel"],
            notification_format="both",
        )

        assert result.status == "created"
        assert result.schedule_type == "weekly"
        assert result.time == "14:30"
        assert result.timezone == "Europe/London"
        assert result.resource_types == ["ec2:instance", "s3:bucket"]
        assert result.recipients == ["admin@example.com", "#slack-channel"]
        assert result.notification_format == "both"
        assert result.cron_expression == "30 14 * * MON"
        assert result.schedule_id.startswith("audit-sched-")
        assert "weekly" in result.message
        assert "14:30" in result.message
