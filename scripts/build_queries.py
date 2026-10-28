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
