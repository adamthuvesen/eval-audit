"""Static HTML convenience rendering for canonical Markdown reports."""

from __future__ import annotations

from html import escape


def render_html_report(markdown_text: str, *, title: str) -> str:
    """Render deterministic, self-contained HTML from canonical Markdown text.

    Markdown remains the evidence artifact. The HTML view deliberately preserves
    the full escaped Markdown body so it cannot drift into a second report model.
    """
    escaped_title = escape(title, quote=True)
    escaped_markdown = escape(markdown_text, quote=False)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"  <title>{escaped_title}</title>\n"
        "  <style>\n"
        "    :root { color-scheme: light; }\n"
        "    body { margin: 0; font: 16px/1.55 -apple-system, BlinkMacSystemFont, "
        "Segoe UI, sans-serif; color: #18202a; background: #f8f8f5; }\n"
        "    main { max-width: 1040px; margin: 0 auto; padding: 40px 24px 56px; }\n"
        "    .canonical-note { margin: 0 0 24px; padding: 12px 14px; "
        "border-left: 4px solid #2f6f73; background: #ffffff; }\n"
        "    pre { margin: 0; padding: 24px; overflow-x: auto; white-space: pre-wrap; "
        "background: #ffffff; border: 1px solid #d9ddd6; border-radius: 6px; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        "  <main>\n"
        '    <p class="canonical-note"><code>report.md</code> is the canonical '
        "reproducibility artifact. This static HTML is an optional convenience "
        "view of the same escaped Markdown report.</p>\n"
        f"    <pre>{escaped_markdown}</pre>\n"
        "  </main>\n"
        "</body>\n"
        "</html>\n"
    )
