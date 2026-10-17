"""Cron entry point: job scan for rings 2-3 (rest of Germany and Europe).

Hermes cron scripts can't take arguments, so this wrapper fixes the rings."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import job_scan  # noqa: E402

if __name__ == "__main__":
    job_scan.main(default_rings="2,3")
