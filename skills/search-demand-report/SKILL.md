---
name: lm-search-demand-report
description: Diagnoses whether a keyword's search-demand change is a market-wide trend or specific to the target, using ListeningMind MCP data (intent_finder · cluster_finder · keyword_info), and generates a "Search Demand Report" rich HTML report (dashboard/A4). It narrows broad seeds ("beauty", "Nike") to a reportable item, decides brand/product vs category mode from the related-query mix, and outputs two fixed sections (market flow comparison · target keyword intent change) with a code-decided verdict against comparable markets. Runs without cluster_finder too. Use it when the user asks "why did search volume drop", "demand diagnosis", "change analysis", "{keyword} trend diagnosis", "is the category dying or just us", "is it the market or just us", or the same in Korean — "검색량이 왜 줄었지", "수요 진단", "변화 분석", "우리 브랜드 수요", "시장 흐름인지 우리만의 문제인지", "search-demand-report", "demand-shift" — or in Japanese — 「検索数が減った理由」「需要診断」「変化分析」「市場全体の流れか自社だけか」.
allowed-tools: Bash, Read, Write, intent_finder, keyword_info, cluster_finder
metadata:
  author: AscentKorea
  category: output
  tags: report, demand, brand, product, category
---

# lm-search-demand-report — Search Demand Report

## What this skill is

> It separates categories and brands, analyses the search volume of the related keywords as a time series,
> and shows where demand is going. A single keyword's change cannot tell you how a category, brand or product
> is really doing. This skill finds the keyword set that fits the keyword type and diagnoses the demand flow
> objectively by comparing outside (market) and inside (composition) trends.

The top of the report is the fixed **"Background and purpose" text (`purpose.body`) + a data-based overview**,
the same layout as lm-queryfinder-report. The paragraph above describes the skill; the report shows `purpose.body`.

**Path verification (path_finder) is not used.** A path snapshot cannot prove churn or demand moving elsewhere,
so it was dropped. Never claim "a move confirmed by paths" or "churn paths" in the report or in chat (lint warns).

## Prerequisites

- **The ListeningMind MCP connector must be connected** — data comes only from `intent_finder` ·
  `cluster_finder` · `keyword_info`. Never use another source and never invent numbers.
- **No API key is requested.** The connector handles authentication.
- python3 (standard library only · no pip install).
- Network egress for `fonts.googleapis.com` (fonts · falls back to system fonts if blocked) and for the
  download URLs the MCP tools return (`github.com`).

If an MCP tool call fails with "tool not found", the connector is not connected: ask the user to connect
the ListeningMind MCP connector and stop.

## Two runtime inputs: TARGET MARKET and REPORT LANGUAGE

1. **TARGET MARKET (`gl`)** — the search market to analyse: `kr`, `jp` or `us`. It goes to every MCP call,
   into `seed.json` / `scope.json` as `"gl"` (it selects the market's classification dictionary), and to
   `ds_aggregate.py build --gl`.
2. **REPORT LANGUAGE (`lang`)** — the language of the report: `kr`, `jp` or `us`. It goes to
   `ds_aggregate.py build --lang` and decides the report's UI labels and the language narrative.json is written in.

**The two are independent.** Analysing the US market with a Japanese report (`--gl us --lang jp`) is valid.
Never infer one from the other, and never infer either from the seed's language or the language the user writes in.

If the user's request does not make both values explicit, **ask once, in a single short question, and do not guess.**
Do not start any MCP call, aggregation or rendering until both values are fixed — there is no default.

## Chat language — the language the user writes in

Everything you say in chat (progress notes · fixed questions · button labels · evidence-table headers · the final
summary) is in **the language of the user's latest message**. Do not switch to Korean because this skill's code
output (classify.md · facts.md · scope brief) is Korean, and do not switch to English because a tool result is English.
The seed's language and the market do not decide the chat language either.
- Fixed questions (scope.md §5 · ask.md · M5-7) keep **their meaning and order** when moved into the user's language.
  Search terms (seed · candidates · the `삼성 냉장고` option) and numbers are never translated.
- If a message mixes languages, follow the language of most of it. If the user names a language, follow that.

## Broad seeds are narrowed first (scope-v2 · `references/scope.md`)

An area word ("beauty", "fashion") or a brand that sells many items on its own ("Nike") is not run as is. When check
catches a broad seed (kind `broad` · `brandwide`), you propose 8–12 item candidates, call keyword_info · intent_finder
**for all candidates at once**, and code judges each candidate's fitness (48-month history · monthly avg ≥ 1,000 ·
not still broad · related queries ≥ 30). Ask **once** with the top 3 fits + free input, then restart from the chosen item.
**Question format (scope-v2):** first the note "the topic is broad; choosing a sub-market makes the analysis more accurate"
with **an input format and examples**, then the evidence table and the options.
Examples and options are a single search term as people type it — `삼성 냉장고` for a brand, `선크림` for an area. Never a
hierarchy such as `삼성 > 냉장고`. The other candidates go on as section 1 comparison candidates but only with the
grade '영역만' (same area only), so section 1 picks from the nearby market (M5-0) first.

