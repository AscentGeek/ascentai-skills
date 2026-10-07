# Brand Competition · Category Map — execution procedure

Read this before Step 0 and run the steps in order. Do not skip.
`judging-rules.md` is the single source of truth for thresholds; `limits.md` holds the known
limits — skim it before you start collecting.

Every MCP call goes through the **2 steps** in `SKILL.md` (`mcp_cache.py lookup` → call → store).
That is not repeated at each step below.

## Step 0 — Collect inputs + create the working folder

**Ask before the first MCP call.** Going back later costs the credits twice. **Ask all of it at once.**

| Ask | Default | Where it lands |
| :---- | :---- | :---- |
| Brand name | (required) | `config.brand` |
| TARGET MARKET | `kr` | `gl` on every call |
| REPORT LANGUAGE | same as market | `--lang` on the renderer |
| Rivals that must be covered (max 10) | none | `watch_brands` |
| Categories that must be covered (max 10) | none | `watch_categories` |
| Official store URL | found with `web_search` | Step 2-c |

**"Tell me if there are none — I will proceed as is."** If there is no answer, or the user says
"you decide", **proceed on the defaults. You ask once.** Only if many categories mean several
turns, say so in one line — **never claim the environment prevents you from continuing.**

- **Specified rivals** are measured across **every** category in Step 5. Do not make the user pick.
- **Specified categories** go into the Step 2 candidates **unconditionally.** Keep them even with
  no evidence, and if there is no volume data **keep the row and mark it "specified, not listed".**
- Keep both **separate from automatic discovery** — the screen must show where each came from.

**Aliases go in `config.json`.** Fold product and line names into the parent brand, and fold in
common misspellings. A different brand sharing the same characters is removed with
`alias_exclude`. A one-character brand matches on token equality only.
**An alias adds to the brand name, it does not replace it** — narrowing is `alias_exclude`'s job.

```bash
SAFE_BRAND=$(echo "<BRAND>" | tr ' /\\:*?"<>|' '_')
WORKDIR="$PWD/tmp/reports/listeningmind-brand-competition-${SAFE_BRAND}-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$WORKDIR"/data/cat "$WORKDIR"/data/cep "$WORKDIR"/work
echo "working folder: $WORKDIR"
```

From here on, replace `{WORKDIR}` with that absolute path, and `{RUN}` means the same folder
(the scripts take it as their first argument).

## Step 1 — Explore the brand (2 calls)

```
intent_finder(keywords=["<BRAND>"], gl="<MARKET>", limit=1000, sort="volume_avg",
              volume_threshold=1, response_format="download_url",
              user_query="<the user's utterance, verbatim>")
path_finder(keyword="<BRAND>", gl="<MARKET>", limit=300, time_point="curr",
            user_query="<the user's utterance, verbatim>")
```

Save as `{WORKDIR}/data/cat/<BRAND>_brand_intent.json` and `_brand_path.json`.
**Warn if there are fewer than 100 related queries** — barely any category will come out.

> `user_query` goes in the MCP call but **never** in `mcp_cache.py --params` (see `SKILL.md`).

## Step 2 — Build the category list (LLM judgement)

From the **tail words** of the related queries ("shokz <u>bone conduction earphones</u>") and the
non-brand nodes of the brand journey, keep **product categories** only.

- Drop: own model names, "genuine", stores, after-sales, careers, price.
- **Do not promote an occasion or situation word to a category.** "traditional liquor gift set"
  is not a category — it is the same demand as the demand facet "for a gift".
- Homonyms go in `flag` (windbreaker = air-conditioner windbreak).
- **Merge `watch_categories` here.** Include them without evidence and tag `"src": "지정"`.
- Write `{WORKDIR}/work/curate.json`. Leave `comp` and `cep` empty at this step.

## Step 2-b — If there are more than 10 candidates, a human sets the scope

**10 or fewer: do not ask. Run them all.** Only above that, fetch the category-term volumes first
(Step 5 needs them anyway), show a table with sizes, and let the user choose.

```
keyword_info(keywords=[<all candidates>], data_type="ads_metrics", gl="<MARKET>")
```

**Do not cut to "the top N by volume", and do not suggest it.** The positions a brand actually
owns are usually small (`limits.md` §6). Tell the user to **mix large and small within each group.**

