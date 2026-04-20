#!/usr/bin/env python3
"""Convert Markdown to styled PDF using markdown + playwright (Chromium)."""
import sys
import markdown

def convert(md_path, pdf_path):
    with open(md_path, 'r', encoding='utf-8') as f:
        md_text = f.read()
    
    html_body = markdown.markdown(
        md_text,
        extensions=['tables', 'fenced_code', 'codehilite', 'toc']
    )
    
    full_html = f"""<!DOCTYPE html>
<html lang="zh-HK">
<head>
<meta charset="utf-8">
<style>
@page {{
    size: A4;
    margin: 1.5cm 1.8cm;
}}
body {{
    font-family: -apple-system, "PingFang HK", "Noto Sans CJK TC", "Microsoft JhengHei", sans-serif;
    font-size: 11px;
    line-height: 1.6;
    color: #1a1a1a;
    max-width: 100%;
}}
h1 {{
    font-size: 22px;
    color: #0d47a1;
    border-bottom: 3px solid #1565c0;
    padding-bottom: 8px;
    margin-top: 0;
}}
h2 {{
    font-size: 16px;
    color: #1565c0;
    border-bottom: 1.5px solid #bbdefb;
    padding-bottom: 5px;
    margin-top: 24px;
}}
h3 {{
    font-size: 13px;
    color: #1976d2;
    margin-top: 18px;
}}
table {{
    border-collapse: collapse;
    width: 100%;
    margin: 10px 0;
    font-size: 10px;
}}
th {{
    background-color: #1565c0;
    color: white;
    padding: 6px 8px;
    text-align: left;
    font-weight: 600;
}}
td {{
    padding: 5px 8px;
    border-bottom: 1px solid #e0e0e0;
}}
tr:nth-child(even) {{
    background-color: #f5f5f5;
}}
code {{
    background-color: #f0f0f0;
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 9.5px;
    font-family: "SF Mono", Menlo, monospace;
}}
pre {{
    background-color: #263238;
    color: #eeffff;
    padding: 12px 16px;
    border-radius: 6px;
    font-size: 9.5px;
    line-height: 1.45;
    overflow-x: auto;
    page-break-inside: avoid;
}}
pre code {{
    background: none;
    color: inherit;
    padding: 0;
}}
blockquote {{
    border-left: 4px solid #ff9800;
    background-color: #fff8e1;
    padding: 10px 14px;
    margin: 12px 0;
    font-size: 10.5px;
}}
blockquote p {{
    margin: 4px 0;
}}
hr {{
    border: none;
    border-top: 1px solid #e0e0e0;
    margin: 18px 0;
}}
strong {{
    color: #0d47a1;
}}
p {{
    margin: 6px 0;
}}
ul, ol {{
    margin: 6px 0;
    padding-left: 22px;
}}
li {{
    margin: 3px 0;
}}
</style>
</head>
<body>
{html_body}
</body>
</html>"""
    
    # Write temp HTML
    tmp_html = '/tmp/_reflector_temp.html'
    with open(tmp_html, 'w', encoding='utf-8') as f:
        f.write(full_html)
    
    # Use playwright to render PDF
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f'file://{tmp_html}')
        page.pdf(
            path=pdf_path,
            format='A4',
            margin={'top': '1.5cm', 'bottom': '1.5cm', 'left': '1.8cm', 'right': '1.8cm'},
            print_background=True,
            display_header_footer=True,
            header_template='<span></span>',
            footer_template='<div style="font-size:9px;color:#999;text-align:center;width:100%"><span class="pageNumber"></span> / <span class="totalPages"></span></div>'
        )
        browser.close()
    
    import os
    os.remove(tmp_html)
    print(f"PDF saved to: {pdf_path}")

if __name__ == '__main__':
    convert(sys.argv[1], sys.argv[2])
