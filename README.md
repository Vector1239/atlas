# Atlas

Open **Atlas** from **Applications** or Spotlight. The installed app is `/Applications/Atlas.app`.

Atlas brings your existing Germany-life project and Hermes Agent into one local Mac app:

- **Today:** weather, Mensa, news, deadlines, and a brief written by Gemma through Hermes' model server (no tools, thinking off). The brief brings together headlines from each region, the job market, standout new roles and events in the next 7 days. Job and event links always carry the listing's real title. With **Settings → Routines → Morning brief in Atlas** on, Atlas writes it once a day after 6:00, while it is open and Hermes is on. Regular chat keeps its Hermes tools and conversation history.
- **Job market:** an overview of the loaded listings: role types, the skills postings ask for (marked when your profile's Skills section already covers them), years of experience, seniority, pay stated in postings (hourly for student roles, yearly otherwise), German requirements, remote share and top cities. Every figure is counted by `app/job_insights.py` from titles, descriptions and provider fields. Atlas reads Bundesagentur descriptions in the background (at most 60 new ones per refresh, cached for a week) so these listings count too. **Explain with Gemma** turns the figures into takeaways for your profile without changing them.
- **Explore:** jobs and events together on a larger political map, with **Map & grid** as the default: all loaded jobs and events appear in a responsive grid below the full-width map, including listings outside the current map area and those without map pins. **Side list** optionally puts them beside the map. **Browse all results** clears filters and jumps to the full grid; **Only this map area** is an opt-in filter. Search and filters sit below the map, directly above the results grid. The sidebar labels the combined loaded total; Explore shows the jobs/events breakdown, visible count and listings excluded by map bounds or missing pins. All matching cards are shown without a Show more step. Pan or zoom to browse the visible area, select a city pin, or use the Around home / Germany / Europe views. The blue home marker uses the saved city coordinates in `config/sources.toml`; it stays separate from filters. Job pins come from `app/content/places.json`; a city not listed there is looked up once with Open-Meteo's geocoder (GeoNames data) and cached in `state/places_cache.json`, and gets a pin only when a town of exactly that name exists in the listing's country. Each refresh runs all three Bundesagentur search groups in `config/sources.toml`: Trier + 50 km, Trier + 150 km and all of Germany. Selecting a city keeps home in the view, and a persistent **Home** button returns there after panning away. Additional filters and source notes are collapsed by default. Switch between Everything, Jobs, Remote and Events; **Remote** lists every remote or home-office role (including Remotive and Jobicy listings open to Germany, Europe or worldwide, labelled with where applicants may live), ignoring distance; search both kinds and filter by radius, city, event dates and category. More filters keep job boards, saved/student roles, remote mentions, posting language, seniority and sorting available. Original job details, bookmarks, feedback and Ask Atlas are still included.
- **Job sources:** Bundesagentur für Arbeit and Arbeitnow work without a key. Optional JSearch searches more publishers across Europe through OpenWeb Ninja or RapidAPI. Add its key in **Settings → Sources**. **Search JSearch now** in Settings → Sources is the only action that can send JSearch requests. Startup, updates, normal refreshes and scheduled scans read cached JSearch results without spending credits, even after the 24-hour cache expires. A manual search can fetch one page per query per 24 hours, with a shared cap of 180 requests per UTC calendar month. OpenWeb Ninja currently offers a 200-request free plan with no credit card required. Saved keys stay in place across updates and restarts; the password field only replaces a key and never reveals the stored value. The key stays in the ignored, owner-only `state/job_credentials.json`; search terms and locations go to the provider, while your profile and chats stay local. Expanding a job fetches the Bundesagentur description or reads structured JobPosting data and readable text from its public listing page, cached for seven days. Details can be unavailable on blocked or JavaScript-only pages. This integration follows the provider approach in [Dossier](https://github.com/AienTech/dossier) with an independent implementation.
- **News:** a continuous image-and-text grid showing every gathered story by default, with real article photos where available. A compact toolbar opens a slide-over for region/source/time/search filters, images-only filtering and English/original headline controls. Publisher labels, publication dates, original titles and source links stay on each story. Today keeps a compact three-story preview linking to News. Existing translations are included locally; new headlines translate automatically in small batches while Gemma is already running and chat is idle. Gathered stories stay available for 14 days after their publication, even if the publisher rotates its feed.
- **Life admin:** add deadlines and work shifts; see the project's work-day budget.
- **Tech:** six live event sources: developers.events, the CCC calendar, Maschinendeck Trier’s public calendar API, Silicon Luxembourg’s calendar, Major League Hacking and Devpost. Reading comes from GitHub, Cloudflare, Google Developers, Mozilla Hacks and Rust. Source, topic/search, event type, date, country/city and radius filters combine. Event cards show source-provided times, entry prices, prize pools and topics where available; **Details & sources** exposes venues, organisers, provenance and checks. Devpost dates are explicitly labelled submission windows rather than in-person event dates. MLH’s current season is selected from the date; Maschinendeck recurring meetings use the calendar’s expanded occurrences for the next 90 days. Calendar all-day end dates follow RFC 5545, and timezone changes are preserved. Duplicate listings combine provenance; failed sources keep their own previous cache without blocking healthy feeds. Feeds refresh on launch, on request and every six hours. Devpost refreshes read at most five pages of the public open/upcoming feed, so coverage is not exhaustive. Curated fallback entries remain labelled with their original check date. Conference data is attributed to [developers.events contributors](https://github.com/scraly/developers-conferences-agenda) under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/); Atlas filters and reformats the listings.
- **Ask Atlas:** one continuing Hermes conversation with local Gemma, web search/extraction, memory and the Germany-life skills. Hermes keeps the conversation itself; **New conversation** starts a fresh one. Searches contact external search providers/sites; model inference stays local. Commands that need approval are declined automatically.
- **Settings:** edit your profile, change reasoning effort, start or stop Hermes and Gemma, manage routines, check sources, and install app updates.

The version (currently 1.12.4) is shown at the bottom of the sidebar and under **Atlas → About Atlas**. It is set in `app/package.json`; bump it there when you change the app.

## Updating Atlas

Open **Settings → Updates**, or **Atlas → Check for Updates…** in the Mac menu. Select **Check for updates**, then **Update & restart** when an update is available. Progress and errors appear in the app; the update log is available on the same page.

The updater fetches `main` from the private `Vector1239/atlas` repository and compares its commit with the installed build. It still detects an update if you have already pulled the source, or if a commit did not bump the version. Builds run in a temporary checkout; the app is signed locally, installed and restarted, with the previous app restored if the new app fails its startup check. Personal profiles, chats and other local data stay in place.

Keep the source clone at its configured location, with Node.js, Git and the GitHub CLI installed and signed in. Updates build the fetched `main` commit in a separate checkout, with its runtime scripts included in the app. Your development checkout, branch, local edits and untracked files are preserved. An older version on GitHub is never offered as a downgrade. Nothing is downloaded or installed until you use the update controls. Stop any active AI request before installing; Gemma’s paused/startup preference is preserved.

If an older installed updater refuses to update because of local edits, quit Atlas with **Command-Q**, then open `app/Update Atlas.command` from this checkout once. It uses the fixed updater to build and install GitHub main; subsequent updates work in the app.

## First use

1. Open Atlas. In **Settings → Local model**, select **Connect to Hermes** once, then **Start Hermes**. Sending a message also starts it. The lower-left status shows **Gemma is ready** while the model is loaded.
2. In **Settings → Your profile**, replace the template placeholders and save.
3. Add your real deadlines in **Life admin**. The example dates are ignored.
4. Enable routines in **Settings → Routines**. Hermes runs them on schedule while it is on, even when Atlas is closed.

Telegram is optional. No cloud model key is required for the installed configuration.

## Local model

Gemma 4 12B Instruct Q4_K_M (7.12 GB), managed by Hermes. Hermes' model server (llama.cpp with Apple Metal) loads it on demand with at least a 64K context and serves Ask Atlas, briefs, translations and routines. The pinned source, exact file size and published SHA-256 are in `app/content/local-model.json`. Install or verify it with `python3 app/install_model.py`, which puts it in `~/.hermes/models/` (and moves a copy from older Atlas versions instead of downloading again) and verifies the SHA-256 before creating the ready marker. Hermes needs its llama.cpp engine once: run `hermes model` → **Local models**, which also lets you pick Gemma as Hermes' default model for routines.

Atlas unloads Gemma after 5 minutes without use, unless a routine is running; the next request loads it again, which takes a few seconds. **Stop Gemma** (at the top of every page while it is active, and in **Settings → Local model**) cancels the current request and unloads it straight away. **Stop Hermes** frees everything Hermes uses; routines and chat pause until you start it again. Quitting Atlas leaves Hermes running so routines keep working.

The current English job titles and headline translations are included locally. Unseen German titles remain clearly labelled in their original language until you select **Translate new titles** with Gemma running. New headlines translate automatically while Gemma is already running and chat is idle; News shows the queue and offers **Translate now**. Translation batches yield to foreground chat. Both translation actions require Gemma to already be running and never start it automatically. Translations are cached by their original text on your Mac. Translated titles do not establish English-only eligibility; check the original listing for requirements. Distances are supplied by job boards and are not driving distances; unknown distances are excluded when you set a radius.

Map pins use verified city centres from [Open-Meteo / GeoNames](https://open-meteo.com/en/docs/geocoding-api); they do not claim an exact employer or event address. Cities without a verified match stay unplaced; untick **Only this map area** to include those listings. City coordinates ship with the app; no profile or job description is sent to a geocoding service. Job radii use the board's distance from Trier; event radii use approximate straight-line distance between city centres. Neither is a travel-distance estimate.

The political basemap bundles [Natural Earth](https://www.naturalearthdata.com/) public-domain country outlines, selected state/regional boundaries, and over 1,300 city locations. City dots and names become denser as you zoom, with listing cities labelled beside their pins and independently visible cities even when filters hide listings. It shows solid country borders and dashed state/regional borders, without terrain or vegetation clutter at regional scales. State outlines cover Germany (all 16 states), Austria, Switzerland, the Netherlands and Belgium. These are generalised boundaries for regional browsing. Details and rebuilding instructions are in [the map data notes](app/content/political-map-README.md).

The regional basemap works offline after installation. At zoom level 10 and above, an online OpenStreetMap street layer shows neighbourhoods, road names and building detail as you zoom further, up to level 19. **City streets** jumps to the selected city, or your saved home when no city is selected; **Regional map** returns to the wider home view. Street tiles use the normal browser cache, with no bulk downloads or map-service key. If tiles cannot load, the bundled outlines and home marker remain available, with a retry control. Viewing city streets sends tile coordinates and normal network information to OpenStreetMap; it does not send your profile or job details. The home pin means the saved city/base location, not live GPS; Atlas does not request device geolocation. Job and event filters never remove this marker. A **Home** control stays visible if the pin leaves the viewport, and **Map only** hides the result list for the widest view.

Events remain a dated selection checked on 17 October 2026, not a comprehensive live event feed. Expired entries disappear, old date checks are flagged, and official calendars are linked below the map.

News images are extracted from RSS enclosures, Media RSS, embedded feed images, or the publisher's Open Graph/Twitter article metadata. They are fetched over public HTTPS in the background, cached under `state/news_images/`, and served through the app's authenticated image endpoint. Original source labels and any image descriptions/credits supplied in the metadata are preserved. Atlas never substitutes unrelated stock images or a Google News logo. Opaque Google News links are resolved through Google’s public reader to the exact publisher article, then its article image is fetched. Google’s generic News logo is rejected. Resolved URLs and successful images are cached; resolver calls are spaced out and back off for fifteen minutes after rate limits. This reader protocol is undocumented, and articles that cannot resolve or publishers that block previews can still remain text-only.

The image cache keeps at most 160 recent article records, limits each image to 4 MiB, reuses successful previews for seven days and retries unavailable previews after fifteen minutes. Redirects are checked, connections are pinned to verified public IPs with hostname-validating TLS, and only supported raster images are served; page HTML and scripts are never rendered. Image fetching sends public article/image URLs and normal network information, without Atlas session cookies, profiles or chat data. The cache is local, excluded from Git, and safe to remove when Atlas is closed.

Fresh news, article images, city street maps, weather, job sources, and external links still need internet. Model inference runs locally.

## How it fits together

Atlas' React interface runs in an Electron Mac app. A Python service reads and updates project data and starts the local model. Chat calls the installed `hermes chat` command and uses real Hermes sessions, memory, skills, and Docker terminal tools. Atlas does not implement a replacement agent.

The app uses `germany-life-hermes` for your profile, deadlines, work log, and feedback. Keep that folder in place. `state/atlas.json` stores app chats and preferences; `state/atlas_snapshot.json` caches sources.

## Development

From a fresh clone, install the project scripts and skills using the [macOS setup guide](germany-life-hermes/SETUP-macOS.md). Hermes (with its gateway installed as a service: `hermes gateway install`), Python 3.12 and Docker Desktop are separate prerequisites; the Gemma weights are downloaded separately and are not stored in Git.

From the repository root:

```bash
cd app
npm ci
npm run build
/opt/homebrew/bin/python3.12 backend.py
```

For a checkout outside `~/Projects/Atlas`, set `ATLAS_PROJECT` to the absolute path of its `germany-life-hermes` folder before starting the app or service. Run `npm start` from `app/` to open the desktop app, or `npm run package` to create an Apple Silicon app under `app/release/`. `npm run build` records the current Git commit in the ignored `app/build-info.json`, which is included in packaged apps for update checks.

For live reload while editing the interface, start the service with `backend.py --port 4317` (or set `ATLAS_PORT` to match), open the launch URL it prints once so the browser gets a session, then run `npm run dev` and open `http://127.0.0.1:4173`.

The service prints a local launch URL that establishes an app session. It listens only on loopback, requires a launch-session cookie for private endpoints, rejects outside origins, and exposes specific app actions. The renderer has no Node access.

Tests from the repository root:

```bash
python3.12 -m unittest discover -s app/tests -v
germany-life-hermes/gl test
node --test app/tests/*.test.js
```

The repository contains app source, tests, icons, project scripts, skills, templates and the npm lockfile. Personal profiles, chats, deadlines, work logs, launch tokens, logs, model weights, dependencies and build output are excluded. Your local data stays in place when cleaning or updating the source; `germany-life-hermes/install.sh` creates missing personal files from the checked-in templates.
