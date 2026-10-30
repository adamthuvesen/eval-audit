"""Names in the persisted audit artifact contract."""

STAGING_PREFIX = ".audit-stage-"

ARTIFACT_FILES = {
    "check_json": "check.json",
    "analysis_json": "analysis.json",
    "report_md": "report.md",
    "report_html": "report.html",
}
ARTIFACT_NAMES = frozenset((*ARTIFACT_FILES.values(), "summary.json"))