| Signal (code) | Broad | Item | Measured (kr · 2026-10-06) |
|---|---|---|---|
| Share of queries where the seed sits in the "thing searched for" slot (end of the query) | < 45% | ≥ 45% | 뷰티 27% / 쿠션 71% · 선크림 78% · 마스크팩 85% |
| Share of queries where the seed is a standalone word | < 70% | ≥ 70% | 뷰티 50% / 쿠션 83% · 선크림 99% · 향수 93% |

These thresholds are calibrated for kr only; jp and us use the kr values for now (the scope brief says so).

## Two modes — decided from the related-query mix (method-v4)

The mode is not decided by whether the seed contains a brand token but by **what the seed's related queries
(intent_finder) mostly are**. `ds_classify.py check` decides it and writes the reason (modeReason) into seed.json.

| Mode | Definition | How code tells (`FIT`) | Example |
|---|---|---|---|
| **entity** brand/product | brand · product keyword | mostly one brand's product, model, line, use searches — related queries containing the seed brand ≥ 50% | 나이키 러닝화 → 나이키 페가수스 · 나이키 보메로 |
| **category** | non-brand keyword | mostly generic modifiers (recommendation · comparison · price) with 2+ brands — brands right before the item ≥ 2 · one brand < 50% | 러닝화 → 러닝화 추천 · 나이키 러닝화 · 호카 러닝화 |

If the mode you wrote in seed.json differs from the code's judgement, or the seed is a topic rather than something people
buy (다이어트), check exits 10 (a broad seed goes to scope.md instead) → **ask once in the fixed format of
`references/ask.md` (evidence table · options A/B/C · one recommendation) and stop.** Never improvise another question.

## Fixed sections (both modes · only these two · this order · fixed names)

| # | Section (id) | Name (fixed label) | Purpose | Brand/product mode | Category mode |
|---|---|---|---|---|---|
| 1 | `external` | **Market flow comparison** (`sec.external`) | did the whole market move together, or only this target · verdict | competing brands in the same category | **nearby market** = substitute · adjacent items (필라테스 → 요가·홈트 · 향수 → 바디미스트 — not 샴푸 just because it is also beauty) |
| 2 | `internal` | **Target keyword intent change** (`sec.internal`) | which intents (search purposes) attached to the target grew or shrank | product lines | search purposes (topics + fixed intents + region · brand · nearby searches) |

Section names come from the `sec.*` keys of `labels/demand-shift.<lang>.json`. Never rename them in the report.

**Both modes produce the same report.** Brand/product mode has the same cover, KPIs and cards, charts and tables. Only two
things differ: section 1 compares **competing brands + the same item name** instead of other items, and section 2 groups by
**product line** instead of search purpose. There is no sub-SKU level — generation/model names (페가수스 41) appear as query
rows when a line is expanded, with a "new" badge.

**Screen layout (fixed · in order)** — the dashboard is one screen without tabs; A4 has the same order in pages.

| Position | Contents |
|---|---|
| Cover | title · seed · reference date / fixed **Background and purpose** text (`purpose.body`) + a 1–2 sentence overview |
| At a glance | 3 KPIs: vs similar categories (gap in %p) · 4-year search volume change of the section 1 analysis target · most-searched purpose (share, whole %) |
| 1 Market flow comparison | verdict card (code sentence + basis) → **chart by category/brand** [volume \| change] tabs → table (rows per category/brand + total · expand each row to its queries) |
| 2 Target keyword intent change | insight cards (purpose chip + 4-year change · rank, links in the body) → **chart by intent** [volume \| change] → table by purpose (expand to queries · top 10 + show all · 'biggest changing query' column) |

