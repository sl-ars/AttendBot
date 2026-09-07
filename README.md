# Auto-Attend

Automatically attends a subject on the university portal (default: `pge.kbtu.kz`) and reports via a Telegram bot. Everything is controlled from Telegram: credentials, target page and schedule are set with bot commands and stored in a persistent state file.

## Quick Start

1. **Install Docker** for your OS
   [https://docs.docker.com/engine/install/](https://docs.docker.com/engine/install/)

2. **Create and fill environment**

   ```bash
   cp .env.example .env
   ```

   * Get **bot token** from **@BotFather**.
   * Get **chat id** from a helper bot (e.g. **@userinfobot** or **@chatid_echo_bot**).
   * Put values into `.env`:

     ```
     TG_BOT_TOKEN=...
     TG_CHAT_ID=...
     BASE_URL=https://pge.kbtu.kz/RegistrationOnline
     ```

   Portal credentials are **not** in `.env` — send them to the bot in Telegram after startup (see below).

3. **Build & run with Docker Compose**

   The Selenium image is multi-arch (amd64 + arm64), so the same command works on Intel/AMD and Apple Silicon/ARM hosts:

   ```bash
   docker compose up --build -d
   ```

   To use an alternative grid image (e.g. `seleniarm/standalone-chromium:latest`), set `SELENIUM_IMAGE` in `.env`.

4. **Watch logs**

   ```bash
   docker compose logs -f bot
   ```

   You should see startup logs and a Telegram “Bot starting” message. Then, **in the bot chat**:

   ```
   /login ваш_логин ваш_пароль
   /status
   ```

---

## Bot commands

Only messages from the configured `TG_CHAT_ID` are accepted. Changes take effect immediately and persist across restarts (state file at `/data/state.json`, mounted as the `bot-data` volume).

| Command | What it does |
| --- | --- |
| `/help` | List all commands |
| `/status` | Account, mode, browser, schedule window, last attended lesson |
| `/login <логин> <пароль>` | Set or change portal credentials |
| `/url <адрес>` | Change the attendance page (e.g. `https://wsp.kbtu.kz/RegistrationOnline`) |
| `/stop` | Pause attendance (browser closes; bot stays responsive) |
| `/start` | Resume attendance |
| `/schedule` | Open the schedule editor (inline buttons — see below) |

**`/schedule` editor** — fully button-driven: main menu → day (Пн…Вс) or `⚙️ Default` → add/delete windows through an hour/minute grid, toggle days on/off, reset a day to defaults, pick the timezone from a paged list (curated page first). Screens live in one message (edited in place); buttons on old messages keep working after a restart. Overnight windows (`22:00-02:00`) are supported — pick an end time earlier than the start.

The password is stored **in plain text** in the state file — consider deleting the `/login` message from the chat afterwards.

---

## Deploy on Coolify

The stack is Coolify-ready: no compose profiles, configuration purely through environment variables, no exposed ports, graceful `SIGTERM`, non-root container.

1. Push this repository to your Git provider.
2. In Coolify: **Resources → New → Docker Compose**, point it at the repo (compose path `docker-compose.yml` at the root).
3. In the resource's **Environment** section, set the two required variables — `TG_BOT_TOKEN` and `TG_CHAT_ID`. The deployment is blocked until they are set (by design, via `${VAR:?…}` markers). Also set `BASE_URL` (no code default — the bot idles without it). Optional variables: `SELENIUM_IMAGE`, `REMOTE_URL`, `STATE_PATH`, `LOG_LEVEL`.
4. Deploy. No domain or port mapping is needed: the bot is a worker, and the Selenium grid stays on the private compose network.

Notes:

* Memory: the grid container is capped at 1 GB (`mem_limit`), runs headless without XvFB, and Chrome uses `--disable-dev-shm-usage` with a small 256 MB `/dev/shm` — the whole stack fits in ~1–1.5 GB RAM.
* The `bot-data` volume keeps credentials, page URL and schedule across deploys and restarts — do not delete it unless you want to reset the bot. After the first deploy, send `/login` and open `/schedule` in Telegram.
* `WSP_LOGIN`/`WSP_PASSWORD` env vars, if set, are imported into the state file on first start only.
* To drive an external grid instead, set `REMOTE_URL` and remove the `selenium` service (and the `depends_on` block) in Coolify's compose editor.

---

## Configuration

### `.env` keys

| Key             | Required      | Example                                  | Notes                                              |
| --------------- | ------------- |------------------------------------------| -------------------------------------------------- |
| `TG_BOT_TOKEN`  | ✅             | `123456:ABC...`                          | From @BotFather                                    |
| `TG_CHAT_ID`    | ✅             | `123456789`                              | From a chat-id bot; only this chat can command the bot |
| `BASE_URL`      | ✅             | `https://pge.kbtu.kz/RegistrationOnline` | Attendance page; **no default in code** — without it the bot idles until `/url` |
| `WSP_LOGIN`     | ⛔️ (seed)     | `a_student`                              | Imported into state on first start only            |
| `WSP_PASSWORD`  | ⛔️ (seed)     | `********`                               | Imported into state on first start only            |
| `SELENIUM_IMAGE`| ⛔️ (defaults) | `selenium/standalone-chrome:latest`      | Grid image (multi-arch amd64+arm64)                |
| `SELENIUM_MEM_LIMIT`| ⛔️ (defaults) | `1g`                                 | Grid container memory ceiling (`512m`, `1.5g`…)   |
| `REMOTE_URL`    | ⛔️ (defaults) | `http://selenium:4444/wd/hub`            | Internal service URL                               |
| `STATE_PATH`    | ⛔️            | `/data/state.json` (in Docker)           | State file location                                |
| `LOG_LEVEL`     | ⛔️            | `INFO` or `DEBUG`                        | Logging level                                      |

---

## Common Commands

* **Start**
  `docker compose up --build -d`
* **Stop**
  `docker compose down`
* **Logs**
  `docker compose logs -f bot`
* **Restart only the bot**
  `docker compose restart bot`
