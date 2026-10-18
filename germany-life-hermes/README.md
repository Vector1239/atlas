# Germany Life on Hermes

A personal assistant for life in Germany as an international MSc Data Science student in
Trier, built on [Hermes Agent](https://hermes-agent.nousresearch.com/) and delivered
through Telegram.

| Job | When | What you get |
|---|---|---|
| Morning brief | 07:30 weekdays, 09:00 weekends | Weather, Mensa, deadlines, news from Trier → region → Germany → Europe, in English |
| Job scan: Trier + region | 18:00 daily | New data / ML / analytics jobs ranked against your profile (silent if nothing new) |
| Job scan: Germany + Europe | Sundays 10:00 | Same, wider radius |
| Deadline reminders | 08:00 daily | Permit, uni and tax reminders, plus work-day limit alerts (no LLM, free) |

In chat it also logs work shifts against the 140-day limit, saves your 👍/👎 on jobs, and
explains German letters.

**Start here: [SETUP-macOS.md](SETUP-macOS.md).**

## How it fits together

```
config/sources.toml ─┐
profile.md ──────────┤   scripts/*.py (plain Python, no LLM)
data/*.{toml,csv} ───┘        │ fetch, filter, dedupe, print
                              ▼
       Hermes cron ── runs the script ── hands its output to the agent + skill
                              │
                              ▼
                 skills/*/SKILL.md ── how to rank, translate and format
                              │
                              ▼
                          Telegram
```

- **Scripts** do the fetching, so results don't depend on the LLM browsing the web. When the
  job scans find nothing new, the agent isn't called at all (no cost).
- **Skills** are standard `SKILL.md` files ([agentskills.io](https://agentskills.io)), so
  they also work with other harnesses.
- **Your data** (`profile.md`, `data/`) stays in this folder. `state/` only remembers what
  was already sent.

| Path | What it is |
|---|---|
| `install.sh` | copies scripts → `~/.hermes/scripts/germany_life/` and skills → `~/.hermes/skills/germany-life/` |
| `gl` | run scripts by hand: `./gl check`, `./gl brief`, `./gl jobs`, `./gl deadlines`, `./gl ctl …`, `./gl test` |
| `config/sources.toml` | news feeds, job searches, keywords, rings |
| `templates/` | starting versions of `profile.md` and the `data/` files |
| `cron/JOBS.md` | the four `hermes cron create` commands |
| `skills/` | `trier-morning-brief`, `job-scan`, `germany-admin` |
| `tests/` | offline tests for the parsers and filters |

## Sources

- **Jobs** (data, AI and software engineering roles such as full stack, backend and mobile; cybersecurity is filtered out; edit `include`/`exclude` in `config/sources.toml`): Bundesagentur für Arbeit job search (free website interface; can change), Arbeitnow (free; has a
  visa-sponsorship filter), Remotive, Jobicy and Himalayas (free remote boards; only roles you may take while
  living in Germany, from any company; each request cached 24 hours; listings link back to the board), JSearch (optional key; broader European coverage, with manual requests, daily caching and a monthly request cap; automatic scans use cached results only)
- **News:** Google News searches for Trier, Uni Trier, Luxembourg, RLP/Saarland and rules for
  internationals; Tagesschau, DW, 16vor, Volksfreund, r/Trier, Politico Europe
- **Daily life:** Open-Meteo (weather), OpenMensa (Studierendenwerk Trier menus)

Atlas does not scrape LinkedIn, StepStone, Indeed or WG-Gesucht directly. JSearch
can return listings indexed by Google for Jobs from multiple publishers.

## Roadmap

- Luxembourg job boards (jobs.lu, Moovijob) via their email alerts
- Train disruptions on Trier ⇄ Luxembourg / Koblenz
- Application tracker (applied / interview / offer) in `data/`
- Monthly report on your 👍/👎 data: what you like, and how precise the ranking is
