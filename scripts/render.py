"""Render report/report.md to HTML and PDF (headless Chrome)."""
import os, subprocess, sys
import markdown

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CSS = """
@page { size: Letter; margin: 0.75in; }
body { font: 11pt/1.45 -apple-system, "Helvetica Neue", Arial, sans-serif; color: #1a1a1a; max-width: 7.5in; margin: 0 auto; }
h1 { font-size: 22pt; margin: 0 0 4pt; }
h2 { font-size: 15pt; margin-top: 22pt; border-bottom: 1px solid #ccc; padding-bottom: 3pt; page-break-after: avoid; }
h3 { font-size: 12pt; margin-top: 14pt; page-break-after: avoid; }
table { border-collapse: collapse; width: 100%; font-size: 9.5pt; margin: 8pt 0; page-break-inside: auto; }
th, td { border: 1px solid #d0d0d0; padding: 3pt 5pt; text-align: left; vertical-align: top; word-break: break-word; }
th { background: #f2f2f2; } tr { page-break-inside: avoid; }
blockquote { border-left: 3px solid #bbb; margin: 6pt 0; padding: 2pt 10pt; color: #333; font-size: 10pt; }
code { font-size: 9.5pt; background: #f5f5f5; padding: 1px 3px; }
a { color: #1a4d8f; word-break: break-all; }
"""

def to_html(md_text, title):
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code", "sane_lists"])
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title>"
            f"<style>{CSS}</style></head><body>{body}</body></html>")

def main(src="report/report.md", out_html="report/report.html", out_pdf="report/report.pdf"):
    with open(src) as f:
        html = to_html(f.read(), "AI-Search Visibility Audit: Out of the Woods Construction")
    with open(out_html, "w") as f:
        f.write(html)
    cmd = [CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
           f"--print-to-pdf={os.path.abspath(out_pdf)}", "file://" + os.path.abspath(out_html)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    print(f"wrote {out_html} and {out_pdf} ({os.path.getsize(out_pdf)} bytes)")

if __name__ == "__main__":
    main(*sys.argv[1:])
