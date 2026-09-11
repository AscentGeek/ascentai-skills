"""Concat CSS files in deterministic order for inline <style> injection.

Order matters: design-tokens (CSS variables) must come first so subsequent
rules can reference them. Overlay (skill-only wrapper) must come last so it
can override ListeningMind.AI defaults like sidebar-offset on .rpt-main.
"""

from pathlib import Path
from typing import List


# Ordered list of stylesheets per skill slug.
# path-opportunity reuses the customer-analysis card shell + adds
# path-opportunity.css (flow tree, path chip-chains, hub cards) last-but-one so
# it can lean on the shared component styles while overlay still wins.
SKILL_STYLES = {
    "path-opportunity": [
        "design-tokens.css",
        "report-shell.css",
        "audience-shared.css",
        "report-components.css",
        "customer-analysis.css",
        "path-opportunity.css",
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
