# Known limits · check these every run

**Skim this before you collect.** Every figure below is measured — from four example runs
(28 · 9 · 6 · 5 categories).

---

## 1. The tools

- **Concurrency is 1.** Calling MCP tools in parallel fails with
  `Too Many Requests: Your API key's concurrent request limit is 1`. Run them serially.
- `intent_finder` returns only queries that **contain the seed**. If the seed is not a word that
  forms compounds, you get modifier variants and nothing else.
- `intent_finder`'s `volume_threshold` **defaults to 100.** Without an explicit `1` the tail is cut.
- A `path_finder` journey's first node may differ from the seed. **Count only journeys that start
  with the seed.**

## 2. Search volume

- Use **`volume_total`** (12-month sum). `volume_avg` moves with the season.
- **Do not describe a trend from `volume_trend`.** Its definition cannot be reversed out.
- **Use only rows that exactly match the keyword you asked for.** The volume data normalises
  spacing, so notation-variant rows come back alongside, with the same Google value as the original
  — adding them double counts (measured: a brand's name in two spellings, 172,500 and 16,427,
  arrived together).
- **A keyword missing from the response = no volume data.** Not zero.

> **What "not listed" means.** `keyword_info` returns **only the keywords it has a record for.**
> A keyword that does not come back means ListeningMind holds no volume for that query — in
> practice, that it is searched too little to meet the collection threshold.
> **It is indistinguishable from "searched zero times", so it is never written as 0%.**
> A brand that genuinely sells running earphones can still be missing from "<brand> running
> earphones" — people simply do not search that compound, which is not the same as there being no
> demand for running earphones.
>
> Three states are printed distinctly — `-` measured, nothing there · `·` not measured · `0%` truly
> zero. **Never use the word "DB" on a customer screen.** Write "no search-volume data".

- `keyword_info` is billed **per call, not per keyword.** One call takes up to **1,000** keywords.
  Measured — requests of 12 · 22 · 60 · 110 · 141 keywords all cost `total_cost` **1**; on a
  different account, 10 and 600 keywords both cost **2**. The value differs by account and date,
  but it is **fixed regardless of keyword count** either way. **Batch 1,000 per call** — splitting
  small pays the same price several times over.

  > The in-house DaaS REST edition bills **10 credits per keyword**. **This is the MCP edition.**
  > Mixing the two throws a cost estimate off by three orders of magnitude.

- **`intent_finder` responses carry no volume** — `data` is an array of keyword strings only, and
  just the ordering is by `volume_avg` (measured). The denominator cannot come from `intent_finder`.
- **A file fetched from `download_url` is a bare list.** `fetch_dl.py` wraps it into
  `{"data": [...]}` at the entrance, because the judging, check and render scripts read `["data"]`
  in 14 places. Fetching it with `curl` dies there.

## 3. Brands with thin data

### No combined query exists

How often `<brand> <category>` is in the volume data tracks the brand's size.

```
large consumer brand   28/28
mid-size brand           9/9
niche brand              5/6      ← one category missing
B2B tool                 0/5
```

Facet combinations (3–4 words) are worse — 57% · 20% · 17% · 0% across the same four runs.
**That is why a facet's real verdict is the journey** (`judging-rules.md` §3).

**Do not branch on brand attributes.** Do not drop the naming axis because a brand is B2B. If every
combination is empty, the ordinary rule produces Unclaimed, and where the journey comes to us it
becomes Emerging lead.

### Too few brand related queries

Under **100** brand related queries, categories barely surface. Measured, one B2B run had only 27,
and its brand journeys ended in its own product names, so **it produced no category at all**.

When that happens, say so in the report and **take the categories from the user**
(`config.watch_categories`). If they came from elsewhere, **say on screen that they did.**

### Specified brands are measured in every category

Do not make the user pick categories for a rival they specified. Measured — a specified rival had
volume in **13 of 28** categories, and its largest position was not the expected one (6,660 · 1.9%)
but a different category entirely (167,470 · 17.8%). Taking only the top few per category hides the
picture of one brand spanning many.

**Specified categories are different.** They go in even without evidence — measured, one category
sat at rank **1,346** in the brand's related queries and automatic discovery never found it.
With no volume data, **keep the row and mark it "specified, not listed".**

## 4. Homonyms

- **Categories** — a word can mean two products at once, and the category term's volume mixes both.
  Record it in `flag` in `curate.json`.
- **Our own aliases** — an alias may be a famous unrelated thing (a telescope, a car model). Putting
  it in `config.own` poisons journey matching. Record it in `own_ambiguous` instead.
