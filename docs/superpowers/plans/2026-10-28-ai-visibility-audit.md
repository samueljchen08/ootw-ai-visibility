# AI-Search Visibility Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run a pipeline that measures Out of the Woods Construction's visibility in AI answer engines for Boston/MetroWest design-build remodeling queries and produces a Markdown + PDF report with recommendations.

**Architecture:** Deterministic Python scripts generate the query set, validate agent output, audit the website, aggregate results, and render the report. Claude subagents (dispatched from the orchestrating session with the Agent tool) do the web-search-heavy work: simulated answer engines, footprint lookup, competitor profiling. The browser harness runs a real-engine spot check. The orchestrator writes narrative sections by hand into `report/narrative/*.md`, which the aggregator inlines.

**Tech Stack:** Python 3.14 (stdlib only for scripts; `markdown` for rendering), `uv run --with` for dependencies, pytest, Google Chrome headless for PDF, Claude Code Agent tool, browser-harness skill.

**Spec:** `docs/superpowers/specs/2026-10-28-ai-visibility-audit-design.md`

## Global Constraints

- Scripts use only the Python standard library except `scripts/render.py` (`markdown`). Run anything needing extras with `uv run --with <pkg>`.
- Run tests with: `uv run --with pytest --with markdown python -m pytest tests -q` from the project root.
- Query set must be deterministic: exactly 40 queries, exactly 8 with `tier: "core"`, no duplicate ids or texts.
- Agent output must be JSON only, matching the record schema in Task 2. Never fabricate engine answers; blocked or failed runs are recorded with `status: "blocked"`.
- Company reference strings: name `Out of the Woods Construction & Cabinetry`, short `Out of the Woods Construction`, domain `outofthewoodsconstruction.com`.
- Scope towns (exact spelling used everywhere): Boston, MetroWest, Waltham, Newton, Wellesley, Needham, Lexington, Reading, Arlington, Belmont, Weston, Concord.
- Commit after each task with a message ending in `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

---

## File Structure

| Path | Responsibility |
|---|---|
| `scripts/build_queries.py` | Deterministic 40-query set; writes `queries.json` |
| `scripts/validate.py` | Schema validation of agent result files |
| `scripts/site_audit.py` | Fetch + parse OOTW site: robots, sitemap, per-page facts, JSON-LD |
| `scripts/aggregate.py` | Load all results, compute scorecard, write `report/report.md` |
| `scripts/render.py` | Markdown to HTML to PDF |
| `agents/answer-engine.md` | Prompt template for simulated answer-engine subagents |
| `agents/footprint.md` | Prompt for review/profile footprint subagent |
| `agents/competitors.md` | Prompt for competitor profiling subagent |
| `report/narrative/*.md` | Hand-written sections inlined by aggregator |
| `tests/test_*.py` | pytest per script |

---

### Task 1: Query set generator

**Files:**
- Create: `scripts/build_queries.py`
- Test: `tests/test_build_queries.py`

**Interfaces:**
- Produces: `build_queries() -> list[dict]` where each dict has keys `id: str`, `text: str`, `service: str` (one of `kitchen, bath, addition, design-build, cabinetry, brand`), `geo: str` (a scope town or `n/a`), `intent: str` (`best, hire, cost, brand`), `tier: str` (`core` or `breadth`). CLI writes `queries.json` as `{"generated": "<date>", "queries": [...]}`.
- Later tasks read `queries.json` and key everything by `id`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_build_queries.py
import json, subprocess, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from build_queries import build_queries, TOWNS

def test_count_and_core():
    qs = build_queries()
    assert len(qs) == 40
    assert sum(1 for q in qs if q["tier"] == "core") == 8

def test_unique_ids_and_texts():
    qs = build_queries()
    assert len({q["id"] for q in qs}) == 40
    assert len({q["text"].lower() for q in qs}) == 40

def test_fields_and_vocab():
    qs = build_queries()
    for q in qs:
        assert set(q) == {"id", "text", "service", "geo", "intent", "tier"}
        assert q["service"] in {"kitchen", "bath", "addition", "design-build", "cabinetry", "brand"}
        assert q["intent"] in {"best", "hire", "cost", "brand"}
        assert q["geo"] in TOWNS or q["geo"] == "n/a"

def test_deterministic():
    assert build_queries() == build_queries()

def test_geo_text_rendering():
    qs = {q["id"]: q for q in build_queries()}
    assert "Boston area" in qs["kitchen-boston-best"]["text"]
    assert "MetroWest Massachusetts" in qs["design-build-metrowest-best"]["text"]
    assert "Newton MA" in qs["kitchen-newton-best"]["text"]

def test_cli_writes_json(tmp_path):
    out = tmp_path / "q.json"
    subprocess.run([sys.executable, "scripts/build_queries.py", str(out)], check=True)
    data = json.loads(out.read_text())
    assert len(data["queries"]) == 40 and "generated" in data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pytest --with markdown python -m pytest tests/test_build_queries.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'build_queries'`

- [ ] **Step 3: Write the implementation**

```python
# scripts/build_queries.py
"""Deterministic query set for the OOTW AI-visibility audit."""
import json, sys, datetime

TOWNS = ["Boston", "MetroWest", "Waltham", "Newton", "Wellesley", "Needham",
         "Lexington", "Reading", "Arlington", "Belmont", "Weston", "Concord"]

def geo_text(town):
    if town == "Boston":
        return "the Boston area"
    if town == "MetroWest":
        return "MetroWest Massachusetts"
    return f"{town} MA"

TEMPLATES = {
    ("kitchen", "best"): "best kitchen remodeling design-build firms in {g}",
    ("kitchen", "cost"): "how much does a kitchen remodel cost in {g} and which design-build firms do them",
    ("bath", "best"): "best bathroom remodeling companies in {g}",
    ("bath", "cost"): "how much does a bathroom remodel cost in {g} and who are the best contractors",
    ("addition", "hire"): "who should I hire for a home addition in {g}",
    ("addition", "cost"): "how much does a home addition cost in {g} and which firms should I consider",
    ("design-build", "best"): "best design-build remodeling firms in {g}",
    ("design-build", "hire"): "who should I hire for a whole-house renovation in {g}",
    ("cabinetry", "best"): "custom cabinetry and kitchen remodeling company in {g}",
}

CORE = [
    ("kitchen", "Boston", "best", None),
    ("kitchen", "Newton", "best", None),
    ("bath", "Wellesley", "best", None),
    ("addition", "Needham", "hire", None),
    ("design-build", "MetroWest", "best", None),
    ("design-build", "Waltham", "best", None),
    ("design-build", "Lexington", "hire",
     "recommend a design-build remodeler along Route 128 near Lexington MA"),
    ("brand", "n/a", "brand", "Out of the Woods Construction Waltham MA reviews"),
]

BREADTH = [
    ("kitchen", "best", ["Wellesley", "Lexington", "Arlington", "Belmont", "Waltham", "MetroWest"]),
    ("bath", "best", ["Newton", "Needham", "Reading", "Weston", "Boston"]),
    ("addition", "hire", ["Newton", "Wellesley", "Lexington", "Concord", "Reading", "Boston"]),
    ("design-build", "best", ["Boston", "Newton", "Wellesley", "Needham", "Reading", "Arlington"]),
    ("design-build", "hire", ["Belmont", "Weston", "Concord"]),
    ("kitchen", "cost", ["Newton", "Waltham"]),
    ("bath", "cost", ["Wellesley"]),
    ("addition", "cost", ["Needham"]),
    ("cabinetry", "best", ["Boston"]),
]
BREADTH_BRAND = [
    ("brand-good-firm", "Is Out of the Woods Construction & Cabinetry in Waltham a good design-build remodeling firm"),
]

def _slug(town):
    return town.lower().replace(" ", "")

def _record(service, town, intent, tier, text=None):
    if text is None:
        text = TEMPLATES[(service, intent)].format(g=geo_text(town))
    rid = f"{service}-{_slug(town)}-{intent}" if town != "n/a" else f"{service}-{intent}"
    return {"id": rid, "text": text, "service": service, "geo": town,
            "intent": intent, "tier": tier}

def build_queries():
    out = [_record(s, t, i, "core", txt) for s, t, i, txt in CORE]
    for service, intent, towns in BREADTH:
        for town in towns:
            out.append(_record(service, town, intent, "breadth"))
    for rid, text in BREADTH_BRAND:
        out.append({"id": rid, "text": text, "service": "brand", "geo": "n/a",
                    "intent": "brand", "tier": "breadth"})
    return out

def main(path="queries.json"):
    data = {"generated": datetime.date.today().isoformat(), "queries": build_queries()}
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"wrote {len(data['queries'])} queries to {path}")

if __name__ == "__main__":
    main(*sys.argv[1:])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with pytest --with markdown python -m pytest tests/test_build_queries.py -q`
Expected: `6 passed`. If the count is not 40, adjust `BREADTH` town lists (the grid above sums to 31 + 1 brand = 32 breadth + 8 core).

- [ ] **Step 5: Generate queries.json and commit**

```bash
python3 scripts/build_queries.py queries.json
git add scripts/build_queries.py tests/test_build_queries.py queries.json
git commit -m "Add deterministic 40-query set generator

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Result record validator

**Files:**
- Create: `scripts/validate.py`
- Test: `tests/test_validate.py`

**Interfaces:**
- Produces: `validate_record(rec: dict, known_ids: set[str] | None = None) -> list[str]` (empty list means valid); `validate_file(path: str, known_ids=None) -> dict` with `{"path", "count", "errors": [str]}`. CLI: `python scripts/validate.py results/simulated/*.json` exits 1 if any errors.
- Record schema (used by Tasks 5, 6, 8, 9):

```json
{
  "query_id": "kitchen-newton-best",
  "engine": "simulated",
  "status": "ok",
  "answer_text": "...",
  "firms_named": ["Firm A"],
  "ootw_mentioned": false,
  "ootw_rank": null,
  "ootw_description": null,
  "sources_cited": ["https://..."],
  "ootw_site_cited": false,
  "notes": ""
}
```
`status` is `ok` or `blocked`. A `blocked` record needs only `query_id`, `engine`, `status`, `notes`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_validate.py
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from validate import validate_record, validate_file

GOOD = {
    "query_id": "kitchen-newton-best", "engine": "simulated", "status": "ok",
    "answer_text": "Top firms include A and B.", "firms_named": ["A", "B"],
    "ootw_mentioned": True, "ootw_rank": 2, "ootw_description": "a Waltham design-build firm",
    "sources_cited": ["https://example.com"], "ootw_site_cited": False, "notes": "",
}

def test_valid_record():
    assert validate_record(GOOD) == []

def test_missing_field():
    rec = dict(GOOD); del rec["sources_cited"]
    assert any("sources_cited" in e for e in validate_record(rec))

def test_rank_without_mention():
    rec = dict(GOOD, ootw_mentioned=False, ootw_rank=2)
    assert any("ootw_rank" in e for e in validate_record(rec))

def test_mention_without_rank():
    rec = dict(GOOD, ootw_rank=None)
    assert any("ootw_rank" in e for e in validate_record(rec))

def test_wrong_types():
    rec = dict(GOOD, firms_named="A, B")
    assert any("firms_named" in e for e in validate_record(rec))

def test_unknown_query_id():
    assert any("query_id" in e for e in validate_record(GOOD, known_ids={"other"}))

def test_blocked_record_minimal():
    rec = {"query_id": "kitchen-newton-best", "engine": "perplexity", "status": "blocked", "notes": "login wall"}
    assert validate_record(rec) == []

def test_validate_file(tmp_path):
    p = tmp_path / "b.json"
    p.write_text(json.dumps([GOOD, dict(GOOD, query_id=5)]))
    res = validate_file(str(p))
    assert res["count"] == 2 and len(res["errors"]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pytest --with markdown python -m pytest tests/test_validate.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'validate'`

- [ ] **Step 3: Write the implementation**

```python
# scripts/validate.py
"""Schema validation for answer-engine result records."""
import json, sys, glob

FULL_FIELDS = {
    "query_id": str, "engine": str, "status": str, "answer_text": str,
    "firms_named": list, "ootw_mentioned": bool, "ootw_rank": (int, type(None)),
    "ootw_description": (str, type(None)), "sources_cited": list,
    "ootw_site_cited": bool, "notes": str,
}
BLOCKED_FIELDS = {"query_id": str, "engine": str, "status": str, "notes": str}

def validate_record(rec, known_ids=None):
    errors = []
    if not isinstance(rec, dict):
        return ["record is not an object"]
    status = rec.get("status", "ok")
    fields = BLOCKED_FIELDS if status == "blocked" else FULL_FIELDS
    for name, typ in fields.items():
        if name not in rec:
            errors.append(f"missing field {name}")
        elif not isinstance(rec[name], typ) or (typ is int and isinstance(rec[name], bool)):
            errors.append(f"field {name} has wrong type {type(rec[name]).__name__}")
    if status not in ("ok", "blocked"):
        errors.append(f"status must be ok or blocked, got {status!r}")
    if known_ids is not None and rec.get("query_id") not in known_ids:
        errors.append(f"unknown query_id {rec.get('query_id')!r}")
    if status == "ok" and not errors:
        if rec["ootw_mentioned"] and not isinstance(rec["ootw_rank"], int):
            errors.append("ootw_rank must be an int >= 1 when ootw_mentioned is true")
        if not rec["ootw_mentioned"] and rec["ootw_rank"] is not None:
            errors.append("ootw_rank must be null when ootw_mentioned is false")
        if isinstance(rec["ootw_rank"], int) and rec["ootw_rank"] < 1:
            errors.append("ootw_rank must be >= 1")
        if not all(isinstance(x, str) for x in rec["firms_named"]):
            errors.append("firms_named must be a list of strings")
        if not all(isinstance(x, str) for x in rec["sources_cited"]):
            errors.append("sources_cited must be a list of strings")
    return errors

def validate_file(path, known_ids=None):
    with open(path) as f:
        data = json.load(f)
    records = data if isinstance(data, list) else [data]
    errors = []
    for i, rec in enumerate(records):
        for e in validate_record(rec, known_ids):
            errors.append(f"{path}[{i}] ({rec.get('query_id') if isinstance(rec, dict) else '?'}): {e}")
    return {"path": path, "count": len(records), "errors": errors}

def main(paths):
    known = None
    try:
        with open("queries.json") as f:
            known = {q["id"] for q in json.load(f)["queries"]}
    except FileNotFoundError:
        pass
    bad = 0
    for pattern in paths:
        for path in sorted(glob.glob(pattern)):
            res = validate_file(path, known)
            for e in res["errors"]:
                print("ERROR", e)
            bad += len(res["errors"])
            print(f"{path}: {res['count']} records, {len(res['errors'])} errors")
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main(sys.argv[1:] or ["results/simulated/*.json", "results/real/*/*.json"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with pytest --with markdown python -m pytest tests/test_validate.py -q`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/validate.py tests/test_validate.py
git commit -m "Add result record validator

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Site audit script

