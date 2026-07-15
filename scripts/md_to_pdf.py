#!/usr/bin/env python3
"""Convert Markdown report to PDF (Chinese-friendly via WeasyPrint).

Usage:
  python3 scripts/md_to_pdf.py path/to/report.md [-o out.pdf]
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path


CSS = """
@page { size: A4; margin: 18mm 16mm; }
body {
  font-family: "Noto Sans CJK SC", "Noto Sans CJK", "Source Han Sans SC",
               "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 11pt;
  line-height: 1.45;
  color: #111;
}
h1 { font-size: 18pt; margin: 0 0 12pt; }
h2 { font-size: 14pt; margin: 16pt 0 8pt; border-bottom: 1px solid #ddd; padding-bottom: 4pt; }
h3 { font-size: 12pt; margin: 12pt 0 6pt; }
p, li { margin: 4pt 0; }
blockquote {
  margin: 8pt 0; padding: 6pt 10pt; background: #f6f6f6; border-left: 3px solid #999;
}
code, pre {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 9.5pt;
}
pre {
  background: #f4f4f4; padding: 8pt; white-space: pre-wrap; word-break: break-word;
}
table { border-collapse: collapse; width: 100%; margin: 8pt 0; font-size: 9.5pt; }
th, td { border: 1px solid #ccc; padding: 4pt 6pt; vertical-align: top; }
th { background: #f0f0f0; }
hr { border: none; border-top: 1px solid #ddd; margin: 14pt 0; }
"""


def md_to_html(md: str) -> str:
    try:
        import markdown  # type: ignore
    except ImportError as e:
        raise SystemExit("Missing dependency: pip install markdown weasyprint") from e

    body = markdown.markdown(
        md,
        extensions=["tables", "fenced_code", "nl2br", "sane_lists"],
        output_format="html5",
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>report</title>
<style>{CSS}</style>
</head>
<body>
{body}
</body>
</html>
"""


def write_pdf(html_doc: str, out: Path) -> None:
    try:
        from weasyprint import HTML  # type: ignore
    except ImportError as e:
        raise SystemExit("Missing dependency: pip install markdown weasyprint") from e
    HTML(string=html_doc, base_url=str(out.parent.resolve())).write_pdf(str(out))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("markdown")
    ap.add_argument("-o", "--output", default="")
    args = ap.parse_args()
    src = Path(args.markdown)
    if not src.exists():
        raise SystemExit(f"missing: {src}")
    out = Path(args.output) if args.output else src.with_suffix(".pdf")
    md = src.read_text(encoding="utf-8")
    # light sanitize of weird control chars
    md = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", md)
    html_doc = md_to_html(md)
    write_pdf(html_doc, out)
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