- Build an exclusion list first for abbreviations of three characters or fewer.
- **Substring matching created phantom volume** (corrected 2026-10-02 · the rule itself lives in
  `judging-rules.md` §1). While matching on a space-stripped substring — in one run a brand token
  of 1,336 was **entirely false positives**, picked up from the middle of two longer words; by the
  same mechanism one brand swallowed another that contained it. In another run 12,390 from a
  different brand's query, plus two more, were credited to the wrong brands — **17,962 of phantom
  volume in the numerator.** The word-boundary rule loses only forms written flush against a
  preceding word, and there were none in either run's real data.
  The rule lives in **three files** — `judge.py` · `cep_deep.py` · `brandkw.py`. Fix one and the
  query list (the denominator) and the verdict look at different sets.

## 5. Finding rivals

- **Leading modifiers alone cannot find a substitute-relationship brand.** People do not search
  "<tool> search volume lookup". In Unclaimed categories, where combined search is empty, look at
  the frequent journey nodes too (Step 6-b). Brands actually found that way include several
  category leaders that never appeared as a modifier.
- **Using a fixed brand dictionary as a gate lets a brand outside the dictionary quietly become a
  demand-facet candidate.** Measured, romanised rival spellings, unrelated manufacturers and even
  **our own aliases** leaked into the facet candidates.
- Retailers, platforms and channels are not rivals. That said, one retailer's name appeared 106
  times on the journeys — **say in the report that it was excluded.**
- **Where the naming axis produces a verdict, modifiers are enough.** Measured, in all 31 such
  categories the leading rival was present among the modifiers. That is why journeys are fetched
  for Unclaimed only.

## 6. Where the verdict wobbles

### `path_finder` limit 300 is a floor

The gates are `max(6, 2% of the journeys received)` and `max(15, 5%)`. **The proportional term and
the floor term meet exactly at 300.** Below 300 the floors bind and the bar quietly tightens.

| Journeys | Floor | Hold gate |
| :---- | :---- | :---- |
| 1,000 | 20 (2.0%) | 50 (5.0%) |
| 300 | 6 (2.0%) | 15 (**5.0%**) ← as designed |
| 150 | 6 (4.0%) | 15 (10.0%) |
| 100 | 6 (6.0%) | 15 (**15.0%**) |

When the volume is the problem, the things to adjust are **the number of facets** and **splitting
the turns** — not `limit`.

### Do not mix limits inside one run

A difference in response size reads as a difference in signal. The defaults are `intent_finder`
1,000 and `path_finder` 300, and they do not change inside a run. That is different from a category
genuinely having little listed — 74 and 66 related queries are normal and are recorded as they are.

### How much do verdicts change at 300

The four example runs' 1,000-journey responses were truncated to the first 300 and rejudged.

| | Absolute gates | Proportional gates (2% · 5%) |
| :---- | :---- | :---- |
| Category journey axis changed | 13 / 48 | **6 / 48** |
| Facet journey axis changed | 9 / 46 | 10 / 46 |

The remaining 6 are only two kinds — **wobble near the 2x boundary** (one was a ratio of 2.06 at
1,000) and **a genuinely thin sample falling to "on hold"** (367 → 8 journeys). The second is not a
wrong answer; it is writing down that we do not know.

**Facets are less stable because their journey sample is smaller.** At 300, read facet verdicts
more carefully.

### Choosing deep-dive targets by volume misses the places we have won

The categories a brand actually owns are usually small. Where they are large, others are already in.

| | Volume rank | Verdict |
| :---- | :---- | :---- |
| Category A | **23rd of 28** | Leading |
| Category B | **24th of 28** | Leading |

Those two were the only places that brand led, and both sit in the bottom five. **Cutting to a
top N sees none of them.** The same applies to the deep-dive targets (Step 7) and the scope (Step 2-b).

### Deep-dive targets: weak first, thin candidate pools excluded

**The priority order is Contested, Trailing, Unclaimed.** That is where the value of acting is —
"what I am weak at, what I do not have at all" changes budgets and behaviour. Leading is left out
of the default recommendation but **named in one line, not hidden.**

**But "leaving Leading out reduces empty results" does not hold.** Measured candidate pools by verdict:

| Verdict | Count | Related queries (median) | Modifier candidates (median) |
| :---- | :---- | :---- | :---- |
| Leading | 4 | 572 | **226** |
| Contested | 16 | 1,000 | 596 |
| Trailing | 15 | 1,000 | 518 |
| **Unclaimed** | 10 | **290** | **116** |

**Unclaimed is emptier than Leading.** Five of the eight thinnest categories are Unclaimed; two are
Leading. The cause of an empty result is not the verdict label — it is **the category being narrow.**

