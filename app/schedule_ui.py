"""Interactive /schedule editor via Telegram inline keyboards.

Stateless by design: every button press encodes the full UI state in
callback_data (kept under Telegram's 64-byte limit), and screens are
re-rendered from the store on every click — no sessions to expire, and
buttons on old messages keep working after a restart. Mutations go through
``BotStore.update_schedule`` (validate-then-commit, lock-protected).

Callback grammar ("t" = target: 0..6 weekday, 7 = default windows):
  sch:m                        main menu
  sch:d:<t>                    day/defaults menu
  sch:t:<t>                    toggle day on/off (t < 7)
  sch:c:<t>                    reset day to default windows (t < 7)
  sch:x:<t>:<i>                delete window i of target t
  sch:w:<t>:sh[:<H>]           add-window wizard: start hour / start minute
  sch:w:<t>:sm:<H>:<M>         end-hour grid
  sch:w:<t>:eh:<H>:<M>:<h>     end-minute grid
  sch:w:<t>:em:<H>:<M>:<h>:<m> commit the window
  sch:z:p:<page>               timezone picker page (0 = curated)
  sch:z:s:<zone>               select timezone
"""
from __future__ import annotations

import logging
import math
import threading
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo, available_timezones

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from .schedule import WEEKDAY_ORDER
from .store import BotStore

logger = logging.getLogger(__name__)

Screen = Tuple[str, InlineKeyboardMarkup]

DAY_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
DAY_FULL = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
DEFAULTS_TARGET = 7

CURATED_TZ = [
    "Asia/Almaty", "Asia/Aqtau", "Asia/Aqtobe", "Asia/Atyrau"
]
ALL_TZ = sorted(available_timezones())
TZ_PER_PAGE = 12
TZ_PAGES = 1 + math.ceil(len(ALL_TZ) / TZ_PER_PAGE)  # page 0 = curated

MINUTES_STEP = 5
GRID_COLS = 6


