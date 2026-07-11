"""Structured static HTML convenience rendering for canonical Markdown reports."""

from __future__ import annotations

import re
from html import escape

_SECTION_RE = re.compile(r"^## (?P<title>.+)$")
_CLAIM_HEADING_RE = re.compile(r"^### Claim `(?P<claim_id>[^`]+)`$")
_BOLD_LINE_RE = re.compile(r"^\*\*(?P<label>.+?)\*\*(?P<rest>.*)$")
_KEY_VALUE_BULLET_RE = re.compile(r"^- \*\*(?P<label>.+?):\*\* ?(?P<value>.*)$")
_ORDERED_BULLET_RE = re.compile(r"^(?P<number>\d+)\. (?P<text>.*)$")


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "section"


def _inline(text: str) -> str:
    escaped = escape(text, quote=False)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def _verdict_slug(text: str) -> str:
    match = re.search(r"`([^`]+)`", text)
    if match is None:
        return "unknown"
    return _slug(match.group(1))


def _cell_text(cell: str) -> str:
    return cell.strip()


def _is_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    return (
        lines[index].lstrip().startswith("|")
        and re.match(
            r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$",
            lines[index + 1],
        )
        is not None
    )


def _parse_table(lines: list[str], index: int) -> tuple[str, int]:
    header = [_cell_text(cell) for cell in lines[index].strip().strip("|").split("|")]
    index += 2
    rows: list[list[str]] = []
    while index < len(lines) and lines[index].lstrip().startswith("|"):
        rows.append([_cell_text(cell) for cell in lines[index].strip().strip("|").split("|")])
        index += 1

    head = "".join(f"<th>{_inline(cell)}</th>" for cell in header)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{_inline(cell)}</td>" for cell in row)
        body_rows.append(f"<tr>{cells}</tr>")
    table = (
        '<div class="table-wrap"><table>'
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table></div>"
    )
    return table, index


def _collect_until_blank(lines: list[str], index: int) -> tuple[list[str], int]:
    out: list[str] = []
    while index < len(lines) and lines[index].strip():
        out.append(lines[index])
        index += 1
    return out, index


def _collect_paragraph(lines: list[str], index: int) -> tuple[str, int]:
    parts: list[str] = []
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            break
        if (
            _is_table_start(lines, index)
            or stripped.startswith("- ")
            or _ORDERED_BULLET_RE.match(stripped)
            or _BOLD_LINE_RE.match(stripped)
        ):
            break
        parts.append(stripped)
        index += 1
    return " ".join(parts), index


def _render_bullets(items: list[str]) -> str:
    rows: list[str] = []
    ordinary: list[str] = []
    for item in items:
        match = _KEY_VALUE_BULLET_RE.match(item)
        if match is None:
            ordinary.append(item[2:])
            continue
        rows.append(
            '<div class="kv-row">'
            f'<span class="kv-label">{_inline(match.group("label"))}</span>'
            f'<span class="kv-value">{_inline(match.group("value"))}</span>'
            "</div>"
        )
    rendered = []
    if rows:
        rendered.append(f'<div class="kv-list">{"".join(rows)}</div>')
    if ordinary:
        rendered.append(
            "<ul>" + "".join(f"<li>{_inline(item)}</li>" for item in ordinary) + "</ul>"
        )
    return "".join(rendered)


def _render_ordered(items: list[str]) -> str:
    return "<ol>" + "".join(f"<li>{_inline(item)}</li>" for item in items) + "</ol>"


def _render_blocks(lines: list[str]) -> str:
    parts: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            index += 1
            continue
        if _is_table_start(lines, index):
            table, index = _parse_table(lines, index)
            parts.append(table)
            continue
        if stripped.startswith("- "):
            items, index = _collect_until_blank(lines, index)
            parts.append(_render_bullets(items))
            continue
        if _ORDERED_BULLET_RE.match(stripped):
            ordered_items: list[str] = []
            while index < len(lines):
                match = _ORDERED_BULLET_RE.match(lines[index].strip())
                if match is None:
                    break
                ordered_items.append(match.group("text"))
                index += 1
            parts.append(_render_ordered(ordered_items))
            continue
        bold = _BOLD_LINE_RE.match(stripped)
        if bold is not None:
            title = bold.group("label")
            rest = bold.group("rest").strip()
            suffix = f" <span>{_inline(rest)}</span>" if rest else ""
            parts.append(f"<h3>{_inline(title)}{suffix}</h3>")
            index += 1
            continue
        paragraph, index = _collect_paragraph(lines, index)
        if paragraph:
            parts.append(f"<p>{_inline(paragraph)}</p>")
        else:
            parts.append(f"<p>{_inline(stripped)}</p>")
            index += 1
    return "\n".join(parts)