- "You decide" or "all of them" means **run them all.** Say up front how many turns it takes.
- **`watch_categories` are always included.**
- Chosen ones go to `curate.json`; the rest go to `work/candidates.json` with `chosen: false`.
  **Do not delete them** — the report has to say "12 of 32 candidates were studied".
- **A position that was not studied is not "none".**

## Step 2-c — Do we actually sell it? Read the official store (no MCP call)

The verdict alone cannot separate "Trailing" from "we do not sell that product". Right after the
categories are fixed, read the brand's **official store** with `web_fetch` and label each category.

| Label | Criterion |
| :-- | :-- |
| Selling | the store has a product (or a category menu) for it |
| Partly selling | there is a product, but in a different form from the category's mainstream (powder vs RTD shake) |
| Not sold | the category listing was read and there is no product |
| Unverified | could not confirm on the store — ask the user. **Do not conclude "not sold".** |

While reading, note the brand's **product line names** and **the category wording the product names
use** — Step 11's self-check needs both.

- Home, top categories and 2–4 sub-listing pages are usually enough. Do not judge from related
  queries alone — people search for things the brand does not sell in that market.
- Put `"presence": {"label","note","src"}` on each category in `curate.json` (evidence URL required).
- The report shows this under the map as "Category priority — starting where we have a product".
  **No badge goes on the map table itself.**

## Step 3 — Category related queries (1 call per category)

```
intent_finder(keywords=["<CATEGORY>"], gl="<MARKET>", limit=1000, sort="volume_avg",
              volume_threshold=1, response_format="download_url")
```

**Do not pick categories. Run them all at the same depth, serially.** Do not change `limit` inside
a run — a size difference reads as a verdict difference.

- **Always pass `volume_threshold=1`.** The default is **100**, so omitting it drops every related
  query under 100 — that is not "no filter". Small categories keep most of their branded queries
  below that line, and losing them throws off **the denominator and the share together**.
- **Do not batch seeds into one call.** `intent_finder`'s `limit` is a **total, not per seed.**
  Batching lets a high-volume category eat the cap and cuts a small one entirely. That trades
  **evidence for a few credits** — do not do it.
- **Exactly 1,000 results means the cap was hit.** Our own queries may have been pushed outside it,
  so write "related-query cap reached" in the report.
- **Do not call `path_finder` here.** Journeys come in Step 6-b, only for Unclaimed.
- **Do not estimate the size from `limit`** — it is only a ceiling. Fetch two or three and look.

## Step 4 — Label the rivals (LLM judgement)

Here it is decided from the **leading modifier** of the related queries alone. Journey-side
candidates are added in Step 6-b.

```bash
python3 {SKILL_DIR}/_shared/render/modifiers.py {RUN} <CATEGORY> ...
```

- Where the naming axis produces a verdict, **the modifier alone is enough.** Substitution matters
  where combined search is empty — that is the Unclaimed side.
- **Do not use a fixed brand dictionary as a gate** — a brand missing from the dictionary quietly
  becomes a demand-facet candidate.
- Drop: **retailers, platforms, channels.**

Fill `comp` in `curate.json`. **Do not pick demand facets yet.**

## Step 5 — Search volume: branded queries and the category term only

**Share of search is a share among brands** — the denominator is that category's **combined
branded query volume of our brand plus rivals.** Generic queries (reviews, price, forums) are not
in the denominator, so **they are not queried.** That is why Step 4 must finish first.

```bash
python3 {SKILL_DIR}/_shared/render/brandkw.py {RUN}   # → work/brandkw.json · brandkw_<i>.json (1,000 each)
```

Each batch also writes `brandkw_<i>.params.json` — **exactly the parameters to send.** Point
lookup, the `keyword_info` call, `fetch_dl.py` and store at that one file so a hand-copied
character cannot split the cache key.

```bash
# ① cache first
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup keyword_info \
  --params-file "{WORKDIR}/work/brandkw_<i>.params.json" --out "{WORKDIR}/data/cat/catvol_<i>.json"
```
```
# ② on a miss, call MCP with exactly what the params file contains
keyword_info(keywords=[...], gl="<MARKET>", data_type="ads_metrics", response_format="download_url")
```
```bash
# ③ fetch + verify + store, in one command
python3 {SKILL_DIR}/_shared/render/fetch_dl.py --url "<download_url>" \
  --sha256 <sha256> --items <item_count> \
  --out "{WORKDIR}/data/cat/catvol_<i>.json" \
  --tool keyword_info --params-file "{WORKDIR}/work/brandkw_<i>.params.json"
```

