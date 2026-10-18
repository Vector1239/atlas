# Setting it up on your MacBook

About an hour, mostly waiting for installs. Do the steps in order in **Terminal**
(⌘ + Space, type "Terminal").

> **One limit of a laptop:** scheduled jobs only run while the Mac is awake. If it's
> asleep at 07:30, Hermes runs the missed job **once** when it wakes, so you get the brief
> late rather than not at all. Step 8 makes it more punctual. When you want it always on,
> move the same setup to a small server; nothing in this folder is Mac-specific.

---

## 1. Install Hermes Agent

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source ~/.zshrc
hermes doctor
```

`hermes doctor` should come back mostly green. (Prefer a window over a terminal? The
Hermes Desktop app for Apple Silicon Macs uses the same setup: `hermes desktop`.)

## 2. Choose the model (LLM)

Easiest is **OpenRouter** (one account, many models):

1. Create an account at openrouter.ai, add a small amount of credit, and **set a monthly
   spending limit** on your API key.
2. Run `hermes model`, pick OpenRouter, paste the key and choose a model.
   Use a **paid** model: free ones get removed and jobs then fail with 404s.

Alternatively `hermes setup --portal` uses a Nous Portal subscription, which also covers web search.

## 3. Connect Telegram

1. In Telegram, message **@BotFather** → `/newbot` → pick a name → copy the **bot token**.
2. Message **@userinfobot** to get your numeric **user ID**.
3. Run `hermes gateway setup`, choose Telegram, and paste the token and your user ID. Your ID
   goes in the allowlist (`TELEGRAM_ALLOWED_USERS`), so **only you** can talk to the bot.
4. Start the gateway as a background service that survives reboots:

   ```bash
   hermes gateway install
   hermes gateway start
   hermes gateway status
   ```

5. Open your bot in Telegram, say hi, then send **`/sethome`**. Scheduled messages go to this chat.

## 4. Sandbox the agent with Docker (recommended)

Out of the box, the agent's terminal commands run directly on your Mac. With the Docker
backend they run in a container that can only see this project folder.

1. Install a Docker runtime: **OrbStack** (lighter; free for personal use) or **Docker Desktop**.
   Check with `docker run hello-world`.
2. Switch Hermes over:

   ```bash
   hermes config set terminal.backend docker
   ```

3. The next step (`./install.sh`) prints two `docker_volumes` lines. Add them to
   `~/.hermes/config.yaml` under `terminal:` (`open -e ~/.hermes/config.yaml`), then run
   `hermes gateway restart`. The project is mounted read-only, and only `data/` is writable.

Skipping Docker for now is fine. Run `./install.sh local` in the next step instead, and leave
Hermes' approval prompts on (`approvals.mode: smart`, the default).

## 5. Put this folder in place and fill in your details

```bash
# assuming you downloaded germany-life-hermes.zip to Downloads
cd ~ && unzip ~/Downloads/germany-life-hermes.zip && cd ~/germany-life-hermes
chmod +x install.sh gl
./install.sh            # or: ./install.sh local   /   ./install.sh docker
```

Then edit your files (`open -e <file>` opens them in TextEdit):

- **`profile.md`**: replace every `<...>`. Keep ID numbers out of it.
- **`data/deadlines.toml`**: your real permit expiry date and uni deadlines. Delete the
  `example = true` lines once the dates are real.

## 6. Test the sources

The scripts need Python 3.11+. If `./gl` says it can't find one: `brew install python@3.12`
(needs Homebrew from brew.sh).

```bash
./gl check        # every news feed, weather, Mensa and job source: ✓ or ✗
./gl brief        # today's raw morning data
./gl jobs         # new jobs near Trier, with nothing marked as seen
./gl test         # offline tests of the parsing logic
```

Edit or disable any ✗ sources in `config/sources.toml` (`enabled = false`). A few feed URLs
there couldn't be tested when this was written.

**Optional, JSearch** (adds broader European coverage): create an account at
[OpenWeb Ninja](https://www.openwebninja.com/api/jsearch) and select the Free plan
(currently 200 requests/month, a hard limit, no credit card required). In Atlas,
open **Settings → Sources**, select OpenWeb Ninja, paste the key and save it.
Then choose **Search JSearch now** when you want new results. RapidAPI keys are also supported; choose RapidAPI for those.

Atlas stores the key in the ignored `state/job_credentials.json` file with owner-only
permissions. The app and installed Hermes scripts share it through the project
folder. For a headless installation, set `JSEARCH_API_KEY` and optionally
`JSEARCH_HOST=openwebninja` or `rapidapi`, and pass those variables through Hermes'
`terminal.env_passthrough`. A saved Atlas key takes precedence over environment
variables; Disconnect saves an empty key to disable JSearch.

JSearch requests are manual only. App startup, update restarts, ordinary refreshes, source checks and cron scans read saved results without making provider requests. Use **Settings → Sources → Search JSearch now** to authorize a search. The legacy `jobs.jsearch.enabled=false` setting also stops older app/cron versions from making automatic requests; leave it false. The manual action in current Atlas works with this safeguard in place. Each configured query fetches one page and is cached for 24 hours. Atlas caps its
JSearch requests (including failures) at 180 per UTC calendar month across the app
and cron scripts. Existing cached searches remain usable at the cap. The six default
queries cover Trier, Luxembourg, Germany, the Netherlands, Austria and Belgium;
edit them in `config/sources.toml`. Country-wide searches do not use a radius.
The provider receives search terms and places, not your profile or chats.
Bundesagentur and Arbeitnow continue working without a JSearch key.

## 7. Create the scheduled jobs

Copy the commands from **`cron/JOBS.md`**, then `hermes cron list`. Fire one right away to
see it in Telegram: `hermes cron run <job_id>`.

Then teach Hermes who you are. In Telegram, send it something like: *"I'm an international
MSc Data Science student at Uni Trier, German level B1, looking for Werkstudent jobs now and
a junior DS role after graduating in 2027."* It keeps this in memory for chats.

## 8. Make the Mac wake up for the brief (optional)

```bash
sudo pmset repeat wakeorpoweron MTWRFSU 07:25:00
```

The Mac then wakes itself at 07:25 every day, most reliably when plugged in. Undo with
`sudo pmset repeat cancel`. In System Settings → Battery → Options you can also stop it
sleeping while plugged in.

---

## Day to day

Things to send your bot:

| You send | What happens |
|---|---|
| `👍 J-3fa2c good stack` / `👎 J-91b0e needs German` | saves the rating; future scans learn from it |
| `worked 5h at Rewe today` / `HiWi 3h yesterday` | logs it, replies with your 140-day budget |
| `how many work days do I have left?` | the budget for this year |
| `remind me 3 Dec to pay the Rundfunkbeitrag` | adds a deadline with reminders |
| a photo of a German letter | plain-English explanation, deadline, draft reply |
| `/trier-morning-brief` | the brief right now |

## Safety checklist

- Only your Telegram user ID is in the allowlist.
- Don't connect your bank or your main email account.
- Don't send passport, permit or tax-ID scans. Black out numbers on letters.
- Install community skills only after reading them.
- Keep `~/.hermes/` (keys, memory) out of any git repo. This project's `.gitignore` already
  keeps `profile.md`, `data/` and `state/` out.
- Anything about visas and work limits is orientation only. Confirm with the Uni Trier
  International Office or the Ausländerbehörde.

## If something breaks

| Symptom | Fix |
|---|---|
| No messages at all | `hermes gateway status` → `hermes gateway restart`; check you sent `/sethome` |
| Bot ignores you | your user ID isn't in `TELEGRAM_ALLOWED_USERS` (`hermes gateway setup` again) |
| A job never fires | `hermes cron status` and `hermes cron doctor` |
| Jobs fail with 404 from the model | the model was removed: `hermes model` and pick another |
| `CERTIFICATE_VERIFY_FAILED` | run the script through `./gl`, or `brew install python@3.12` |
| A source shows ✗ in `./gl check` | fix its URL or set `enabled = false` in `config/sources.toml` |
| Brief arrives late | the Mac was asleep; see step 8 |