**Files:**
- Create: `scripts/site_audit.py`
- Test: `tests/test_site_audit.py`

**Interfaces:**
- Produces: `parse_robots(text: str) -> dict[str, dict]` keyed by lowercase user-agent with `{"allow": [...], "disallow": [...]}`; `ai_crawler_status(rules: dict) -> dict[str, str]` mapping each of `GPTBot, ChatGPT-User, OAI-SearchBot, PerplexityBot, ClaudeBot, Claude-SearchBot, Google-Extended, Bingbot` to `allowed`, `blocked`, or `unspecified`; `extract_jsonld(html: str) -> list[str]` of `@type` values; `page_facts(url: str, html: str) -> dict` with `title, meta_description, h1, word_count, jsonld_types, towns_named, services_named, has_faq, internal_links`; CLI writes `results/audit/site.json` as `{"domain", "fetched_at", "robots": {...}, "ai_crawlers": {...}, "sitemap_found": bool, "llms_txt_found": bool, "pages": [page_facts...], "coverage": {"service_pages": {...}, "town_pages": {...}}}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_site_audit.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from site_audit import parse_robots, ai_crawler_status, extract_jsonld, page_facts

ROBOTS = """User-agent: *
Disallow: /admin
User-agent: GPTBot
Disallow: /
User-agent: PerplexityBot
Allow: /
"""

def test_parse_robots_groups():
    r = parse_robots(ROBOTS)
    assert r["*"]["disallow"] == ["/admin"]
    assert r["gptbot"]["disallow"] == ["/"]
    assert r["perplexitybot"]["allow"] == ["/"]

def test_ai_crawler_status():
    s = ai_crawler_status(parse_robots(ROBOTS))
    assert s["GPTBot"] == "blocked"
    assert s["PerplexityBot"] == "allowed"
    assert s["ClaudeBot"] == "unspecified"

def test_wildcard_block_applies():
    s = ai_crawler_status(parse_robots("User-agent: *\nDisallow: /\n"))
    assert s["ClaudeBot"] == "blocked"

HTML = """<html><head><title>Kitchens | OOTW</title>
<meta name="description" content="Kitchen remodeling in Waltham and Newton">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"LocalBusiness","name":"OOTW"}</script>
</head><body><h1>Kitchen Remodeling</h1>
<p>We serve Waltham, Newton and Wellesley with kitchen and bathroom remodeling plus additions.</p>
<h2>Frequently Asked Questions</h2>
<a href="/bathrooms">Baths</a><a href="https://houzz.com/x">Houzz</a></body></html>"""

def test_extract_jsonld():
    assert extract_jsonld(HTML) == ["LocalBusiness"]

def test_page_facts():
    f = page_facts("https://outofthewoodsconstruction.com/kitchens", HTML)
    assert f["title"] == "Kitchens | OOTW"
    assert f["meta_description"].startswith("Kitchen remodeling")
    assert f["h1"] == "Kitchen Remodeling"
    assert set(f["towns_named"]) == {"Waltham", "Newton", "Wellesley"}
    assert set(f["services_named"]) >= {"kitchen", "bath", "addition"}
    assert f["has_faq"] is True
    assert f["internal_links"] == ["https://outofthewoodsconstruction.com/bathrooms"]
    assert f["word_count"] > 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pytest --with markdown python -m pytest tests/test_site_audit.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'site_audit'`

