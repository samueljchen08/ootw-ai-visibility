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
            qid = rec.get("query_id") if isinstance(rec, dict) else "?"
            errors.append(f"{path}[{i}] ({qid}): {e}")
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
            if path.endswith((".input.json", ".raw.json")):
                continue
            res = validate_file(path, known)
            for e in res["errors"]:
                print("ERROR", e)
            bad += len(res["errors"])
            print(f"{path}: {res['count']} records, {len(res['errors'])} errors")
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main(sys.argv[1:] or ["results/simulated/batch-*.json", "results/real/*/*.json"])