**Table and chart rules**
- 12-month rolling periods × 4. A period cell = volume + an arrow vs the previous period (▲ red up · ▼ blue down) + grey %.
  Arrow opacity shows the size. No direction, flow-type, year-on-year or composition columns.
- New: one "new YYYY.MM" badge in the period it first appears · arrows only after that · the 4-year column shows "—" ·
  a dashed line on the 48-month chart where it appears.
- Click a 48-month sparkline for a large chart (period cards · hover values · first-appearance point).
- Line chart legend = check chips. Clicking one keeps only that line, **redraws the axis for it**, and shows max · min · latest.
- Extra explanations go in an (i) tooltip next to the title, not in the body.
- **Not included**: summary tab · action suggestions · data-notes card · section lead sentences · an "Insights" subheading ·
  source tags (intent/cluster).

## Keyword-set classification is decided by the method (`references/keyword-method.md`)

Which query goes into which section is defined by **`references/keyword-method.md`** and applied by `ds_classify.py`.
You judge in only five places — ① seed decomposition (seed.json · M1) ② the analysis target's same-meaning names (M3a)
③ the section 1 comparison set (M5) ④ comparison targets' representative spellings (M5a · optional) ⑤ section 2
lines / topics (M8) — and record the rule number for every choice in picks.json. Code builds the bundles with the same
rules — **never write plan.json by hand.**

The classification dictionary is **per market** (`render/ds_market.py` · chosen by `seed.gl`): kr · jp · us.

| Section | Brand/product mode | Category mode | Modifiers |
|---|---|---|---|
| 1 Market flow | only the brand changes (B′ spellings × I* — the same item names and synonyms as the target) | other items in the same parent category (+ spelling variants) | generic item words only |
| 2 Intent change | product line P (incl. generation / model queries) · with and without brand name in one line | intent bundles (brand → topic → 계급도·순위 → 추천·입문 → 비교·후기 → 가격 → 신제품) | brand/product: no exploration · attribute words · category: the intent word is the bundle key |

## Principle — structure, numbers and verdicts are code; only interpretation is yours

```
MCP intent(seed) → seed.json (you: M1 · upper · gl) → ds_classify.py check (code: topic · broad seed · mode)
   [broad seed] → scope.json (you: candidates) → keyword_info · intent(all candidates) → ds_scope.py score (code: fitness) → user choice → restart
   → MCP cluster(seed · required for category) · cluster(upper · if available) · intent(upper) · intent(brand + category) → propose (code · proximity grade)
   [nearby < 4] → seed.near (you: M5-0 substitute · adjacent) → intent(near) → propose → picks.json (you: M3a · M5 · M8) → [comparison target without evidence] ask the user (M5-7)
   → plan (code) → keyword_info → ds_aggregate.py build (code: checks · numbers · verdict) → facts.md
   → narrative.json (you: sentences into fixed slots only) → lint → ds_render.py → publish
```

- Section order, titles, tables, charts and colours are fixed in code (`labels/demand-shift.<lang>.json`).
- Every number is computed by code. narrative may only use number strings written in facts.md.
- The section 1 verdict (업계와 같은 흐름 / 업계 대비 약세 / 업계 대비 강세 / 판정 보류 — same as market / weaker than market /
  stronger than market / no verdict) is decided by code. Sentences use that verdict as is.
- A string the finders did not return cannot be measured. **Exception: analysis-target strings built from chosen same-meaning names**
  (나이키 + 조깅화) are verified by keyword_info values; build drops them if there is no value.
- **Values are search volume summed over engines** — Naver + Google in kr. jp and us return only a monthly total, which the code
  reads as the Google value. Anomaly detection never changes a value; only identical Google values are counted once.
- **Chart lines and table rows = the sum of the bundle's queries.** Expanding a row and adding its queries gives the same number;
  "total" is the sum of the bundles. Build checks this (sum_check) and **exits 12** without a report if it fails.

## MCP call protocol

Data comes from the **ListeningMind MCP tools**. Because the caller is **you** and not code, two things are your
responsibility: **① check the cache ② secure the response file.**

### Discover SKILL_DIR (at the top of every Bash command)