- [ ] **Step 3: Write the implementation**

```python
# scripts/site_audit.py
"""Deterministic audit of outofthewoodsconstruction.com for AI-search readiness."""
import json, re, sys, html as htmllib, datetime, urllib.request, urllib.parse
from html.parser import HTMLParser

DOMAIN = "outofthewoodsconstruction.com"
BASE = f"https://www.{DOMAIN}"
TOWNS = ["Boston", "MetroWest", "Waltham", "Newton", "Wellesley", "Needham",
         "Lexington", "Reading", "Arlington", "Belmont", "Weston", "Concord"]
SERVICE_TERMS = {
    "kitchen": r"\bkitchens?\b", "bath": r"\bbath(room)?s?\b",
    "addition": r"\badditions?\b", "design-build": r"design[\s/-]?build",
    "cabinetry": r"\bcabinet(ry|s)?\b", "whole-house": r"whole[\s-]house",
}
AI_CRAWLERS = ["GPTBot", "ChatGPT-User", "OAI-SearchBot", "PerplexityBot",
               "ClaudeBot", "Claude-SearchBot", "Google-Extended", "Bingbot"]
MAX_PAGES = 40
UA = "Mozilla/5.0 (compatible; OOTW-visibility-audit/1.0)"

def parse_robots(text):
    rules, current = {}, []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, val = [p.strip() for p in line.split(":", 1)]
        key = key.lower()
        if key == "user-agent":
            agent = val.lower()
            rules.setdefault(agent, {"allow": [], "disallow": []})
            current = [agent] if not current or rules[current[-1]]["allow"] or rules[current[-1]]["disallow"] else current + [agent]
        elif key in ("allow", "disallow") and current:
            for a in current:
                rules[a][key].append(val)
    return rules

def ai_crawler_status(rules):
    out = {}
    for bot in AI_CRAWLERS:
        group = rules.get(bot.lower()) or rules.get("*")
        if group is None:
            out[bot] = "unspecified"
        elif "/" in group["disallow"] and "/" not in group["allow"]:
            out[bot] = "blocked"
        elif bot.lower() in rules:
            out[bot] = "allowed"
        else:
            out[bot] = "unspecified" if not group["disallow"] else "allowed"
    return out

def extract_jsonld(html):
    types = []
    for m in re.finditer(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict):
                for node in item.get("@graph", [item]):
                    t = node.get("@type") if isinstance(node, dict) else None
                    if isinstance(t, list):
                        types.extend(t)
                    elif t:
                        types.append(t)
    return types

class _Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.links = []; self._skip = 0
        self.title = None; self._in_title = False; self.h1 = None; self._in_h1 = False
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style"): self._skip += 1
        if tag == "title": self._in_title = True
        if tag == "h1" and self.h1 is None: self._in_h1 = True
        if tag == "a" and a.get("href"): self.links.append(a["href"])
    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip: self._skip -= 1
        if tag == "title": self._in_title = False
        if tag == "h1": self._in_h1 = False
    def handle_data(self, data):
        if self._in_title: self.title = (self.title or "") + data
        elif self._in_h1: self.h1 = (self.h1 or "") + data
        elif not self._skip: self.parts.append(data)

def page_facts(url, html):
    p = _Text(); p.feed(html)
    text = htmllib.unescape(" ".join(" ".join(p.parts).split()))
    md = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)', html, re.I)
    host = urllib.parse.urlparse(url).netloc.replace("www.", "")
    internal = []
    for href in p.links:
        full = urllib.parse.urljoin(url, href.split("#")[0])
        if urllib.parse.urlparse(full).netloc.replace("www.", "") == host and full not in internal and not full.endswith((".jpg", ".png", ".pdf")):
            internal.append(full)
    return {
        "url": url,
        "title": (p.title or "").strip(),
        "meta_description": htmllib.unescape(md.group(1)) if md else "",
        "h1": (p.h1 or "").strip(),
        "word_count": len(text.split()),
        "jsonld_types": extract_jsonld(html),
        "towns_named": [t for t in TOWNS if re.search(rf"\b{t}\b", text)],
        "services_named": [s for s, rx in SERVICE_TERMS.items() if re.search(rx, text, re.I)],
        "has_faq": bool(re.search(r"frequently asked|\bFAQs?\b", text, re.I)),
        "internal_links": internal,
    }

def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")

def main(out="results/audit/site.json"):
    result = {"domain": DOMAIN, "fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
              "robots": {}, "ai_crawlers": {}, "sitemap_found": False, "llms_txt_found": False,
              "pages": [], "errors": []}
    try:
        _, robots = fetch(f"{BASE}/robots.txt")
        result["robots"] = parse_robots(robots); result["robots_raw"] = robots
    except Exception as e:
        robots = ""; result["errors"].append(f"robots.txt: {e}")
    result["ai_crawlers"] = ai_crawler_status(result["robots"])
    try:
        result["llms_txt_found"] = fetch(f"{BASE}/llms.txt")[0] == 200
    except Exception:
        pass
    queue = []
    sitemap_urls = re.findall(r"Sitemap:\s*(\S+)", robots, re.I) or [f"{BASE}/sitemap.xml"]
    for sm in sitemap_urls:
        try:
            _, xml = fetch(sm)
            locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
            if locs:
                result["sitemap_found"] = True
                queue.extend(l for l in locs if not l.endswith(".xml"))
                for sub in [l for l in locs if l.endswith(".xml")]:
                    try:
                        queue.extend(re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", fetch(sub)[1]))
                    except Exception as e:
                        result["errors"].append(f"{sub}: {e}")
        except Exception as e:
            result["errors"].append(f"{sm}: {e}")
    if not queue:
        queue = [BASE + "/"]
    seen = set()
    while queue and len(result["pages"]) < MAX_PAGES:
        url = queue.pop(0)
        if url in seen: continue
        seen.add(url)
        try:
            _, html = fetch(url)
        except Exception as e:
            result["errors"].append(f"{url}: {e}"); continue
        facts = page_facts(url, html)
        result["pages"].append(facts)
        if not result["sitemap_found"]:
            queue.extend(l for l in facts["internal_links"] if l not in seen)
    result["coverage"] = {
        "service_pages": {s: [p["url"] for p in result["pages"] if s in p["services_named"] and s in (p["title"] + p["h1"] + p["url"]).lower().replace("bathroom", "bath")] for s in SERVICE_TERMS},
        "town_pages": {t: [p["url"] for p in result["pages"] if t.lower() in (p["title"] + " " + p["h1"] + " " + p["url"]).lower()] for t in TOWNS},
        "towns_anywhere": sorted({t for p in result["pages"] for t in p["towns_named"]}),
        "jsonld_anywhere": sorted({t for p in result["pages"] for t in p["jsonld_types"]}),
    }
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"audited {len(result['pages'])} pages -> {out}; errors: {len(result['errors'])}")

if __name__ == "__main__":
    main(*sys.argv[1:])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with pytest --with markdown python -m pytest tests/test_site_audit.py -q`