- The list = related queries **containing a brand name (aliases included)** + **the category term**
  (the term goes into the denominator of the branded share). Measured — 20 categories, 5,891
  related queries → 1,145 (19%), `keyword_info` 6 calls → 2.
- **Batch 1,000 per call.** `keyword_info` is billed **per call, not per keyword** — measured,
  `cost_detail.total_cost` is the same for 12 keywords as for 141. **Batching small only costs more.**
- If Step 6-b finds **a new brand**, add it to `config.extra_brands` and rerun
  `brandkw.py {RUN} --skip-done` — volumes already fetched drop out of the batches, so the same
  keyword is never bought twice. `brandkw.json` (the coverage baseline) stays complete.
- Save as `catvol_<i>.json` — `data/cat/*vol*.json` is what the judging and check scripts read.
- **Do not shrink the denominator to a top-N.** Billing is per call, so it saves nothing.
- **`check_run.py` blocks below 95% coverage** — measured against `brandkw.json`.
- Use **`ads_metrics` only**, and **`volume_total`** (12-month sum). A keyword missing from the
  response means no data — **not zero**.
- The number **differs from a QueryFinder topic total** (which uses all related queries as the
  denominator). State the definition in the report.

## Step 6 — Naming axis verdict (fixed Python rules)

```bash
python3 {SKILL_DIR}/_shared/render/judge.py {RUN}
```

| Verdict | Rule |
| :-- | :-- |
| Unclaimed | branded share < 10% **or** branded query volume < 1,000 a year |
| Leading / Trailing | 2x rule between our brand and the leading rival (independent of the denominator) |
| Contested | in between |

