# AttendBot

## Purpose

Automates attendance on a KBTU university portal (default `pge.kbtu.kz`, overridable): during configured weekly time windows it drives a headless browser through a Selenium Grid, logs in, clicks the attendance button, and reports events to a Telegram chat. The bot is controlled from Telegram (`/login`, `/schedule`, `/stop`, …); credentials and schedule live in a persistent state file, not in env.

## Stack

- Python 3.12, managed with `uv` (`uv.lock`, `.python-version`)
- selenium 4 — remote WebDriver client only; browsers run in the Selenium Grid container, not in this process
- pyTelegramBotAPI (telebot) — Telegram transport: polling, dispatch, retries, sends
- python-dotenv; stdlib `tomllib`/`zoneinfo`
- Runs as a Docker Compose stack: `bot` (this image) + standalone Selenium/Chromium

## Repository map

- `main.py` — entry point: wiring, signal handlers, crash notification
- `app/config.py` — `Settings` from env vars (Telegram required; WSP creds are one-time seed)
- `app/store.py` — `BotStore`: thread-safe persistent state (credentials, base URL, schedule) + `RuntimeState` snapshots
- `app/schedule.py` — schedule parsing/validation (`from_toml`/`from_dict`/`to_dict`) and window queries
- `app/commands.py` — `CommandProcessor` (pure command logic: parse → mutate store → reply text) + `create_telebot` (telebot handler wiring, chat-id auth, `sch:*` callbacks)
- `app/schedule_ui.py` — stateless `/schedule` inline-keyboard editor (screens re-rendered from `callback_data` + store)
- `app/driver_factory.py` — remote Chrome driver construction
- `app/telegram.py` — `TelegramNotifier`: sync send facade over the shared `TeleBot` instance
- `app/pages/login_page.py` — portal login page object (GWT/Vaadin selectors)
- `app/services/attendance.py` — `AttendanceService`: main loop, browser lifecycle, failure recovery
- `Dockerfile` / `docker-compose.yml` — build and stack

## Commands

```bash
uv sync                                          # install deps into .venv
uv run python main.py                            # run locally (needs env vars + reachable Selenium grid)
uv run python -m compileall main.py app          # syntax check; no tests/linters are configured

cp .env.example .env                             # required env vars before any run
docker compose up --build -d                     # multi-arch image: same command on AMD64 and ARM64
docker compose logs -f bot && docker compose down
```

## Configuration

Required env: `TG_BOT_TOKEN`, `TG_CHAT_ID` (see `.env.example`). The chat id doubles as command authorization.
Also set `BASE_URL` — there is **no default in code**; without it the attendance loop idles until `/url` is used.
Optional: `WSP_LOGIN`/`WSP_PASSWORD` (one-time seed for the state file — afterwards managed via `/login`), `SELENIUM_IMAGE`, `SELENIUM_MEM_LIMIT` (grid `mem_limit`), `REMOTE_URL`, `STATE_PATH`, `LOG_LEVEL`.

## Critical invariants

- **State file is the source of truth** for credentials, base URL and schedule (`STATE_PATH`, `/data/state.json` in Docker, `bot-data` volume). `WSP_*`/`BASE_URL` env vars are one-time seeds consumed only when the state file is absent; `BASE_URL` has no code-level default.
- **Threading model**: attendance loop in the main thread; telebot `infinity_polling` in a daemon thread (retries/reconnects owned by the library); command semantics live in `CommandProcessor` as pure logic. The `WebDriver` is owned exclusively by the attendance thread — command handlers must never touch it; they mutate `BotStore` and set the shared `wake` event.
- Attendance must not depend on Telegram: all notifications are best-effort, and command-poll failures back off and retry without affecting the loop.
- The `/schedule` editor is stateless: every screen is fully encoded in `callback_data` (≤64 bytes) and re-rendered from the store — no sessions; buttons on old messages survive restarts. Mutations still go only through `BotStore.update_schedule`.
- `app/config.py` evaluates `os.environ[...]` in the dataclass body, i.e. **at import time** (after `load_dotenv()` on module import). Required vars must exist before the process starts or import raises `KeyError`.
- Portal selectors in `login_page.py`/`attendance.py` (`gwt-uid-*`, `v-button primary`, `v-label-bold`) are coupled to the portal's GWT/Vaadin DOM; `gwt-uid` numbering can change when the portal updates its UI. Selectors are the most likely breakage point — verify them against the live page before "fixing" logic.
- The process listens on no ports and never runs a browser itself; it only speaks WebDriver to `REMOTE_URL`.
- Browser lifecycle is schedule-driven: the driver is closed when outside all windows / paused / credentials missing, and recreated when the next window opens. Keep that ownership inside `AttendanceService`.
- Dependency versions are pinned in `pyproject.toml` + `uv.lock`; the image installs with `uv sync --frozen`. Keep lockfile in sync when touching deps.

## Deployment

Deployable worker — Coolify-ready by construction: configuration via environment, stdout logging, graceful SIGTERM (implemented in `main.py`), non-root container, no secrets in the image. The Compose file is intentional (bot + Selenium grid) and must stay Coolify-compatible: no compose profiles (unsupported by Coolify — coollabsio/coolify#6395), no service-level `env_file` (the file is absent on Coolify; vars flow through `${VAR}` interpolation from a local `.env` or the Coolify env UI), required vars (`TG_BOT_TOKEN`, `TG_CHAT_ID`) marked `${VAR:?…}` so deployment is blocked until they are set, Selenium image selected via `SELENIUM_IMAGE` (multi-arch default), no exposed ports (the grid must stay on the internal network). Persistent state lives in the `bot-data` volume — do not drop it on redeploys.

## Architecture

See `ARCHITECTURE.md` for components, runtime flow, failure handling, and known limitations.
