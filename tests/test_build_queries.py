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
