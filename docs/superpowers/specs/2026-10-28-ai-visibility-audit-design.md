# AI-Search Visibility Audit for Out of the Woods Construction — Design

Date: 2026-10-28. Deliverable due to Dave by Friday 2026-10-30.

## Goal

Measure where Out of the Woods Construction & Cabinetry (OOTW, Waltham MA,
outofthewoodsconstruction.com) appears when homeowners ask AI answer engines
about design-build remodeling in the Boston area and MetroWest, record what the
engines say, and recommend website wording and SEO changes that could improve
visibility. Output is a Markdown report rendered to PDF.

## Scope

- Services: kitchen remodeling, bath remodeling, additions, whole-house
  design-build, custom cabinetry.
- Geography: Boston, MetroWest, and the Route 128 corridor from Reading toward
  Needham, Wellesley, and Newton. Towns used in queries: Waltham, Newton,
  Wellesley, Needham, Lexington, Reading, Arlington, Belmont, Weston, Concord.
- Engines: simulated answer engines (Claude subagents with live web search)
  for breadth; real Perplexity, Google AI Mode, and ChatGPT (if signed in) via
  the browser harness for a spot check.

Out of scope: paid-ads analysis, backlink audits, keyword volume research,
changing the live website.

## Architecture

Approach chosen: in-session agent fan-out orchestrated from Claude Code, with
small Python scripts for deterministic work. No external LLM API key is used.

```
queries.json ─┬─> answer-engine agents (x5, 8 queries each) ─> results/simulated/*.json
              └─> browser spot check (8 queries x 2-3 engines) ─> results/real/*.json + screenshots
site audit script ─────────────────────────────────────────────> results/audit/site.json
footprint agent (GBP/Houzz/Yelp) ──────────────────────────────> results/audit/footprint.json
aggregate.py (reads all results) ──────────────────────────────> report/report.md
render.py (markdown -> html -> headless Chrome) ───────────────> report/report.pdf
competitor agent (reads aggregate) ────────────────────────────> results/competitors.json
```

### Project layout

```
~/ootw-ai-visibility/
  inputs/            Dave's audit / missing-items list, if provided
  agents/            prompt templates (answer-engine.md, footprint.md, competitors.md)
  scripts/           build_queries.py, validate.py, site_audit.py, aggregate.py, render.py
  queries.json       generated query set
  results/           simulated/, real/, audit/, competitors.json
  report/            report.md, report.html, report.pdf
  tests/             pytest for scripts
  docs/superpowers/  specs and plans
```

## Components

### 1. Query set (`scripts/build_queries.py` -> `queries.json`)

Generates about 40 queries from a grid of service x geography x intent, plus
brand queries. Each query record: `id`, `text`, `service`, `geo`, `intent`,
`tier` (`core` for the 8 spot-check queries, `breadth` otherwise). Intents:
`best` ("best kitchen remodeling design-build firm in Newton MA"),
`hire` ("who should I hire for a home addition in Wellesley"),
`cost` ("how much does a kitchen remodel cost in Waltham MA and who does it"),
`brand` ("Out of the Woods Construction Waltham reviews").
The list is deterministic so a re-run is comparable.

### 2. Answer-engine agents (`agents/answer-engine.md`)

Five parallel subagents, each given 8 queries. The prompt instructs the agent
to act as a consumer AI answer engine (Perplexity/ChatGPT-search style): run
web searches for the query as a homeowner would, compose the answer a user
would see (typically 3-6 recommended firms with one-line reasons), and return
strict JSON only. Per query:

```json
{
  "query_id": "k-newton-best",
  "answer_text": "...",
  "firms_named": ["Firm A", "Firm B"],
  "ootw_mentioned": true,
  "ootw_rank": 3,
  "ootw_description": "how the answer characterized OOTW, or null",
  "sources_cited": ["https://..."],
  "ootw_site_cited": false,
  "notes": "anything odd: no local results, directory-only sources, etc."
}
```

Agents write to `results/simulated/batch-N.json`. `scripts/validate.py`
checks each file against the schema; a failed batch is re-run once.
A dry run on 3 queries gates the full fan-out.

### 3. Real-engine spot check (browser harness)