So the filter is **the sample size** — under **30** modifier candidates you cannot pick 3 facets and
the deep dive returns an empty table. Measured, 1 of 17 deep dives failed, and it had **9** modifiers
(all 16 successes had 88 or more).

- **If a broader term exists, recommend it.** A narrow variant's demand sits in the broader term
  (4 modifiers vs 212). `judge.py` finds it.
- **If fewer than 3 are possible, do not block — give the user the choice.**
- **The exclusion appears in the report's Limits section** — not "no opportunity" but "this axis
  cannot measure it".

## 7. Scope — when there are more than 10

Category counts vary widely by brand (5 to 32 measured). **At 10 or fewer, do not ask — run them all.**
Above that, a human decides at Step 2-b.

- **The agent narrowing is forbidden; a human narrowing is allowed.** The difference is **declaration** —
  decided by a human and recorded in the report, it is scope; dropped by the agent for volume, it is
  an omission.
- **Fetch the category-term volumes before asking.** Do not make someone choose without sizes.
- **Do not recommend a top N.** Tell them to mix large and small within each group.
- Exclusions stay in `work/candidates.json` and the Limits section lists them.
  **A position that was not studied is not "none".**

## 8. Environments where responses must be moved by hand

### "There is no way to save automatically" was a wrong rule (corrected 2026-10-01)

For a while this file said "do not wait for automatic saving in chat · there is no way". The
evidence was that **60 saved responses were searched and no download URL was found.**
**The investigation itself was wrong.**

**The URL is in the tool-result envelope, not in the saved file.** Once downloaded, the file holds
only the payload (`data`, without `cost_detail`). So no amount of searching the saved copies finds
it — **it was not absent, it could not have been there.**

**There are three ways in** — ① fetch the result's download URL ② `cp` the path the host saved
③ a heredoc, only for a small response that came in the body. **Hand-copying is the last resort.**

That one wrong rule made the agent transcribe responses by hand, and to reduce that cost we piled
on workarounds like "store only the first 4 nodes" (later withdrawn after a 41 → 0 loss). The user
also heard "in this environment I have to move the file myself…" every time — which was not true.

**The lesson · to prove something is absent you have to look in the right place.** Not in the saved
copy does not mean not in the envelope. If you have never looked at the envelope, you have "not
checked", not "not there".

### Do not estimate the size from `limit`

`limit` is a ceiling and is usually not reached.

| | |
| :---- | :---- |
| Characters per related-query row | about **17** |
| Measured rows per category | **33 to 1,000** (a 30x spread) |
| 300 journeys | about **25,000 characters** (facet seeds run longer) |

Computing "categories × a full 1,000 rows" gives 1.5x the real figure, and that number is what makes
someone abandon a run. **Fetch a few for real, then decide.**

### Do not truncate journeys to the first 4 nodes (rule withdrawn)

There used to be a rule that "category and facet journeys lose nothing if only the first 4 nodes are
recorded". It was true while the verdict looked only at **the first brand within 3 steps of the seed.**

**It became wrong when the journey axis changed to "distinct branded queries anywhere on the
journey".** Measured — in one category's journeys a rival first appears at **step 4**. Keeping only
the first 4 nodes turns **41 into 0**, and our own count drops 29 → 27, flipping the verdict.

All nodes are stored now, and `check_run.py` blocks a file carrying `nodes_kept` with a `✗`.
If the volume is a burden, split the turns — do not cut the journeys.

### Splitting the turns is a supported path

If one turn cannot finish it, use several. That is different from shrinking the run or truncating
responses.

It works because **the run folder is the state.** Splitting turns does not reduce cumulative context,
but when the conversation grows long enough to be summarised, the raw responses leave the context
and only the files remain. The scripts read files, so it still reaches the end.

**Run `check_run.py` first on every turn.** After a summary you do not remember what was saved, and
relying on memory refetches a category you already have — **paying twice.**

## 9. The screen

- Attach rate can exceed 100%. **Do not call it a share.**
- **Never write "not listed" as 0%.** `-` is "measured, nothing there"; `·` is "not measured".
- **Do not attach a journey tag where the naming axis produced a verdict.** Measured, 40% disagree
  and it becomes noise.
- The synthesis matrix's horizontal axis gets long (23 columns measured). In horizontal scroll, the
  category, verdict and volume columns stay pinned.
- **No development notes.** "What we could not measure" belongs; "which design we chose" does not.
  What stays on screen is the **legend** and the **interpretation**.
- **Never hardcode a run-specific sentence into the renderer.** Given the right conditions it prints
  on another brand's run — measured, one brand's explanatory sentence and tooltip strings went out
  in a different run.
