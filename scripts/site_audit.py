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
    rules, current, fresh = {}, [], False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, val = [p.strip() for p in line.split(":", 1)]
        key = key.lower()
        if key == "user-agent":
            agent = val.lower()
            rules.setdefault(agent, {"allow": [], "disallow": []})
            current = current + [agent] if fresh else [agent]
            fresh = True
        elif key in ("allow", "disallow") and current:
            fresh = False
            for a in current:
                rules[a][key].append(val)
    return rules

def ai_crawler_status(rules):
    out = {}
    for bot in AI_CRAWLERS:
        specific = rules.get(bot.lower())
        group = specific if specific is not None else rules.get("*")
        if group is None:
            out[bot] = "unspecified"
        elif "/" in group["disallow"] and "/" not in group["allow"]:
            out[bot] = "blocked"
        elif specific is not None:
            out[bot] = "allowed"
        else:
            out[bot] = "unspecified"
    return out

def extract_jsonld(html):
    types = []
    for m in re.finditer(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            continue
        for item in (data if isinstance(data, list) else [data]):
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
        if (urllib.parse.urlparse(full).netloc.replace("www.", "") == host and full not in internal
                and not full.lower().endswith((".jpg", ".jpeg", ".png", ".pdf", ".gif", ".svg"))):
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
    robots = ""
    try:
        _, robots = fetch(f"{BASE}/robots.txt")
        result["robots"] = parse_robots(robots); result["robots_raw"] = robots
    except Exception as e:
        result["errors"].append(f"robots.txt: {e}")
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
    def _head(p):
        return (p["title"] + " " + p["h1"] + " " + p["url"]).lower().replace("bathroom", "bath")
    result["coverage"] = {
        "service_pages": {s: [p["url"] for p in result["pages"] if s in p["services_named"] and s.split("-")[0] in _head(p)] for s in SERVICE_TERMS},
        "town_pages": {t: [p["url"] for p in result["pages"] if t.lower() in _head(p)] for t in TOWNS},
        "towns_anywhere": sorted({t for p in result["pages"] for t in p["towns_named"]}),
        "jsonld_anywhere": sorted({t for p in result["pages"] for t in p["jsonld_types"]}),
    }
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"audited {len(result['pages'])} pages -> {out}; errors: {len(result['errors'])}")

if __name__ == "__main__":
    main(*sys.argv[1:])
