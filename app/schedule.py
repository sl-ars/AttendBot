from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

WEEKDAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# Built-in schedule used when neither the state file nor schedule.toml exists.
DEFAULT_SCHEDULE_DATA: Dict[str, Any] = {
    "timezone": "Asia/Almaty",
    "defaults": {"windows": ["07:00-22:00"]},
    "weekdays": {},
}


def _parse_time(s: str) -> time:
    hh, mm = s.strip().split(":")
    return time(hour=int(hh), minute=int(mm))


def parse_windows(vals: Iterable[str] | None) -> List[Tuple[time, time]]:
    """Parse "HH:MM-HH:MM" strings; raises ValueError with a readable message."""
    out: List[Tuple[time, time]] = []
    for v in vals or []:
        cleaned = v.replace(" ", "")
        if "-" not in cleaned:
            raise ValueError(f"неверное окно {v!r}: ожидается HH:MM-HH:MM")
        start_s, end_s = cleaned.split("-", 1)
        try:
            out.append((_parse_time(start_s), _parse_time(end_s)))
        except ValueError as e:
            raise ValueError(f"неверное окно {v!r}: {e}") from e
    return out


def format_window(w: Tuple[time, time]) -> str:
    return f"{w[0]:%H:%M}-{w[1]:%H:%M}"


@dataclass(frozen=True)
class DayRule:
    enabled: bool
    windows: List[Tuple[time, time]]  # [(start, end), ...]


@dataclass(frozen=True)
class Schedule:
    tz: ZoneInfo
    default_windows: List[Tuple[time, time]]
    days: Dict[int, DayRule] = field(default_factory=dict)  # weekday index -> DayRule

    # ---- Construction ----

    @classmethod
    def from_toml(cls, path: str) -> "Schedule":
        with open(path, "rb") as f:
            return cls.from_dict(tomllib.load(f))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Schedule":
        tz_name = data.get("timezone")
        if not tz_name:
            raise ValueError("расписание: не задан 'timezone'")
        try:
            tz = ZoneInfo(str(tz_name))
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(f"расписание: неизвестный часовой пояс {tz_name!r}") from e

        default_windows = parse_windows(data.get("defaults", {}).get("windows"))

        days: Dict[int, DayRule] = {}
        wd = data.get("weekdays", {}) or {}
        for idx, name in enumerate(WEEKDAY_ORDER):
            d = wd.get(name, {}) or {}
            enabled = bool(d.get("enabled", True))
            windows = parse_windows(d.get("windows")) or default_windows
            days[idx] = DayRule(enabled=enabled, windows=windows)

        return cls(tz=tz, default_windows=default_windows, days=days)

    def to_dict(self) -> Dict[str, Any]:
        """Canonical dict (same shape as schedule.toml / the state file).

        A day that uses the default windows omits 'windows', so later edits of
        the defaults still propagate to it.
        """
        wd: Dict[str, Any] = {}
        for idx, name in enumerate(WEEKDAY_ORDER):
            rule = self.days[idx]
            entry: Dict[str, Any] = {"enabled": rule.enabled}
            if rule.windows != self.default_windows:
                entry["windows"] = [format_window(w) for w in rule.windows]
            wd[name] = entry
        return {
            "timezone": self.tz.key,
            "defaults": {"windows": [format_window(w) for w in self.default_windows]},
            "weekdays": wd,
        }

    # ---- Queries ----

    def _window_bounds(self, day: datetime, start_t: time, end_t: time) -> Tuple[datetime, datetime]:
        start_dt = day.replace(hour=start_t.hour, minute=start_t.minute, second=0, microsecond=0)
        end_dt = day.replace(hour=end_t.hour, minute=end_t.minute, second=0, microsecond=0)
        if end_t <= start_t:  # overnight window
            end_dt += timedelta(days=1)
        return start_dt, end_dt

    def is_open(self, dt: datetime) -> bool:
        """Return True if dt (converted to schedule tz) is inside any window.

        Checks yesterday's rule too, so the second half of an overnight window
        (e.g. 22:00-02:00 after midnight) counts as open.
        """
        dt = dt.astimezone(self.tz)
        for day_offset in (0, -1):
            cur = dt + timedelta(days=day_offset)
            rule = self.days[cur.weekday()]
            if not rule.enabled or not rule.windows:
                continue
            for start_t, end_t in rule.windows:
                start_dt, end_dt = self._window_bounds(cur, start_t, end_t)
                if start_dt <= dt < end_dt:
                    return True
        return False

    def seconds_until_next_open(self, dt: datetime) -> int:
        """Seconds until the next time we are inside an open window. 0 if already open."""
        dt = dt.astimezone(self.tz)

        for day_offset in range(-1, 8):  # yesterday's overnight window … one week ahead
            cur = dt + timedelta(days=day_offset)
            rule = self.days[cur.weekday()]
            if not rule.enabled or not rule.windows:
                continue
            for start_t, end_t in rule.windows:
                start_dt, end_dt = self._window_bounds(cur, start_t, end_t)
                if dt < end_dt:
                    if dt < start_dt:
                        return max(0, int((start_dt - dt).total_seconds()))
                    return 0

        # Fallback — shouldn't happen with weekly coverage; wake in 1 hour.
        return 3600

    def seconds_until_close(self, dt: datetime) -> Optional[int]:
        """Seconds until the currently open window ends. None if not inside any window."""
        dt = dt.astimezone(self.tz)
        for day_offset in (0, -1):
            cur = dt + timedelta(days=day_offset)
            rule = self.days[cur.weekday()]
            if not rule.enabled or not rule.windows:
                continue
            for start_t, end_t in rule.windows:
                start_dt, end_dt = self._window_bounds(cur, start_t, end_t)
                if start_dt <= dt < end_dt:
                    return int((end_dt - dt).total_seconds())
        return None

    # ---- Presentation ----

    def describe(self) -> str:
        names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        lines = [f"Timezone: {self.tz.key}"]
        for idx, rule in self.days.items():
            if not rule.enabled:
                lines.append(f"• {names[idx]}: off")
                continue
            windows = ", ".join(format_window(w) for w in rule.windows)
            lines.append(f"• {names[idx]}: {windows or 'default'}")
        return "\n".join(lines)
