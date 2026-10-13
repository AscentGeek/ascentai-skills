# Judging rules · the single source of truth

To change a threshold, edit **only this file**. SKILL.md and the scripts refer here.

---

## 0. Separate the three data states first

This comes before any verdict. Mix them and "not listed" quietly turns into "0%".

| State | On screen | Meaning |
| :---- | :---- | :---- |
| Not queried | `·` | it was not among that category's rival candidates, so it was never measured |
| **No volume data** | `-` | it was requested from `keyword_info` and the row is missing from the response |
| Actually zero | `0%` | the row is in the response and the value is 0 |

In the scripts, volume `None` = not listed, `0` = actually zero.

---

## 1. Naming axis — share of search

```
share of search = that brand's branded query volume
                ÷ the category's combined branded query volume (ours + rivals)
```

The denominator is **branded queries only**. Generic queries (reviews, price, forums) are not in
it — which is why Step 5 never queries them (`brandkw.py`). It asks: **among the people who pick
this category by brand, how much is ours?**

This is the metric Les Binet and James Hankins published in 2020 as **share of search**; the
definition here is the same one.

| Parameter | Value |
| :---- | :---- |
| 2x rule | ours vs the leading rival |
| Floor | none — no floor is applied to the share itself |
| Unclaimed | **branded share < 10%** (`NAMEMIN`) **or** branded query volume < 1,000 a year (`BVOLMIN`) |

```
branded share = branded query volume (deduplicated) ÷ (that volume + the category term's volume)
```

It asks whether this is a category people choose by brand — around 80% means the brand fight is
the market; a single digit means being first matters little. If the sample is too small (under
1,000 a year) one or two queries flip the share, so that is Unclaimed as well.

**Why the denominator changed from all related queries.** ① Leading, Contested and Trailing follow
the 2x rule, so they are **independent of the denominator**; the only place it was actually used
was the Unclaimed floor. ② Fetching volume for every related query took three quarters of the
run time (5,891 related queries → 1,145). ③ Dilution by generic queries forced the floor down to
3%, and that 3% meant something different in every category. Dilution is now read as its own
axis — **branded share**.

**The number differs from a QueryFinder topic total** (which uses all related queries as the
denominator). State the definition in the report.

**Why it changed from attach rate.** Attach rate (`<brand> X` ÷ `X`) **misses entirely a brand
whose product name is itself the category.** Measured — in "zero soju", "Zero-two soju" (12,340)
was first, but there is no query "Zero-two zero soju", so its attach rate fell to 0. Share of
search counts "Zero-two soju" as it stands.

**The top query is not used in the verdict.** The largest branded query is shown for reference,
but it is whole-brand demand, not this category's share.

### Brand matching

- **A brand (or alias) must start at a word boundary.** Strip the spaces, cut at every word
  boundary, and if one of those tails **starts with** the brand, it matches. The end may fall
  inside a word (Syntha → Syntha6). Starting mid-word does not match. What happened when this
  rule was missing is measured in `limits.md` §4.
- Product and line names **fold into the parent brand**; common misspellings fold in too.
- **A different brand sharing the same characters is removed with `alias_exclude`.**
- **An alias adds to the brand name, it does not replace it.** Narrowing is `alias_exclude`'s job.
- **A one-character brand matches on token equality only** — it must not be buried inside a longer word.
- Brand candidates = the union of `comp` in `curate.json` + `config.extra_brands` (found during the
  run but absent from `comp`).

## 2. Journey axis — branded queries on the journey

The **distinct count** of that brand's queries appearing across **all nodes** of the `path_finder`
journeys (300 by default). **It equals the number PathView shows when you filter the keyword list
by brand name** — the screen and the report agree.

| Parameter | Value |
| :---- | :---- |
| 2x rule | same as the naming axis |
| Floor | **3** — under 3 on both sides it is "none" |
| On hold | none |

As a secondary figure, record the **first appearance step** — how many steps after the seed, or
"before the seed".

**The journeys must be stored with all nodes.** Keeping only the first 4 nodes drops a brand that
first appears later (measured — one brand first appears at step 4, and 41 became 0).

**Why it changed from first transition.** "Journeys whose first brand appears within 3 steps of the
seed" was hard to explain and did not match the number on the PathView screen.

**Known weaknesses — state them in the report's method section.**
- A brand with many product lines is favoured (each line is a separate query).
- Non-core products count as the brand too (a brand's tonic water in a soju category).

## 3. Demand facets — judged on the journey axis alone

The combined search `<brand> <facet> <category>` **barely exists.** Measured — in one run **9 of 9**
had no volume data. Category-level measurements point the same way (share of facets where the
combined own-brand search is listed: 61% · 16% · 3% · 0% across four runs).

**So the naming axis is not used for demand facets.** The verdict comes from the journey axis alone.

| Parameter | Value |
| :---- | :---- |
| What is counted | distinct branded queries across **all nodes** of the journeys seeded with `<facet> <category>` |
| 2x rule | same as the category |
| Floor | **3** — under 3 on both sides it is "none" |
| On hold | none |

It is **the same metric** as the category's journey axis, so it reads with the same eye.

### What goes in the table — demand facet × brand matrix

Columns are **facet · verdict · volume · share · per-brand count of queries on the journey**.
**Left out** — own combined search, attach rate, sample size, a "journey / combined volume" toggle,
and collapsed rival rows.

**The brand columns are the whole run's rivals.** Restricting them to the few chosen in a category
traps the competitive picture inside that category's boundary — measured, one brand appeared 53
times on a facet's journeys while being absent from that category's rival list.

**`intent_finder` is not called with a facet seed** — it only returns queries containing the seed,
and a facet seed is 3–4 words, so about eight come back. **One call per facet, `path_finder`.**

### The note above the table (customer-facing wording)

> Searches that attach the brand name, such as "<brand> <facet> <category>", do not appear in these
> situations, so the verdict comes from the brands those searchers went on to look for.
> Cell figures = branded queries appearing across the 300 search journeys.

### One-line summary

Attach one sentence per category — ① the top 3 facets by demand and their share ② the facets where
we lead (or that there are none) ③ the situation where we fall furthest behind. Put units on the
numbers — "queries on the journey: ours 0 vs theirs 19".

### Demand facet labels

Pick the words that **split demand inside that category** — occasion, use, feature, form, grade.
**Flavour and ingredient are not demand facets** — they are product variants. Gender, age, colour,
model name, store and community are excluded too.

## 4. Not decided yet

- **How facet demand is computed.** Today only the single query "<facet> <category>" is counted.
  Whether to switch to a token sum, as share of search does, is open.
- **Share of search for facets.** Whether to revive the naming axis from facet related queries
  (about 20 credits a run).
- **Journey axis scope.** Today `path_finder` is called only for Unclaimed categories. Whether to
  fill Trailing ones too (1 credit per category).
- **The unit of a brand.** Product brand or parent company.
- **Automatic discovery of brands not in the dictionary.** Today a human fills `curate.comp` +
  `config.extra_brands`. Producing candidates from token frequency, as a topic rollup does, is next.
- **Facet × rival combined search is not queried.** An "Unclaimed" facet means **we** did not take
  it, not that nobody did.
