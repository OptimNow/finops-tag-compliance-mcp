"""Unit tests for SchedulerService (Phase 2.4).

Tests the scheduled compliance snapshot service that runs automated
compliance scans on a configurable schedule and stores results in
the history database for trend tracking.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server.services.scheduler_service import SchedulerService

# APScheduler classes are imported locally inside start(), so we mock them
# at their source modules, not on scheduler_service.
ASYNC_SCHEDULER_PATH = "apscheduler.schedulers.asyncio.AsyncIOScheduler"
CRON_TRIGGER_PATH = "apscheduler.triggers.cron.CronTrigger"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_scan_result():
    """Create a mock compliance scan result with expected attributes."""
    result = MagicMock()
    result.compliance_score = 0.75
    result.total_resources = 50
    result.violations = [MagicMock(), MagicMock(), MagicMock()]
    return result


@pytest.fixture
def scan_callback(mock_scan_result):
    """Create a mock async scan callback that returns a compliance result."""
    return AsyncMock(return_value=mock_scan_result)


@pytest.fixture
def store_callback():
    """Create a mock async store callback."""
    return AsyncMock()


@pytest.fixture
def enabled_service(scan_callback, store_callback):
    """Create an enabled SchedulerService with mock callbacks."""
    return SchedulerService(
        scan_callback=scan_callback,
        store_callback=store_callback,
        schedule_hour=2,
        schedule_minute=0,
        enabled=True,
    )


@pytest.fixture
def disabled_service(scan_callback, store_callback):
    """Create a disabled SchedulerService."""
    return SchedulerService(
        scan_callback=scan_callback,
        store_callback=store_callback,
        enabled=False,
    )


# =============================================================================
# Initial State Tests
# =============================================================================


class TestInitialState:
    """Tests for default property values on a freshly created service."""

    def test_is_not_running_initially(self, enabled_service):
        assert enabled_service.is_running is False

    def test_is_enabled_when_configured(self, enabled_service):
        assert enabled_service.is_enabled is True

    def test_is_disabled_when_configured(self, disabled_service):
        assert disabled_service.is_enabled is False

    def test_last_run_is_none(self, enabled_service):
        assert enabled_service.last_run is None

    def test_last_status_is_none(self, enabled_service):
        assert enabled_service.last_status is None

    def test_last_error_is_none(self, enabled_service):
        assert enabled_service.last_error is None

    def test_run_count_is_zero(self, enabled_service):
        assert enabled_service.run_count == 0


# =============================================================================
# Start Tests
# =============================================================================


class TestStart:
    """Tests for starting the scheduler."""

    async def test_start_when_enabled(self, enabled_service):
        """Starting an enabled service returns True and sets running=True."""
        with patch(ASYNC_SCHEDULER_PATH) as MockScheduler, patch(
            CRON_TRIGGER_PATH
        ) as MockTrigger:
            mock_scheduler_instance = MagicMock()
            MockScheduler.return_value = mock_scheduler_instance
            MockTrigger.return_value = MagicMock()

            result = await enabled_service.start()

        assert result is True
        assert enabled_service.is_running is True
        mock_scheduler_instance.start.assert_called_once()
        mock_scheduler_instance.add_job.assert_called_once()

    async def test_start_when_disabled(self, disabled_service):
        """Starting a disabled service returns False and does not start scheduler."""
        result = await disabled_service.start()

        assert result is False
        assert disabled_service.is_running is False

    async def test_start_without_apscheduler_installed(self, enabled_service):
        """When apscheduler is not installed, returns False gracefully."""
        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if "apscheduler" in name:
                raise ImportError("No module named 'apscheduler'")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            result = await enabled_service.start()

        assert result is False
        assert enabled_service.is_running is False

    async def test_start_scheduler_creation_failure(self, enabled_service):
        """When APScheduler constructor throws, returns False."""
        with patch(
            ASYNC_SCHEDULER_PATH,
            side_effect=RuntimeError("Scheduler init failed"),
        ), patch(CRON_TRIGGER_PATH):
            result = await enabled_service.start()

        assert result is False
        assert enabled_service.is_running is False

    async def test_start_configures_cron_trigger(self, scan_callback, store_callback):
        """Cron trigger is created with the correct schedule parameters."""
        service = SchedulerService(
            scan_callback=scan_callback,
            store_callback=store_callback,
            schedule_hour=14,
            schedule_minute=30,
            schedule_timezone="America/New_York",
            enabled=True,
        )

        with patch(ASYNC_SCHEDULER_PATH) as MockScheduler, patch(
            CRON_TRIGGER_PATH
        ) as MockTrigger:
            MockScheduler.return_value = MagicMock()
            MockTrigger.return_value = MagicMock()

            await service.start()

            MockTrigger.assert_called_once_with(
                hour=14,
                minute=30,
                timezone="America/New_York",
            )

    async def test_start_adds_job_with_correct_id(self, enabled_service):
        """Job is added with id='daily_compliance_snapshot'."""
        with patch(ASYNC_SCHEDULER_PATH) as MockScheduler, patch(CRON_TRIGGER_PATH):
            mock_inst = MagicMock()
            MockScheduler.return_value = mock_inst

            await enabled_service.start()

            call_kwargs = mock_inst.add_job.call_args
            assert call_kwargs.kwargs["id"] == "daily_compliance_snapshot"
            assert call_kwargs.kwargs["replace_existing"] is True
            assert call_kwargs.kwargs["misfire_grace_time"] == 3600


# =============================================================================
# Stop Tests
# =============================================================================


class TestStop:
    """Tests for stopping the scheduler."""

    async def test_stop_running_scheduler(self, enabled_service):
        """Stopping a running scheduler calls shutdown and sets running=False."""
        with patch(ASYNC_SCHEDULER_PATH) as MockScheduler, patch(CRON_TRIGGER_PATH):
            mock_inst = MagicMock()
            MockScheduler.return_value = mock_inst

            await enabled_service.start()
            assert enabled_service.is_running is True

            await enabled_service.stop()

        assert enabled_service.is_running is False
        mock_inst.shutdown.assert_called_once_with(wait=False)

    async def test_stop_when_not_running(self, enabled_service):
        """Stopping when not running does not raise an error."""
        assert enabled_service.is_running is False
        await enabled_service.stop()  # Should not raise
        assert enabled_service.is_running is False

    async def test_stop_handles_shutdown_exception(self, enabled_service):
        """If shutdown throws, the service handles it gracefully."""
        with patch(ASYNC_SCHEDULER_PATH) as MockScheduler, patch(CRON_TRIGGER_PATH):
            mock_inst = MagicMock()
            mock_inst.shutdown.side_effect = RuntimeError("Shutdown error")
            MockScheduler.return_value = mock_inst

            await enabled_service.start()
            # Should not raise
            await enabled_service.stop()


# =============================================================================
# Run Snapshot Tests
# =============================================================================


class TestRunSnapshot:
    """Tests for the _run_snapshot method (via run_now)."""

    async def test_run_snapshot_success(
        self, enabled_service, scan_callback, store_callback, mock_scan_result
    ):
        """Successful snapshot calls scan then store, updates status."""
        await enabled_service.run_now()

        scan_callback.assert_called_once()
        store_callback.assert_called_once_with(mock_scan_result)
        assert enabled_service.last_status == "success"
        assert enabled_service.last_error is None
        assert enabled_service.run_count == 1
        assert enabled_service.last_run is not None
        assert isinstance(enabled_service.last_run, datetime)

    async def test_run_snapshot_scan_failure(self, store_callback):
        """When scan_callback raises, status becomes 'error'."""
        failing_scan = AsyncMock(side_effect=RuntimeError("AWS API timeout"))

        service = SchedulerService(
            scan_callback=failing_scan,
            store_callback=store_callback,
            enabled=True,
        )

        await service.run_now()

        assert service.last_status == "error"
        assert "AWS API timeout" in service.last_error
        assert service.run_count == 0  # Failed runs don't increment count
        store_callback.assert_not_called()
        assert service.last_run is not None

    async def test_run_snapshot_store_failure(self, scan_callback, mock_scan_result):
        """When store_callback raises, status becomes 'error'."""
        failing_store = AsyncMock(side_effect=RuntimeError("Database write failed"))

        service = SchedulerService(
            scan_callback=scan_callback,
            store_callback=failing_store,
            enabled=True,
        )

        await service.run_now()

        assert service.last_status == "error"
        assert "Database write failed" in service.last_error
        assert service.run_count == 0
        scan_callback.assert_called_once()

    async def test_run_snapshot_sets_last_run_timestamp(self, enabled_service):
        """last_run is set to a datetime around the time of execution."""
        before = datetime.now(timezone.utc)
        await enabled_service.run_now()
        after = datetime.now(timezone.utc)

        assert enabled_service.last_run is not None
        assert before <= enabled_service.last_run <= after

    async def test_run_snapshot_clears_previous_error_on_success(self, store_callback):
        """After a failure, a successful run clears last_error."""
        scan_cb = AsyncMock()
        # First call fails, second succeeds
        result = MagicMock()
        result.compliance_score = 0.80
        result.total_resources = 20
        result.violations = []
        scan_cb.side_effect = [RuntimeError("Temporary failure"), result]

        service = SchedulerService(
            scan_callback=scan_cb,
            store_callback=store_callback,
            enabled=True,
        )

        await service.run_now()
        assert service.last_status == "error"
        assert service.last_error is not None

        await service.run_now()
        assert service.last_status == "success"
        assert service.last_error is None


# =============================================================================
# Run Now Tests
# =============================================================================


class TestRunNow:
    """Tests for the run_now() public method."""

    async def test_run_now_delegates_to_run_snapshot(
        self, enabled_service, scan_callback, store_callback
    ):
        """run_now calls _run_snapshot which invokes callbacks."""
        await enabled_service.run_now()

        scan_callback.assert_called_once()
        store_callback.assert_called_once()

    async def test_run_now_works_without_scheduler_started(
        self, enabled_service, scan_callback
    ):
        """run_now works even if start() was never called."""
        assert enabled_service.is_running is False
        await enabled_service.run_now()
        scan_callback.assert_called_once()

    async def test_run_now_on_disabled_service(self, disabled_service):
        """run_now can be called on a disabled service (manual trigger)."""
        await disabled_service.run_now()
        assert disabled_service.last_status == "success"
        assert disabled_service.run_count == 1


# =============================================================================
# Properties Tests
# =============================================================================


class TestProperties:
    """Tests for all scheduler properties."""

    async def test_is_running_after_start(self, enabled_service):
        with patch(ASYNC_SCHEDULER_PATH) as MockScheduler, patch(CRON_TRIGGER_PATH):
            MockScheduler.return_value = MagicMock()
            await enabled_service.start()
            assert enabled_service.is_running is True

    async def test_is_running_after_stop(self, enabled_service):
        with patch(ASYNC_SCHEDULER_PATH) as MockScheduler, patch(CRON_TRIGGER_PATH):
            MockScheduler.return_value = MagicMock()
            await enabled_service.start()
            await enabled_service.stop()
            assert enabled_service.is_running is False

    def test_is_enabled_reflects_config_true(self, scan_callback, store_callback):
        service = SchedulerService(
            scan_callback=scan_callback,
            store_callback=store_callback,
            enabled=True,
        )
        assert service.is_enabled is True

    def test_is_enabled_reflects_config_false(self, scan_callback, store_callback):
        service = SchedulerService(
            scan_callback=scan_callback,
            store_callback=store_callback,
            enabled=False,
        )
        assert service.is_enabled is False

    async def test_last_run_type(self, enabled_service):
        await enabled_service.run_now()
        assert isinstance(enabled_service.last_run, datetime)

    async def test_last_status_success(self, enabled_service):
        await enabled_service.run_now()
        assert enabled_service.last_status == "success"

    async def test_last_status_error(self, store_callback):
        service = SchedulerService(
            scan_callback=AsyncMock(side_effect=Exception("boom")),
            store_callback=store_callback,
            enabled=True,
        )
        await service.run_now()
        assert service.last_status == "error"

    async def test_last_error_on_failure(self, store_callback):
        service = SchedulerService(
            scan_callback=AsyncMock(side_effect=ValueError("bad input")),
            store_callback=store_callback,
            enabled=True,
        )
        await service.run_now()
        assert service.last_error == "bad input"

    async def test_run_count_increments(self, enabled_service):
        assert enabled_service.run_count == 0
        await enabled_service.run_now()
        assert enabled_service.run_count == 1
        await enabled_service.run_now()
        assert enabled_service.run_count == 2
        await enabled_service.run_now()
        assert enabled_service.run_count == 3


# =============================================================================
# Get Status Tests
# =============================================================================


class TestGetStatus:
    """Tests for the get_status() method."""

    def test_get_status_initial(self, enabled_service):
        """Initial status has all expected keys with correct initial values."""
        status = enabled_service.get_status()

        assert status["enabled"] is True
        assert status["running"] is False
        assert "02:00 UTC" in status["schedule"]
        assert status["run_count"] == 0
        assert status["last_run"] is None
        assert status["last_status"] is None
        assert status["last_error"] is None

    def test_get_status_disabled_service(self, disabled_service):
        status = disabled_service.get_status()
        assert status["enabled"] is False
        assert status["running"] is False

    async def test_get_status_after_successful_run(self, enabled_service):
        await enabled_service.run_now()
        status = enabled_service.get_status()

        assert status["run_count"] == 1
        assert status["last_run"] is not None
        assert status["last_status"] == "success"
        assert status["last_error"] is None

    async def test_get_status_after_failed_run(self, store_callback):
        service = SchedulerService(
            scan_callback=AsyncMock(side_effect=Exception("scan crashed")),
            store_callback=store_callback,
            enabled=True,
        )
        await service.run_now()
        status = service.get_status()

        assert status["run_count"] == 0
        assert status["last_status"] == "error"
        assert status["last_error"] == "scan crashed"
        assert status["last_run"] is not None

    def test_get_status_custom_schedule(self, scan_callback, store_callback):
        service = SchedulerService(
            scan_callback=scan_callback,
            store_callback=store_callback,
            schedule_hour=14,
            schedule_minute=30,
            schedule_timezone="Europe/London",
            enabled=True,
        )
        status = service.get_status()
        assert "14:30 Europe/London" in status["schedule"]

    async def test_get_status_includes_next_run_when_active(self, enabled_service):
        """When scheduler is running, status includes next_run."""
        with patch(ASYNC_SCHEDULER_PATH) as MockScheduler, patch(CRON_TRIGGER_PATH):
            mock_inst = MagicMock()
            mock_job = MagicMock()
            mock_job.next_run_time = datetime(
                2026, 3, 1, 2, 0, 0, tzinfo=timezone.utc
            )
            mock_inst.get_job.return_value = mock_job
            MockScheduler.return_value = mock_inst

            await enabled_service.start()

            status = enabled_service.get_status()

        assert "next_run" in status
        assert "2026-03-01" in status["next_run"]

    async def test_get_status_no_next_run_when_job_missing(self, enabled_service):
        """When get_job returns None, next_run is not in status."""
        with patch(ASYNC_SCHEDULER_PATH) as MockScheduler, patch(CRON_TRIGGER_PATH):
            mock_inst = MagicMock()
            mock_inst.get_job.return_value = None
            MockScheduler.return_value = mock_inst

            await enabled_service.start()

            status = enabled_service.get_status()

        assert "next_run" not in status

    async def test_get_status_handles_get_job_exception(self, enabled_service):
        """If get_job throws, next_run is simply omitted."""
        with patch(ASYNC_SCHEDULER_PATH) as MockScheduler, patch(CRON_TRIGGER_PATH):
            mock_inst = MagicMock()
            mock_inst.get_job.side_effect = RuntimeError("Job store error")
            MockScheduler.return_value = mock_inst

            await enabled_service.start()

            status = enabled_service.get_status()

        assert "next_run" not in status


# =============================================================================
# Multiple Runs Tests
# =============================================================================


class TestMultipleRuns:
    """Tests for multiple sequential snapshot runs."""

    async def test_run_count_increments_on_success(self, enabled_service):
        """run_count increments for each successful run."""
        for i in range(5):
            await enabled_service.run_now()
            assert enabled_service.run_count == i + 1

    async def test_run_count_does_not_increment_on_failure(self, store_callback):
        """Failed runs do not increment run_count."""
        service = SchedulerService(
            scan_callback=AsyncMock(side_effect=Exception("fail")),
            store_callback=store_callback,
            enabled=True,
        )

        await service.run_now()
        await service.run_now()
        await service.run_now()

        assert service.run_count == 0

    async def test_mixed_success_and_failure_count(self, store_callback):
        """run_count only counts successful runs in a mixed sequence."""
        result_ok = MagicMock()
        result_ok.compliance_score = 0.9
        result_ok.total_resources = 10
        result_ok.violations = []

        scan_cb = AsyncMock()
        scan_cb.side_effect = [
            result_ok,                  # success: count=1
            RuntimeError("fail"),       # fail: count=1
            result_ok,                  # success: count=2
            RuntimeError("fail again"), # fail: count=2
            result_ok,                  # success: count=3
        ]

        service = SchedulerService(
            scan_callback=scan_cb,
            store_callback=store_callback,
            enabled=True,
        )

        await service.run_now()
        assert service.run_count == 1
        assert service.last_status == "success"

        await service.run_now()
        assert service.run_count == 1
        assert service.last_status == "error"

        await service.run_now()
        assert service.run_count == 2
        assert service.last_status == "success"

        await service.run_now()
        assert service.run_count == 2

        await service.run_now()
        assert service.run_count == 3

    async def test_last_run_updates_each_time(self, enabled_service):
        """last_run timestamp updates with each call."""
        await enabled_service.run_now()
        first_run = enabled_service.last_run

        await enabled_service.run_now()
        second_run = enabled_service.last_run

        assert second_run >= first_run


# =============================================================================
# Scheduler Lifecycle Tests
# =============================================================================


class TestSchedulerLifecycle:
    """Tests for the full start -> run -> stop lifecycle."""

    async def test_full_lifecycle(
        self, enabled_service, scan_callback, store_callback
    ):
        """Start, run_now, stop sequence works correctly."""
        with patch(ASYNC_SCHEDULER_PATH) as MockScheduler, patch(CRON_TRIGGER_PATH):
            mock_inst = MagicMock()
            MockScheduler.return_value = mock_inst

            # Start
            started = await enabled_service.start()
            assert started is True
            assert enabled_service.is_running is True

            # Run
            await enabled_service.run_now()
            assert enabled_service.run_count == 1
            assert enabled_service.last_status == "success"

            # Stop
            await enabled_service.stop()
            assert enabled_service.is_running is False

            # State persists after stop
            assert enabled_service.run_count == 1
            assert enabled_service.last_status == "success"

    async def test_run_now_after_stop(
        self, enabled_service, scan_callback, store_callback
    ):
        """run_now still works after scheduler has been stopped."""
        with patch(ASYNC_SCHEDULER_PATH) as MockScheduler, patch(CRON_TRIGGER_PATH):
            MockScheduler.return_value = MagicMock()

            await enabled_service.start()
            await enabled_service.stop()

            # Manual trigger still works
            await enabled_service.run_now()
            assert enabled_service.run_count == 1

    async def test_double_stop_is_safe(self, enabled_service):
        """Calling stop() twice does not raise."""
        with patch(ASYNC_SCHEDULER_PATH) as MockScheduler, patch(CRON_TRIGGER_PATH):
            MockScheduler.return_value = MagicMock()

            await enabled_service.start()
            await enabled_service.stop()
            await enabled_service.stop()  # Second stop should be safe

            assert enabled_service.is_running is False


# =============================================================================
# Constructor Configuration Tests
# =============================================================================


class TestConstructorConfiguration:
    """Tests for constructor parameter handling."""

    def test_default_schedule(self, scan_callback, store_callback):
        service = SchedulerService(
            scan_callback=scan_callback,
            store_callback=store_callback,
        )
        status = service.get_status()
        assert "02:00 UTC" in status["schedule"]
        assert service.is_enabled is True

    def test_custom_schedule(self, scan_callback, store_callback):
        service = SchedulerService(
            scan_callback=scan_callback,
            store_callback=store_callback,
            schedule_hour=23,
            schedule_minute=45,
            schedule_timezone="Asia/Tokyo",
        )
        status = service.get_status()
        assert "23:45 Asia/Tokyo" in status["schedule"]

    def test_enabled_default_true(self, scan_callback, store_callback):
        service = SchedulerService(
            scan_callback=scan_callback,
            store_callback=store_callback,
        )
        assert service.is_enabled is True

    def test_explicitly_disabled(self, scan_callback, store_callback):
        service = SchedulerService(
            scan_callback=scan_callback,
            store_callback=store_callback,
            enabled=False,
        )
        assert service.is_enabled is False