def _split_sections(markdown_text: str) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    current_title: str | None = None
    current_lines: list[str] = []
    for line in markdown_text.splitlines():
        match = _SECTION_RE.match(line)
        if match is not None:
            if current_title is not None:
                sections.append((current_title, current_lines))
            current_title = match.group("title")
            current_lines = []
            continue
        if current_title is not None:
            current_lines.append(line)
    if current_title is not None:
        sections.append((current_title, current_lines))
    return sections


def _summary_fields(lines: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in lines:
        match = _KEY_VALUE_BULLET_RE.match(line.strip())
        if match is not None:
            fields[match.group("label")] = match.group("value")
    return fields


def _render_summary_grid(fields: dict[str, str]) -> str:
    verdict = fields.get("Verdict", "n/a")
    verdict_class = _verdict_slug(verdict)
    order = [
        "Verdict",
        "Claim status",
        "Why",
        "What would change it",
        "Reviewer pushback",
    ]
    cards = []
    for label in order:
        if label not in fields:
            continue
        value = fields[label]
        extra = (
            f' <span class="verdict-badge verdict-{verdict_class}">{_inline(value)}</span>'
            if label == "Verdict"
            else f"<p>{_inline(value)}</p>"
        )
        cards.append(f'<article class="summary-card"><h3>{escape(label)}</h3>{extra}</article>')
    return '<div class="summary-grid">' + "".join(cards) + "</div>"


def _audit_summary_stanzas(lines: list[str]) -> list[tuple[str | None, list[str]]]:
    stanzas: list[tuple[str | None, list[str]]] = []
    current_claim: str | None = None
    current_lines: list[str] = []
    saw_claim_heading = False

    for line in lines:
        match = _CLAIM_HEADING_RE.match(line.strip())
        if match is not None:
            saw_claim_heading = True
            if current_claim is not None or current_lines:
                stanzas.append((current_claim, current_lines))
            current_claim = match.group("claim_id")
            current_lines = []
            continue
        current_lines.append(line)

    if current_claim is not None or current_lines:
        stanzas.append((current_claim, current_lines))
    if not saw_claim_heading:
        return [(None, lines)]
    return [(claim_id, stanza_lines) for claim_id, stanza_lines in stanzas if claim_id is not None]


def _render_audit_summary(lines: list[str]) -> str:
    stanzas = _audit_summary_stanzas(lines)
    if len(stanzas) == 1 and stanzas[0][0] is None:
        return _render_summary_grid(_summary_fields(lines))

    rendered: list[str] = []
    for claim_id, stanza_lines in stanzas:
        fields = _summary_fields(stanza_lines)
        rendered.append(
            '<article class="claim-card audit-summary-claim">'
            f"<h3>Claim <code>{escape(claim_id or '', quote=False)}</code></h3>"
            f"{_render_summary_grid(fields)}"
            "</article>"
        )
    return "".join(rendered)


def _collect_claim_card(lines: list[str], index: int) -> tuple[str, int]:
    header = lines[index].strip()
    match = _BOLD_LINE_RE.match(header)
    assert match is not None
    label = match.group("label")
    rest = match.group("rest").strip()
    card_class = _slug(label)
    index += 1
    body: list[str] = []
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped and _BOLD_LINE_RE.match(stripped):
            break
        body.append(lines[index])
        index += 1
    return (
        f'<article class="claim-card {card_class}">'
        f"<h3>{_inline(label)}{' <span>' + _inline(rest) + '</span>' if rest else ''}</h3>"
        f"{_render_blocks(body)}"
        "</article>",
        index,
    )


def _render_claims(lines: list[str]) -> str:
    parts: list[str] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue
        if _is_table_start(lines, index):
            table, index = _parse_table(lines, index)
            parts.append(table)
            continue
        if _BOLD_LINE_RE.match(stripped):
            card, index = _collect_claim_card(lines, index)
            parts.append(card)
            continue
        block, index = _collect_paragraph(lines, index)
        if block:
            parts.append(f"<p>{_inline(block)}</p>")
        else:
            parts.append(f"<p>{_inline(stripped)}</p>")
            index += 1
    return "\n".join(parts)


def _render_section(title: str, lines: list[str]) -> str:
    section_class = f"section-{_slug(title)}"
    if title == "Audit Summary":
        body = _render_audit_summary(lines)
    elif title == "Claims":
        body = _render_claims(lines)
    else:
        body = _render_blocks(lines)
    return (
        f'<section class="report-section {section_class}" id="{_slug(title)}">'
        f"<h2>{escape(title)}</h2>"
        f"{body}"
        "</section>"
    )


def render_html_report(markdown_text: str, *, title: str) -> str:
    """Render deterministic, self-contained HTML from canonical Markdown text.

    Markdown remains the evidence artifact. This HTML is a structured review
    surface over the same text: no extra conclusions, no independent report
    model, and no external assets.
    """
    escaped_title = escape(title, quote=True)
    sections = _split_sections(markdown_text)
    nav = "".join(
        f'<a href="#{_slug(section_title)}">{escape(section_title)}</a>'
        for section_title, _ in sections
    )
    rendered_sections = "\n".join(
        _render_section(section_title, section_lines) for section_title, section_lines in sections
    )
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"  <title>{escaped_title}</title>\n"
        "  <style>\n"
        "    :root { color-scheme: light; --ink: #17202a; --muted: #5b6673; "
        "--line: #d9ddd6; --paper: #ffffff; --wash: #f7f7f2; --green: #206b4f; "
        "--amber: #8a5b00; --red: #9a3412; --blue: #285b8f; }\n"
        "    * { box-sizing: border-box; }\n"
        "    body { margin: 0; font: 15px/1.55 -apple-system, BlinkMacSystemFont, "
        "Segoe UI, sans-serif; color: var(--ink); background: var(--wash); }\n"
        "    header { padding: 36px 28px 22px; border-bottom: 1px solid var(--line); "
        "background: var(--paper); }\n"
        "    main { max-width: 1120px; margin: 0 auto; padding: 28px 20px 52px; }\n"
        "    h1 { margin: 0 0 8px; font-size: 32px; letter-spacing: 0; }\n"
        "    h2 { margin: 0 0 18px; font-size: 22px; letter-spacing: 0; }\n"
        "    h3 { margin: 0 0 10px; font-size: 15px; letter-spacing: 0; }\n"
        "    p { margin: 0 0 14px; }\n"
        "    code { padding: 1px 5px; border-radius: 4px; background: #eef0ea; "
        "font: 0.92em ui-monospace, SFMono-Regular, Menlo, monospace; }\n"
        "    nav { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }\n"
        "    nav a { color: var(--blue); text-decoration: none; padding: 5px 8px; "
        "border: 1px solid var(--line); border-radius: 6px; background: #fbfbf8; }\n"
        "    .canonical-note { max-width: 1120px; margin: 0 auto; color: var(--muted); }\n"
        "    .report-section { margin: 0 0 18px; padding: 22px; border: 1px solid var(--line); "
        "border-radius: 8px; background: var(--paper); }\n"
        "    .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); "
        "gap: 12px; }\n"
        "    .summary-card, .claim-card { padding: 14px; border: 1px solid var(--line); "
        "border-radius: 8px; background: #fbfbf8; }\n"
        "    .summary-card p, .claim-card p { margin-bottom: 0; }\n"
        "    .verdict-badge { display: inline-block; padding: 7px 10px; border-radius: 999px; "
        "font-weight: 700; background: #eef0ea; }\n"
        "    .verdict-switch { color: var(--green); background: #e7f3eb; }\n"
        "    .verdict-hold, .verdict-drop-from-shortlist { color: var(--red); background: #f8ebe6; }\n"
        "    .verdict-hedge-on-cost, .verdict-rerun-more-n { color: var(--amber); background: #fff4d8; }\n"
        "    .verdict-inconclusive-no-action { color: var(--blue); background: #e8f0f8; }\n"
        "    .claim-card { margin: 14px 0 0; }\n"
        "    .claim-card.verdict-explainer { border-left: 4px solid var(--blue); }\n"
        "    .claim-card.copyable-summary { border-left: 4px solid var(--green); }\n"
        "    .claim-card.verdict-sensitivity { border-left: 4px solid var(--amber); }\n"
        "    .table-wrap { overflow-x: auto; margin: 12px 0; }\n"
        "    table { width: 100%; border-collapse: collapse; font-size: 14px; }\n"
        "    th, td { padding: 8px 9px; border-bottom: 1px solid var(--line); text-align: left; "
        "vertical-align: top; }\n"
        "    th { color: var(--muted); background: #f1f3ee; font-weight: 700; }\n"
        "    .kv-list { display: grid; gap: 8px; }\n"
        "    .kv-row { display: grid; grid-template-columns: minmax(140px, 220px) 1fr; gap: 12px; "
        "padding: 8px 0; border-bottom: 1px solid #eef0ea; }\n"
        "    .kv-label { color: var(--muted); font-weight: 700; }\n"
        "    ul, ol { margin: 0 0 12px 22px; padding: 0; }\n"
        "    @media (max-width: 680px) { header { padding: 26px 18px 18px; } "
        "main { padding: 18px 12px 36px; } .report-section { padding: 16px; } "
        ".kv-row { grid-template-columns: 1fr; gap: 2px; } }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        "  <header>\n"
        f'    <div class="canonical-note"><h1>{escaped_title}</h1>'
        "<p><code>report.md</code> remains the canonical reproducibility artifact. "
        "This HTML is a structured review view of the same audit evidence.</p>"
        f"<nav>{nav}</nav></div>\n"
        "  </header>\n"
        f"  <main>{rendered_sections}</main>\n"
        "</body>\n"
        "</html>\n"
    )
