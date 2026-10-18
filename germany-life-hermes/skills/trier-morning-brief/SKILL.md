---
name: trier-morning-brief
description: Turn the MORNING DATA block (weather, Mensa, deadlines, work days, news from Trier, the region, Germany and Europe) into a short English morning brief for an international MSc Data Science student in Trier. Use for the scheduled morning brief, or when the user asks what's new today.
version: 0.2.0
metadata:
  hermes:
    tags: [germany, trier, news, briefing]
    category: germany-life
---

# Trier Morning Brief

## When to Use
- The "Morning brief" cron job. The MORNING DATA block in your prompt comes from
  `germany_life/morning_brief.py`.
- The user asks for today's brief in chat. Run
  `bash {{GL}}/gl brief` and use its output as the data block.

## Procedure
1. Read PROFILE first. It says who the reader is and what they care about.
2. Use only what is in the data block. Do not search the web, and never add a news item
   that isn't in it. Every news line keeps its link.
3. Translate German headlines (`[de]`) into English. Keep names and places as they are.
4. Choose items in this order: local relevance to Trier or Uni Trier, then rules that affect
   international students (residence permits, Blue Card, work limits, Deutschlandticket,
   rent, university), then the data, AI and software job market, then general news. Skip crime reports,
   accidents and sports unless they are major. Drop duplicates of the same story.
5. Write the message in this shape, skipping any section with nothing in it:

   ☀️ **<Weekday, date>**: <weather today in one line>
   ⏰ **Deadlines**: <only if the DEADLINES section has items; bold the nearest>
   📍 **Trier**: 2–4 items
   🇱🇺 **Region**: 1–3 items
   🇩🇪 **Germany**: 2–3 items
   🇪🇺 **Europe**: 1–2 items
   💼 **Jobs**: only if the data has a jobs section; one line on the market from its numbers,
      then up to 2 standout roles (new ones first), each with why it fits the PROFILE
   🎟️ **Events**: only if the data lists events this week; up to 2, with day and place
   🍽️ **Mensa**: one line, two student-priced dishes, only if a canteen is open
   🧮 Work days: one line, only if 100 or more of the 140 are used

   Each news item is one line: `• <English headline>: <why it matters, ≤12 words> <link>`.
6. Keep the whole message under about 350 words. Never invent job numbers: use only counts given in the data.
7. If half or more of the sources in SOURCE STATUS failed, end with one line:
   `⚠️ Sources down: <names>` so the user can run `./gl check`.

## Pitfalls
- Google News titles end in " - <Publisher>". Keep the publisher once and don't repeat it.
- Times in the data block are Europe/Berlin.
- For anything about visas, permits or work rules, add "(confirm with the Ausländerbehörde or
  the International Office)". Never present it as legal advice.
- "(nothing new)" under a ring is normal. Don't pad it with older items.
