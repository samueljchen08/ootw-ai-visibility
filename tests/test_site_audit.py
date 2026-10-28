import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from site_audit import parse_robots, ai_crawler_status, extract_jsonld, page_facts

ROBOTS = """User-agent: *
Disallow: /admin
User-agent: GPTBot
Disallow: /
User-agent: PerplexityBot
Allow: /
"""

def test_parse_robots_groups():
    r = parse_robots(ROBOTS)
    assert r["*"]["disallow"] == ["/admin"]
    assert r["gptbot"]["disallow"] == ["/"]
    assert r["perplexitybot"]["allow"] == ["/"]

def test_ai_crawler_status():
    s = ai_crawler_status(parse_robots(ROBOTS))
    assert s["GPTBot"] == "blocked"
    assert s["PerplexityBot"] == "allowed"
    assert s["ClaudeBot"] == "unspecified"

def test_wildcard_block_applies():
    s = ai_crawler_status(parse_robots("User-agent: *\nDisallow: /\n"))
    assert s["ClaudeBot"] == "blocked"

HTML = """<html><head><title>Kitchens | OOTW</title>
<meta name="description" content="Kitchen remodeling in Waltham and Newton">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"LocalBusiness","name":"OOTW"}</script>
</head><body><h1>Kitchen Remodeling</h1>
<p>We serve Waltham, Newton and Wellesley with kitchen and bathroom remodeling plus additions.</p>
<h2>Frequently Asked Questions</h2>
<a href="/bathrooms">Baths</a><a href="https://houzz.com/x">Houzz</a></body></html>"""

def test_extract_jsonld():
    assert extract_jsonld(HTML) == ["LocalBusiness"]

def test_page_facts():
    f = page_facts("https://outofthewoodsconstruction.com/kitchens", HTML)
    assert f["title"] == "Kitchens | OOTW"
    assert f["meta_description"].startswith("Kitchen remodeling")
    assert f["h1"] == "Kitchen Remodeling"
    assert set(f["towns_named"]) == {"Waltham", "Newton", "Wellesley"}
    assert set(f["services_named"]) >= {"kitchen", "bath", "addition"}
    assert f["has_faq"] is True
    assert f["internal_links"] == ["https://outofthewoodsconstruction.com/bathrooms"]
    assert f["word_count"] > 5
