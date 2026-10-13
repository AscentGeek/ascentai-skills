# Screen spec · config.json

## config.json

```json
{
  "brand": "<brand>",
  "own": ["<brand>", "<romanised>", "<product line>", "<common misspelling>"],
  "own_ambiguous": ["<alias that also means something else>"],
  "alias": { "<rival>": ["<rival>", "<romanised>"] },
  "self_keywords": ["<company name>", "<service name>"]
}
```

| Key | Required | Meaning |
| :---- | :---- | :---- |
| `brand` | ● | one spelling of our brand. The brand name used in share of search |
| `own` | ● | every alias of ours. **Used for journey matching** — adding model names sharpens the journey axis |
| `own_ambiguous` | | aliases that are homonyms and must not go in `own`. Recorded, not used |
| `alias` | | rival spelling variants, product lines and common misspellings. **Adds to the brand name, does not replace it** |
| `alias_exclude` | | removes a different brand that shares the same characters |
| `self_keywords` | | keywords summed into total brand volume. If present, a reference column appears |
| `gl` | | market. `kr` · `jp` · `us`. Asked at Step 0, default `kr` |
| `extra_brands` | | brands found during the run but absent from `curate.comp` |
| `watch_brands` | | rivals the user specified (max 10). Measured in **every** category and never cut from the table |
| `watch_categories` | | categories the user specified (max 10). Added to Step 2 candidates without evidence; **the row is kept** even with no volume data |

## work/candidates.json — scope (only when there are more than 10 candidates)

```json
{"<category A>": {"vol": 1830400, "chosen": true},
 "<category B>": {"vol": 61200, "chosen": false}}
```

The result of the user's choice at Step 2-b. **Excluded candidates are not deleted** — the report's
Limits section carries "only M of N candidates were studied" and the exclusion list. Without this
file that line does not appear (a run where everything was studied).

## work/curate.json — the only file the LLM writes

```json
{
  "_note": "one line on why these were picked",
  "<category>": {
    "group": "<group>",
    "comp": ["<rival>", "<rival>"],
    "cep": ["<facet>", "<facet>"],
    "presence": {"label": "참전", "note": "<what was seen>", "src": "<evidence URL>"},
    "flag": "homonyms go here",
    "src": "지정 — only on rows that came from config.watch_categories"
  }
}
```

`group` is the map's group column and sets the sort order. `comp` is picked from **two sources** —
the leading modifiers of the related queries and the frequent nodes of the journeys. A row with
`src: "지정"` gets a **specified** badge next to its name on the map, and with no volume it stays as
`-` (measured, nothing there) or `·` (not measured) — never 0.

`presence.label` is one of `참전` · `부분 참전` · `미판매` · `미확인`. These four are **internal
values**, like the verdicts; only their display is translated.

## Screen frame

The report holds **two views** in one file, switched from the mini toolbar at the top right.

| View | What | Classes |
| :-- | :-- | :-- |
| **Dashboard** (default) | cover block + cards stacked · sorting, row expansion and tabs all work | `view-dash` · `dash-cover-block` · `dash-card` |
| **A4** | one page per section · for print and PDF | `view-a4` · `rpt-page` |

The cover block is a gradient (brand name · collection conditions) plus the "What we looked at"
summary box. Each section is one `dash-card`, with a title and a badge (S0 and so on) in its head.

**A4 is not a copy of the screen — it is the reading edition.**

- What the map rows reveal on click is laid out after the table as a **"Evidence by category"** section.
- Instead of the volume/share toggle, **both are printed in one cell** ("7,738 · 56.9%").
- Sorting, paging, "show all brands" and tooltips are removed. They cannot be clicked on paper.
- The rival brand column block is folded — 21 columns do not fit a 714px page width.
- **No `id` survives into the A4 copy.** Duplicated ids make the JS bind to the first copy only.

