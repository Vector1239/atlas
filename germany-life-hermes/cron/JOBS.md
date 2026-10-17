# Cron jobs

Paste these into Terminal once, after `./install.sh` and `./gl check`. Every job delivers to
your Telegram **home channel**, so send `/sethome` to your bot in a direct message first.

Each LLM job runs its script first. The script's output becomes a data block in front of the
prompt, and the attached skill tells the agent what to do with it. The prompts are kept
self-contained because cron runs start fresh, with no chat memory.

```bash
# 1. Morning brief: weekdays 07:30, weekends 09:00
hermes cron create "weekdays at 7:30" \
  "Write my morning brief from the MORNING DATA block above, following the trier-morning-brief skill. Use only the data block; do not search the web." \
  --script germany_life/morning_brief.py --skill trier-morning-brief \
  --name "Morning brief (weekdays)" --deliver telegram

hermes cron create "weekends at 9am" \
  "Write my morning brief from the MORNING DATA block above, following the trier-morning-brief skill. Use only the data block; do not search the web." \
  --script germany_life/morning_brief.py --skill trier-morning-brief \
  --name "Morning brief (weekends)" --deliver telegram

# 2. Job scan, Trier + region: every day at 18:00
#    (skipped without any LLM call when nothing new turned up)
hermes cron create "daily at 18:00" \
  "Rank the new jobs in the JOB SCAN block above for me, following the job-scan skill. If no job scores 3/5 or more, reply with only [SILENT]." \
  --script germany_life/job_scan_daily.py --skill job-scan \
  --name "Job scan: Trier + region" --deliver telegram

# 3. Job scan, rest of Germany + Europe: Sundays 10:00
hermes cron create "every sunday 10am" \
  "Rank the new jobs in the JOB SCAN block above for me, following the job-scan skill. Jobs in Europe outside Germany are for after graduation. If no job scores 3/5 or more, reply with only [SILENT]." \
  --script germany_life/job_scan_weekly.py --skill job-scan \
  --name "Job scan: Germany + Europe" --deliver telegram

# 4. Deadline and work-day reminders: daily 08:00, no LLM at all (free)
hermes cron create "daily at 8am" --no-agent \
  --script germany_life/deadlines.py \
  --name "Deadline reminders" --deliver telegram
```

## Check they work

```bash
hermes cron list            # four jobs, with their next run times
hermes cron run <job_id>    # fire one now (it runs on the next scheduler tick, within a minute)
hermes cron status          # is the scheduler alive?
hermes cron doctor          # failed runs, missing scripts, overdue jobs
```

Outputs are also saved in `~/.hermes/cron/output/<job_id>/`.

## Cheaper runs (optional)

Scheduled jobs can use a cheaper model than your chat:

```bash
hermes config set cron.model <a cheap, fast model from your provider>
```

## Changing things later

- Times: `hermes cron edit <job_id> --schedule "weekdays at 7:00"`
- Sources, keywords, rings: edit `config/sources.toml`. No reinstall needed, since scripts read it on every run.
- Skills or scripts: edit them in this folder, then run `./install.sh` again.
- Pause everything (e.g. on holiday): `hermes cron pause <job_id>` / `hermes cron resume <job_id>`
