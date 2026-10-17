"""Deadline and work-day reminders, no LLM involved.

Runs as a Hermes "no-agent" cron job: whatever this prints is sent to Telegram as
is, and printing nothing means no message. Reminders come from data/deadlines.toml
(on each day listed in `remind_days`) and from the work log (once each time a
threshold of the yearly work-day limit is crossed).

By hand: ./gl deadlines   (adds --dry-run; add --all to list everything upcoming)
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gl_common as gl  # noqa: E402

DEFAULT_REMIND_DAYS = [30, 14, 7, 3, 1, 0]
WORKDAY_LEVELS = [100, 120, 130, 140]


def deadline_lines(today: dt.date, show_all: bool) -> list[str]:
    lines = []
    for entry in gl.load_deadlines():
        days = (entry["date"] - today).days
        remind = entry.get("remind_days", DEFAULT_REMIND_DAYS)
        due = days in remind or -3 <= days < 0
        if not (due or (show_all and days >= 0)):
            continue
        if days == 0:
            when = "TODAY"
        elif days < 0:
            when = f"{-days} day{'s' if days != -1 else ''} overdue"
        else:
            when = f"in {days} day{'s' if days != 1 else ''}"
        lines.append(f"• {entry.get('title', '?')} — {when} ({entry['date'].strftime('%a %d %b %Y')})")
        if entry.get("note") and due:
            lines.append(f"  {entry['note']}")
    return lines


def workday_lines(today: dt.date, dry_run: bool) -> list[str]:
    summary = gl.workdays_summary(today.year)
    if summary is None:
        return []
    path = gl.state_dir() / "workday_alert.json"
    alerted = gl.load_json(path, {})
    last = alerted.get(str(today.year), 0)
    crossed = [level for level in WORKDAY_LEVELS if summary["used"] >= level > last]
    if not crossed:
        return []
    if not dry_run:
        alerted[str(today.year)] = crossed[-1]
        gl.save_json(path, alerted)
    return [f"• Work-day limit: {gl.workdays_line(summary)}",
            "  Above the limit you need permission from the Ausländerbehörde; HiWi jobs at the "
            "university don't count. Check with the International Office if unsure."]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="don't record work-day alerts as sent")
    parser.add_argument("--all", action="store_true", help="list every upcoming deadline")
    args = parser.parse_args()

    today = gl.now(gl.load_config()).date()
    lines = deadline_lines(today, args.all) + workday_lines(today, args.dry_run)
    if lines:
        print("⏰ Reminders\n" + "\n".join(lines))


if __name__ == "__main__":
    main()
