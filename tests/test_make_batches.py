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
