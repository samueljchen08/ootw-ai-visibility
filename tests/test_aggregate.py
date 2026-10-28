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
