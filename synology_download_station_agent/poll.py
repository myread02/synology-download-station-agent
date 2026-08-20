import os
import time
import requests
from typing import Optional, List, Dict, Any
from .client import SynologyClient, SynologyClientError

# Synology Download Station task status codes
STATUS_FINISHED = "finished"  # Code 8 in DSM API or status string

def send_telegram_notification(bot_token: str, chat_id: str, message: str) -> bool:
    """Send a notification message via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        return resp.json().get("ok", False)
    except Exception as e:
        print(f"[ERROR] Failed to send Telegram alert: {e}")
        return False


def check_and_notify_finished_tasks(
    client: SynologyClient,
    telegram_bot_token: Optional[str] = None,
    telegram_chat_id: Optional[str] = None,
    auto_cleanup: bool = False,
) -> List[Dict[str, Any]]:
    """
    Polls active tasks, finds finished downloads, notifies Telegram, and optionally cleans up.
    Returns list of finished task dicts processed in this run.
    """
    bot_token = telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID")

    try:
        result = client.list_tasks(additional=["detail", "transfer"])
        tasks = result.get("data", {}).get("tasks", [])
    except SynologyClientError as e:
        print(f"[ERROR] Polling failed: {e}")
        return []

    finished_tasks = []
    finished_task_ids = []

    for task in tasks:
        status = str(task.get("status", "")).lower()
        # Seeding means the download is complete but DSM is still uploading it.
        if status in ("finished", "8", "completed", "done", "seeding", "9"):
            title = task.get("title", "Unknown Task")
            task_id = task.get("id")
            finished_tasks.append(task)
            if task_id:
                finished_task_ids.append(task_id)

            msg = f"🎉 <b>Download Complete!</b>\n\n<b>File:</b> {title}\n<b>ID:</b> <code>{task_id}</code>"
            print(f"[INFO] Download complete: {title}")

            if bot_token and chat_id:
                send_telegram_notification(bot_token, chat_id, msg)

    if auto_cleanup and finished_task_ids:
        try:
            client.delete_task(finished_task_ids, force_complete=True)
            print(f"[INFO] Cleaned up {len(finished_task_ids)} completed task(s).")
        except SynologyClientError as e:
            print(f"[ERROR] Failed to auto-cleanup tasks: {e}")

    return finished_tasks


def run_polling_loop(
    interval_seconds: int = 60,
    auto_cleanup: bool = False,
):
    """Run continuous polling loop every N seconds."""
    print(f"[INFO] Starting Synology task polling service (interval: {interval_seconds}s)...")
    with SynologyClient() as client:
        while True:
            try:
                check_and_notify_finished_tasks(client, auto_cleanup=auto_cleanup)
            except Exception as e:
                print(f"[ERROR] Unexpected exception in poll loop: {e}")
            time.sleep(interval_seconds)
