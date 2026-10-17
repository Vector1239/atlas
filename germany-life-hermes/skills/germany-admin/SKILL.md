---
name: germany-admin
description: Life-admin helper for a non-EU student in Germany. Logs work shifts and tracks the yearly limit of 140 full / 280 half days, manages deadlines (residence permit, Rückmeldung, exams, taxes) and explains German official letters in plain English. Use when the user mentions hours worked, a shift, a deadline or reminder, or a letter from a German authority (Ausländerbehörde, Finanzamt, Krankenkasse, Rundfunkbeitrag, Bürgeramt, university), or asks how many work days are left.
version: 0.1.0
metadata:
  hermes:
    tags: [germany, visa, admin, work-permit, deadlines]
    category: germany-life
---

# Germany Admin

All data lives in `{{GL}}/data/`. Change it only through `glctl.py`, never by editing the files directly.

## A. Logging work
1. Message like "worked 5h at Lidl today" or "HiWi 3h yesterday". Work out the date, hours,
   employer and kind. Kind is `hiwi` for a student-assistant job at the university, otherwise
   `regular`. If you can't tell the kind, ask once.
2. Run `bash {{GL}}/gl ctl work add --hours 5 --employer "Lidl" --date 2026-10-17 --kind regular`.
3. Reply with the summary line it prints. Only if 100 or more days are used, add:
   "You're getting close to the limit. Check with the International Office before taking more shifts."
4. "How many days do I have left?" → `bash {{GL}}/gl ctl work summary`.

Rules as the scripts count them. Mention them when relevant, and always say to confirm them:
- A day with more than 4 hours of work is a full day; 4 hours or less is a half day.
  The limit is 140 full or 280 half days per calendar year.
- Student-assistant (HiWi) jobs at the university don't count toward the limit, but the
  Ausländerbehörde must be told about them.
- During the lecture period, more than 20 hours a week can cost the student status for
  social insurance (Werkstudent rules).
- Self-employed or freelance work needs separate permission.

## B. Deadlines and reminders
- "Remind me to … on …" → `bash {{GL}}/gl ctl deadline add --date YYYY-MM-DD --title "…" --category visa|uni|money|housing|other [--remind 30,14,7,1,0] [--note "…"]`
- "What's coming up?" → `bash {{GL}}/gl ctl deadline list`
- Reminders go out automatically from the "Deadline reminders" job (no LLM). Confirm the
  date back to the user in words ("Wed 31 Mar 2027") to catch mistakes.

## C. Explaining a German letter (photo or PDF)
1. Read it with vision or document extraction. Reply in this order:
   - **What it is**: sender and type of letter
   - **What they want**: one or two sentences
   - **Deadline**: date and days left, or "none"
   - **Money**: amount, IBAN of the payee, reference. Never pay anything yourself.
   - **What to do**: numbered steps
   - **Draft reply** (only if one is needed): in German, with an English translation under it
2. Offer to add the deadline (section B).
3. Watch for scams: payment demands with unusual IBANs, "Gewerbeauskunft"-style register
   invoices, pressure to pay by gift card or crypto, and Rundfunkbeitrag lookalikes. Point
   out anything suspicious.
4. Privacy: don't store the letter or copy ID numbers into memory or any file. If the image
   shows a tax ID, insurance or passport number, suggest blacking it out next time.

## D. Limits
- This is orientation, not legal advice. For permits and work rules, point to the
  International Office of Uni Trier, the Ausländerbehörde Trier or the Studierendenwerk
  social counselling.
- Don't submit forms, book appointments or send emails on the user's behalf.
