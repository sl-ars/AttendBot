# Auto-Attend for WSP

Automatically attend for a subject and send a message via telegram bot

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
     WSP_LOGIN=...
     WSP_PASSWORD=...
     TG_BOT_TOKEN=...
     TG_CHAT_ID=...
     ```

3. **Edit schedule**
   Update time windows and timezone in `schedule.toml` (defaults are included). Example:

   ```toml
   timezone = "Asia/Almaty"

   [defaults]
   windows = ["07:00-19:00"]

   [weekdays.monday]
   enabled = true
   windows = ["07:00-12:00", "13:00-15:00"]

   [weekdays.saturday]
   enabled = false

   [weekdays.sunday]
   enabled = false
   ```

4. **Build & run with Docker Compose (choose your profile)**

   * **Apple Silicon / ARM64**:

     ```bash
     docker compose --profile arm64 up --build -d
     ```
   * **Intel/AMD (x86_64)**:

     ```bash
     docker compose --profile amd64 up --build -d
     ```

5. **Watch logs**

   ```bash
   docker compose logs -f bot
   ```

   You should see startup logs and a Telegram “Bot starting” message.

---

## Configuration

### `.env` keys

| Key             | Required      | Example                                  | Notes                                      |
| --------------- | ------------- |------------------------------------------| ------------------------------------------ |
| `WSP_LOGIN`     | ✅             | `a_student`                              | WSP username                               |
| `WSP_PASSWORD`  | ✅             | `********`                               | WSP password                               |
| `TG_BOT_TOKEN`  | ✅             | `123456:ABC...`                          | From @BotFather                            |
| `TG_CHAT_ID`    | ✅             | `123456789`                              | From a chat-id bot                         |
| `REMOTE_URL`    | ⛔️ (defaults) | `http://selenium:4444/wd/hub`            | Internal service URL                       |
| `BASE_URL`      | ⛔️            | `https://wsp.kbtu.kz/RegistrationOnline` | WSP page                                   |
| `SCHEDULE_PATH` | ⛔️            | `schedule.toml`                          | Path to schedule file                      |
| `LOG_LEVEL`     | ⛔️            | `INFO` or `DEBUG`                        | Logging level                              |


### `schedule.toml`

* `timezone` must be a valid IANA zone (e.g. `Asia/Almaty`).
* Each weekday can be `enabled=true/false`.
* Time windows `"HH:MM-HH:MM"`. Multiple windows per day are supported.
* Overnight windows are supported (e.g. `"22:00-02:00"`).

---

## Common Commands

* **Start (ARM64)**
  `docker compose --profile arm64 up --build -d`
* **Start (AMD64)**
  `docker compose --profile amd64 up --build -d`
* **Stop**
  `docker compose down`
* **Logs**
  `docker compose logs -f bot`
* **Restart only the bot**
  `docker compose restart bot`
* **Check Selenium status**
  `curl http://localhost:4444/status | jq .`
