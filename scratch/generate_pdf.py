import markdown
from playwright.sync_api import sync_playwright
import os

def markdown_to_pdf(md_path: str, output_pdf_path: str):
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    # Convert markdown to html with table and fence extensions
    html_content = markdown.markdown(md_text, extensions=["tables", "fenced_code", "nl2br"])

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>The Illusion of Completion - Architectural Post-Mortem</title>
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

    @page {{
        size: A4;
        margin: 20mm 15mm 20mm 15mm;
        @bottom-right {{
            content: counter(page);
            font-family: 'Inter', sans-serif;
            font-size: 9pt;
            color: #64748b;
        }}
    }}

    body {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        color: #1e293b;
        line-height: 1.6;
        font-size: 10.5pt;
        background-color: #ffffff;
        margin: 0;
        padding: 0;
    }}

    h1 {{
        font-size: 20pt;
        font-weight: 800;
        color: #0f172a;
        line-height: 1.25;
        margin-top: 0;
        margin-bottom: 8px;
        border-bottom: 2px solid #3b82f6;
        padding-bottom: 12px;
    }}

    h2 {{
        font-size: 13.5pt;
        font-weight: 700;
        color: #1e3a8a;
        margin-top: 24px;
        margin-bottom: 10px;
        border-bottom: 1px solid #e2e8f0;
        padding-bottom: 6px;
        page-break-after: avoid;
    }}

    h3 {{
        font-size: 11.5pt;
        font-weight: 600;
        color: #1e293b;
        margin-top: 18px;
        margin-bottom: 6px;
        page-break-after: avoid;
    }}

    p {{
        margin-top: 0;
        margin-bottom: 10px;
        text-align: justify;
    }}

    blockquote {{
        margin: 14px 0;
        padding: 10px 16px;
        background: #f8fafc;
        border-left: 4px solid #3b82f6;
        border-radius: 0 6px 6px 0;
        font-style: italic;
        color: #334155;
    }}

    blockquote p {{
        margin: 0;
    }}

    table {{
        width: 100%;
        border-collapse: collapse;
        margin: 16px 0;
        font-size: 9.5pt;
        page-break-inside: avoid;
    }}

    th, td {{
        padding: 8px 12px;
        border: 1px solid #cbd5e1;
        text-align: left;
    }}

    th {{
        background-color: #f1f5f9;
        font-weight: 600;
        color: #0f172a;
    }}

    tr:nth-child(even) td {{
        background-color: #f8fafc;
    }}

    pre {{
        background: #0f172a;
        color: #f8fafc;
        padding: 12px 14px;
        border-radius: 6px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 8.5pt;
        line-height: 1.45;
        overflow-x: auto;
        margin: 14px 0;
        page-break-inside: avoid;
    }}

    code {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 9pt;
        background: #f1f5f9;
        color: #0369a1;
        padding: 2px 5px;
        border-radius: 4px;
    }}

    pre code {{
        background: transparent;
        color: inherit;
        padding: 0;
    }}

    ul, ol {{
        margin-top: 0;
        margin-bottom: 12px;
        padding-left: 22px;
    }}

    li {{
        margin-bottom: 4px;
    }}

    hr {{
        border: 0;
        height: 1px;
        background: #e2e8f0;
        margin: 20px 0;
    }}

    .header-badge {{
        display: inline-block;
        background: #eff6ff;
        color: #1d4ed8;
        padding: 4px 10px;
        font-size: 8.5pt;
        font-weight: 600;
        border-radius: 12px;
        margin-bottom: 12px;
        border: 1px solid #bfdbfe;
    }}
</style>
</head>
<body>
<div class="header-badge">ARCHITECTURAL WHITE PAPER • SYSTEMS ENGINEERING & AI ALIGNMENT</div>
{html_content}
</body>
</html>
"""

    temp_html_path = output_pdf_path.replace(".pdf", ".html")
    with open(temp_html_path, "w", encoding="utf-8") as f:
        f.write(full_html)

    print(f"[*] HTML rendered at: {temp_html_path}")
    print("[*] Launching headless browser for PDF compilation...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"file:///{os.path.abspath(temp_html_path)}")
        page.wait_for_load_state("networkidle")
        page.pdf(
            path=output_pdf_path,
            format="A4",
            margin={"top": "20mm", "bottom": "20mm", "left": "15mm", "right": "15mm"},
            print_background=True
        )
        browser.close()

    print(f"[+] Successfully generated publication PDF: {output_pdf_path}")

if __name__ == "__main__":
    md_file = "d:/omniroute-monetizer/docs/THE_ILLUSION_OF_COMPLETION_AGENT_POSTMORTEM.md"
    pdf_file = "d:/omniroute-monetizer/docs/THE_ILLUSION_OF_COMPLETION_AGENT_POSTMORTEM.pdf"
    markdown_to_pdf(md_file, pdf_file)
