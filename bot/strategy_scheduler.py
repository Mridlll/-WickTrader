#!/usr/bin/env python3
"""Strategy Scheduler for WickTrader.

Time-based scheduling for strategy activation/deactivation.
Allows running different strategies at different times of day.

Usage:
    from bot.strategy_scheduler import StrategyScheduler
    scheduler = StrategyScheduler(runner, config)
    await scheduler.run()
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, time
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum

import yaml

# Add project paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from utils.logger import get_logger

logger = get_logger("scheduler")

# Try to import pytz, fall back to UTC-only if not available
try:
    import pytz
    HAS_PYTZ = True
except ImportError:
    HAS_PYTZ = False
    logger.warning("pytz not installed, using UTC only")


class ScheduleType(str, Enum):
    """Types of schedules."""
    ALWAYS_ON = "always_on"
    TIME_BASED = "time_based"


@dataclass
class TimeSchedule:
    """Time-based schedule for a strategy."""
    strategy_name: str
    always_on: bool = True
    hours_start: int = 0      # Hour to start (0-23)
    hours_end: int = 24       # Hour to end (0-24, 24 = midnight)
    minutes_start: int = 0    # Minutes
    minutes_end: int = 0      # Minutes
    days: List[str] = None    # Days of week (mon, tue, wed, thu, fri, sat, sun)
    timezone: str = "UTC"

    def __post_init__(self):
        if self.days is None:
            self.days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

    @classmethod
    def from_config(cls, name: str, config: Dict[str, Any], timezone: str = "UTC") -> "TimeSchedule":
        """Create schedule from config dict.

        Args:
            name: Strategy name
            config: Schedule config from YAML
            timezone: Default timezone

        Returns:
            TimeSchedule instance
        """
        if config.get("always_on", False):
            return cls(strategy_name=name, always_on=True)

        # Parse hours (format: "HH:MM-HH:MM" or "HH-HH")
        hours_str = config.get("hours", "00:00-24:00")
        start_str, end_str = hours_str.split("-")

        # Parse start time
        if ":" in start_str:
            hours_start, minutes_start = map(int, start_str.split(":"))
        else:
            hours_start = int(start_str)
            minutes_start = 0

        # Parse end time
        if ":" in end_str:
            hours_end, minutes_end = map(int, end_str.split(":"))
        else:
            hours_end = int(end_str)
            minutes_end = 0

        # Parse days
        days_config = config.get("days", ["mon", "tue", "wed", "thu", "fri", "sat", "sun"])
        days = [d.lower().strip() for d in days_config]

        return cls(
            strategy_name=name,
            always_on=False,
            hours_start=hours_start,
            hours_end=hours_end,
            minutes_start=minutes_start,
            minutes_end=minutes_end,
            days=days,
            timezone=config.get("timezone", timezone)
        )


class StrategyScheduler:
    """Time-based strategy scheduler.

    Automatically starts/stops strategies based on configured schedules.
    """

    def __init__(self, runner: "MultiStrategyRunner", config: Dict[str, Any]):
        """Initialize scheduler.

        Args:
            runner: MultiStrategyRunner instance to control
            config: Scheduler configuration from YAML
        """
        self.runner = runner
        self.schedules: Dict[str, TimeSchedule] = {}
        self.check_interval: int = 60  # Check every minute
        self._running = False
        self._task: Optional[asyncio.Task] = None

        self._load_schedules(config)

    def _load_schedules(self, config: Dict[str, Any]) -> None:
        """Load schedules from config.

        Args:
            config: Scheduler section from strategies.yaml
        """
        if not config.get("enabled", False):
            logger.info("Scheduler disabled in config")
            return

        default_tz = config.get("timezone", "UTC")
        time_schedules = config.get("time_schedules", {})

        for strategy_name, schedule_config in time_schedules.items():
            schedule = TimeSchedule.from_config(strategy_name, schedule_config, default_tz)
            self.schedules[strategy_name] = schedule

            if schedule.always_on:
                logger.info(f"[{strategy_name}] Schedule: Always On")
            else:
                logger.info(
                    f"[{strategy_name}] Schedule: {schedule.hours_start:02d}:{schedule.minutes_start:02d}-"
                    f"{schedule.hours_end:02d}:{schedule.minutes_end:02d} "
                    f"on {', '.join(schedule.days)}"
                )

    async def run(self) -> None:
        """Main scheduler loop.

        Checks schedules every minute and starts/stops strategies accordingly.
        """
        self._running = True
        logger.info("Scheduler started")

        while self._running:
            try:
                await self._check_and_update_strategies()
                await asyncio.sleep(self.check_interval)

            except asyncio.CancelledError:
                logger.info("Scheduler cancelled")
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(self.check_interval)

        logger.info("Scheduler stopped")

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _check_and_update_strategies(self) -> None:
        """Check all schedules and update strategy states."""
        for name, schedule in self.schedules.items():
            try:
                should_run = self._should_strategy_run(schedule)
                current_status = self.runner.strategies.get(name)

                if not current_status:
                    continue

                is_running = current_status.status.value == "running"

                if should_run and not is_running:
                    logger.info(f"[{name}] Scheduler: Starting (schedule active)")
                    await self.runner.start_strategy(name)

                elif not should_run and is_running:
                    logger.info(f"[{name}] Scheduler: Stopping (schedule inactive)")
                    await self.runner.stop_strategy(name)

            except Exception as e:
                logger.error(f"[{name}] Scheduler check error: {e}")

    def _should_strategy_run(self, schedule: TimeSchedule) -> bool:
        """Check if a strategy should be running based on its schedule.

        Args:
            schedule: TimeSchedule for the strategy

        Returns:
            True if strategy should be running
        """
        if schedule.always_on:
            return True

        # Get current time in the schedule's timezone
        now = self._get_current_time(schedule.timezone)

        # Check day of week
        current_day = now.strftime("%a").lower()
        if current_day not in schedule.days:
            return False

        # Check time range
        current_minutes = now.hour * 60 + now.minute
        start_minutes = schedule.hours_start * 60 + schedule.minutes_start
        end_minutes = schedule.hours_end * 60 + schedule.minutes_end

        # Handle overnight schedules (e.g., 22:00-06:00)
        if start_minutes > end_minutes:
            # Schedule wraps around midnight
            return current_minutes >= start_minutes or current_minutes < end_minutes
        else:
            return start_minutes <= current_minutes < end_minutes

    def _get_current_time(self, timezone: str) -> datetime:
        """Get current time in specified timezone.

        Args:
            timezone: Timezone name (e.g., "UTC", "US/Eastern")

        Returns:
            Current datetime in the timezone
        """
        if HAS_PYTZ and timezone != "UTC":
            try:
                tz = pytz.timezone(timezone)
                return datetime.now(tz)
            except Exception:
                pass

        # Fall back to UTC
        return datetime.utcnow()

    def get_schedule_status(self) -> Dict[str, Any]:
        """Get current schedule status.

        Returns:
            Dictionary with schedule information
        """
        status = {}

        for name, schedule in self.schedules.items():
            should_run = self._should_strategy_run(schedule)

            if schedule.always_on:
                schedule_str = "Always On"
            else:
                schedule_str = (
                    f"{schedule.hours_start:02d}:{schedule.minutes_start:02d}-"
                    f"{schedule.hours_end:02d}:{schedule.minutes_end:02d}"
                )

            status[name] = {
                "schedule": schedule_str,
                "days": schedule.days if not schedule.always_on else "all",
                "should_run": should_run,
                "timezone": schedule.timezone
            }

        return status

    def print_schedule_status(self) -> None:
        """Print formatted schedule status."""
        status = self.get_schedule_status()
        now = datetime.utcnow()

        print("\n  SCHEDULE STATUS")
        print("  " + "-" * 50)
        print(f"  Current time (UTC): {now.strftime('%Y-%m-%d %H:%M')}")
        print()

        for name, info in status.items():
            active = "[ACTIVE]" if info["should_run"] else "[INACTIVE]"
            print(f"  {active} {name}")
            print(f"          Schedule: {info['schedule']}")
            if info["days"] != "all":
                print(f"          Days: {', '.join(info['days'])}")
            print()


async def run_with_scheduler(runner: "MultiStrategyRunner", scheduler_config: Dict[str, Any]) -> None:
    """Run the multi-strategy runner with scheduler.

    Args:
        runner: MultiStrategyRunner instance
        scheduler_config: Scheduler configuration
    """
    scheduler = StrategyScheduler(runner, scheduler_config)

    # Print initial schedule status
    scheduler.print_schedule_status()

    # Start scheduler in background
    scheduler_task = asyncio.create_task(scheduler.run())

    try:
        # Run until cancelled
        await asyncio.gather(scheduler_task, return_exceptions=True)
    except asyncio.CancelledError:
        await scheduler.stop()
