"""Turn a raw browser capture plus hand annotations into a result record."""
import json, sys, datetime, re

def annotate(raw_path, out_path, engine, firms, ootw_rank=None, ootw_description=None, notes=""):
    raw = json.load(open(raw_path))
    text = raw["text"]
    # Strip Perplexity chrome: keep from the first 'Finished' / answer start if present
    m = re.search(r"\nFinished\n\d+s\n", text)
    if m:
        text = text[m.end():]
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    mentioned = bool(re.search(r"out of the woods", raw["text"], re.I))
    rec = {"query_id": raw["query_id"], "engine": engine, "status": "ok",
           "answer_text": text[:4000], "firms_named": firms,
           "ootw_mentioned": mentioned, "ootw_rank": ootw_rank if mentioned else None,
           "ootw_description": ootw_description if mentioned else None,
           "sources_cited": raw.get("links", []), 
           "ootw_site_cited": any("outofthewoodsconstruction.com" in u for u in raw.get("links", [])),
           "notes": notes, "captured_at": datetime.datetime.now().isoformat(timespec="seconds"),
           "capture_url": raw.get("url")}
    json.dump(rec, open(out_path, "w"), indent=2)
    return rec

if __name__ == "__main__":
    spec = json.load(open(sys.argv[1]))
    for s in spec:
        r = annotate(**s)
        print(r["query_id"], r["engine"], "mentioned" if r["ootw_mentioned"] else "not mentioned", len(r["firms_named"]), "firms")