```bash
SKILL_DIR=$(find ~/.claude/skills ~/.claude/plugins /mnt/skills /mnt/user-data \
    ~/.codex/skills ~/.gemini/skills ~/.config/skills ./skills . \
    -maxdepth 4 -type d -name lm-search-demand-report 2>/dev/null \
    | grep -v '\.trash' | head -1)
[ -z "$SKILL_DIR" ] && echo "❌ skill path not found" >&2
echo "SKILL_DIR=$SKILL_DIR"
```

Install paths differ per host. If it comes back empty, find the directory this SKILL.md sits in and use that (the place
where `references/` · `_shared/` · `scripts/` are at the same level). Never hardcode a `cd`.

### 2 steps per call (no exceptions)

```bash
# ① Before the call · check the cache
python3 "$SKILL_DIR/scripts/mcp_cache.py" lookup <tool> \
  --params '<MCP parameter JSON>' --out "$WORKDIR/<file>.json"
```

- **exit 0 = hit** · the file is already filled → **do not call MCP.** Go on.
- **exit 2 = miss** · call the tool with `"response_format": "download_url"` and `"is_skills": true`, then ②.

```bash
# ② Fetch the download URL → verify → store in the cache (one command)
python3 "$SKILL_DIR/_shared/render/fetch_dl.py" --url "<browser_download_url>" \
  --out "$WORKDIR/<file>.json" --sha256 <download.sha256> --items <download.item_count> \
  --tool <tool> --params '<exactly the same parameter JSON as in ①>'
```

`--params` **must be identical** in ① and ②, and must not contain `user_query`, `response_format` or `is_skills` changes between runs —
otherwise the next run will not hit. Leave out `--items` when the envelope has no `item_count` (cluster_finder).

### Response file rules (the most important part)

The scripts read the MCP response as is, so it must sit in the file **raw and unprocessed**. Try these from the top.

1. **The tool result carries a download URL** → `fetch_dl.py` as above. It verifies sha256 and the record count, wraps the
   payload into `{"data": ...}`, and stores it in the cache. On a mismatch it does not save; it leaves `<out>.partial`, and
   **refetching the same URL costs no credits.** `--items` is the envelope's `item_count`, not the number of keywords sent.
   **Do not use `curl`.**
2. **The host saved the result to a file** (`Tool result too large for context, stored at …` · `Error: result (N characters)
   exceeds maximum allowed tokens. Output has been saved to …`) → this is not a failure. `cp "<saved path>" "$WORKDIR/<file>.json"`,
   then `mcp_cache.py store <tool> --params '<same JSON>' --file "$WORKDIR/<file>.json"`. **Do not call the tool again.**
3. **It arrived in the body** → only then write the raw JSON with a heredoc, then `mcp_cache.py store` as in 2.

**Absolutely forbidden** · reducing the number of keywords, `limit` or `data_type`, or summarising/excerpting records
because the response is large. If reducing scope seems unavoidable, stop and tell the user.

### Failed calls

- `Too Many Requests` — concurrent request limit. Wait and retry the same call. **Never call two MCP tools at the same time.**
- cluster_finder blocked by the plan (`Not Authenticated` · `Invalid API Key` for that option) — skip it and continue
  without the file (see workflow.md Step 2). Tell the user in one line that cluster data was not available.
- `Insufficient Lima` · `Account Locked` — stop and report the reason as given. Other calls will fail too.
- A failed call is never stored in the cache.

### Session cache

`~/.lima-agents/mcp-cache/<session>/` · within one conversation the same `(tool + parameters)` is never bought twice, also
across skills. It works only when the host gives a session env var; without one the skill calls MCP every time — deliberately,
rather than reuse another conversation's data. `LIMA_MCP_REFRESH=1` bypasses it.

### user_query

Every MCP call takes a `user_query` parameter that ListeningMind stores in its history. **It is not attached automatically** —
put the **user's utterance verbatim** (no translation, summary or paraphrase). It is not part of the cache key.

### is_skills

Every MCP call takes `"is_skills": true` — it tells ListeningMind the call comes from a skill, not a plain prompt.
**It is not attached automatically** and defaults to `false`, so add it to every call. It is not part of the cache key
(never put it in `--params`).

### Credits

Cost is counted **per call, not per keyword** — keyword_info costs the same for 50 keywords as for 1,000, so do not split
calls smaller than needed (one keyword_info call takes up to 1,000 keywords). Report only the measured
`cost_detail.total_cost` from the envelope. Never state a remaining balance.

