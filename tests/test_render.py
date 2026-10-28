import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from render import to_html

def test_to_html_renders_tables_and_title():
    md = "# Title\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n> quote\n"
    html = to_html(md, "Report")
    assert "<table>" in html and "<td>1</td>" in html
    assert "<title>Report</title>" in html
    assert "@page" in html
