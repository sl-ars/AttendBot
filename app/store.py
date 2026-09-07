"""Persistent runtime state: WSP credentials, base URL and schedule.

The Telegram command thread mutates state while the attendance thread reads
it, so every access goes through a lock. Writes are atomic (tmp file +
os.replace) with 0600 permissions — the file contains the WSP password in
plain text, exactly like the .env file did before.

Seed chain on first start (no state file yet): WSP_LOGIN/WSP_PASSWORD and
BASE_URL from the environment (one-time import), built-in default schedule.
Once the state file exists it is the single source of truth.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from .schedule import DEFAULT_SCHEDULE_DATA, Schedule

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimeState:
    """Immutable snapshot the attendance loop re-reads every iteration."""

    wsp_login: Optional[str]
    wsp_password: Optional[str]
    base_url: Optional[str]
    schedule: Schedule
    paused: bool


class BotStore:
    """Owns all mutable bot state and persists it to a JSON file on change."""

    def __init__(
        self,
        path: str,
        *,
        seed_login: Optional[str] = None,
        seed_password: Optional[str] = None,
        seed_base_url: Optional[str] = None,
    ) -> None:
        self._path = path
        self._lock = threading.Lock()
        self.paused = False  # runtime-only flag, deliberately not persisted
        self._seed_login = seed_login
        self._seed_password = seed_password
        self._seed_base_url = seed_base_url
        self._data = self._load()

    # ---------- persistence ----------

    def _save_locked(self, data: Dict[str, Any]) -> None:
        tmp = f"{self._path}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self._path)

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self._path):
            try:
                with open(self._path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    Schedule.from_dict(data.get("schedule") or DEFAULT_SCHEDULE_DATA)
                    return data
                logger.error("State file %s is not a JSON object; starting fresh", self._path)
            except (json.JSONDecodeError, ValueError, OSError):
                logger.exception("State file %s unreadable; starting fresh", self._path)

        data: Dict[str, Any] = {
            "wsp_login": self._seed_login,
            "wsp_password": self._seed_password,
            "base_url": self._seed_base_url,
            "schedule": copy.deepcopy(DEFAULT_SCHEDULE_DATA),
        }

        logger.info("Creating state file %s", self._path)
        try:
            with self._lock:
                self._save_locked(data)
        except OSError:
            logger.exception("Cannot write state file %s; state will not persist", self._path)
        return data

    # ---------- reads ----------

    def snapshot(self) -> RuntimeState:
        with self._lock:
            data = self._data
            try:
                schedule = Schedule.from_dict(data.get("schedule") or DEFAULT_SCHEDULE_DATA)
            except ValueError:
                logger.exception("Stored schedule invalid; falling back to default")
                schedule = Schedule.from_dict(DEFAULT_SCHEDULE_DATA)
            return RuntimeState(
                wsp_login=data.get("wsp_login") or None,
                wsp_password=data.get("wsp_password") or None,
                base_url=data.get("base_url") or None,
                schedule=schedule,
                paused=self.paused,
            )

    # ---------- mutations (validate → commit → persist) ----------

    def set_credentials(self, login: str, password: str) -> None:
        with self._lock:
            self._data["wsp_login"] = login
            self._data["wsp_password"] = password
            self._save_locked(self._data)

    def set_base_url(self, url: str) -> None:
        with self._lock:
            self._data["base_url"] = url
            self._save_locked(self._data)

    def update_schedule(self, mutator: Callable[[Dict[str, Any]], None]) -> Schedule:
        """Apply mutator to a copy of the schedule dict, validate, commit, save.

        Raises ValueError (with a readable message) when the result is invalid;
        in that case nothing is committed.
        """
        with self._lock:
            candidate = copy.deepcopy(self._data.get("schedule") or DEFAULT_SCHEDULE_DATA)
            mutator(candidate)
            schedule = Schedule.from_dict(candidate)  # validates
            self._data["schedule"] = candidate
            self._save_locked(self._data)
            return schedule
