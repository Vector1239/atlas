"""A job-market overview from the listings Atlas already has, computed without an AI model.

Role types, skills, experience and pay come from titles, descriptions and the providers' own
fields. Every number is a count over real postings, so Gemma can explain it but never makes it up.
"""
from __future__ import annotations

import collections
import re
import statistics

FAMILIES = [
    ("Research & university", r"wissenschaftlich|hilfskraft|\bhiwi\b|research assistant|doktorand|\bph\.?d\b|postdoc|promotion|forscher|researcher"),
    ("Data engineering", r"data engineer|daten ?ingenieur|analytics engineer|data architect|datenarchitekt|\betl\b|data platform|big data|datenbank|database"),
    ("Data science", r"data scien|datenwissenschaft|scientist"),
    ("ML & AI", r"machine learning|maschinelles lernen|\bml\b|\bai\b|\bki\b|künstliche intelligenz|artificial intelligence|deep learning|computer vision|\bnlp\b|\bllm|mlops"),
    ("Analytics & BI", r"analy|business intelligence|\bbi\b|reporting|controlling|statisti|insight"),
    ("Software & IT", r"software|develop|entwickl|engineer|informati|programm|devops|cloud|\bit\b|\bit-|system|admin"),
    ("Consulting & product", r"consult|berater|beratung|product|produkt|project|projekt|manage"),
]
FAMILY_RULES = [(name, re.compile(pattern, re.I)) for name, pattern in FAMILIES]

SKILLS = {
    "Python": r"\bpython\b", "SQL": r"\bsql\b|postgres|\bmysql\b", "R": None,
    "Machine learning": r"machine learning|maschinelles lernen|\bml\b", "Statistics": r"statisti",
    "Deep learning": r"deep learning|neural net|neuronale", "LLMs & GenAI": r"\bllms?\b|large language|generative ai|\bgen ?ai\b|\bgpt|langchain|\brag\b|prompt engineering",
    "NLP": r"\bnlp\b|natural language", "Computer vision": r"computer vision|bildverarbeitung|image processing|opencv",
    "Pandas / NumPy": r"\bpandas\b|\bnumpy\b", "scikit-learn": r"scikit|sklearn", "PyTorch": r"pytorch",
    "TensorFlow": r"tensorflow|\bkeras\b", "Spark": r"\b(?:py)?spark\b", "Databricks": r"databricks",
    "Snowflake": r"snowflake", "Airflow": r"airflow", "dbt": r"\bdbt\b", "Kafka": r"\bkafka\b",
    "ETL & pipelines": r"\betl\b|\belt\b|data pipeline|datenpipeline|data warehous", "AWS": r"\baws\b|amazon web services",
    "Azure": r"\bazure\b", "Google Cloud": r"\bgcp\b|google cloud|bigquery", "Docker & Kubernetes": r"\bdocker\b|kubernetes|\bk8s\b",
    "MLOps": r"mlops|mlflow|model deployment", "Git": r"\bgit\b|github|gitlab", "Linux": r"\blinux\b",
    "Power BI": r"power ?bi", "Tableau": r"tableau", "Excel": r"\bexcel\b", "SAP": r"\bsap\b",
    "Java": r"\bjava\b(?!\s*script)", "Scala": r"\bscala\b", "C++": r"c\+\+", "JavaScript / TypeScript": r"javascript|typescript|node\.?js",
    "MATLAB": r"matlab",
}
SKILL_RULES = {name: re.compile(pattern, re.I) for name, pattern in SKILLS.items() if pattern}
# "R" is a single capital letter: case-sensitive, and not R&D, R+V or a word fragment.
SKILL_RULES["R"] = re.compile(r"(?<![\w&.+'’-])R(?![\w&+#'’-])")

LEVEL_ENTRY = re.compile(r"junior|graduate|absolvent|einsteiger|trainee|entry|young professional", re.I)
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "ten": 10,
                "ein": 1, "einem": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "sechs": 6, "sieben": 7, "acht": 8, "zehn": 10}
_N = r"(\d{1,2}|" + "|".join(NUMBER_WORDS) + r")"
EXPERIENCE = [
    re.compile(r"(?<!seit )\b" + _N + r"\s*\+?\s*(?:(?:-|–|to|bis)\s*\d{1,2}\s*)?(?:years?|yrs?|jahre?n?)\b(?:\s+[\w-]+){0,5}?\s+(?:experience|erfahrung|berufserfahrung|praxiserfahrung)", re.I),
    re.compile(r"(?:experience|erfahrung)\b[^.;\n]{0,30}?(?:mindestens|at least|min\.|von)?\s*\b" + _N + r"\s*\+?\s*(?:years?|jahre?n?)\b", re.I),
]
SEVERAL_YEARS = re.compile(r"mehrjährige|mehreren jahren|several years|multiple years|many years|langjährige|extensive experience", re.I)
NO_EXPERIENCE = re.compile(r"berufseinsteiger|keine berufserfahrung|no (?:prior |previous )?experience (?:is )?(?:required|needed)|"
                           r"erste (?:praktische |berufliche )?(?:berufs)?erfahrung|first (?:practical |professional )?experience", re.I)