def _kb(rows: List[List[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(keyboard=rows)


def _btn(label: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(label, callback_data=data)


# ---------- raw schedule-dict helpers (run inside BotStore.update_schedule) ----------

def _entry(data: Dict, t: int) -> Dict:
    if t == DEFAULTS_TARGET:
        return data.setdefault("defaults", {})
    return data.setdefault("weekdays", {}).setdefault(WEEKDAY_ORDER[t], {})


def _effective_windows(data: Dict, t: int) -> List[str]:
    if t == DEFAULTS_TARGET:
        return list(data.get("defaults", {}).get("windows") or [])
    entry = data.get("weekdays", {}).get(WEEKDAY_ORDER[t], {})
    explicit = entry.get("windows")
    if explicit is not None:
        return list(explicit)
    return list(data.get("defaults", {}).get("windows") or [])


# ---------- screens ----------

def menu_screen(store: BotStore) -> Screen:
    st = store.snapshot()
    lines = [f"📅 Расписание — {st.schedule.tz.key}"]
    for idx, rule in st.schedule.days.items():
        if not rule.enabled:
            lines.append(f"• {DAY_FULL[idx]}: ⏸ выкл")
            continue
        ws = ", ".join(f"{a:%H:%M}-{b:%H:%M}" for a, b in rule.windows) or "—"
        marker = "" if rule.windows != st.schedule.default_windows else " (default)"
        lines.append(f"• {DAY_FULL[idx]}: {ws}{marker}")
    dw = ", ".join(f"{a:%H:%M}-{b:%H:%M}" for a, b in st.schedule.default_windows) or "—"
    lines.append(f"⚙️ Default: {dw}")

    rows = []
    week = [
        _btn(f"{DAY_SHORT[i]} {'✅' if st.schedule.days[i].enabled else '⏸'}", f"sch:d:{i}")
        for i in range(7)
    ]
    for i in range(0, 7, 4):
        rows.append(week[i:i + 4])
    rows.append([_btn("🌐 Часовой пояс", "sch:z:p:0"), _btn("⚙️ Default", f"sch:d:{DEFAULTS_TARGET}")])
    return "\n".join(lines), _kb(rows)


def day_screen(store: BotStore, t: int, note: str = "") -> Screen:
    if not 0 <= t <= DEFAULTS_TARGET:
        raise ValueError(f"bad schedule target {t}")
    st = store.snapshot()
    if t == DEFAULTS_TARGET:
        windows = st.schedule.default_windows
        title = "⚙️ Окна по умолчанию\nДни без своих окон используют эти окна."
    else:
        rule = st.schedule.days[t]
        windows = rule.windows
        title = f"📅 {DAY_FULL[t]} — {'вкл' if rule.enabled else '⏸ выкл'}"
    lines = [title]
    if t != DEFAULTS_TARGET and windows == st.schedule.default_windows:
        lines.append("(используются окна по умолчанию)")
    ws = ", ".join(f"{a:%H:%M}-{b:%H:%M}" for a, b in windows)
    lines.append(f"Окна: {ws or '—'}")
    if note:
        lines.append(note)

    rows: List[List[InlineKeyboardButton]] = []
    if t != DEFAULTS_TARGET:
        enabled = st.schedule.days[t].enabled
        rows.append([
            _btn("⏸ Выключить день" if enabled else "✅ Включить день", f"sch:t:{t}"),
            _btn("🗑 Сбросить к default", f"sch:c:{t}"),
        ])
    for i, (a, b) in enumerate(windows):
        rows.append([_btn(f"❌ {a:%H:%M}-{b:%H:%M}", f"sch:x:{t}:{i}")])
    rows.append([_btn("➕ Добавить окно", f"sch:w:{t}:sh")])
    rows.append([_btn("◀️ Назад", "sch:m")])
    return "\n".join(lines), _kb(rows)


def _grid(prefix: str, values: List[int], fmt="{:02d}") -> List[List[InlineKeyboardButton]]:
    btns = [_btn(fmt.format(v), f"{prefix}:{v}") for v in values]
    return [btns[i:i + GRID_COLS] for i in range(0, len(btns), GRID_COLS)]


def _wizard_screen(text: str, rows: List[List[InlineKeyboardButton]], t: int) -> Screen:
    rows.append([_btn("◀️ Отмена", f"sch:d:{t}")])
    return text, _kb(rows)


def tz_screen(page: int, note: str = "") -> Screen:
    page = max(0, min(page, TZ_PAGES - 1))
    zones = CURATED_TZ if page == 0 else ALL_TZ[(page - 1) * TZ_PER_PAGE: page * TZ_PER_PAGE]
    lines = [f"🌐 Часовой пояс — стр. {page + 1}/{TZ_PAGES}"]
    if page == 0:
        lines.append("Часто используемые:")
    if note:
        lines.append(note)
    rows = [[_btn(z, f"sch:z:s:{z}")] for z in zones]
    nav: List[InlineKeyboardButton] = []
    if page > 0:
        nav.append(_btn("◀️", f"sch:z:p:{page - 1}"))
    nav.append(_btn(f"{page + 1}/{TZ_PAGES}", f"sch:z:p:{page}"))
    if page < TZ_PAGES - 1:
        nav.append(_btn("▶️", f"sch:z:p:{page + 1}"))
    rows.append(nav)
    rows.append([_btn("🏠 Меню", "sch:m")])
    return "\n".join(lines), _kb(rows)


# ---------- callback dispatch ----------

def handle_callback(data: str, store: BotStore, wake: threading.Event) -> Optional[Screen]:
    """Process one sch:* callback; returns the screen to render (None = ignore)."""
    tok = data.split(":")
    if len(tok) < 2 or tok[0] != "sch":
        return None
    try:
        return _dispatch(tok, store, wake)
    except (ValueError, IndexError, KeyError):
        logger.warning("Bad schedule callback: %r", data, exc_info=True)
        return menu_screen(store)


def _dispatch(tok: List[str], store: BotStore, wake: threading.Event) -> Optional[Screen]:
    kind = tok[1]

    if kind == "m":
        return menu_screen(store)

    if kind == "d":
        return day_screen(store, int(tok[2]))

    if kind == "t":
        t = int(tok[2])
        enabled = store.snapshot().schedule.days[t].enabled

        def toggle(d: Dict) -> None:
            _entry(d, t)["enabled"] = not enabled

        store.update_schedule(toggle)
        wake.set()
        return day_screen(store, t)

    if kind == "c":
        t = int(tok[2])

        def clear(d: Dict) -> None:
            d.setdefault("weekdays", {}).pop(WEEKDAY_ORDER[t], None)

        store.update_schedule(clear)
        wake.set()
        return day_screen(store, t)

    if kind == "x":
        t, i = int(tok[2]), int(tok[3])

        def delete(d: Dict) -> None:
            ws = _effective_windows(d, t)
            del ws[i]
            _entry(d, t)["windows"] = ws

        store.update_schedule(delete)
        wake.set()
        return day_screen(store, t)

    if kind == "w":
        t = int(tok[2])
        stage = tok[3]
        if stage == "sh":
            if len(tok) == 4:
                return _wizard_screen("➕ Окно: выберите час начала", _grid(f"sch:w:{t}:sh", range(24)), t)
            H = int(tok[4])
            return _wizard_screen(f"➕ Начало {H:02d}:__ — минуты", _grid(f"sch:w:{t}:sm:{H}", range(0, 60, MINUTES_STEP)), t)
        if stage == "sm":
            H, M = int(tok[4]), int(tok[5])
            return _wizard_screen(f"➕ Начало {H:02d}:{M:02d} — час конца", _grid(f"sch:w:{t}:eh:{H}:{M}", range(24)), t)
        if stage == "eh":
            H, M, h = int(tok[4]), int(tok[5]), int(tok[6])
            return _wizard_screen(f"➕ {H:02d}:{M:02d} — {h:02d}:__ минуты конца", _grid(f"sch:w:{t}:em:{H}:{M}:{h}", range(0, 60, MINUTES_STEP)), t)
        if stage == "em":
            H, M, h, m = int(tok[4]), int(tok[5]), int(tok[6]), int(tok[7])
            window = f"{H:02d}:{M:02d}-{h:02d}:{m:02d}"
            note = ""
            if (h, m) <= (H, M):
                note = "ℹ️ Окно переходит через полночь"

            def add(d: Dict) -> None:
                ws = _effective_windows(d, t)
                ws.append(window)
                _entry(d, t)["windows"] = ws

            store.update_schedule(add)
            wake.set()
            return day_screen(store, t, note)
        return None

    if kind == "z":
        if tok[2] == "p":
            return tz_screen(int(tok[3]))
        if tok[2] == "s":
            zone = ":".join(tok[3:])
            try:
                ZoneInfo(zone)
            except (ValueError, KeyError):
                return tz_screen(0, note=f"❌ Неизвестная зона: {zone}")
            store.update_schedule(lambda d: d.__setitem__("timezone", zone))
            wake.set()
            return menu_screen(store)
        return None

    return None