Expected: `5 passed`

- [ ] **Step 5: Run the audit for real and inspect**

Run: `python3 scripts/site_audit.py && python3 -c "import json;d=json.load(open('results/audit/site.json'));print(d['ai_crawlers'], d['sitemap_found'], len(d['pages']), d['coverage']['towns_anywhere'], d['coverage']['jsonld_anywhere'])"`
Expected: a page count between 1 and 40, no exception. Note `errors` for the report's methodology section.

- [ ] **Step 6: Commit**

```bash
git add scripts/site_audit.py tests/test_site_audit.py results/audit/site.json
git commit -m "Add deterministic site audit and capture OOTW results

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Aggregator and report builder

**Files:**
- Create: `scripts/aggregate.py`
- Test: `tests/test_aggregate.py`
- Create: `report/narrative/README.md` (lists slot filenames)

**Interfaces:**
- Consumes: `queries.json` (Task 1), records matching Task 2 schema in `results/simulated/*.json` (list per file) and `results/real/<engine>/*.json` (one record per file), `results/audit/site.json` (Task 3), optional `results/audit/footprint.json` and `results/competitors.json` (free-form JSON, inlined as tables if present).
- Produces: `load_records(results_dir) -> list[dict]`; `compute(records, queries) -> dict` with keys `overall`, `by_service`, `by_geo`, `by_intent`, `by_engine`, `leaderboard`, `ootw_quotes`, `coverage`; `build_report(summary, queries, records, site, narrative_dir) -> str`; CLI writes `report/report.md`.
- Each stat row is `{"n": int, "mentioned": int, "mention_rate": float, "avg_rank": float|None, "site_cited": int}`.
- Narrative slots: files in `report/narrative/` named `executive_summary.md`, `recommendations.md`, `plan_30_60_90.md`, `daves_audit.md`, `methodology_notes.md`. Missing file -> placeholder line `_Section not yet written._`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_aggregate.py
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from aggregate import compute, load_records, build_report, _stat

QUERIES = [
    {"id": "kitchen-newton-best", "service": "kitchen", "geo": "Newton", "intent": "best", "tier": "core", "text": "q1"},
    {"id": "bath-wellesley-best", "service": "bath", "geo": "Wellesley", "intent": "best", "tier": "core", "text": "q2"},
    {"id": "addition-needham-hire", "service": "addition", "geo": "Needham", "intent": "hire", "tier": "breadth", "text": "q3"},
]
def rec(qid, engine="simulated", mentioned=False, rank=None, firms=(), cited=False, status="ok", desc=None):
    return {"query_id": qid, "engine": engine, "status": status, "answer_text": "txt",
            "firms_named": list(firms), "ootw_mentioned": mentioned, "ootw_rank": rank,
            "ootw_description": desc, "sources_cited": [], "ootw_site_cited": cited, "notes": ""}

RECORDS = [
    rec("kitchen-newton-best", mentioned=True, rank=2, firms=["A", "Out of the Woods Construction"], cited=True, desc="Waltham design-build firm"),
    rec("bath-wellesley-best", firms=["A", "B"]),
    rec("addition-needham-hire", firms=["B"]),
    rec("kitchen-newton-best", engine="perplexity", mentioned=True, rank=1, firms=["Out of the Woods Construction", "A"]),
    rec("bath-wellesley-best", engine="perplexity", status="blocked"),
]

def test_stat_rates():
    s = _stat(RECORDS[:3])
    assert s["n"] == 3 and s["mentioned"] == 1 and abs(s["mention_rate"] - 1/3) < 1e-9
    assert s["avg_rank"] == 2 and s["site_cited"] == 1

def test_blocked_excluded_from_rates_but_counted():
    out = compute(RECORDS, QUERIES)
    assert out["by_engine"]["perplexity"]["n"] == 1
    assert out["coverage"]["perplexity"] == {"ok": 1, "blocked": 1}

def test_dimensions():
    out = compute(RECORDS, QUERIES)
    assert out["by_service"]["kitchen"]["mentioned"] == 2
    assert out["by_geo"]["Wellesley"]["mentioned"] == 0
    assert out["by_intent"]["hire"]["n"] == 1

def test_leaderboard_order_and_ootw_quotes():
    out = compute(RECORDS, QUERIES)
    names = [row["firm"] for row in out["leaderboard"]]
    assert names[0] == "A"
    assert out["leaderboard"][0]["mentions"] == 3
    assert out["ootw_quotes"][0]["description"] == "Waltham design-build firm"

def test_load_records(tmp_path):
    (tmp_path / "simulated").mkdir(); (tmp_path / "real" / "perplexity").mkdir(parents=True)
    (tmp_path / "simulated" / "batch-1.json").write_text(json.dumps(RECORDS[:2]))
    (tmp_path / "real" / "perplexity" / "q.json").write_text(json.dumps(RECORDS[3]))
    recs = load_records(str(tmp_path))
    assert len(recs) == 3 and {r["engine"] for r in recs} == {"simulated", "perplexity"}

def test_build_report_has_sections_and_slots(tmp_path):
    (tmp_path / "executive_summary.md").write_text("HEADLINE FINDING")
    site = {"ai_crawlers": {"GPTBot": "allowed"}, "sitemap_found": True, "llms_txt_found": False,
            "pages": [], "coverage": {"service_pages": {}, "town_pages": {}, "towns_anywhere": [], "jsonld_anywhere": []}, "errors": []}
    md = build_report(compute(RECORDS, QUERIES), QUERIES, RECORDS, site, str(tmp_path))
    for h in ["## 1. Executive summary", "## 3. Visibility scorecard", "## 5. Who wins instead", "## 10. Appendix"]:
        assert h in md
    assert "HEADLINE FINDING" in md
    assert "_Section not yet written._" in md
    assert "| perplexity |" in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pytest --with markdown python -m pytest tests/test_aggregate.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'aggregate'`

- [ ] **Step 3: Write the implementation**

```python
# scripts/aggregate.py
"""Aggregate answer-engine results into report/report.md."""
import json, glob, os, sys, datetime
from collections import defaultdict

OOTW_ALIASES = ("out of the woods",)
NARRATIVE_SLOTS = {
    "executive_summary": "1. Executive summary",
    "methodology_notes": None,  # appended inside section 2
    "recommendations": "7. Recommendations",
    "plan_30_60_90": "8. 30/60/90-day plan",
    "daves_audit": "9. Items from Dave's audit",
}

def is_ootw(name):
    return any(a in name.lower() for a in OOTW_ALIASES)

def _stat(records):
    ok = [r for r in records if r.get("status", "ok") == "ok"]
    mentioned = [r for r in ok if r["ootw_mentioned"]]
    ranks = [r["ootw_rank"] for r in mentioned if isinstance(r["ootw_rank"], int)]
    return {"n": len(ok), "mentioned": len(mentioned),
            "mention_rate": (len(mentioned) / len(ok)) if ok else 0.0,
            "avg_rank": (sum(ranks) / len(ranks)) if ranks else None,
            "site_cited": sum(1 for r in ok if r.get("ootw_site_cited"))}

def load_records(results_dir="results"):
    recs = []
    for path in sorted(glob.glob(os.path.join(results_dir, "simulated", "*.json"))):
        with open(path) as f:
            data = json.load(f)
        for r in (data if isinstance(data, list) else [data]):
            r.setdefault("engine", "simulated"); recs.append(r)
    for path in sorted(glob.glob(os.path.join(results_dir, "real", "*", "*.json"))):
        engine = os.path.basename(os.path.dirname(path))
        with open(path) as f:
            data = json.load(f)
        for r in (data if isinstance(data, list) else [data]):
            r.setdefault("engine", engine); recs.append(r)
    return recs

def compute(records, queries):
    qmap = {q["id"]: q for q in queries}
    groups = {"by_service": defaultdict(list), "by_geo": defaultdict(list),
              "by_intent": defaultdict(list), "by_engine": defaultdict(list)}
    coverage = defaultdict(lambda: {"ok": 0, "blocked": 0})
    firm_mentions, firm_ranks = defaultdict(int), defaultdict(list)
    quotes = []
    for r in records:
        q = qmap.get(r["query_id"], {})
        coverage[r["engine"]][r.get("status", "ok")] += 1
        groups["by_engine"][r["engine"]].append(r)
        if q:
            groups["by_service"][q["service"]].append(r)
            groups["by_geo"][q["geo"]].append(r)
            groups["by_intent"][q["intent"]].append(r)
        if r.get("status", "ok") != "ok":
            continue
        for i, firm in enumerate(r["firms_named"], 1):
            key = "Out of the Woods Construction" if is_ootw(firm) else firm.strip()
            firm_mentions[key] += 1; firm_ranks[key].append(i)
        if r["ootw_mentioned"]:
            quotes.append({"query_id": r["query_id"], "engine": r["engine"], "rank": r["ootw_rank"],
                           "description": r.get("ootw_description"), "query_text": q.get("text", "")})
    leaderboard = sorted(
        [{"firm": f, "mentions": n, "avg_rank": round(sum(firm_ranks[f]) / n, 2)} for f, n in firm_mentions.items()],
        key=lambda x: (-x["mentions"], x["avg_rank"], x["firm"]))
    out = {"overall": _stat(records), "leaderboard": leaderboard, "ootw_quotes": quotes,
           "coverage": {k: dict(v) for k, v in coverage.items()}}
    for name, g in groups.items():
        out[name] = {k: _stat(v) for k, v in sorted(g.items())}
    return out

def _pct(x): return f"{100 * x:.0f}%"
def _rank(x): return "-" if x is None else f"{x:.1f}"

def _table(title, rows):
    lines = [f"| {title} | Answers | OOTW mentioned | Mention rate | Avg rank | Site cited |", "|---|---|---|---|---|---|"]
    for k, s in rows.items():
        lines.append(f"| {k} | {s['n']} | {s['mentioned']} | {_pct(s['mention_rate'])} | {_rank(s['avg_rank'])} | {s['site_cited']} |")
    return "\n".join(lines)

def _slot(narrative_dir, name):
    path = os.path.join(narrative_dir, f"{name}.md")
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    return "_Section not yet written._"

def _optional_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None

def _dict_table(d, key_header="Item", val_header="Value"):
    lines = [f"| {key_header} | {val_header} |", "|---|---|"]
    for k, v in d.items():
        lines.append(f"| {k} | {v if not isinstance(v, (list, dict)) else json.dumps(v)} |")
    return "\n".join(lines)

def build_report(summary, queries, records, site, narrative_dir="report/narrative",
                 footprint=None, competitors=None):
    qmap = {q["id"]: q for q in queries}
    o = summary["overall"]
    md = [f"# AI-Search Visibility Audit: Out of the Woods Construction & Cabinetry",
          f"Prepared {datetime.date.today().isoformat()} for Dave. Boston-area and MetroWest design-build remodeling.", ""]
    md += ["## 1. Executive summary", "",
           f"**Scorecard.** {o['mentioned']} of {o['n']} AI answers mentioned Out of the Woods ({_pct(o['mention_rate'])}). "
           f"Average rank when mentioned: {_rank(o['avg_rank'])}. Answers citing outofthewoodsconstruction.com: {o['site_cited']}.", "",
           _slot(narrative_dir, "executive_summary"), ""]
    md += ["## 2. Methodology and limitations", "",
           f"- {len(queries)} queries across services (kitchen, bath, additions, design-build, cabinetry) and towns along Route 128 and MetroWest.",
           "- Simulated engine: Claude subagents performing live web searches and composing an answer the way a consumer AI answer engine does. This measures what the open web lets an AI say about the company. It is a proxy for, not a transcript of, ChatGPT or Perplexity.",
           "- Real engines: the eight core queries were run in a browser on the engines listed in the coverage table. Blocked runs are counted but excluded from rates.", "",
           "| Engine | Answers captured | Blocked |", "|---|---|---|"]
    for eng, c in sorted(summary["coverage"].items()):
        md.append(f"| {eng} | {c.get('ok', 0)} | {c.get('blocked', 0)} |")
    md += ["", _slot(narrative_dir, "methodology_notes"), ""]
    md += ["## 3. Visibility scorecard", "",
           _table("Engine", summary["by_engine"]), "",
           _table("Service", summary["by_service"]), "",
           _table("Town / area", summary["by_geo"]), "",
           _table("Intent", summary["by_intent"]), ""]
    md += ["## 4. What engines say about Out of the Woods", ""]
    if summary["ootw_quotes"]:
        md += ["| Query | Engine | Rank | How OOTW was described |", "|---|---|---|---|"]
        for qt in summary["ootw_quotes"]:
            md.append(f"| {qt['query_text']} | {qt['engine']} | {qt['rank']} | {qt['description'] or ''} |")
    else:
        md.append("Out of the Woods was not mentioned in any captured answer.")
    md += ["", "## 5. Who wins instead and why", "",
           "| # | Firm | Mentions | Avg position |", "|---|---|---|---|"]
    for i, row in enumerate(summary["leaderboard"][:15], 1):
        md.append(f"| {i} | {row['firm']} | {row['mentions']} | {row['avg_rank']} |")
    if competitors:
        md += ["", "### Competitor signal comparison", ""]
        for c in competitors if isinstance(competitors, list) else competitors.get("firms", []):
            md += [f"**{c.get('firm', '?')}**", "", _dict_table({k: v for k, v in c.items() if k != "firm"}), ""]
    md += ["", "## 6. Website and footprint audit findings", "",
           "### outofthewoodsconstruction.com", "",
           f"- Sitemap found: {site.get('sitemap_found')}. llms.txt found: {site.get('llms_txt_found')}. Pages audited: {len(site.get('pages', []))}.",
           f"- Structured data types found anywhere: {', '.join(site['coverage'].get('jsonld_anywhere', [])) or 'none'}.",
           f"- Scope towns named anywhere on the site: {', '.join(site['coverage'].get('towns_anywhere', [])) or 'none'}.", "",
           "| AI crawler | robots.txt status |", "|---|---|"]
    for bot, st in site.get("ai_crawlers", {}).items():
        md.append(f"| {bot} | {st} |")
    md += ["", "| Service | Dedicated page(s) |", "|---|---|"]
    for s, urls in site["coverage"].get("service_pages", {}).items():
        md.append(f"| {s} | {', '.join(urls) or 'none'} |")
    md += ["", "| Town | Dedicated page(s) |", "|---|---|"]
    for t, urls in site["coverage"].get("town_pages", {}).items():
        md.append(f"| {t} | {', '.join(urls) or 'none'} |")
    md += ["", "| Page | Title | H1 | Words | JSON-LD | Towns named |", "|---|---|---|---|---|---|"]
    for p in site.get("pages", []):
        md.append(f"| {p['url'].replace('https://www.outofthewoodsconstruction.com', '') or '/'} | {p['title']} | {p['h1']} | {p['word_count']} | {', '.join(p['jsonld_types']) or '-'} | {', '.join(p['towns_named']) or '-'} |")
    if footprint:
        md += ["", "### Review and profile footprint", "", _dict_table(footprint, "Profile", "Findings")]
    md += ["", "## 7. Recommendations", "", _slot(narrative_dir, "recommendations"), "",
           "## 8. 30/60/90-day plan", "", _slot(narrative_dir, "plan_30_60_90"), "",
           "## 9. Items from Dave's audit", "", _slot(narrative_dir, "daves_audit"), "",
           "## 10. Appendix: every query and answer", ""]
    for q in queries:
        md += [f"### {q['text']}", "", f"_{q['id']} · {q['service']} · {q['geo']} · {q['intent']} · {q['tier']}_", ""]
        for r in [r for r in records if r["query_id"] == q["id"]]:
            if r.get("status", "ok") != "ok":
                md += [f"**{r['engine']}**: blocked. {r.get('notes', '')}", ""]; continue
            md += [f"**{r['engine']}** · firms: {', '.join(r['firms_named']) or 'none'} · OOTW: {'rank ' + str(r['ootw_rank']) if r['ootw_mentioned'] else 'not mentioned'}", "",
                   "> " + r["answer_text"].replace("\n", "\n> "), ""]
            if r["sources_cited"]:
                md += ["Sources: " + ", ".join(r["sources_cited"]), ""]
    return "\n".join(md)

def main(results_dir="results", out="report/report.md"):
    with open("queries.json") as f:
        queries = json.load(f)["queries"]
    records = load_records(results_dir)
    site = _optional_json(os.path.join(results_dir, "audit", "site.json")) or {"ai_crawlers": {}, "coverage": {}, "pages": []}
    footprint = _optional_json(os.path.join(results_dir, "audit", "footprint.json"))
    competitors = _optional_json(os.path.join(results_dir, "competitors.json"))
    summary = compute(records, queries)
    with open(os.path.join(os.path.dirname(out), "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    with open(out, "w") as f:
        f.write(build_report(summary, queries, records, site, "report/narrative", footprint, competitors))
    print(f"{len(records)} records -> {out}; overall mention rate {_pct(summary['overall']['mention_rate'])}")

if __name__ == "__main__":
    main(*sys.argv[1:])
```

Also create `report/narrative/README.md`:

```markdown
Narrative slots inlined by scripts/aggregate.py. One file per section:
executive_summary.md, methodology_notes.md, recommendations.md, plan_30_60_90.md, daves_audit.md
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with pytest --with markdown python -m pytest tests/test_aggregate.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/aggregate.py tests/test_aggregate.py report/narrative/README.md
git commit -m "Add results aggregator and report builder

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Renderer (Markdown to HTML to PDF)

**Files:**
- Create: `scripts/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `report/report.md`.
- Produces: `to_html(md_text: str, title: str) -> str` (full HTML document with embedded print CSS); CLI writes `report/report.html` and `report/report.pdf` via headless Chrome at `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_render.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from render import to_html

def test_to_html_renders_tables_and_title():
    md = "# Title\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n> quote\n"
    html = to_html(md, "Report")
    assert "<table>" in html and "<td>1</td>" in html
    assert "<title>Report</title>" in html
    assert "@page" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --with markdown python -m pytest tests/test_render.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'render'`

- [ ] **Step 3: Write the implementation**

```python
# scripts/render.py
"""Render report/report.md to HTML and PDF (headless Chrome)."""
import os, subprocess, sys
import markdown

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CSS = """
@page { size: Letter; margin: 0.75in; }
body { font: 11pt/1.45 -apple-system, "Helvetica Neue", Arial, sans-serif; color: #1a1a1a; max-width: 7.5in; margin: 0 auto; }
h1 { font-size: 22pt; margin: 0 0 4pt; } h2 { font-size: 15pt; margin-top: 22pt; border-bottom: 1px solid #ccc; padding-bottom: 3pt; page-break-after: avoid; }
h3 { font-size: 12pt; margin-top: 14pt; page-break-after: avoid; }
table { border-collapse: collapse; width: 100%; font-size: 9.5pt; margin: 8pt 0; page-break-inside: auto; }
th, td { border: 1px solid #d0d0d0; padding: 3pt 5pt; text-align: left; vertical-align: top; }
th { background: #f2f2f2; } tr { page-break-inside: avoid; }
blockquote { border-left: 3px solid #bbb; margin: 6pt 0; padding: 2pt 10pt; color: #333; font-size: 10pt; }
code { font-size: 9.5pt; background: #f5f5f5; padding: 1px 3px; }
"""

def to_html(md_text, title):
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code", "sane_lists"])
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title><style>{CSS}</style></head><body>{body}</body></html>"

def main(src="report/report.md", out_html="report/report.html", out_pdf="report/report.pdf"):
    with open(src) as f:
        html = to_html(f.read(), "AI-Search Visibility Audit: Out of the Woods Construction")
    with open(out_html, "w") as f:
        f.write(html)
    cmd = [CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
           f"--print-to-pdf={os.path.abspath(out_pdf)}", "file://" + os.path.abspath(out_html)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    print(f"wrote {out_html} and {out_pdf} ({os.path.getsize(out_pdf)} bytes)")

if __name__ == "__main__":
    main(*sys.argv[1:])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --with markdown python -m pytest tests/test_render.py -q`
Expected: `1 passed`

- [ ] **Step 5: Smoke-test the PDF path on a stub report**

```bash
mkdir -p report && printf '# Smoke\n\n| a | b |\n|---|---|\n| 1 | 2 |\n' > report/report.md
uv run --with markdown python scripts/render.py && ls -la report/report.pdf
```
Expected: `report/report.pdf` exists and is larger than 5 KB. If Chrome errors, add `--no-sandbox` to `cmd`.

- [ ] **Step 6: Commit**

```bash
git add scripts/render.py tests/test_render.py
git commit -m "Add Markdown to PDF renderer via headless Chrome

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Answer-engine agent prompt and dry run

**Files:**
- Create: `agents/answer-engine.md`
- Create: `scripts/make_batches.py`
- Test: `tests/test_make_batches.py`

**Interfaces:**
- Consumes: `queries.json`.
- Produces: `make_batches(queries, size=8) -> list[list[dict]]` (deterministic, core queries spread across batches); CLI `python scripts/make_batches.py` writes `results/simulated/batch-N.input.json` for N in 1..5 and prints the ready-to-paste prompt path for each. Subagents write `results/simulated/batch-N.json`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_make_batches.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from make_batches import make_batches
from build_queries import build_queries

def test_batches_cover_all_queries_once():
    qs = build_queries()
    batches = make_batches(qs, 8)
    assert len(batches) == 5 and all(len(b) == 8 for b in batches)
    ids = [q["id"] for b in batches for q in b]
    assert sorted(ids) == sorted(q["id"] for q in qs)

def test_core_queries_spread():
    batches = make_batches(build_queries(), 8)
    assert all(any(q["tier"] == "core" for q in b) for b in batches)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --with markdown python -m pytest tests/test_make_batches.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'make_batches'`

- [ ] **Step 3: Write the implementation and prompt template**

```python
# scripts/make_batches.py
"""Split queries.json into agent batches and emit filled prompts."""
import json, os, sys, math

def make_batches(queries, size=8):
    core = [q for q in queries if q["tier"] == "core"]
    rest = [q for q in queries if q["tier"] != "core"]
    n = math.ceil(len(queries) / size)
    batches = [[] for _ in range(n)]
    for i, q in enumerate(core + rest):
        batches[i % n].append(q)
    return batches

def main(size=8):
    with open("queries.json") as f:
        queries = json.load(f)["queries"]
    with open("agents/answer-engine.md") as f:
        template = f.read()
    os.makedirs("results/simulated", exist_ok=True)
    for i, batch in enumerate(make_batches(queries, int(size)), 1):
        inp = f"results/simulated/batch-{i}.input.json"
        with open(inp, "w") as f:
            json.dump(batch, f, indent=2)
        prompt = template.replace("{{QUERIES_JSON}}", json.dumps(batch, indent=2)).replace(
            "{{OUTPUT_PATH}}", os.path.abspath(f"results/simulated/batch-{i}.json"))
        with open(f"results/simulated/batch-{i}.prompt.md", "w") as f:
            f.write(prompt)
        print(f"batch {i}: {len(batch)} queries -> results/simulated/batch-{i}.prompt.md")

if __name__ == "__main__":
    main(*sys.argv[1:])
```

`agents/answer-engine.md`:

```markdown
You are simulating a consumer AI answer engine (the kind of answer a homeowner gets from Perplexity or ChatGPT with web search turned on). For each query below, do what such an engine does:

1. Run 2-4 web searches with the WebSearch tool, phrased as the query and natural variants. Use WebFetch on at most 3 of the most relevant result pages when you need detail (a firm's service area, what a directory page lists).
2. Compose the answer the user would see: a direct, helpful answer, typically naming 3-6 specific firms with one-line reasons, grounded only in what the search results say. Do not invent firms, awards, or reviews. If results are thin or only directories appear, say so in the answer the way an engine would.
3. Record every firm named, in the order named. Record whether "Out of the Woods Construction" (also written "Out of the Woods Construction & Cabinetry", Waltham MA, outofthewoodsconstruction.com) was named, its 1-based position among firms, and the exact phrase you used to describe it. Record whether any cited URL is on outofthewoodsconstruction.com.

Be a neutral engine, not an advocate. Do not search for Out of the Woods specifically unless the query itself names it. Do not favor it.

Write a JSON array to the file {{OUTPUT_PATH}} using the Write tool, one object per query, exactly these keys:

{"query_id": "<id from input>", "engine": "simulated", "status": "ok", "answer_text": "<the full answer you composed, 80-250 words>", "firms_named": ["..."], "ootw_mentioned": true|false, "ootw_rank": <int or null>, "ootw_description": "<phrase or null>", "sources_cited": ["<url>", ...], "ootw_site_cited": true|false, "notes": "<brief: thin results, directory-heavy, etc.>"}

Rules: ootw_rank is null when ootw_mentioned is false. firms_named excludes directories (Houzz, Yelp, Angi, Thumbtack, BuildZoom) and lists only remodeling firms. sources_cited lists the URLs you actually relied on. Output nothing else to the file. When done, reply with one line: the path written and the count of records.

Queries:

{{QUERIES_JSON}}
```

- [ ] **Step 4: Run test to verify it passes, then generate prompts**

Run: `uv run --with pytest --with markdown python -m pytest tests/test_make_batches.py -q && python3 scripts/make_batches.py`
Expected: `2 passed`, then five lines `batch N: 8 queries -> ...`.

- [ ] **Step 5: Dry run with 3 queries**

Create a 3-query dry-run prompt: take the first 3 queries from `results/simulated/batch-1.input.json`, fill the template with output path `results/simulated/dryrun.json`, and dispatch ONE subagent (Agent tool, `subagent_type: general-purpose`) with that prompt. Then validate:

```bash
python3 scripts/validate.py results/simulated/dryrun.json
```
Expected: `3 records, 0 errors`. Read the three answers. Check: firms are real Boston-area remodelers, answer_text reads like an engine answer, sources are real URLs, no directories in firms_named. If the output fails, fix the prompt wording in `agents/answer-engine.md`, re-run `make_batches.py`, and repeat the dry run once. Delete `dryrun.json` afterwards so it is not aggregated.

- [ ] **Step 6: Commit**

```bash
git add agents/answer-engine.md scripts/make_batches.py tests/test_make_batches.py results/simulated/*.input.json
git commit -m "Add answer-engine agent prompt and batcher, dry run passed

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Full simulated fan-out

**Files:**
- Produce: `results/simulated/batch-1.json` through `batch-5.json`

**Interfaces:**
- Consumes: `results/simulated/batch-N.prompt.md` (Task 6).
- Produces: validated records for all 40 queries, engine `simulated`.

- [ ] **Step 1: Dispatch five subagents in parallel**

In one message, call the Agent tool five times (`subagent_type: general-purpose`, `description: "Answer-engine batch N"`), each prompt being the full contents of `results/simulated/batch-N.prompt.md`. Wait for all five notifications.

- [ ] **Step 2: Validate**

```bash
python3 scripts/validate.py results/simulated/batch-*.json
```
Expected: 5 files, 8 records each, 0 errors. For any batch with errors, re-dispatch that one batch with the validator's error lines appended under a heading `Previous attempt failed validation; fix these:`. One retry only; if it still fails, remove the failing records and note the dropped query ids in `report/narrative/methodology_notes.md`.

- [ ] **Step 3: Sanity-check aggregate**

```bash
python3 scripts/aggregate.py && head -40 report/report.md
```
Expected: `40 records -> report/report.md` and a plausible overall mention rate.

- [ ] **Step 4: Commit**

```bash
git add results/simulated/batch-*.json
git commit -m "Capture simulated answer-engine results for 40 queries

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Real-engine spot check (browser harness)

**Files:**
- Produce: `results/real/<engine>/<query_id>.json` and `.png` for engines `perplexity`, `google-ai-mode`, `chatgpt`.

**Interfaces:**
- Consumes: the 8 `tier: core` queries from `queries.json`.
- Produces: records in Task 2 schema with `engine` set to the engine name and extra key `captured_at` (ISO timestamp). Blocked runs: `{"query_id", "engine", "status": "blocked", "notes"}`.

- [ ] **Step 1: Invoke the browser-harness skill and open Perplexity**

Follow the skill's instructions to attach to a browser. Navigate to `https://www.perplexity.ai`. If a login or captcha wall appears and cannot be passed, write blocked records for all 8 queries for that engine and move to the next engine.

- [ ] **Step 2: For each core query on each engine**

Type the query text, submit, wait for the answer to finish streaming (poll until the text stops changing for 3 seconds, max 90 seconds). Extract the answer text and the list of source URLs from the page. Take a screenshot to `results/real/<engine>/<query_id>.png`. Write the JSON record by hand from what the page shows: `firms_named` in order of appearance, OOTW rank, description phrase, `ootw_site_cited`. Start a fresh thread or new chat between queries so answers do not carry context.

Engine URLs: Perplexity `https://www.perplexity.ai`; Google AI Mode `https://www.google.com/search?udm=50&q=<urlencoded query>`; ChatGPT `https://chatgpt.com` (only if already signed in; otherwise blocked).

- [ ] **Step 3: Validate and aggregate**

```bash
python3 scripts/validate.py "results/real/*/*.json" && python3 scripts/aggregate.py
```
Expected: 0 errors; coverage table shows per-engine ok/blocked counts.

- [ ] **Step 4: Commit**

```bash
git add results/real
git commit -m "Capture real-engine spot check for core queries

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Footprint and competitor agents