- The synthesis is **a draft assembled from the aggregates.** A human polishes it before presenting.

## 10. Why the related-query axis was dropped from the facet matrix

Slicing a category's related queries by facet leaves a sample of 3 to 70 (measured — of 1,000
related queries for one category, 7 contained a given facet word). One or two per brand says
nothing, and with a journey column in the same table **the difference in sample size reads as a
difference in signal.**

So a facet is judged from journeys **fetched separately** with `<facet> <category>` as the seed.
Calling `intent_finder` on the same seed returns almost nothing — measured, 8 results (even with
`volume_threshold=1`), while `path_finder` returned 981 journeys.

**Facets are not given a verdict badge.** `<brand> <facet> <category>` is 3–4 words, so it is
searched only for large brands (listed 0–57%), and only **12–35%** of facets can be measured by
journey at all. Rival combinations fill only **16%**. Badging what was not measured reads as a
verdict, so the facet table stays a **demand list**.

**A facet with no volume data is dropped from the seeds.** The response comes back empty.

**Gating facet selection on "appearances in the category's journeys" was rejected by measurement** —
it correlates barely at all with seed availability, losing three good facets to save two bad ones.

## 11. The shell CSS ships with its unused rules (decided 2026-10-06)

Of `report-shell.css`'s 73 rules the report uses **24** (the sidebar, `rpt-toolbar` and site footer
are web-app only). `overlay.css` is 10 of 30; `audience-shared.css` is 6 of 9. About 10KB of CSS the
report cannot use rides along in every customer file.

**It is still not trimmed.**

- The three files are **byte copies** of `_core/styles/`. The moment they are trimmed the two copies
  diverge, and a later change in `_core` never reaches this one.
- The four sibling reports carry the same ratio (30 of 94). Being the only one that differs costs
  more than it saves.

The whole report is around 330KB, so 10KB is 3%. The place to cut is not the CSS but the A4 copy (53KB).

## 12. "CEP" was renamed to "demand facet" (QA 2026-10-02)

**More than half of what actually gets picked is not a Category Entry Point.** Classifying the 60-odd
labels from four runs:

| Nature | Examples |
| :---- | :---- |
| Occasion · use (a real CEP) | for a gift · office · travel · running · swimming |
| **Product attribute · form** | alcohol-free · wired · wireless · bluetooth · open-ear · bone conduction |
| **Grade** | premium · high-end |
| **Channel** | marketplace names |

Calling it "CEP" **points at something other than the marketing term's definition.** A customer who
recalls CEP theory and then looks at the screen finds a mismatch. So the on-screen and in-document
name became **demand facet**.

**The labelling rule was aligned at the same time** — it used to say "occasion, use and feature only"
while actually accepting form (wired/wireless) and grade (premium). It now reads "the words that
split demand inside that category — occasion, use, feature, form, grade", excluding gender, age,
colour, model name, store, community, flavour and ingredient.

**The code identifiers were not changed** — the `cep` key, `data/cep/`, `cep_deep.py`, `cep_cols`.
Changing them breaks every run already collected, and they are names a customer never sees, so there
is nothing to gain. Writing the correspondence down once, here, is enough.

**The trigger "CEP별 경쟁" stays in `description`** — people still call it that.

## 13. Search terms are shown in the market's language, with a translation toggle

`--lang` changes the report's chrome and prose. The search terms themselves stay in the market's
language by default — that is the market's own data, and a translated string cannot be checked
against ListeningMind's screens.

When market language and REPORT LANGUAGE differ, Step 9-b builds a translation map and the renderer
takes it as `--translations`. Both spellings are then in the HTML and the **"Translate keywords"**
toolbar button swaps them; without the map the button does not appear.

What the toggle covers: **category names, group names, demand facets, rival brand names and the
representative queries** — everything `kw_extract.py` collects.

Five things stay in the original on purpose:

- **Our own brand name.** It is the report's subject and the same string goes into the cover, the
  `<title>` and several `data-` attributes, where the two-copy span cannot live.
- **`title=` tooltips.** A native browser tooltip prints tags as literal text, so the toggle cannot
  reach inside one.
- **SVG text labels** (the bubble map's category labels). `<span>` is not valid inside `<svg><text>`,
  so a translated copy cannot be carried there.
- **The related-query chips** in an expanded row. They are the raw queries, dozens per category, and
  the brand inside each is highlighted by substring replacement — there is no clean seam for a
  second copy. They are evidence you check against ListeningMind, so the original is the useful form.
- **Any term the map does not cover.** A key that does not match the original byte for byte leaves
  that term untranslated, and nothing warns about it — check a few terms on screen after toggling.
