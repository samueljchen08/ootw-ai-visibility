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
