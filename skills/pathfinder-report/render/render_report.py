#!/usr/bin/env python3
"""Render a ListeningMind.AI-style HTML report from the path-opportunity
pipeline JSON outputs.

Usage (WORKDIR = {project}/tmp/reports/listeningmind-path-opportunity-{seed}-{timestamp}/):
    python3 _shared/render/render_report.py \\
        --skill path-opportunity \\
        --paths   "$WORKDIR/lm_paths.json" \\
        --actions "$WORKDIR/lm_actions.json" \\
        --meta    "$WORKDIR/lm_path_result.json" \\
        --category "냉장고" --gl kr --date 2026-07-22 \\
        --out "$WORKDIR/path-opportunity-report.html"

Output is a single self-contained HTML file — all CSS inlined, Google Fonts CDN
the only (optional) external dependency, no Chart.js/JS libraries. The report is
the customer-analysis card shell (cover + two tabs + A4 print view) with a
journey flow tree + path cards + hub cards. Standard library only.
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import components as ca            # shared shell builders (t, purpose_box, actions panel)  # noqa: E402
import components_path as cp       # path-specific builders (flow tree, path/hub cards)  # noqa: E402
from inline_styles import inline_styles  # noqa: E402


PKG_ROOT = HERE.parent.parent
STYLES_DIR = PKG_ROOT / "_shared" / "styles"
LABELS_DIR = PKG_ROOT / "_shared" / "labels"
TEMPLATES_DIR = PKG_ROOT / "_shared" / "templates"


FONT_HREF = {
    "kr": "https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;900&display=swap",
    "jp": "https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;600;700;900&display=swap",
    "us": "https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;500;600;700;900&display=swap",
}
HTML_LANG = {"kr": "ko", "jp": "ja", "us": "en"}
LOCALE_FONT_OVERRIDE = {
    "kr": "",
    "jp": "html { --font-family: 'Noto Sans JP', -apple-system, BlinkMacSystemFont, Sans-serif; }",
    "us": "html { --font-family: 'Noto Sans', -apple-system, BlinkMacSystemFont, Sans-serif; }",
}
TOOLBAR_DASH_BTN = {"kr": "대시보드", "jp": "ダッシュボード", "us": "Dashboard"}
TOOLBAR_PRINT_BTN = {"kr": "인쇄", "jp": "印刷", "us": "Print"}


# Tab / view-toggle script (no charts). Also drives the volume-badge tooltip on
# any `.persona-card__volbadge`; path/hub summary badges use their own static
# classes and are ignored by this handler.
BASE_SCRIPT = r"""
(function(){
  var tabs = document.querySelectorAll('.dash-tab');
  var panels = document.querySelectorAll('.dash-tab-panel');
  tabs.forEach(function(tab){
    tab.addEventListener('click', function(){
      var idx = tab.getAttribute('data-panel');
      tabs.forEach(function(t){
        var on = t.getAttribute('data-panel') === idx;
        t.classList.toggle('active', on);
        t.setAttribute('aria-selected', on ? 'true' : 'false');
      });
      panels.forEach(function(p){
        p.classList.toggle('active', p.getAttribute('data-panel') === idx);
      });
    });
  });
  var viewBtns = document.querySelectorAll('.mini-toolbar__view button');
  viewBtns.forEach(function(btn){
    btn.addEventListener('click', function(){
      var mode = btn.getAttribute('data-view');
      document.body.classList.toggle('view-mode-dash', mode === 'dash');
      document.body.classList.toggle('view-mode-a4',   mode === 'a4');
      viewBtns.forEach(function(b){ b.classList.toggle('active', b === btn); });
    });
  });
})();
"""


def _load_labels(skill: str, gl: str) -> dict:
    return json.loads((LABELS_DIR / f"{skill}.{gl}.json").read_text(encoding="utf-8"))


def _common_blocks(skill: str, gl: str, category: str, labels: dict, *, title_key: str, dash_tab_key: str) -> dict:
    inlined_css = inline_styles(STYLES_DIR, skill)
    if LOCALE_FONT_OVERRIDE.get(gl):
        inlined_css += "\n\n/* === locale font override === */\n" + LOCALE_FONT_OVERRIDE[gl]
    return {
        "{{LANG}}": HTML_LANG.get(gl, "en"),
        "{{FONT_HREF}}": FONT_HREF.get(gl, FONT_HREF["us"]),
        "{{CATEGORY}}": category,
        "{{REPORT_TITLE}}": ca.t(labels, title_key),
        "{{TOOLBAR_DASH_LABEL}}": ca.t(labels, dash_tab_key),
        "{{TOOLBAR_A4_LABEL}}": "A4",
        "{{TOOLBAR_DASH_BTN}}": TOOLBAR_DASH_BTN.get(gl, "Dashboard"),
        "{{TOOLBAR_PRINT_BTN}}": TOOLBAR_PRINT_BTN.get(gl, "Print"),
        "{{INLINED_CSS}}": inlined_css,
    }


def _apply(template: str, blocks: dict) -> str:
    # Single-pass substitution: re.sub's replacement text is never re-scanned,
    # so an LLM/keyword field containing a literal "{{TOKEN}}" can't be expanded
    # a second time.
    pattern = re.compile("|".join(re.escape(k) for k in blocks))
    return pattern.sub(lambda m: blocks[m.group(0)], template)


def render_path(args) -> str:
    gl = args.gl.lower()
    paths_doc = json.loads(Path(args.paths).read_text(encoding="utf-8"))
    paths = paths_doc.get("paths", [])
    hubs = paths_doc.get("hubs", [])
    overview = paths_doc.get("overview") or ""
    actions = json.loads(Path(args.actions).read_text(encoding="utf-8")) if args.actions else {}
    meta = json.loads(Path(args.meta).read_text(encoding="utf-8")) if args.meta else {}
    flow_tree = meta.get("flowTree", [])

    meta_view = {
        "date": args.date,
        "pathCount": meta.get("pathCount", 0),
        "hubCount": meta.get("hubCount", len(hubs)),
        "nodeCount": meta.get("nodeCount", 0),
    }

    labels = _load_labels("path-opportunity", gl)
    gl_label = ca.t(labels, f"country.{gl.upper()}")
    market_label = ca.t(labels, f"report.marketLabel.{gl.upper()}")

    # {{CATEGORY}} is injected raw into <title>, so escape it here; the cp/ca
    # builders html-escape category internally, so they receive it unescaped.
    blocks = _common_blocks(
        "path-opportunity", gl, html.escape(args.category), labels,
        title_key="agent.pathAnalysis.name",
        dash_tab_key="pathAnalysis.dash.journeyTab",
    )
    blocks.update({
        "{{DASH_COVER}}": cp.dash_cover_html(meta_view, args.category, gl_label, market_label, labels, overview=overview),
        "{{DASH_TABS}}": cp.dash_tabs_html(labels),
        "{{DASH_PANEL_JOURNEY}}": cp.dash_panel_journey_html(paths, hubs, flow_tree, args.category, labels),
        "{{DASH_PANEL_ACTIONS}}": ca.dash_panel_actions_html(actions, labels),
        "{{A4_COVER_PAGE}}": cp.a4_cover_page_html(meta_view, args.category, labels),
        "{{A4_BODY_PAGE}}": cp.a4_body_page_html(paths, hubs, flow_tree, actions, args.category, market_label, labels, overview=overview),
        "{{INLINE_SCRIPT}}": BASE_SCRIPT,
    })
    template = (TEMPLATES_DIR / "path-opportunity.html").read_text(encoding="utf-8")
    return _apply(template, blocks)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render ListeningMind.AI-style path-opportunity HTML report.")
    parser.add_argument("--skill", required=True, choices=["path-opportunity"])
    parser.add_argument("--category", required=True)
    parser.add_argument("--gl", required=True, choices=["kr"])
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--out", required=True, help="Output HTML path")
    parser.add_argument("--paths", help="path-opportunity: lm_paths.json path")
    parser.add_argument("--actions", help="path-opportunity: lm_actions.json path")
    parser.add_argument("--meta", help="path-opportunity: lm_path_result.json path")
    args = parser.parse_args()

    for k in ("paths", "meta"):
        if not getattr(args, k):
            parser.error(f"path-opportunity requires --{k}")
    html_str = render_path(args)

    Path(args.out).write_text(html_str, encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