**Files:**
- Create: `agents/footprint.md`, `agents/competitors.md`
- Produce: `results/audit/footprint.json`, `results/competitors.json`

**Interfaces:**
- Consumes: `report/summary.json` leaderboard (Task 4 output) for the competitor prompt.
- Produces: `footprint.json` as a flat object `{ "Google Business Profile": "<rating, review count, categories, completeness>", "Houzz": "...", "Yelp": "...", "Facebook": "...", "NAP consistency": "...", "Other directories": "..." }`. `competitors.json` as a list of objects with keys `firm, town, what_engines_credit, service_pages, town_pages, review_footprint, awards_press, notable_signal_ootw_lacks`.

- [ ] **Step 1: Write `agents/footprint.md`**

```markdown
Research the public review and directory footprint of Out of the Woods Construction & Cabinetry, Inc. (Waltham MA, 260 Bear Hill Rd Suite 201, (781) 641-3332, outofthewoodsconstruction.com; earlier addresses in Arlington and Acton appear online). Use WebSearch and WebFetch only. For each of Google Business Profile, Houzz, Yelp, Facebook, BuildZoom, Angi, Nextdoor: record star rating, review count, most recent review date if visible, categories/services listed, and whether the address and phone match the website. Note any duplicate or stale listings (old Arlington/Acton addresses). Do not guess; write "not found" or "not visible" where applicable.

Write a flat JSON object to {{OUTPUT_PATH}} with string values, keys exactly: "Google Business Profile", "Houzz", "Yelp", "Facebook", "BuildZoom", "Angi", "Nextdoor", "NAP consistency", "Stale or duplicate listings". Reply with one line when done.
```

