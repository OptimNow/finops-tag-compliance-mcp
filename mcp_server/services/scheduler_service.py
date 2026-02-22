# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Scheduled compliance snapshot service.

Runs automated compliance scans on a configurable schedule and stores
results in the history database for trend tracking.

Phase 2.4: Daily Compliance Snapshots
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class SchedulerService:
    """Manages scheduled compliance scans using APScheduler.

    On start, adds a cron job that:
    1. Runs a full compliance scan (all resource types, all regions)
    2. Stores the result in the history database
    3. Logs success/failure with scan metadata

    Usage::

        scheduler = SchedulerService(
            scan_callback=my_scan_function,
            store_callback=my_store_function,
            schedule_hour=2,
            schedule_minute=0,
        )
        await scheduler.start()
        # ... server runs ...
        await scheduler.stop()
    """

    def __init__(
        self,
        scan_callback: Callable,
        store_callback: Callable,
        schedule_hour: int = 2,
        schedule_minute: int = 0,
        schedule_timezone: str = "UTC",
        enabled: bool = True,
    ):
        """Initialize the scheduler service.

        Args:
            scan_callback: Async function that performs a compliance scan.
                          Signature: async () -> ComplianceResult
            store_callback: Async function that stores a scan result.
                          Signature: async (ComplianceResult) -> None
            schedule_hour: Hour to run the daily scan (0-23, default: 2)
            schedule_minute: Minute to run the daily scan (0-59, default: 0)
            schedule_timezone: Timezone for the schedule (default: "UTC")
            enabled: Whether the scheduler is active (default: True)
        """
        self._scan_callback = scan_callback
        self._store_callback = store_callback
        self._schedule_hour = schedule_hour
        self._schedule_minute = schedule_minute
        self._schedule_timezone = schedule_timezone
        self._enabled = enabled
        self._scheduler: Optional[Any] = None
        self._running = False
        self._last_run: Optional[datetime] = None
        self._last_status: Optional[str] = None
        self._last_error: Optional[str] = None
        self._run_count: int = 0

    async def start(self) -> bool:
        """Start the scheduler.

        Returns:
            True if started successfully, False if disabled or failed.
        """
        if not self._enabled:
            logger.info("SchedulerService: disabled via configuration")
            return False

        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.cron import CronTrigger
        except ImportError:
            logger.warning(
                "SchedulerService: apscheduler not installed. "
                "Install with: pip install apscheduler>=3.10.0"
            )
            return False

        try:
            self._scheduler = AsyncIOScheduler()

            trigger = CronTrigger(
                hour=self._schedule_hour,
                minute=self._schedule_minute,
                timezone=self._schedule_timezone,
            )

            self._scheduler.add_job(
                self._run_snapshot,
                trigger=trigger,
                id="daily_compliance_snapshot",
                name="Daily Compliance Snapshot",
                replace_existing=True,
                misfire_grace_time=3600,  # Allow up to 1 hour late
            )

            self._scheduler.start()
            self._running = True

            logger.info(
                f"SchedulerService: started daily compliance snapshot "
                f"(schedule: {self._schedule_hour:02d}:{self._schedule_minute:02d} "
                f"{self._schedule_timezone})"
            )
            return True

        except Exception as e:
            logger.error(f"SchedulerService: failed to start: {e}")
            self._running = False
            return False

    async def stop(self) -> None:
        """Stop the scheduler gracefully."""
        if self._scheduler and self._running:
            try:
                self._scheduler.shutdown(wait=False)
                self._running = False
                logger.info("SchedulerService: stopped")
            except Exception as e:
                logger.warning(f"SchedulerService: error during shutdown: {e}")

    async def _run_snapshot(self) -> None:
        """Execute a compliance snapshot scan.

        This is the job function called by APScheduler.
        """
        start_time = datetime.now(timezone.utc)
        logger.info("SchedulerService: starting scheduled compliance snapshot")

        try:
            # Run the compliance scan
            result = await self._scan_callback()

            # Store the result in history
            await self._store_callback(result)

            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            self._last_run = start_time
            self._last_status = "success"
            self._last_error = None
            self._run_count += 1

            logger.info(
                f"SchedulerService: snapshot complete "
                f"(score={result.compliance_score:.1%}, "
                f"resources={result.total_resources}, "
                f"violations={len(result.violations)}, "
                f"elapsed={elapsed:.1f}s)"
            )

        except Exception as e:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            self._last_run = start_time
            self._last_status = "error"
            self._last_error = str(e)

            logger.error(
                f"SchedulerService: snapshot failed after {elapsed:.1f}s: {e}"
            )

    async def run_now(self) -> None:
        """Trigger an immediate compliance snapshot (for testing or manual use)."""
        logger.info("SchedulerService: manual snapshot triggered")
        await self._run_snapshot()

    @property
    def is_running(self) -> bool:
        """Whether the scheduler is currently running."""
        return self._running

    @property
    def is_enabled(self) -> bool:
        """Whether the scheduler is configured as enabled."""
        return self._enabled

    @property
    def last_run(self) -> Optional[datetime]:
        """Timestamp of the last snapshot run."""
        return self._last_run

    @property
    def last_status(self) -> Optional[str]:
        """Status of the last run: 'success' or 'error'."""
        return self._last_status

    @property
    def last_error(self) -> Optional[str]:
        """Error message from the last failed run, if any."""
        return self._last_error

    @property
    def run_count(self) -> int:
        """Number of snapshots completed since server start."""
        return self._run_count

    def get_status(self) -> dict:
        """Get scheduler status for health checks.

        Returns:
            Dictionary with scheduler state, suitable for /health endpoint.
        """
        status = {
            "enabled": self._enabled,
            "running": self._running,
            "schedule": (
                f"{self._schedule_hour:02d}:{self._schedule_minute:02d} "
                f"{self._schedule_timezone}"
            ),
            "run_count": self._run_count,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "last_status": self._last_status,
            "last_error": self._last_error,
        }

        # Add next run time if scheduler is active
        if self._scheduler and self._running:
            try:
                job = self._scheduler.get_job("daily_compliance_snapshot")
                if job and job.next_run_time:
                    status["next_run"] = job.next_run_time.isoformat()
            except Exception:
                pass

        return status