_AMOUNT = r"\d{1,3}(?:[.,  ]\d{3})+(?:,\d{2})?|\d+(?:[.,]\d{1,2})?"
_CURRENCY = r"(?:€|eur\b|euro\b)"
MONEY = re.compile(rf"(?:{_CURRENCY}\s*)?({_AMOUNT})\s*(k\b|tsd\.?|tausend)?\s*(?:{_CURRENCY})?"
                   rf"(?:\s*(?:-|–|bis|to)\s*(?:{_CURRENCY}\s*)?({_AMOUNT})\s*(k\b|tsd\.?|tausend)?)?\s*(?:{_CURRENCY})?", re.I)
PAY_WORDS = re.compile(r"gehalt|vergütung|verguetung|salary|compensation|brutto|gross|lohn|bezahlung|\bpay\b|paid|verdienst|einkommen|tarif|"
                       r"stunde|\bstd\b|hour|/h\b|monat|month|jahr|year|p\.\s?a\.", re.I)
NOT_PAY = re.compile(r"umsatz|revenue|funding|investment|finanzierung|förder|million|\bmio\b|\bmrd|billion|zuschuss|ticket|rabatt|discount|budget|bonus", re.I)
HOURLY = re.compile(r"stunde|\bstd\b|/\s?h\b|per hour|hourly|an hour|/hr\b", re.I)
MONTHLY = re.compile(r"monat|month|\bmtl\b", re.I)
YEARLY = re.compile(r"jahr|year|annual|p\.\s?a\.|jährlich", re.I)
LIMITS = {"hour": (8, 150), "month": (500, 20000), "year": (10000, 300000)}


def family(job):
    for text in (job.get("title_en") or "", job.get("title") or "", job.get("occupation") or ""):
        for name, rule in FAMILY_RULES:
            if text and rule.search(text):
                return name
    return "Other"


def skills(text):
    return [name for name, rule in SKILL_RULES.items() if rule.search(text)]


def profile_skills(profile):
    """Skills named in the profile's Skills section, ignoring <placeholders> and what is still being learned."""
    match = re.search(r"^#+[^\n]*skill[^\n]*\n(.*?)(?=^#|\Z)", profile or "", re.I | re.M | re.S)
    if not match:
        return []
    lines = [line for line in re.sub(r"<!--.*?-->|<[^>]*>", " ", match.group(1), flags=re.S).splitlines()
             if not re.match(r"\s*[-*]?\s*learning\b", line, re.I)]
    return skills("\n".join(lines))


def _years(value):
    return NUMBER_WORDS.get(value.lower(), None) if not value.isdigit() else int(value)


def experience_years(job, text):
    """The minimum years a posting asks for, or None when it doesn't say."""
    months = job.get("experience_months")
    if isinstance(months, (int, float)) and months > 0:
        return round(months / 12, 1)
    found = [_years(match.group(1)) for rule in EXPERIENCE for match in rule.finditer(text)]
    found = [value for value in found if value is not None and 0 < value <= 15]
    if found:
        return min(found)
    if NO_EXPERIENCE.search(text):
        return 0
    if SEVERAL_YEARS.search(text):
        return 3
    return None


def _number(value, unit):
    value = value.replace(" ", "").replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", value):
        number = float(re.sub(r"[.,]", "", value))
    elif re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+,\d{2}", value):
        number = float(re.sub(r"[.,]", "", value[:-3]))
    else:
        number = float(value.replace(",", "."))
    return number * 1000 if unit else number


def pay(job, text):
    """{"period": "hour"|"year", "low", "high"} from the provider's fields or the description; monthly × 12."""
    salary = job.get("salary") or {}
    if salary and (salary.get("currency") or "EUR").upper() == "EUR":
        period = {"HOUR": "hour", "MONTH": "month", "YEAR": "year"}.get((salary.get("period") or "").upper())
        values = [v for v in (salary.get("min"), salary.get("max")) if isinstance(v, (int, float)) and v > 0]
        if period and values:
            return _period_result(period, min(values), max(values))
    for match in MONEY.finditer(text):
        if not re.search(_CURRENCY, match.group(0), re.I):
            continue
        context = text[max(0, match.start() - 70):match.end() + 40]
        # Perks and company figures are excluded only when they sit right next to the amount.
        if NOT_PAY.search(text[max(0, match.start() - 45):match.end() + 12]) or not PAY_WORDS.search(context):
            continue
        try:
            low = _number(match.group(1), match.group(2))
            high = _number(match.group(3), match.group(4) or match.group(2)) if match.group(3) else low
        except ValueError:
            continue
        after = text[match.end():match.end() + 30]
        stated = [period for words in (after, context) for period, rule in (("hour", HOURLY), ("month", MONTHLY), ("year", YEARLY))
                  if rule.search(words)]
        # A stated period wins; otherwise (or if it doesn't fit the amount) the size of the amount decides.
        for period in stated[:1] + ["hour" if low <= 150 else "month" if low <= 12000 else "year"]:
            result = _period_result(period, min(low, high), max(low, high))
            if result:
                return result
    return None


