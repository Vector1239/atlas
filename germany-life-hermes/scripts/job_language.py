"""Extract stated German requirements; CEFR levels are never inferred from fluency."""
from __future__ import annotations

import html
import re

LANG = r"\b(?:german|deutsch(?:[- ]?(?:kenntnisse[n]?|sprachkenntnisse[n]?)|e[nrms]?)?)\b"
LEVEL = r"\b[abc][12](?:\s*[/–-]\s*(?:[abc])?[12])?\+?(?!\w)"
OTHER_LANGUAGE = re.compile(r"\b(?:english|englisch\w*|french|französisch\w*|spanish|italian|dutch)\b", re.I)
PATTERNS = [
    re.compile(LANG + r"(?P<bridge>(?:(?:mind|min|bzw|ca)\.|[^.;!?\n]){0,65}?)" + r"(?P<level>" + LEVEL + r")", re.I),
    re.compile(r"(?P<level>" + LEVEL + r")\s*[-–]?\s*(?:(?:level|niveau|proficiency|kenntnisse|in|of|the|der|deutschen|sprache)\s*){0,6}" + LANG, re.I),
]
OPTIONAL = re.compile(r"nice[- ]to[- ]have|preferred|preferably|optional|a plus|bonus|von vorteil|wünschenswert|idealerweise|not mandatory", re.I)
NEGATED = re.compile(r"\bno (?:prior |previous )?(?:german|deutsch)|(?:not|nicht|keine?)\s+(?:strictly\s+)?(?:required|necessary|needed|mandatory|erforderlich|notwendig|vorausgesetzt)|keine?\s+deutschkenntnisse", re.I)
REQUIRED = re.compile(r"required|requirement|mandatory|must|at least|minimum|mindestens|erforderlich|notwendig|voraussetzung|benötig|brauchen|setzt.*voraus", re.I)
EDUCATION = re.compile(r"courses?|classes|lessons|training|unterricht|sprachkurs|schulung|learn german|deutsch lernen", re.I)
QUALITATIVE = re.compile(r"(?:fluent|native|business[- ](?:level|fluent)|professional proficiency)(?:\s+[\w-]+){0,2}\s+german|"
                         r"german(?:\s+[\w-]+){0,3}\s+(?:fluent|native|business[- ](?:level|fluent))|"
                         r"fließend\w*\s+deutsch|verhandlungssicher\w*\s+deutsch|sehr gute\s+deutschkenntnisse|deutsch\s+als\s+muttersprache", re.I)


def _context(text, match, isolate=True):
    # Keep neighbouring sentences and other languages from lending their levels/cues.
    start = max([text.rfind(mark, 0, match.start()) for mark in '.!?;\n'] + [0])
    if start:
        start += 1
    end = min([at for mark in '.!?;\n' if (at := text.find(mark, match.end())) >= 0] + [len(text)])
    if isolate:
        if OTHER_LANGUAGE.search(text[start:match.start()]):
            start = match.start()
        other = OTHER_LANGUAGE.search(text, match.end(), end)
        if other:
            end = other.start()
    return text[max(start, match.start()-90):min(end,match.end()+65)].strip()


def german_requirement(text):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    candidates = []
    for rule in PATTERNS:
        for match in rule.finditer(text):
            if OTHER_LANGUAGE.search(match.groupdict().get('bridge') or ''):
                continue
            context = _context(text, match)
            if NEGATED.search(context):
                continue
            level = re.sub(r"\s+", "", match.group('level')).upper().replace('/', '–').replace('-', '–')
            # B1/B2 and B1–2 both retain the stated range.
            if re.search(r"–[12]$",level):
                level = level[:-1]+level[0]+level[-1]
            full_context = _context(text,match,isolate=False)
            alternative = bool(OTHER_LANGUAGE.search(full_context) and re.search(r"\b(?:or|oder)\s+(?:german|deutsch\w*|english|englisch\w*|french|französisch\w*|spanish|italian|dutch)\b", full_context, re.I))
            status = 'mentioned' if alternative else 'preferred' if OPTIONAL.search(context) else 'required'
            if EDUCATION.search(context) and not REQUIRED.search(context):
                status = 'mentioned'
            label = f"German {level} {status}"
            candidates.append({'status':status,'level':level,'label':label,'evidence':context[:220],
                               'explicit':bool(REQUIRED.search(context))})
    for match in QUALITATIVE.finditer(text):
        context = _context(text, match)
        if NEGATED.search(context):
            continue
        status = 'preferred' if OPTIONAL.search(context) else 'required'
        candidates.append({'status':status,'level':None,'label':f"German {status}", 'evidence':context[:220], 'explicit':bool(REQUIRED.search(context))})
    # An explicit generic requirement still matters when the level is unstated.
    if not candidates:
        for match in re.finditer(LANG,text,re.I):
            context = _context(text,match)
            if NEGATED.search(context):
                return {'status':'not_required','level':None,'label':'German not required','evidence':context[:220]}
            if REQUIRED.search(context) and not OTHER_LANGUAGE.search(context):
                candidates.append({'status':'required','level':None,'label':'German required','evidence':context[:220],'explicit':True})
    if not candidates:
        return {'status':'unknown','level':None,'label':'','evidence':''}
    candidates.sort(key=lambda row: ({'required':0,'preferred':1,'mentioned':2}[row['status']], not row['explicit'], row['level'] is None))
    return {key:value for key,value in candidates[0].items() if key != 'explicit'}
