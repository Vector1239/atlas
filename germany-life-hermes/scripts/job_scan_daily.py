"""Cron entry point: job scan for rings 0-1 (Trier and the region).

Hermes cron scripts can't take arguments, so this wrapper fixes the rings."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import job_scan  # noqa: E402

if __name__ == "__main__":
    job_scan.main(default_rings="0,1")
