---
name: lm-pathfinder-report
description: >-
  Analyzes the search journey of a seed keyword with ListeningMind MCP
  (path_finder · keyword_info) and generates a "Search Journey Analysis"
  rich HTML report (dashboard/A4). Using the PathFinder agent's analysis frame,
  it groups keyword-to-keyword routes into main routes (top 5) and key branch
  points (hubs), and presents flow type, drop-off/merge points, search volume and
  insights through a journey flow diagram, route cards and hub cards.
  Use it when the user asks for "search journey analysis", "pathfinder report",
  "customer journey analysis", "{category} search paths", "search path report",
  or the same requests in Korean — "검색 여정 분석", "패스파인더 리포트", "고객 여정 분석",
  "{카테고리} 검색 경로", "검색 경로 리포트" — or in Japanese —
  「検索ジャーニー分析」「パスファインダーレポート」「顧客ジャーニー分析」
  「{カテゴリ}の検索経路」「検索経路レポート」.
allowed-tools: Bash, Read, Write, path_finder, keyword_info
metadata:
  author: AscentKorea
  category: output
  tags: report, search journey
---

# lm-pathfinder-report — Search Journey Analysis Report

## Prerequisites

- **ListeningMind MCP connector must be connected** — data comes only from the 4 MCP tools
  (`intent_finder` · `keyword_info` · `cluster_finder` · `path_finder`).
- Allow outbound network access to `fonts.googleapis.com` (fonts · falls back to system fonts if blocked).
- python3 (standard library) required · no pip install needed.

## Execution

When the user asks for a search journey analysis, **you must Read
`references/path-opportunity.md` first**, then execute from Step 0 in order.
Do not skip steps on your own.

`{SKILL_DIR}` is the absolute path of the directory this SKILL.md sits in
(`references/` · `_shared/` · `api/` · `scripts/` are at the same level).

## Two runtime inputs: TARGET MARKET and REPORT LANGUAGE

This edition serves every market, so it takes **two independent settings**. Establish both
**before any tool call** (Step 0 of `references/query-opportunity.md`):

1. **TARGET MARKET (`gl`)** — the search market to analyze: `kr`, `jp` or `us`.
   It is passed to the ListeningMind MCP tools and to the aggregator as `--gl <MARKET>`.
2. **REPORT LANGUAGE (`lang`)** — the language of the report and of the whole conversation:
   `kr` (Korean), `jp` (Japanese) or `us` (English).
   It is passed to the renderer as `--lang <REPORT_LANGUAGE>`.

**The two are independent.** Analyzing the US market and reporting in Japanese
(`--gl us --lang jp`) is a valid, expected combination. Never infer one from the other.

If the user's request does not make both values explicit, **ask once, in a single short
question, and do not guess.** Do not start any MCP call, aggregation or rendering until
both values are fixed.

## Inputs (ask the user in chat at Step 0)

1. **Seed keyword**: the analysis target (written in the language of the target market —
   Korean for `kr`, Japanese for `jp`, English for `us`)
2. **TARGET MARKET (`gl`)**: `kr` · `jp` · `us`
3. **REPORT LANGUAGE (`lang`)**: `kr` · `jp` · `us`
4. **Time point**: `curr` (current · default) / `3m` · `6m` · `9m` · `12m`

If the seed is already given, proceed with it. If market or report language is missing,
ask once — there is no default. The time point defaults to `curr` when unspecified.

**Never ask for an API key** — data comes from the MCP connector. If an MCP tool call fails
with "tool not found", the connector is not connected: ask the user to connect the
ListeningMind MCP connector and stop. **Do not invent data.**

## Output

`{WORKDIR}/path-opportunity-report.html` — a self-contained HTML file (dashboard↔A4 toggle · printable PDF).
`{WORKDIR}` is `tmp/reports/listeningmind-path-opportunity-{seed}-{timestamp}/` inside the running project.

---

## MCP call protocol

Data comes from the **ListeningMind MCP tools**. Because the caller is **you (the LLM)**
and not code, two things are your responsibility: **① check the cache ② secure the
response file**.

### Discover SKILL_DIR dynamically (at the top of every Bash command)

```bash
SKILL_DIR=$(find ~/.claude/skills ~/.claude/plugins /mnt/skills /mnt/user-data \
    ~/.codex/skills ~/.gemini/skills ~/.config/skills ./skills . \
    -maxdepth 4 -type d -name lm-pathfinder-report 2>/dev/null \
    | grep -v '\.trash' | head -1)
[ -z "$SKILL_DIR" ] && echo "❌ skill path not found" >&2
echo "SKILL_DIR=$SKILL_DIR"
```

