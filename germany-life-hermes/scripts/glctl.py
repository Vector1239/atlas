"""Small command-line tool the agent (or you) uses to update your data files.

  glctl.py work add --hours 5 --employer "Company" [--date 2026-10-17] [--kind regular|hiwi] [--note ...]
  glctl.py work summary [--year 2026]
  glctl.py job show J-1a2b3
  glctl.py job rate J-1a2b3 up|down [note...]
  glctl.py deadline add --date 2027-03-31 --title "..." [--category visa] [--remind 60,30,14,7,1] [--note ...]
  glctl.py deadline list

Writes only inside the project's data/ folder. Works on Python 3.9+ except
`deadline list`, which reads TOML and needs 3.11+.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gl_common as gl  # noqa: E402

WORKLOG_FIELDS = ["date", "hours", "employer", "kind", "note"]
FEEDBACK_FIELDS = ["date", "job_id", "rating", "title", "company", "note"]


def _append_csv(name: str, fields: list[str], row: dict) -> None:
    path = gl.data_dir() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if new_file:
            writer.writeheader()
        writer.writerow(row)


def work_add(args) -> None:
    day = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    if not 0 < args.hours <= 24:
        sys.exit("hours must be between 0 and 24")
    _append_csv("worklog.csv", WORKLOG_FIELDS, {"date": day.isoformat(), "hours": f"{args.hours:g}",
                                                "employer": args.employer, "kind": args.kind,
                                                "note": args.note or ""})
    print(f"Logged {args.hours:g} h ({args.kind}) on {day.isoformat()} at {args.employer}.")
    print(gl.workdays_line(gl.workdays_summary(day.year)))


def work_summary(args) -> None:
    print(gl.workdays_line(gl.workdays_summary(args.year or dt.date.today().year)))


def _job(job_id: str) -> dict:
    index = gl.load_json(gl.data_dir() / "jobs_index.json", {})
    key = job_id.strip()
    if key.lower().startswith("j-"):
        key = "J-" + key[2:].lower()
    job = index.get(key)
    if not job:
        sys.exit(f"{job_id} is not in data/jobs_index.json (only jobs sent in the last 120 days are kept)")
    return job


def job_show(args) -> None:
    print(json.dumps(_job(args.job_id), ensure_ascii=False, indent=1))


def job_rate(args) -> None:
    job = _job(args.job_id)
    note = " ".join(args.note).strip()
    _append_csv("job_feedback.csv", FEEDBACK_FIELDS, {
        "date": dt.date.today().isoformat(), "job_id": args.job_id, "rating": args.rating,
        "title": job.get("title", ""), "company": job.get("company", ""), "note": note})
    print(f"Saved {'👍' if args.rating == 'up' else '👎'} for {job.get('title')} @ {job.get('company')}.")


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)  # a JSON string is a valid TOML basic string


def deadline_add(args) -> None:
    day = dt.date.fromisoformat(args.date)
    remind = [int(x) for x in args.remind.split(",")] if args.remind else [30, 14, 7, 3, 1, 0]
    block = ["", "[[deadline]]", f"title = {_toml_string(args.title)}", f"date = {day.isoformat()}",
             f"category = {_toml_string(args.category)}", f"remind_days = {remind}"]
    if args.note:
        block.append(f"note = {_toml_string(args.note)}")
    path = gl.data_dir() / "deadlines.toml"
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(block) + "\n")
    print(f"Added deadline {day.isoformat()}: {args.title} (reminders {remind} days before).")


def deadline_list(args) -> None:
    today = dt.date.today()
    entries = [e for e in gl.load_deadlines() if (e["date"] - today).days >= -7]
    for entry in entries:
        print(f"{entry['date'].isoformat()}  ({(entry['date'] - today).days:+d} d)  "
              f"[{entry.get('category', 'other')}] {entry.get('title', '?')}")
    if not entries:
        print("No upcoming deadlines in data/deadlines.toml.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    groups = parser.add_subparsers(dest="group", required=True)

    work = groups.add_parser("work").add_subparsers(dest="action", required=True)
    p = work.add_parser("add")
    p.add_argument("--hours", type=float, required=True)
    p.add_argument("--employer", required=True)
    p.add_argument("--date")
    p.add_argument("--kind", choices=["regular", "hiwi"], default="regular")
    p.add_argument("--note")
    p.set_defaults(func=work_add)
    p = work.add_parser("summary")
    p.add_argument("--year", type=int)
    p.set_defaults(func=work_summary)

    job = groups.add_parser("job").add_subparsers(dest="action", required=True)
    p = job.add_parser("show")
    p.add_argument("job_id")
    p.set_defaults(func=job_show)
    p = job.add_parser("rate")
    p.add_argument("job_id")
    p.add_argument("rating", choices=["up", "down"])
    p.add_argument("note", nargs="*")
    p.set_defaults(func=job_rate)

    deadline = groups.add_parser("deadline").add_subparsers(dest="action", required=True)
    p = deadline.add_parser("add")
    p.add_argument("--date", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--category", default="other")
    p.add_argument("--remind", help="comma-separated days before, e.g. 60,30,14,7,1,0")
    p.add_argument("--note")
    p.set_defaults(func=deadline_add)
    p = deadline.add_parser("list")
    p.set_defaults(func=deadline_list)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
