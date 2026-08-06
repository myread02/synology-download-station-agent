# Synology Download Station Agent: API Pipeline for Hermes Agent & Telegram

`synology-download-station-agent` is a secure, local-only API pipeline that allows **Hermes Agent** to execute local LAN commands to your **Synology NAS (Download Station)**, while **Telegram** acts solely as your secure control and notification interface.

Managed with [**`uv`**](https://github.com/astral-sh/uv) for fast, zero-configuration dependency and environment execution.

---

## 🏗️ Architecture Overview

```text
[ Telegram App ] 
       │ (HTTPS Telegram Bot API)
       ▼
[ Hermes Agent Host ] (Local Network)
       │ (Local LAN API: http://192.168.x.x:5000)
       ▼
[ Synology Download Station ]
```

* **No NAS Port Forwarding Required:** Your Synology NAS does **not** need to be exposed to the public internet.
* **Local LAN Security:** Hermes Agent and Synology talk strictly over your local network (LAN).
* **Remote Management:** Telegram handles authentication and long-polling via Telegram's servers, allowing you to trigger downloads safely from anywhere.

---

## 🌐 Supported Protocols & File Types

Synology Download Station supports a wide range of protocols and file types out of the box:

| Protocol | Description | Examples / Formats |
| :--- | :--- | :--- |
| **BitTorrent** | Magnet links & Torrent files | `magnet:?xt=urn:btih:...`, `.torrent` files |
| **HTTP / HTTPS** | Direct web downloads | `http://domain.com/file.zip`, `https://...` |
| **FTP / FTPS / SFTP** | File Transfer Protocol downloads | `ftp://user:pass@server/path/file.ext`, `sftp://...` |
| **NZB (Usenet)** | Usenet newsgroup downloads | `.nzb` files |
| **eMule (ed2k)** | Peer-to-peer ed2k network | `ed2k://\|file\|...\|/` |
| **FlashGet / Thunder / QQDL** | Proprietary download link schemes | `thunder://...`, `flashget://...`, `qqdl://...` |

### Supported Input Formats
- **Magnet URIs & Links** (Direct string input via `synology-download-station-agent add` or `/download` in Telegram)
- **`.torrent` & `.nzb` Files**
- **Direct Files**: `.iso`, `.zip`, `.rar`, `.7z`, `.tar.gz`, `.mp4`, `.mkv`, `.pdf`, `.bin`, `.dmg`, etc.
- **Cyberlockers & Web Premium Accounts** (Direct file host links via DSM configured File Hosting accounts like Rapidgator, Mega, YouTube, etc.)

---

## ⚡ Implemented Functions & Commands (`uv` workflow)

### 🛠️ CLI Execution via `uv`

No manual `pip install` or `venv` activation required! `uv` automatically sets up and manages the environment on demand:

| CLI Command | Equivalent Python Function | Description |
| :--- | :--- | :--- |
| `uv run python3 syno_add.py "<magnet_uri>"` | `client.add_magnet()` | Quick direct add for Hermes Agent local execution. |
| `uv run synology-download-station-agent add "<uri>"` | `client.add_magnet()` | Adds download task to Download Station. |
| `uv run synology-download-station-agent list` | `client.list_tasks()` | Displays active & completed task IDs, titles, and statuses. |
| `uv run synology-download-station-agent poll --once` | `poll.check_and_notify_finished_tasks()` | Single check for completed tasks & sends Telegram alert. |
| `uv run synology-download-station-agent poll --interval 60 --cleanup` | `poll.run_polling_loop()` | Runs background polling loop and auto-cleans completed tasks. |

---

## 🚀 Quick Start with `uv`

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/myread02/synology-download-station-agent.git
   cd synology-download-station-agent
   ```

2. **Sync Dependencies with `uv`:**
   ```bash
   uv sync
   ```
   *(Creates `.venv` automatically in < 1 second).*

3. **Configure Local Environment (`.env`):**
   Copy `.env.example` to `.env` and fill in your NAS connection details:
   ```bash
   cp .env.example .env
   ```

   Edit `.env`:
   ```ini
   SYNO_LOCAL_IP=192.168.1.100     # Your NAS LAN IP address
   SYNO_LOCAL_PORT=5000            # HTTP (5000) or HTTPS (5001)
   SYNO_USE_HTTPS=false            # Set true if using HTTPS (5001)
   SYNO_VERIFY_SSL=true            # Set false if using self-signed certs
   SYNO_USER=hermes_bot            # Dedicated NAS user account
   SYNO_PASS=YourSecurePassword    # User password
   ```

4. **Verify Execution with `uv`:**
   ```bash
   uv run python3 syno_add.py "magnet:?xt=urn:btih:..."
   ```

---

## 🤖 Hermes Agent Configuration for Telegram Control

Register `synology-download-station-agent` in Hermes Agent so that when you send a magnet link in Telegram, Hermes executes the command locally using `uv`.

1. **Copy `hermes_skill.json` to Hermes Skills Directory:**
   ```json
   {
     "name": "synology_download",
     "display_name": "Synology Download Station",
     "description": "Adds a magnet link or download URI to local Synology Download Station over LAN using uv.",
     "command": "/download",
     "execution": {
       "type": "local_command",
       "command_template": "uv run python3 syno_add.py \"{magnet_uri}\""
     }
   }
   ```

2. **Telegram Execution Flow:**
   * You send in Telegram: `/download magnet:?xt=urn:btih:...`
   * Hermes Agent executes `uv run python3 syno_add.py "<magnet_link>"` locally over your LAN.
   * Hermes Agent sends the success response back to your Telegram chat.

---

## 🔔 Completion Notifications

Choose Option A (Synology DSM Webhook) or Option B (Hermes `uv` polling loop).

### Option A: Synology Webhook (Recommended)

Configure Synology DSM to send a direct Telegram message via Webhook when a download completes:

1. Open **DSM > Control Panel > Notification > Webhook**.
2. Click **Add** and select **Custom**.
3. Configure Provider parameters:
   * **Provider Name:** `Telegram Bot`
   * **Callback URL:** `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/sendMessage`
   * **HTTP Method:** `POST`
   * **Header:** `Content-Type: application/json`
   * **Payload (JSON):**
     ```json
     {
       "chat_id": "YOUR_TELEGRAM_USER_ID",
       "text": "🎉 Download Complete: %EVENT_MESSAGE%"
     }
     ```
4. Attach this notification event to **Download Station Task Completed** events under **Notification > Rules**.

---

### Option B: Hermes Background Polling Service via `uv`

If you prefer Hermes to manage status checks locally without Webhooks:

1. Configure Telegram credentials in `.env`:
   ```ini
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   TELEGRAM_CHAT_ID=123456789
   ```

2. Run single check:
   ```bash
   uv run synology-download-station-agent poll --once
   ```

3. Run continuous polling loop (every 60s with auto-cleanup of completed tasks):
   ```bash
   uv run synology-download-station-agent poll --interval 60 --cleanup
   ```

---

## 🧪 Testing with `uv`

Run unit tests:
```bash
uv run python -m unittest discover -s tests
```

---

## 📜 License
MIT License.
