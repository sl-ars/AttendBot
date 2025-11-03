from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Dict, Iterable, List, Tuple
from zoneinfo import ZoneInfo

WEEKDAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _parse_time(s: str) -> time:
    hh, mm = s.strip().split(":")
    return time(hour=int(hh), minute=int(mm))


def _parse_windows(vals: Iterable[str] | None) -> List[Tuple[time, time]]:
    if not vals:
        return []
    out: List[Tuple[time, time]] = []
    for v in vals:
        start_s, end_s = v.replace(" ", "").split("-")
        out.append((_parse_time(start_s), _parse_time(end_s)))
    return out


@dataclass(frozen=True)
class DayRule:
    enabled: bool
    windows: List[Tuple[time, time]]  # [(start, end), ...]


@dataclass(frozen=True)
class Schedule:
    tz: ZoneInfo
    default_windows: List[Tuple[time, time]]
    days: Dict[int, DayRule] = field(default_factory=dict)  # weekday index -> DayRule

    @classmethod
    def from_toml(cls, path: str) -> "Schedule":
        with open(path, "rb") as f:
            data = tomllib.load(f)

        tz = ZoneInfo(data["timezone"])
        default_windows = _parse_windows(data.get("defaults", {}).get("windows"))

        days: Dict[int, DayRule] = {}
        wd = data.get("weekdays", {})
        for idx, name in enumerate(WEEKDAY_ORDER):
            d = wd.get(name, {})
            enabled = bool(d.get("enabled", True))
            windows = _parse_windows(d.get("windows")) or default_windows
            days[idx] = DayRule(enabled=enabled, windows=windows)

        return cls(tz=tz, default_windows=default_windows, days=days)

    # ---- Queries ----

    def is_open(self, dt: datetime) -> bool:
        """Return True if dt (converted to schedule tz) is inside any window."""
        dt = dt.astimezone(self.tz)
        rule = self.days[dt.weekday()]
        if not rule.enabled or not rule.windows:
            return False

        for start_t, end_t in rule.windows:
            start_dt = dt.replace(hour=start_t.hour, minute=start_t.minute, second=0, microsecond=0)
            end_dt = dt.replace(hour=end_t.hour, minute=end_t.minute, second=0, microsecond=0)
            if end_t <= start_t:  # overnight window
                end_dt += timedelta(days=1)
            if start_dt <= dt < end_dt:
                return True
        return False

    def seconds_until_next_open(self, dt: datetime) -> int:
        """Seconds until the next time we are inside an open window. 0 if already open."""
        dt = dt.astimezone(self.tz)

        for day_offset in range(0, 8):  # look up to one week ahead
            cur = dt + timedelta(days=day_offset)
            rule = self.days[cur.weekday()]
            if not rule.enabled or not rule.windows:
                continue

            for start_t, end_t in rule.windows:
                start_dt = cur.replace(hour=start_t.hour, minute=start_t.minute, second=0, microsecond=0)
                end_dt = cur.replace(hour=end_t.hour, minute=end_t.minute, second=0, microsecond=0)
                if end_t <= start_t:
                    end_dt += timedelta(days=1)

                if dt < end_dt:
                    if dt < start_dt:
                        return max(0, int((start_dt - dt).total_seconds()))
                    if start_dt <= dt < end_dt:
                        return 0

        # Fallback — shouldn't happen with weekly coverage; wake in 1 hour.
        return 3600
