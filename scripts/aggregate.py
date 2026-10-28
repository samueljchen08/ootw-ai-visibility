"""Aggregate answer-engine results into report/report.md."""
import json, glob, os, sys, datetime
from collections import defaultdict

OOTW_ALIASES = ("out of the woods",)
SITE_PREFIX = "https://www.outofthewoodsconstruction.com"

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

def _load(path):
    with open(path) as f:
        data = json.load(f)
    return data if isinstance(data, list) else [data]

def load_records(results_dir="results"):
    recs = []
    for path in sorted(glob.glob(os.path.join(results_dir, "simulated", "batch-*.json"))):
        if path.endswith(".input.json"):
            continue
        for r in _load(path):
            r.setdefault("engine", "simulated"); recs.append(r)
    for path in sorted(glob.glob(os.path.join(results_dir, "real", "*", "*.json"))):
        engine = os.path.basename(os.path.dirname(path))
        for r in _load(path):
            r.setdefault("engine", engine); recs.append(r)
    return recs

def compute(records, queries):
    qmap = {q["id"]: q for q in queries}
    groups = {"by_service": defaultdict(list), "by_geo": defaultdict(list),
              "by_intent": defaultdict(list), "by_engine": defaultdict(list)}
    coverage = defaultdict(lambda: {"ok": 0, "blocked": 0})
    firm_mentions, firm_ranks = defaultdict(int), defaultdict(list)
    domain_counts = defaultdict(int)
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
        for url in r.get("sources_cited", []):
            dom = url.split("//")[-1].split("/")[0].replace("www.", "")
            if dom:
                domain_counts[dom] += 1
        if r["ootw_mentioned"]:
            quotes.append({"query_id": r["query_id"], "engine": r["engine"], "rank": r["ootw_rank"],
                           "description": r.get("ootw_description"), "query_text": q.get("text", "")})
    leaderboard = sorted(
        [{"firm": f, "mentions": n, "avg_rank": round(sum(firm_ranks[f]) / n, 2)} for f, n in firm_mentions.items()],
        key=lambda x: (-x["mentions"], x["avg_rank"], x["firm"]))
    top_domains = sorted(domain_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
    out = {"overall": _stat(records), "leaderboard": leaderboard, "ootw_quotes": quotes,
           "coverage": {k: dict(v) for k, v in coverage.items()},
           "top_cited_domains": [{"domain": d, "citations": c} for d, c in top_domains]}
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

def _cell(v):
    s = v if isinstance(v, str) else json.dumps(v)
    return s.replace("|", "\\|").replace("\n", " ")

def _dict_table(d, key_header="Item", val_header="Value"):
    lines = [f"| {key_header} | {val_header} |", "|---|---|"]
    for k, v in d.items():
        lines.append(f"| {k} | {_cell(v)} |")
    return "\n".join(lines)

def build_report(summary, queries, records, site, narrative_dir="report/narrative",
                 footprint=None, competitors=None):
    o = summary["overall"]
    cov = site.get("coverage", {})
    md = ["# AI-Search Visibility Audit: Out of the Woods Construction & Cabinetry",
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
            md.append(f"| {qt['query_text']} | {qt['engine']} | {qt['rank']} | {_cell(qt['description'] or '')} |")
    else:
        md.append("Out of the Woods was not mentioned in any captured answer.")
    md += ["", "## 5. Who wins instead and why", "",
           "| # | Firm | Mentions | Avg position |", "|---|---|---|---|"]
    for i, row in enumerate(summary["leaderboard"][:15], 1):
        md.append(f"| {i} | {row['firm']} | {row['mentions']} | {row['avg_rank']} |")
    if summary.get("top_cited_domains"):
        md += ["", "### Sources engines relied on most", "", "| Domain | Citations |", "|---|---|"]
        for d in summary["top_cited_domains"][:12]:
            md.append(f"| {d['domain']} | {d['citations']} |")
    if competitors:
        md += ["", "### Competitor signal comparison", ""]
        for c in (competitors if isinstance(competitors, list) else competitors.get("firms", [])):
            md += [f"**{c.get('firm', '?')}**", "", _dict_table({k: v for k, v in c.items() if k != "firm"}), ""]
    md += ["", "## 6. Website and footprint audit findings", "",
           "### outofthewoodsconstruction.com", "",
           f"- Sitemap found: {site.get('sitemap_found')}. llms.txt found: {site.get('llms_txt_found')}. Pages audited: {len(site.get('pages', []))}.",
           f"- Structured data types found anywhere: {', '.join(cov.get('jsonld_anywhere', [])) or 'none'}.",
           f"- Scope towns named anywhere on the site: {', '.join(cov.get('towns_anywhere', [])) or 'none'}.", "",
           "| AI crawler | robots.txt status |", "|---|---|"]
    for bot, st in site.get("ai_crawlers", {}).items():
        md.append(f"| {bot} | {st} |")
    md += ["", "| Service | Dedicated page(s) |", "|---|---|"]
    for s, urls in cov.get("service_pages", {}).items():
        md.append(f"| {s} | {', '.join(u.replace(SITE_PREFIX, '') for u in urls) or 'none'} |")
    md += ["", "| Town | Dedicated page(s) |", "|---|---|"]
    for t, urls in cov.get("town_pages", {}).items():
        md.append(f"| {t} | {', '.join(u.replace(SITE_PREFIX, '') for u in urls) or 'none'} |")
    md += ["", "| Page | Title | H1 | Words | JSON-LD | Towns named |", "|---|---|---|---|---|---|"]
    for p in site.get("pages", []):
        md.append(f"| {p['url'].replace(SITE_PREFIX, '') or '/'} | {_cell(p['title'])} | {_cell(p['h1'])} | {p['word_count']} | {', '.join(p['jsonld_types']) or '-'} | {', '.join(p['towns_named']) or '-'} |")
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
                md += ["Sources: " + ", ".join(f"<{u}>" for u in r["sources_cited"]), ""]
    return "\n".join(md)

def main(results_dir="results", out="report/report.md"):
    with open("queries.json") as f:
        queries = json.load(f)["queries"]
    records = load_records(results_dir)
    site = _optional_json(os.path.join(results_dir, "audit", "site.json")) or {"ai_crawlers": {}, "coverage": {}, "pages": []}
    footprint = _optional_json(os.path.join(results_dir, "audit", "footprint.json"))
    competitors = _optional_json(os.path.join(results_dir, "competitors.json"))
    summary = compute(records, queries)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(os.path.join(os.path.dirname(out), "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    with open(out, "w") as f:
        f.write(build_report(summary, queries, records, site, "report/narrative", footprint, competitors))
    print(f"{len(records)} records -> {out}; overall mention rate {_pct(summary['overall']['mention_rate'])}")

if __name__ == "__main__":
    main(*sys.argv[1:])
