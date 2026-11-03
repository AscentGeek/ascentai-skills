---
name: lm-season-trend-report
description: Collects 48 months of search volume for the queries searched together with a seed keyword (ListeningMind MCP · intent_finder · cluster_finder · keyword_info) and generates a "Season & Trend Analysis" rich HTML report (dashboard/A4). It answers three questions — ① which monthly search patterns repeat every year (seasonal keywords by month · seasonal calendar by theme) ② what changed from the previous 12 months to the last 12 months (key trends · trends by theme) ③ what rose and fell in the last 3 months (QoQ · QoQ+YoY top 20). Use it when the user asks for a "season trend analysis", "seasonality analysis", "when is peak season", "monthly search pattern", "what is trending now", "{keyword} seasonal analysis", or the same in Korean — "시즌·트렌드 분석", "시즈널리티 분석", "성수기 언제", "월별 검색 패턴", "요즘 뜨는 검색어", "{키워드} 시즌 분석", "season-trend-report" — or in Japanese — 「シーズン・トレンド分析」「季節性分析」「繁忙期はいつ」「月別検索パターン」「最近伸びている検索語」.
allowed-tools: Bash, Read, Write, intent_finder, keyword_info, cluster_finder
metadata:
  author: AscentKorea
  category: output
  tags: report, season, trend
---

# lm-season-trend-report — Season & Trend Analysis

## What this skill is

> It groups the queries searched together with the seed into themes and, from 48 months of search volume, shows
> **the monthly patterns that repeat every year**, **what changed from the previous 12 months to the last 12 months**, and
> **which searches rose or fell in the last 3 months against the previous 3 months and the same 3 months last year**.
> The goal is **organisation** — laying out, from search data, when which searches rise every year and which searches
> recently grew or shrank.

## Prerequisites

- **The ListeningMind MCP connector must be connected.** Data comes only from `intent_finder` · `cluster_finder` · `keyword_info`.
  Never use another source and never invent numbers. Do not ask for an API key or look for one in environment variables or `.env`.
- python3 (standard library only).
- If an MCP tool call fails with "tool not found", the connector is not connected → ask the user to connect it and stop.

## Two runtime inputs: TARGET MARKET and REPORT LANGUAGE

1. **TARGET MARKET (`gl`)** — the search market to analyse: `kr`, `jp` or `us`. It goes to every MCP call,
   to `st_prepare.py --gl` and into `config.json` as `"gl"`.
2. **REPORT LANGUAGE (`lang`)** — the language of the report: `kr`, `jp` or `us`. It goes into `config.json` as `"lang"`
   and decides the report's UI labels, the number units in `facts.md` (만 · 万 · K) and the language narrative.json is written in.

**The two are independent.** Analysing the US market with a Japanese report (`gl us · lang jp`) is valid.
Never infer one from the other, and never infer either from the seed's language or the language the user writes in.

If the user's request does not make both values explicit, **ask once, in a single short question, and do not guess.**
Do not start any MCP call, build or render until both values are fixed — there is no default.

## Chat language — the language the user writes in

Everything you say in chat (progress notes · fixed questions · the final summary) is in **the language of the user's
latest message**. Do not switch to Korean because this skill's code output (facts.md · off.txt) is Korean, and do not
switch to English because a tool result is English. Search terms and numbers are never translated.

## Report structure (fixed · this order · these names)

| Position | Content |
|---|---|
| Cover | Title · seed · collection date / **Background and purpose** (fixed text) + a three-line summary (seasonal pattern · last-12-month trend · last-3-month risers and fallers, one sentence each, insight only, no numbers) |
| Tab 1 · Seasonal patterns | ① **Monthly search volume of the seed by year** — the seed query's monthly volume drawn as 4 yearly lines over a Jan–Dec axis (the y-axis covers the data range · the latest year bold · each year's peak month · hover shows that month's 4 values) ② **Seasonal keywords by month** — criteria card + insight (`month_note`) + 4 keywords per month and "N more", the current month highlighted ③ **Seasonal calendar by theme** — insight (`calendar_note`) + rows = themes (with at least 1 seasonal keyword), cells = the keywords that rise in that month (seed word shortened) · clicking a keyword opens the evidence dialog (yearly peak months · seasonal index · that month's average · 4 years × 12 months chart and table) |
| Tab 2 · Last 12 months | Numbers are 12-month totals; table headers are the periods (24.10–25.09 · 25.10–26.09). ① **Key trends** — 0–5 groups you form from queries whose last 12 months are ≥ 1.5× or ≤ half of the previous 12 months, or that are new (12-month total ≥ 5,000 in either period, unclassified included), each with a title · basis · one-line interpretation · table (or "No movement meets the criteria above.") ② **Trends by theme** — every theme (largest last-12-month volume first), each with name · query count + left (growing) and right (shrinking) tables of 5 (expandable to the top 20) · clicking a keyword opens the evidence dialog (monthly chart and table for the two periods, no metric boxes) |
| Tab 3 · Last 3 months: up & down | From all queries including unclassified: criteria card (STEP 1 QoQ · STEP 2 YoY) + insight (`updown_note`) + one table chosen by two toggles [rising / falling] × [QoQ (default · QoQ only, seasonal risers included) / QoQ+YoY (both)] (both sorted by QoQ change · 20 rows · last 24 months · last 3 months · QoQ · YoY, change and %) · clicking a keyword opens the evidence dialog (YoY · QoQ boxes + monthly chart and table for the two periods) |

Do not add, remove or reorder tabs or cards. Do not hand-edit HTML/CSS.
Do not use judgement words such as "opportunity", "recommend" or "forecast" — the report shows facts only (when things rise, what grew and shrank).

