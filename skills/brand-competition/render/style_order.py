"""Stylesheet order for this skill's report slugs.

design-tokens.css first (CSS variables), overlay.css last (skill-only wrapper).
The concatenation itself lives in _core/render/inline_styles.py.

report-components.css is not listed: it only carries insight boxes, bar rows and
action cards, none of which this report uses.
"""

SKILL_STYLES = {
    "brand-competition": [
        "design-tokens.css",
        "report-shell.css",
        "audience-shared.css",
        "brand-competition.css",
        "overlay.css",
    ],
}