Design tokens come from the **LM design system**: `design-tokens.css` · `report-shell.css` ·
`overlay.css` · `audience-shared.css` are byte copies of `_core/styles/` and **are not edited here.**
There is no dark mode — the four sibling reports have none.

**The scrollbars are made visible on purpose.** `design-tokens.css` paints every scrollbar
transparent and only reveals it under `.is-scrolling`, a class the ListeningMind.AI web app's JS
adds. A standalone HTML file has no such JS, so the handle disappears entirely — a trackpad user
swipes past it, but a mouse user has no way to move a wide table sideways. `brand-competition.css`
restores it with `::-webkit-scrollbar`. Note that giving `scrollbar-color`/`scrollbar-width` a value
makes Chrome ignore those pseudo-elements and fall back to the auto-hiding macOS overlay scrollbar,
so both are set back to `auto` and Firefox is handled by `@supports not selector(::-webkit-scrollbar)`.

## Sections

### Cover · in-one-page figure · register

The cover's big title is the **skill name** (「Brand competition analysis」), the brand goes
underneath, and the top line is 「<skill name> · <market>」 from `config.gl`. The A4 cover is the same.
Korean prose is written in the polite register (…합니다).

The in-one-page figure is a **network graph**: the brand at the hub, one circle per category around it.

- Circle area ∝ that category's **all-brand volume** (`sos.denom` = ours + rivals' branded queries, 12 months)
- The fill rising from the bottom = **our share of search** = our branded volume ÷ all-brand volume
- Text in the circle = 「share%」 and 「our volume / all-brand volume」. Below radius 46 the text drops under the circle
- Colour = the same palette the pie used, assigned in order of our volume
- A category with no branded volume gets no circle; its name is listed under the figure
- The fill is drawn as a circular **segment path, not a clipPath** — the A4 copy strips `id`, which
  would break a `url(#…)` reference
- Layout treats 「the larger of circle and label」 as the radius and pushes overlaps apart, alternating
  large and small circles around the ring
- **Extremes and node count** — the largest radius is 150 at 7 nodes and shrinks as `150·√(7/N)`
  (floor 70). If area-proportional drawing would squash 40% or more of the circles (at least two)
  below radius 27, it switches to a **log scale** and says so in the caption. Do not switch on a plain
  max/min ratio — an ordinary run would then always be log. The figures inside a circle are the exact
  values; size only gives a sense of scale
- **Interaction** — in the dashboard the layout continues as a physics layout from the same
  coordinates: drag a node or the hub, drag the background to pan, **mouse wheel zooms while over the
  graph** (cursor-anchored, 0.2–5x, and page scroll is blocked only over the graph), ＋/－ buttons and
  re-layout. **A4 and print use the static layout computed on the server.**
- This figure **replaces** the old 「our branded volume by category」 pie and the 「category demand by
  verdict」 bars. Neither is emitted any more.

| | Section | What it answers |
| :---- | :---- | :---- |
| — | In one page | one-line insight · the brand-to-category network graph · opportunity quadrant bubble map |
| S0 | Category map | group · category · category term volume · branded volume · verdict · 1st/2nd · ours (in related queries · on journeys · volume · share) · rival brand columns. **Volume view / share view toggle.** Expanding a row shows per-brand share bars, the reason for the verdict, the journey axis and a demand-facet note |
| S0-p | Category priority | only when `presence` exists — regroups the map against what we actually sell |
| S0-d | Demand facet deep dive | a facet × brand matrix plus a one-line summary, per chosen category |
| S1 | Synthesis | **only what a single row cannot show.** Sections with no value are omitted |
| — | Limits | what this run could not measure |

**Do not add or remove cells arbitrarily, and do not emit a section that is not in this table.**

### Verdict colours

The four verdicts take LM system colours through tokens, so changing the design system changes them
in one place.

