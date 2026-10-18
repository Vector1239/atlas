---
name: job-scan
description: Rank fresh job postings (Bundesagentur für Arbeit, Arbeitnow, remote boards, optional JSearch) in data, AI and software engineering (full stack, backend, mobile; no cybersecurity) for an international MSc Data Science student at Uni Trier, and save 👍/👎 feedback on jobs by their J-xxxxx id. Use for the scheduled job-scan cron jobs, when the user asks for jobs, or when the user replies to a job with 👍, 👎 or a J-xxxxx id.
version: 0.2.0
metadata:
  hermes:
    tags: [germany, jobs, career, data-science]
    category: germany-life
---

# Job Scan

## When to Use
- The "Job scan" cron jobs. The JOB SCAN block in your prompt comes from
  `germany_life/job_scan_daily.py` (Trier + region) or `job_scan_weekly.py` (Germany + Europe).
- The user asks for jobs in chat. Run
  `bash {{GL}}/gl jobs --rings 0,1` (rings: 0 Trier, 1 region,
  2 Germany, 3 Europe) and use the output as the data block.
- The user rates a job, e.g. `👍 J-3fa2c good stack` or `👎 J-91b0e needs German`.

## Ranking (cron or on request)
1. Read PROFILE (German level, graduation date, what they want now and later) and
   RECENT FEEDBACK (what they liked and disliked). Use both when you rate.
2. Give each job a fit score from 1 to 5 with a reason of 12 words or fewer. Rules:
   - `student-job` (Werkstudent, HiWi, internship, thesis) belongs under **Now**. Full-time
     junior roles belong under **After graduation**.
   - `senior`: drop it unless the profile asks for senior roles.
   - `german-required` or `posting-in-german`: score at most 2 if the profile's German is below B2.
   - Look like roles the user rated 👎 → score lower. Look like 👍 → score higher.
   - Use only the data block. Don't invent salary, requirements or anything the posting doesn't show.
3. Reply in this shape, with at most 8 jobs:

   💼 **Job scan: <rings>**, <N> new
   **Now**
   `J-xxxxx` ⭐4/5 · <title> · <company> (<city>) · <flags> · <link>
   ↳ <why it fits>
   **After graduation**
   ...
   <"+K more with lower scores: J-…, J-…" if any were cut>
   Reply 👍 J-xxxxx or 👎 J-xxxxx (reason optional) and I'll learn what you like.

4. If no job scores 3 or more, reply with only `[SILENT]`.
5. If NEW JOBS is "(none)" and SOURCE STATUS shows failures, reply with one line naming the
   failed sources and suggest running `./gl check`.

## Saving feedback (chat)
1. Pull the id out of the message (`J-` followed by 5 characters) along with 👍/👎 and any reason.
2. Run `bash {{GL}}/gl ctl job rate J-xxxxx up|down <reason>`.
   To see a job's details: `bash {{GL}}/gl ctl job show J-xxxxx`.
3. Confirm in one line. If the reason is a general preference ("no consulting", "only Python
   roles"), also save it to memory and suggest adding it to profile.md.

## Pitfalls
- Only jobs sent in the last 120 days are in `{{GL}}/data/jobs_index.json`. Older ids can't be rated.
- Bundesagentur postings have no description, so flags come from the title alone.
- Don't apply to jobs, email employers or fill in forms on the user's behalf.