Install paths differ per host. The list above is only the set of known paths, so **if it comes
back empty, find the actual directory this SKILL.md sits in and use that** (the place where
`references/` · `_shared/` · `scripts/` are at the same level).

Use it in every later command · `python3 "$SKILL_DIR/scripts/mcp_cache.py" ...` · never hardcode a `cd`.

#### 2 steps per call (no exceptions)

```bash
# ① Before the call · check the cache
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup <tool> \
  --params '<MCP parameter JSON>' --out "{WORKDIR}/<file>.json"
```

- **exit 0 = hit** · the file is already filled → **do not call MCP.** Go straight on to the next step.
- **exit 2 = miss** · go to ②.

```bash
# ② Call MCP → dump the raw response verbatim → store it in the cache
python3 {SKILL_DIR}/scripts/mcp_cache.py store <tool> \
  --params '<exactly the same parameter JSON as in ①>' --file "{WORKDIR}/<file>.json" \
  --expect <record count read from the envelope>
```

`--params` **must be identical** in ① and ②. If they differ, the next run will not hit the cache.

### Response file rules (the most important part)

The aggregator (`_shared/render/*_aggregate.py`) reads the MCP response as-is.
So the response must sit in the file **raw and unprocessed**.

**Rule · pass files around by path only.** Both `mcp_cache.py store --file` and
`*_aggregate.py --raw` take a path and read it themselves. You do not need to pull the
contents into your context and rewrite them, and you must not (large payloads lose records).

- **No summarizing, excerpting or restructuring.** The moment you do, the aggregator cannot read
  it or the numbers go wrong.
- **Do not drop a single record.** If it is the top 1,000, that means all 1,000.
- Verify with `--expect <record count>` — the length of the `data` array (for cluster_finder, the
  length of `rels` + the number of `communities`).
  keyword_info may return a few **more** keywords than you requested (the server adds notation
  variants) · enter the number received, not the number requested. If it does not match, `store`
  rejects it, and then you redo it. **Do not proceed with truncated data.**
**Default · the host saved the result to a file** (bulk queries almost always land here)
The tool result arrives as this instead of a body:
`Tool result too large for context, stored at /mnt/user-data/tool_results/....json`
In Claude Code it arrives as `Error: result (N characters) exceeds maximum allowed tokens. Output has been
saved to …/tool-results/….txt`. **Do not be fooled by the leading `Error:` or the `.txt` extension** — the
content is the raw JSON. Do not follow the accompanying "read the file to the end" advice either; just pass the
path. **Do not call the tool again** (it costs credits twice).
**It is not a failure — it means the entire response is in that file.** Pass the path straight through:
```bash
cp "<saved path>" "{WORKDIR}/lm_query.json"
```

**Exception · the response arrived in the body** (small payloads)
Only then write the raw text with a heredoc:
```bash
cat > "{WORKDIR}/lm_query.json" <<'DUMP_EOF'
<the entire raw MCP response JSON>
DUMP_EOF
```

**Absolutely forbidden** · reducing ① the number of keywords queried, ② the `data_type`, or
③ summarizing/excerpting records because the response is large. All three silently corrupt the
report's numbers. If reducing scope seems unavoidable, **do not proceed — report it to the user.**

### Session cache

`~/.lima-agents/mcp-cache/<session>/` · within the same conversation, the same `(tool + parameters)`
does not call MCP again. **Data another report skill fetched with the same parameters is reused too** —
the structural queries (`intent_finder` · `path_finder` · `cluster_finder`) take the same parameters as
the sibling skills, so they hit directly. `keyword_info` does not hit, because each skill passes a
different keyword list (total-report calls it once for the union of the 3 finders, so instead its own
internal duplicates disappear).
To bypass the cache, set `LIMA_MCP_REFRESH=1`.

### user_query · record the query alongside the call in the history

The MCP tools (path_finder · keyword_info) accept an optional `user_query` parameter and store it in the history
(for query–search correlation analysis). **It is not attached automatically**, so you put it in yourself.

Put in the **user's utterance verbatim** · no translating, summarizing or paraphrasing.
It is not part of the cache key, so the cache still hits even when the wording changes.