Branded share = branded query volume (deduplicated) ÷ (that volume + the category term's volume).
It asks "is this a category people choose by brand" — around 80% means the brand fight is the
market; a single digit means being first matters little.

## Step 6-b — Journeys, for Unclaimed only (1 call per category)

Call it **only for categories that came out Unclaimed.** Not for the rest.

```
path_finder(keyword="<CATEGORY>", gl="<MARKET>", limit=300, time_point="curr")
```
```bash
python3 {SKILL_DIR}/_shared/render/pathcand.py {RUN}   # frequent journey nodes → more rivals
python3 {SKILL_DIR}/_shared/render/judge.py    {RUN}   # rerun to fill the journey axis
```

If a new rival appears on the journeys, add it to `comp`, fetch volume **for that brand only**,
and rerun `judge.py`. **If nothing is Unclaimed, no journey call is made at all** — that is normal,
and the report records "journey axis not run (nothing Unclaimed)".

## Step 7 — Choose the deep-dive targets (a human chooses)

`judge.py` has already ranked the **deep-dive candidates**. Read that block and recommend **3–5**.

**Prefer the weak and the empty — Contested, then Trailing, then Unclaimed.** That is where the
value of acting is. **Leave Leading out of the default recommendation,** but **say so in one line** —
"the 2 Leading positions are places to defend, so I put them behind; tell me if you want them."
Someone who wants the defensive view has to be able to ask.

**Do not choose by top volume.** Mix so the groups are not lopsided.

**Do not recommend a category whose candidate pool is too thin.** `judge.py` marks those excluded —
under 30 modifiers you cannot pick 3 demand facets, so **the deep dive returns an empty table.**

- **If there is a broader term, recommend that instead.** `judge.py` finds it — a narrow variant's
  demand sits in the broader term.
- **If fewer than 3 are possible, do not block — hand it to the user** (`judge.py` warns): let them
  choose between "run the 2 that are possible" and "skip demand facets and stop at the map".
- **The exclusions appear in the report.** They must not read as "no opportunity".

**This is the second and last point where you ask a human. Do not render the report before they
choose** — a report with empty demand facets reads as finished. Render runs once, after the
demand-facet collection is complete.

## Step 8 — Demand facets of the chosen categories: label → select → collect

| | What happens | Who |
| :---- | :---- | :---- |
| 8-a | Is the modifier **a word that splits demand inside this category** — occasion, use, feature, form, grade | **LLM** |
| | Drop: gender, age, colour, model name, store, community, flavour, ingredient | |
| 8-b | Of the labelled facets, **the top 3 by volume**; unlisted ones excluded | **fixed rule** |

Write `deep: true` and `cep` into `curate.json` — **the code and the files keep the name `cep`**
(`data/cep/` · `cep_deep.py`). It is "demand facet" only on screen and in the docs.
One seed, **one call**, per facet.

```
path_finder(keyword="<FACET> <CATEGORY>", gl="<MARKET>", limit=300, time_point="curr")
```

**300 is a floor. Never lower it** — below it the gate floors bind, the bar quietly tightens and
only "on hold" grows (`limits.md` §6). If the volume is the problem, **cut the number of facets or
split the turns.**

- Save as `data/cep/<FACET> <CATEGORY>_path.json`.
- **Do not call `intent_finder`** — a facet seed is 3–4 words and returns almost nothing.
- **A demand facet is judged on the journey axis alone.** The combined search
  `<brand> <facet> <category>` barely exists — measured, **9 of 9** had no volume data in one run.
- **Split the turns here too.** `check_run.py` prints progress as `세부 수요 심층 경로 5/12`.
- Then fetch the facet volumes **in one batch** — `<facet> X`, `<brand> <facet> X`, and the brands
  found on the journeys.

## Step 9 — Demand facet verdicts

```bash
python3 {SKILL_DIR}/_shared/render/cep_deep.py {RUN}
```

**Order matters.** `judge.py` rewrites `judge.json`, so `cep_deep.py` runs after it.

## Step 9-b — Translate the search terms (only when MARKET language ≠ REPORT LANGUAGE)

The report shows search terms exactly as they are searched in the market. When the report language
differs from the market's, the reader cannot read them, so build the translations that back the
**"Translate keywords" toolbar button**. Skip this step when the two match — the button then does
not appear at all.

First extract only the terms that actually reach the screen:

```bash
python3 {SKILL_DIR}/_shared/render/kw_extract.py {RUN} --out "{WORKDIR}/kw_to_translate.json"
```

Read the `keywords` array and translate **every** entry into REPORT LANGUAGE, saving
`{WORKDIR}/lm_keyword_tr.json` as `{"original": "translation", ...}`.

- Use the **original string as the key**, byte for byte. A key that does not match leaves that
  term untranslated — silently.
- Do **not** add terms that are not in the list, and do not drop any.
- **Brand and product names take the form commonly used in REPORT LANGUAGE**
  (`진로` → `Jinro` / `ジンロ`). **If there is no common form, keep the original** — do not
  invent a romanisation.
- These are search terms, not sentences. Keep them short, in the shape someone would type.
- Translate only — never append a gloss or an explanation.

**Our own brand name is not in the list and is not translated.** It is the report's subject and the
same string goes into the cover, the `<title>` and several `data-` attributes, where the two-copy
span cannot live — translating it would split its spelling across one report.

`title=` tooltips keep the original for the same reason: a native browser tooltip prints tags as
literal text, so the toggle cannot reach inside one. The bubble map's SVG labels and the raw
related-query chips keep the original too — `references/limits.md` §13 lists all five exceptions.

## Step 10 — Render

```bash
python3 {SKILL_DIR}/_shared/render/check_run.py {RUN}
python3 {SKILL_DIR}/_shared/render/render_report.py \
    --skill brand-competition --run {RUN} \
    --gl <MARKET> --lang <REPORT_LANGUAGE> --date <YYYY-MM-DD> \
    --out "{WORKDIR}/brand-competition-report.html"
# If you did Step 9-b, append --translations "{WORKDIR}/lm_keyword_tr.json"
```

**If `check_run.py` prints a single `✗`, do not run the renderer.** If it cannot be filled,
**stop there and say what is missing** — a half-empty report is the worst outcome.

The toolbar at the top right switches **Dashboard / A4**, and printing goes out as A4.
**The synthesis section is a draft** — a human polishes it before it is presented.

## Step 11 — Final message: results + self-check + suggested fixes

After the report is written, the message must contain all three. **Suggest only — do not fix**
(fixing costs more calls, and the scope is the user's call).

1. **Key results** — where to defend, where we are fighting, the real weaknesses, what to claim
   first, adjacent markets in a different form.
2. **Self-check** — look at the run's data and write only what applies.
   - **A market split by synonyms** — if two wordings of the same market get different verdicts,
     also give the share recomputed on the combined branded queries.
   - **Category name vs the brand's own wording** — if the official store's product names use a
     different word from the category term, say that category's verdict is low-confidence.
   - **A missing product line name** — if related queries use the line name without the brand name,
     say our side is undercounted.
   - **Related-query cap reached** (1,000) · **thin sample** (branded volume under 10,000 a year).
   - **A missing brand-position category** — if a position the brand's own material pushes is not
     among the candidates, say so. Candidates only come from `<brand> X` queries, so an intended
     position gets missed.
3. **Suggested fixes** — one line each: what to change (add an alias, merge categories, swap the
   category term, add a category) and an estimate of the extra calls. If the user picks one,
   apply it on the next turn.

Write the message in REPORT LANGUAGE, and give the file path:

```
✅ Category map created: {WORKDIR}/brand-competition-report.html
Open it in a browser for the map, the demand-facet deep dive and the synthesis in Dashboard or
A4 view; Cmd+P saves it as an A4 PDF.
Open it on macOS: open {WORKDIR}/brand-competition-report.html
```

## Credits

One call = one credit. **Counted per call, not per keyword.**

```
2 brand exploration · N category related queries · v volume batches
B Unclaimed journeys (can be 0) · C demand-facet deep dives · 1 facet volumes
```

**A category costs 1 call.** Journeys attach only to Unclaimed. Measured, up to the map —
28 categories 35 credits · 8 categories 15 · 6 categories 16 · 5 categories 15.

Related queries are one call per category (Step 3); volumes take **branded queries only**, batched
1,000 at a time (Step 5). Related queries are not batched — the cap is a total, so a small category
gets cut.

## Do not

- **Do not branch on brand attributes.** Do not drop the naming axis because a brand is B2B. If
  combined search is empty, the ordinary rule produces Unclaimed, and if the journey comes to us
  it becomes Emerging lead.
- **Do not write an unlisted value as 0%.** `-` is "measured, nothing there"; `·` is "not measured".
- **Do not save a summarised, excerpted or restructured response.** "only the part used in the
  verdict", "keep just the counts", "only the rows ending in …" — all of it. A hand-picked subset
  **becomes the verdict badge.** If you cannot move it, do not shrink the run — **stop and say so.**
- **Do not drop categories because of volume.** Running a few makes it a sample, not a map, and the
  missing positions read as "none". Narrow the scope through Step 2-b, by **a human**, with the
  exclusion list kept.
- **Do not abandon a run on an estimate of the size.** Fetch a few for real, and if it still does not
  fit, **split the turns.** Asking to change the environment is the last resort.
- **Do not make hand-copying the default.** If there is a download URL use `fetch_dl.py`; if the host
  saved the file, `cp` the path. Do not tell the user "in this environment I have to copy it myself" —
  it is usually not true.
- **Do not pull response contents into context and rewrite them.** Files are passed **by path only.**
- **Do not skip the cache step.** Buying the same `(tool + parameters)` twice doubles the credits.
- **Do not put a verdict badge on a demand facet.** Badging something that was not measured reads as
  a verdict. The facet table is a demand list.
- **Do not move a journey-axis value into a naming-axis cell.** "Trailing" means 2x behind on the
  naming axis.
- **Do not attach a journey tag where the naming axis produced a verdict** — measured, 40% disagree.
- **Do not hide the denominator.** Share of search is divided by the category's combined branded
  query volume of our brand plus rivals.
- **Do not put total brand volume in the combined-volume column.** Reference only, in its own column.
- **Do not put a homonym in the brand's own aliases** — keep it in `own_ambiguous`.
- **Do not describe a trend from `volume_trend`.** The definition cannot be reversed out.
- **Do not call the REST API directly.** This is the MCP edition.
- **Do not hand-write HTML.** The output comes from `render_report.py` only. If you cannot run it,
  stop there and write down what is missing.
- **Do not explain the construction on screen.** No "share of search = …" caption under a table.
  What stays is the **legend** and the **interpretation**; definitions live in column `title` tooltips.
- **Do not put development notes in the report.** "What we could not measure" belongs there;
  "which design we chose" does not. **Never hardcode a run-specific sentence into the renderer** —
  it will print on another brand's run.
- **Do not put the facet count on the map.** Use the brand's related-query and journey counts instead.
- **Do not emit a per-category card in the synthesis.** That is the map rewritten as prose.

## Verify

If you changed a script, run both. Both must print `0 checks failed`.

```bash
python3 {SKILL_DIR}/_shared/render/judge.py         --selftest
python3 {SKILL_DIR}/_shared/render/render_report.py --selftest
```