## Principle — structure and numbers are code; you decide only three things

```
MCP intent(seed) · cluster(seed) → st_prepare.py (code: query list) → keyword_info (1,000 per call)
  → config.json (you: relevance filter rel/exc · theme rules · gl · lang) → st_build.py (code: every number · facts.md)
  → [review off.txt · untagged.txt → fix config and build again, at most 3 times]
  → narrative.json (you: sentences in fixed slots only) → st_render.py (code: lint · HTML)
```

The analysis covers queries with a 4-year total of 1,000 or more (config `min_total` can change it). You decide only
**① the relevance filter ② the theme rules ③ the sentences and the key-trend groups**. The seasonal index, the monthly
seasonal keywords, the calendar placement by theme, the 12-month change by theme, the key-trend candidates (1.5× · half ·
new), the check for queries that spiked together in the same month, the rising/falling decision (QoQ · QoQ+YoY) and all sorting are decided by code. Sentences use only the numbers in `facts.md`.

## MCP call protocol

### Discover SKILL_DIR (at the top of every Bash command)

```bash
SKILL_DIR=$(find ~/.claude/skills ~/.claude/plugins /mnt/skills /mnt/user-data \
    ~/.codex/skills ~/.gemini/skills ~/.config/skills ./skills . \
    -maxdepth 4 -type d -name lm-season-trend-report 2>/dev/null | grep -v '\.trash' | head -1)
[ -z "$SKILL_DIR" ] && echo "❌ skill path not found" >&2
R="$SKILL_DIR/_shared/render"; CACHE="$SKILL_DIR/scripts/mcp_cache.py"
```

If it is empty, use the folder this SKILL.md is in (`references/` · `_shared/` · `scripts/` are on the same level).

### 2 steps per call (no exceptions)

```bash
# ① Before the call · check the cache
python3 "$CACHE" lookup <tool> --params '<MCP parameter JSON>' --out "$WORKDIR/<file>.json"
```

- **exit 0 = hit** → do not call MCP.
- **exit 2 = miss** → call the tool as shown in the call example (`references/workflow.md`), then ②.

```bash
# ② Download → verify → store in the cache (one command)
python3 "$R/fetch_dl.py" --url "<browser_download_url>" --out "$WORKDIR/<file>.json" \
  --sha256 <download.sha256> --items <download.item_count> --tool <tool> --params '<the same JSON as ①>'
```

- `--params` **must be identical** in ① and ②. If they differ, the next run will not hit the cache.
- The cluster_finder envelope has no `item_count` → drop `--items`.
- **Do not use `curl`.** If the result says it was saved to a host file (`Tool result too large…stored at …`), that is not a failure —
  `cp "<saved path>" "$WORKDIR/<file>.json"` then `mcp_cache.py store <tool> --params '<same JSON>' --file "$WORKDIR/<file>.json"`. Do not call again.
- Never shrink the keyword count · `limit` · `data_type`, and never summarise or excerpt records because a response is large.

### user_query · record what the user asked

The MCP tools accept `user_query` — it records **what the user asked** alongside the call.
Send the user's message **verbatim** (no translation, summary or rewording), on every call.
If the message contains personal data — phone numbers, email addresses,
ID / card / account numbers, etc. — stop, and ask the user to send the request again without it.

```json
"user_query": "<the user's message, verbatim>"
```

> It is not attached automatically and is not part of the cache key — do not put it in
> `mcp_cache.py --params`.

### is_skills · mark the call as a skill call

The MCP tools accept `is_skills` — it tells the platform the call **comes from a skill**, not a plain prompt.
It defaults to `false`, so send it **as `true`**, on every call:

```json
"is_skills": true
```

> It is not attached automatically and is not part of the cache key — do not put it in
> `mcp_cache.py --params`.

### skill_desc · record which skill and version made the call

The MCP tools accept `skill_desc` — it tells the platform **which skill and version** made the call.
Send this object **as is** (a JSON object, not a string), next to `"is_skills": true`, on every call:

```json
"skill_desc": {"name": "__SKILL_NAME__", "version": "__SKILL_VERSION__"}
```

> It is not attached automatically and is not part of the cache key — do not put it in
> `mcp_cache.py --params`.

### Failed calls

- `Too Many Requests` — concurrency limit. Repeat the same call a little later. **Never call two MCP tools at once.** One at a time.
- If cluster_finder is blocked by the plan (`Not Authenticated` · `Invalid API Key`), skip it and continue. Say so in one line in chat.
- `Insufficient Lima` · `Account Locked` — stop and pass on the reason exactly as given.
- Never store a failed call in the cache.

### Credits

Cost is counted by **calls**, not keywords. keyword_info takes up to 1,000 keywords per call — do not split more than needed.
Only state values confirmed by the envelope's `cost_detail.total_cost`, and never state the remaining balance.

## Execution

Read `references/workflow.md` first and run it from Step 0 in order.

| File | When |
|---|---|
| `references/workflow.md` | Always, first |
| `references/config.md` | When writing config.json (relevance filter · theme rules) |
| `references/narrative.md` | When writing narrative.json (cover summary · notes) |

## Don'ts

- Do not put 4-year long-term trends, industry comparisons or cause judgements in the report or chat (that is lm-search-demand-report's area).
- Do not write judgement or forecast sentences such as "opportunity", "should push", "will rise next season". Write "it rose in October in each of the last 4 years".
- Do not conclude about a whole theme from one keyword.
- Do not restate search volume as sales or market share.
- Do not invent numbers. Use only numbers in facts.md, or ratios computed from them.
- Do not use exaggerations (collapse · plummet · shock · huge hit). Lint blocks them.
