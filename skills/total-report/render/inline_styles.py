"""Concat CSS files in deterministic order for inline <style> injection.

MERGED harness (total-report): one SKILL_STYLES map holding all four report
slugs — the three vendored finder reports (query/path/cluster) plus the new
`total-insight` umbrella.

Order matters:
  * design-tokens.css (CSS variables) MUST come first so subsequent rules can
    reference them.
  * overlay.css (skill-only single-page wrapper) MUST come last so it can
    override ListeningMind.AI defaults (e.g. .rpt-main sidebar offset, view
    toggle display rules).

For `total-insight` we inline the union of every finder's stylesheet — the
umbrella embeds all three finders' dashboard bodies verbatim, so their native
CSS (query-opportunity.css / path-opportunity.css / cluster-landscape.css) must
all be present, followed by total-overview.css (the umbrella chrome: 4-tab nav,
total cover, hub cross-view) and finally overlay.css.
"""

from pathlib import Path
from typing import List


# Ordered list of stylesheets per skill slug.
SKILL_STYLES = {
    # ── individual finder reports (kept so the standalone render_<finder>
    #    adapters still work exactly as in the sibling skills) ──
    "query-opportunity": [
        "design-tokens.css",
        "report-shell.css",
        "audience-shared.css",
        "report-components.css",
        "customer-analysis.css",
        "overlay.css",
    ],
    "path-opportunity": [
        "design-tokens.css",
        "report-shell.css",
        "audience-shared.css",
        "report-components.css",
        "customer-analysis.css",
        "path-opportunity.css",
        "overlay.css",
    ],
    "cluster-landscape": [
        "design-tokens.css",
        "report-shell.css",
        "audience-shared.css",
        "report-components.css",
        "customer-analysis.css",
        "cluster-landscape.css",  # .cl-* : hub table + From→To flow section
        "overlay.css",
    ],
    # ── total-insight umbrella: union of all finder styles + total-overview,
    #    tokens first, overlay LAST ──
    "total-insight": [
        "design-tokens.css",
        "report-shell.css",
        "audience-shared.css",
        "report-components.css",
        "customer-analysis.css",
        "query-opportunity.css",   # inert on card path but harmless (legacy chart view)
        "path-opportunity.css",    # .flow-* / .path-* / .hub-* journey styles
        "cluster-landscape.css",   # .cl-* hub table + flows
        "total-overview.css",      # .tot-* umbrella chrome: 4-tab nav + total cover + hub cross-view
        "overlay.css",
    ],
}


def inline_styles(styles_dir: Path, skill: str) -> str:
    files = SKILL_STYLES[skill]
    chunks: List[str] = []
    for name in files:
        path = styles_dir / name
        chunks.append(f"/* === {name} === */\n{path.read_text(encoding='utf-8')}")
    return "\n\n".join(chunks)
