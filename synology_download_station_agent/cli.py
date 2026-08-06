import sys
import argparse
from typing import List, Optional, Any
from urllib.parse import parse_qs, urlparse, unquote
from .client import SynologyClient, SynologyClientError
from .poll import check_and_notify_finished_tasks, run_polling_loop

STATUS_MAP = {
    "1": "⏳ Waiting",
    "waiting": "⏳ Waiting",
    "2": "⬇️ Downloading",
    "downloading": "⬇️ Downloading",
    "3": "⏸️ Paused",
    "paused": "⏸️ Paused",
    "4": "⏳ Finishing",
    "finishing": "⏳ Finishing",
    "5": "🔍 Checking Hash",
    "hash_checking": "🔍 Checking Hash",
    "6": "⏳ Seeding",
    "7": "⏳ Filehosting",
    "8": "✅ Done",
    "finished": "✅ Done",
    "completed": "✅ Done",
    "done": "✅ Done",
    "9": "🌱 Seeding (Done)",
    "seeding": "🌱 Seeding (Done)",
}


def format_task_status(status_val: Any) -> str:
    """Format raw DSM status code or string into human-readable label."""
    s = str(status_val).lower().strip()
    if s in STATUS_MAP:
        return STATUS_MAP[s]
    try:
        code = int(s)
        if code >= 100:
            return f"❌ Error (code {code})"
    except ValueError:
        pass
    return s.capitalize()


def format_task_title(task: dict) -> str:
    """Helper to extract clean display name from raw magnet links or hashes when in waiting state."""
    title = task.get("title", "unnamed")
    status = str(task.get("status", "")).lower()

    if title.startswith("magnet:?"):
        parsed = urlparse(title)
        query = parse_qs(parsed.query)
        dn = query.get("dn")
        if dn and dn[0]:
            return f"{unquote(dn[0])} (Resolving Magnet...)"
        return f"{title[:35]}... (Resolving Magnet...)"

    # If title is BTIH hash / B32 string during waiting phase
    if status in ("waiting", "1") and len(title) in (32, 40) and title.isalnum():
        return f"{title} (Fetching Metadata...)"

    return title


def format_bytes(size: int) -> str:
    """Format byte size into human readable string."""
    if size <= 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="synology-download-station-agent",
        description="Local LAN Synology Download Station CLI for Hermes Agent",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # 'add' subcommand
    add_parser = subparsers.add_parser("add", help="Add a magnet link or download URL")
    add_parser.add_argument("uri", help="Magnet link or HTTP/FTP download URL")
    add_parser.add_argument("--destination", "-d", help="Optional destination folder path on NAS")

    # 'list' subcommand
    list_parser = subparsers.add_parser("list", help="List current tasks in Download Station")
    list_parser.add_argument(
        "--type",
        "-t",
        default="all",
        choices=["all", "downloading", "completed"],
        help="Filter task type: all (default, includes finished tasks), downloading, completed",
    )

    # 'poll' subcommand
    poll_parser = subparsers.add_parser("poll", help="Poll Download Station for completed tasks")
    poll_parser.add_argument("--once", action="store_true", help="Run a single poll check and exit")
    poll_parser.add_argument("--interval", type=int, default=60, help="Polling interval in seconds (default: 60)")
    poll_parser.add_argument("--cleanup", action="store_true", help="Automatically remove completed tasks")

    return parser


def main(args: Optional[List[str]] = None):
    parser = build_parser()
    parsed_args = parser.parse_args(args)

    if not parsed_args.command:
        parser.print_help()
        sys.exit(1)

    if parsed_args.command == "add":
        try:
            with SynologyClient() as client:
                client.add_magnet(parsed_args.uri, destination=parsed_args.destination)
                print("Task successfully added to Synology Download Station!")
        except SynologyClientError as e:
            print(f"Error adding task: {e}")
            sys.exit(1)

    elif parsed_args.command == "list":
        try:
            with SynologyClient() as client:
                tasks_resp = client.list_tasks(
                    additional=["detail", "transfer"],
                    task_type=parsed_args.type,
                )
                tasks = tasks_resp.get("data", {}).get("tasks", [])
                if not tasks:
                    print("No tasks found in Download Station.")
                else:
                    print(f"Found {len(tasks)} task(s):")
                    for t in tasks:
                        status_str = format_task_status(t.get("status", "unknown"))
                        title = format_task_title(t)
                        tid = t.get("id")

                        transfer = t.get("additional", {}).get("transfer", {})
                        size_total = transfer.get("size_total", 0)
                        size_dl = transfer.get("size_downloaded", 0)

                        progress = ""
                        if size_total > 0:
                            pct = (size_dl / size_total) * 100
                            progress = f" | {format_bytes(size_dl)} / {format_bytes(size_total)} ({pct:.1f}%)"

                        print(f"  • [{tid}] {title} - Status: {status_str}{progress}")
        except SynologyClientError as e:
            print(f"Error listing tasks: {e}")
            sys.exit(1)

    elif parsed_args.command == "poll":
        if parsed_args.once:
            with SynologyClient() as client:
                check_and_notify_finished_tasks(client, auto_cleanup=parsed_args.cleanup)
        else:
            run_polling_loop(interval_seconds=parsed_args.interval, auto_cleanup=parsed_args.cleanup)


if __name__ == "__main__":
    main()