- [ ] **Step 2: Write `agents/competitors.md`**

```markdown
Below is a leaderboard of remodeling firms that AI answer engines recommended for Boston-area and MetroWest design-build queries. For the top {{N}} firms (skip any that are directories or national chains), research each with WebSearch and WebFetch and record: the town they are based in; what the engines or the web credit them for (awards, press, specialties); whether their website has dedicated pages per service (kitchen, bath, additions) and per town; their review footprint (Houzz/Google counts if visible); and the single most notable signal they have that Out of the Woods Construction & Cabinetry (Waltham) appears to lack.

Write a JSON list to {{OUTPUT_PATH}}, one object per firm with keys exactly: firm, town, what_engines_credit, service_pages, town_pages, review_footprint, awards_press, notable_signal_ootw_lacks. All values are strings. Reply with one line when done.

Leaderboard:
{{LEADERBOARD_JSON}}
```

- [ ] **Step 3: Dispatch both agents in parallel**

Fill `{{OUTPUT_PATH}}` with absolute paths; fill `{{N}}` with 8 and `{{LEADERBOARD_JSON}}` with the first 12 rows of `report/summary.json` `leaderboard` (so the agent can skip non-firms and still reach 8). Dispatch both with the Agent tool in one message. Wait for both.

- [ ] **Step 4: Check and aggregate**