## Execution

Read `references/workflow.md` first and run it from Step 0 in order.

## Reference files

| File | When |
|---|---|
| `references/workflow.md` | always, first |
| `references/keyword-method.md` | **always** · keyword-set classification method (M1–M9 · M5-0 nearby market · method-v5.12) |
| `references/scope.md` | when check returns kind broad · brandwide · narrowing the seed (candidates · checks · verdict · fixed question) |
| `references/ask.md` | when check exits 10 (topic · mode) · fixed question format and how to handle the answer |
| `references/plan-schema.md` | plan.json structure (plan is made by ds_classify) |
| `references/narrative.md` | when writing narrative.json |
| `references/rules.md` | verdict thresholds · data notes (rules-v5) |
| `references/pitfalls.md` | before writing picks |

## Don'ts

- Do not match the chat language to the documents or tool output — answer in the language the user writes in.
- Do not send a broad seed to the topic question — the check order is broad seed → topic → mode.
- Do not put intent-attached queries (필라테스 1:1 · 근처 필라테스) into the target. Do not mix a lower level (근력 운동 ⊂ 홈트) into the comparison set.
- Do not show region and brand names only as one combined bundle (catchall `split: true`).
- Do not run a broad seed (뷰티 · a multi-item brand alone) without narrowing. Do not pick the narrowed item for the user
  (only when exactly one candidate fits, notify and proceed).
- Do not call path_finder. Do not claim paths, churn or moves.
- Do not add, remove or reorder sections. Do not hand-edit HTML/CSS.
- Do not split brand/product mode section 2 by use or attribute (6인용 · 스텐 · 추천). Split by product line names only.
- **Section 1 compares representative names only.** In category mode each section 1 bundle (analysis target included) is
  `up to 2 representative names` — the analysis target is the seed item + the first chosen same-meaning name
  (synonyms.pick → analyst), a comparison target is its name + its first M5a spelling. So **list same-meaning names by
  search volume, largest first.** In brand/product mode each section 1 bundle is the front/back orders of
  `brand spelling × representative item name` only (나이키 러닝화 · 러닝화 나이키). The other same-meaning names form the
  detailed bundle (`plan.target`), which is used only for the coverage check below — it is not shown in the report.
- Comparison targets' other spellings (English etc.) come from classify.md candidates (M5a · optional) or as analyst —
  only those with measured values remain.
- **Working checks never go into the report.** Leave-one-out stability, representative-spelling coverage and the sum check are
  read only in build output and facts.md; fix problems before publishing (review the comparison set · add spellings).
- **Representative-spelling coverage.** For each section 1 bundle, build measures the last 12 months of
  `representative spellings ÷ detailed bundle`. Under 90% it warns — add that brand's spelling via M5a before publishing.
  Put the detailed bundle strings (`broad`) into keyword_info too.
- Do not leave a brand/product-mode comparison set with finder strings only — the synonyms mixed into the target (러닝화 ·
  조깅화) and brand spellings (adidas) must be mixed into the comparison set the same way (plan does this via verify).
- Do not put unrelated parent categories (치킨 · 노트북 · 여행) into the comparison set.
- **Do not add a comparison target only because it is in the same area.** Section 1's market = items people weigh against
  each other for the same need (substitute · adjacent). Code grades each candidate's proximity (가까움 · 근거 약함 · 영역만 —
  near · weak evidence · same area only); with fewer than 4 near ones, check substitute · adjacent candidates via intent_finder
  (M5-0). If you use a comparison target that is not '가까움', confirm once with the user before plan (M5-7).
- **Do not fill the comparison set from your own knowledge first.** Category mode picks items searched together with the seed
  from the seed cluster (`lm_cluster_seed.json`) first. If the upper term's cluster is polluted by other meanings, call one
  other upper term's cluster; use analyst candidates only when there are still fewer than 3 — and say so in chat.
- Do not judge from a single engine's numbers. Do not talk about demand from a single month's year-on-year change
  (12-month period sums only).
- Do not turn search volume into sales or market share. Do not estimate price tiers from search data.
- No aggressive or exaggerated expressions (거짓말 · 몰락 · 충격 · 폭망 — lie · collapse · shock · flop). Lint blocks them.