def _period_result(period, low, high):
    floor, ceiling = LIMITS[period]
    if not (floor <= low <= ceiling and floor <= high <= ceiling):
        return None
    if period == "month":
        period, low, high = "year", low * 12, high * 12
    return {"period": period, "low": round(low, 2), "high": round(high, 2)}


def _spread(values):
    values = sorted(values)
    if not values:
        return None
    low, high = (statistics.quantiles(values, n=4)[0], statistics.quantiles(values, n=4)[2]) if len(values) >= 4 else (values[0], values[-1])
    return {"n": len(values), "median": round(statistics.median(values), 2), "low": round(low, 2), "high": round(high, 2)}


def _top(counter, limit):
    return [{"name": name, "count": count} for name, count in counter.most_common(limit)]


def analyze(jobs, profile=""):
    """jobs: enriched listings, each with the best description Atlas has as `text`."""
    rows = []
    for job in jobs:
        text = " ".join(filter(None, [job.get("title", ""), job.get("title_en") or "", " ".join(job.get("tags") or []),
                                      " ".join(job.get("skills") or []), job.get("text", "")]))
        level = ("Student & intern" if "student-job" in job.get("flags", []) else "Senior & lead" if "senior" in job.get("flags", [])
                 else None)
        years = experience_years(job, job.get("text", ""))
        if level is None:
            level = "Entry & junior" if LEVEL_ENTRY.search(f"{job.get('title', '')} {job.get('title_en') or ''}") or years == 0 else "Professional"
        rows.append({"job": job, "family": family(job), "skills": skills(text), "years": years, "level": level,
                     "pay": pay(job, job.get("text", "")), "described": bool(job.get("text"))})
    described = [row for row in rows if row["described"]]
    have = set(profile_skills(profile))
    skill_counts = collections.Counter(name for row in described for name in row["skills"])
    families = []
    for name, count in collections.Counter(row["family"] for row in rows).most_common():
        members = [row for row in rows if row["family"] == name]
        inner = collections.Counter(skill for row in members if row["described"] for skill in row["skills"])
        families.append({"name": name, "count": count, "students": sum(row["level"] == "Student & intern" for row in members),
                         "top_skills": [skill for skill, _ in inner.most_common(3)],
                         "jobs": [{key: row["job"].get(key) for key in ("id", "title_en", "title", "company", "city")} for row in members[:4]]})
    buckets = collections.Counter()
    for row in rows:
        if row["years"] is not None:
            buckets["0–1 years" if row["years"] < 2 else "2–3 years" if row["years"] < 4 else "4–5 years" if row["years"] < 6 else "6+ years"] += 1
    paid = [row for row in rows if row["pay"]]
    hourly = [(row["pay"]["low"] + row["pay"]["high"]) / 2 for row in paid if row["pay"]["period"] == "hour"]
    yearly = [(row["pay"]["low"] + row["pay"]["high"]) / 2 for row in paid if row["pay"]["period"] == "year"]
    flags = lambda name: sum(name in row["job"].get("flags", []) for row in described)
    in_demand = [{"name": name, "count": count, "share": round(count / len(described), 3), "have": name in have}
                 for name, count in skill_counts.most_common(14)]
    return {
        "total": len(rows), "described": len(described),
        "students": sum(row["level"] == "Student & intern" for row in rows),
        "families": families,
        "levels": [{"name": name, "count": sum(row["level"] == name for row in rows)}
                   for name in ("Student & intern", "Entry & junior", "Professional", "Senior & lead")],
        "skills": in_demand,
        "experience": {"known": sum(buckets.values()), "median": statistics.median([row["years"] for row in rows if row["years"] is not None])
                       if buckets else None,
                       "buckets": [{"name": name, "count": buckets[name]} for name in ("0–1 years", "2–3 years", "4–5 years", "6+ years")]},
        "pay": {"known": len(paid), "hourly": _spread(hourly), "annual": _spread(yearly),
                "examples": [{"id": row["job"].get("id"), "title": row["job"].get("title_en") or row["job"].get("title"),
                              "company": row["job"].get("company"), **row["pay"]} for row in paid[:12]]},
        "language": {"described": len(described), "german_required": flags("german-required"),
                     "posting_in_german": flags("posting-in-german"), "english": flags("english")},
        "remote": sum(bool(row["job"].get("remote")) for row in rows),
        "visa": sum(bool(row["job"].get("visa")) for row in rows),
        "cities": _top(collections.Counter(row["job"].get("city") for row in rows
                                           if row["job"].get("city") and row["job"].get("city") != "Location not provided"), 6),
        "companies": [row for row in _top(collections.Counter(row["job"].get("company") for row in rows if row["job"].get("company")), 8)
                      if row["count"] > 1],
        "profile_skills": sorted(have),
        "gaps": [row["name"] for row in in_demand if not row["have"] and row["share"] >= 0.1][:5] if have else [],
    }