```bash
python3 -c "import json; json.load(open('results/audit/footprint.json')); c=json.load(open('results/competitors.json')); print(len(c), 'competitors')" && python3 scripts/aggregate.py
```
Expected: valid JSON, 6-8 competitors, report sections 5 and 6 now include the new tables.

- [ ] **Step 5: Commit**

```bash
git add agents/footprint.md agents/competitors.md results/audit/footprint.json results/competitors.json
git commit -m "Add footprint and competitor agents with captured results

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Narrative sections, final render, delivery check

**Files:**
- Create: `report/narrative/executive_summary.md`, `methodology_notes.md`, `recommendations.md`, `plan_30_60_90.md`, `daves_audit.md`
- Produce: `report/report.md`, `report/report.pdf`

**Interfaces:**
- Consumes: `report/summary.json`, `results/audit/site.json`, `results/audit/footprint.json`, `results/competitors.json`, `report/report.md` data sections, any file in `inputs/`.

- [ ] **Step 1: Read the data**

```bash
python3 scripts/aggregate.py && sed -n '1,200p' report/report.md && cat results/audit/site.json | python3 -m json.tool | head -120
```

- [ ] **Step 2: Write `executive_summary.md`**

Three headline findings and top five actions, each finding citing a number from the scorecard and each action pointing to a section 7 recommendation. 150-250 words. No restating of the scorecard line already printed above the slot.

- [ ] **Step 3: Write `methodology_notes.md`**

Dates run, dropped queries if any, engines blocked and why, the caveat that simulated results reflect the open web as of the run date.

- [ ] **Step 4: Write `recommendations.md`**

Four subsections, each item formatted as **Finding** (one sentence with the data point) then **Change** (specific) then **Draft copy** where applicable:
1. Website wording: homepage and service-page phrasing that names services plus towns the way queries are phrased (e.g., "design-build kitchen remodeling in Newton, Wellesley, Needham and Waltham"), a plain-language service-area statement listing the Route 128 towns, an "About" paragraph an engine can quote (founded 1992, Waltham, design/build, Big50 2006, repeat-client share).
2. Structured data: `LocalBusiness`/`HomeAndConstructionBusiness` JSON-LD with `areaServed` for each town, `Service` entities per service, `FAQPage` where FAQ copy exists, `Review`/`AggregateRating` only if sourced from a real platform.
3. New pages: one page per service and a service-area page or per-town pages for the towns with zero coverage in the site audit, each with project examples from that town. A FAQ page answering the cost and "who should I hire" questions in the query set.
4. Off-site: fix the stale listings and NAP mismatches found in footprint.json; review generation on Google and Houzz; the directories the engines actually cited in `sources_cited` (pull the top cited domains from `report/summary.json` and `results/simulated/*.json`); any crawler blocked in robots.txt.

Ground each item in a concrete number or URL from the results. Do not recommend anything the audit shows is already done.

- [ ] **Step 5: Write `plan_30_60_90.md` and `daves_audit.md`**

30/60/90 as three bullet lists ordered by effort and impact. `daves_audit.md`: if `inputs/` has a file, list each missing item and map it to a recommendation; otherwise one sentence saying the list was not received by the report date and will be reconciled when it arrives.

- [ ] **Step 6: Build, render, inspect**

```bash
python3 scripts/aggregate.py && uv run --with markdown python scripts/render.py
```
Open `report/report.pdf` with the Read tool and check: title page renders, tables are not clipped, every `_Section not yet written._` placeholder is gone (`grep -c "not yet written" report/report.md` must print 0), appendix has 40 query headings (`grep -c '^### ' report/report.md` is at least 40).

- [ ] **Step 7: Run the whole test suite and commit**

```bash
uv run --with pytest --with markdown python -m pytest tests -q
git add report/narrative report/report.md report/report.pdf report/summary.json
git commit -m "Write narrative sections and render final report for Dave

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```
Expected: all tests pass (22 total), PDF committed, path `~/ootw-ai-visibility/report/report.pdf` reported to the user.

---

## Self-review

- Spec coverage: query set (T1), schema and validation (T2), site audit with robots/sitemap/JSON-LD/town and service coverage (T3), aggregation with per-dimension scorecard, leaderboard, quotes, blocked coverage (T4), PDF via Chrome (T5), answer-engine prompt and dry-run gate (T6), fan-out with one retry and drop-and-note (T7), real-engine spot check with blocked handling (T8), footprint and competitor agents (T9), narrative sections including Dave's audit slot and 30/60/90 (T10). Error handling from the spec maps to T2 (malformed JSON), T7 step 2 (retry then drop), T8 step 1 (blocked), T3 main (per-URL errors).
- Type consistency: record keys identical in T2 schema, T4 tests, T6 prompt, T8. `_stat` row keys match `_table`. `coverage` shape `{engine: {ok, blocked}}` used in T4 test and `build_report`. `make_batches(queries, size)` used by its own CLI only.
- Placeholders: none; every narrative step says what to write and how to ground it.