The 8 `core` queries are run on Perplexity and Google AI Mode (no login
needed) and ChatGPT if the controlled browser is already signed in. For each
run the answer text and a screenshot are saved to
`results/real/<engine>/<query_id>.{json,png}`. The JSON uses the same schema
as above plus `engine` and `captured_at`. If an engine blocks or requires
login, the record has `status: "blocked"` and is reported as such.

### 4. Site and footprint audit

`scripts/site_audit.py` (deterministic, curl/python only) records for
outofthewoodsconstruction.com:

- robots.txt rules affecting GPTBot, ChatGPT-User, PerplexityBot, ClaudeBot,
  Google-Extended, Bingbot, and whether a sitemap and llms.txt exist.
- For each page in the sitemap (or a crawl of internal links, capped at 40):
  title, meta description, H1, word count, presence of JSON-LD and its
  `@type`s, and which scope towns and services are named.
- Site-wide: whether a dedicated page exists per service and per town, and
  whether phone/address/NAP is machine-readable.

`agents/footprint.md` is one subagent that records review counts, ratings,
and profile completeness for OOTW on Google Business Profile, Houzz, Yelp,
and Facebook, and whether the NAP matches the website. Output
`results/audit/footprint.json`.

### 5. Competitor pass (`agents/competitors.md`)

After aggregation, one subagent takes the top 8-10 firms by mention count and
records, per firm: what engines credit them for, their town/service page
coverage, review footprint, and awards or press cited. Output
`results/competitors.json`. The report compares these signals to OOTW's.

### 6. Aggregation and report (`scripts/aggregate.py`, `scripts/render.py`)

`aggregate.py` reads all result files and computes:

- Overall mention rate, average rank when mentioned, website citation rate.
- The same by service, by town, by intent, and by engine (simulated vs each
  real engine).
- Firm leaderboard: mention count and average rank across all queries.
- Verbatim list of every sentence engines wrote about OOTW.

It fills `report/report.md` from a template with these sections:

1. Executive summary (one page: scorecard, three headline findings, top five
   actions).
2. Methodology and limitations (simulated vs real engines, date, query list
   size, what a simulated engine does and does not prove).
3. Visibility scorecard (tables by service, town, intent, engine).
4. What engines say about OOTW (verbatim, with sources).
5. Who wins instead and why (leaderboard plus signal comparison).
6. Website and footprint audit findings.
7. Recommendations: website wording, structured data, new pages, off-site
   citations and reviews. Each has rationale tied to a finding and a draft
   of the suggested copy where applicable.
8. 30/60/90-day plan.
9. Items from Dave's audit (populated from `inputs/` if present, otherwise a
   note that it was not received).
10. Appendix: every query with the full answer and sources.

Recommendation text in sections 1, 7, and 8 is written by the orchestrating
session after reading the aggregate, not generated by the script; the script
produces the data sections and leaves marked slots.

`render.py` converts Markdown to HTML (python `markdown` via `uv run --with`)
with a print stylesheet, then runs
`Google Chrome --headless --print-to-pdf` to produce `report/report.pdf`.

## Error handling

- Malformed agent JSON: validator reports which records fail; batch is re-run
  once with the validation errors included in the prompt. Persistent failures
  are dropped and listed in the methodology section.
- Browser blocks, captchas, or login walls: recorded as `blocked`, never
  fabricated. The report shows coverage per engine.
- Site fetch failures: recorded per URL; audit continues.
- Any query with zero local results is kept and flagged; it is itself a
  finding.

## Testing

- `tests/test_build_queries.py`: deterministic output, expected count, all
  8 core queries present, no duplicates.
- `tests/test_validate.py`: accepts a valid record, rejects missing fields,
  wrong types, rank present when not mentioned.
- `tests/test_aggregate.py`: fixtures with known mention counts produce the
  expected rates, ranks, leaderboard ordering, and per-dimension tables;
  blocked records are excluded from rates but counted in coverage.
- `tests/test_site_audit.py`: parsing of robots.txt rules and JSON-LD
  extraction against fixture HTML.
- Manual gate: 3-query dry run reviewed before full fan-out.

## Timeline

Wednesday 2026-10-28: scaffold, scripts, tests, dry run, full fan-out.
Thursday 2026-10-29: browser spot check, audits, competitor pass, write
recommendations, render PDF. Friday 2026-10-30: deliver to Dave.