| Verdict | Token | Resolves to | Shape |
| :---- | :---- | :---- | :---- |
| Leading | `--j-own` → `--success-main` | `#1ABC9C` | filled |
| Emerging lead | `--j-own` | `#1ABC9C` | dashed border · pale fill |
| Contested | `--j-cmp` → `--warning-main` | `#FBBD08` | filled |
| Trailing | `--j-low` → `--error-main` | `#FF247A` | filled |
| Unclaimed | `--j-emp` → `--gray-400` | `#AAB4C4` | filled |

### Demand facet bars (the measurement axis)

"Named · on the journey · absent" is **not a verdict — it is what was measured.** So it does not use
the verdict palette; using it would make "named" read as Leading. The families are kept apart and
**lightness carries strong signal → none**.

| Cell | Token | Resolves to |
| :---- | :---- | :---- |
| Named | `--m-name` | `--brand-violet-darker` |
| On the journey | `--m-path` | violet-main mixed 45% into white |
| Absent | `--m-none` | `--gray-200` |

The three must stay a dark → mid → light ramp. An earlier attempt used `violet-lightest` for the
middle step, which collided in lightness with `gray-200` and made "on the journey" and "absent"
look identical.

Text colour is the matching dark tone (`--j-*-t`). `build_report.py`'s selftest checks that the
measurement axis never borrows a verdict colour.

**Do not explain the construction.** No caption under a table saying "share of search = …" or
"the verdict is the 2x rule …". What stays on screen is the **legend** (what an axis, colour or
symbol means) and the **interpretation** (so what do we do). If a definition is unavoidable, put it
in the column heading's `title` tooltip, where it does not interrupt the reading.

**No development notes in the report.** "What we could not measure" (the Limits section) is what a
customer needs; "which design we chose" is not. Tools we did not use, version history, other runs
and the rationale for internal rules all come out. **Never hardcode a run-specific sentence into
the renderer** — given the right conditions it prints on another brand's run.

### Synthesis — 4 sections always, 4 conditional

| | Section | Condition |
| :---- | :---- | :---- |
| ① | Where to defend and where to take | always |
| ② | Where the category verdict and its facets disagree | always (if none, say so) |
| ③ | What this run judged on | always |
| ④ | What we could not measure | always |
| ⑤ | Rivals you keep meeting | a brand leads in 2 or more categories |
| ⑥ | By group | 2 or more groups hold 3 or more categories |
| ⑦ | Where naming and journey disagree | there is a disagreement |
| ⑧ | Watched brands | `watch_brands` is set |

Specified categories (`watch_categories`) get no section of their own — they are badged on the S0 row.

**No per-category card.** That is the S0 row rewritten as prose, with no reason to read it.
Measured section counts across four runs — 8 · 5 · 5 · 4.

### Bubble map

Horizontal = category volume (log) · vertical = our share ÷ the leader's share · circle size = our
volume · colour = verdict. **If no category reaches half the leader's share it is not drawn**, and
that fact is stated in one line.

### S1 colour rule

Only the top two ranks within a row are tinted — **1st at 38% accent tint, 2nd at 12%, 3rd and below
untinted.** Missing values and 0 are excluded from ranking. Ties use standard competition ranking.
If the 1st or 2nd is not on the horizontal axis, it is written in the rightmost "top 2 off-table"
cell in the same colour.

**Colours are not compared across columns or across rows.**

The horizontal axis is ours + specified brands + automatically discovered rivals that appeared in
two or more categories, capped at **12 columns**. Specified brands outrank the cap and carry a
badge. The values are absolute, so a row does not add to 100%.

## Print · sharing

`report.html` is a single file (no external assets; only the font comes from Google Fonts, and a
blocked font merely falls back to system fonts).

Deliver it by telling the user the path — this skill does not push the body into chat.

**Printing goes out as the A4 view.** Whichever view is on screen, `@media print` emits the A4
pages. Each evidence block and card carries `break-inside:avoid`, so one category is never split
across two pages.
