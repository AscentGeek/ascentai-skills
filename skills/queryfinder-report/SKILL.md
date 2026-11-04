---
name: lm-queryfinder-report
description: >-
  Analyzes the related queries of a seed keyword with ListeningMind MCP
  (intent_finder · keyword_info) and generates a "Query Opportunity Analysis"
  rich HTML report (dashboard/A4). Using the QueryFinder agent's analysis frame,
  it groups related queries by search purpose and by brand/non-brand, and
  presents search intent, evidence keywords, search volume and insights as cards.
  Use it when the user asks for "query opportunity analysis", "queryfinder report",
  "related query analysis", "{category} query opportunities", "search opportunity
  report", or the same requests in Korean — "쿼리 기회 분석", "쿼리파인더 리포트",
  "연관 쿼리 분석", "{카테고리} 쿼리 기회", "검색 기회 리포트" — or in Japanese —
  「クエリ機会分析」「クエリファインダーレポート」「関連クエリ分析」「{カテゴリ}のクエリ機会」
  「検索機会レポート」.
allowed-tools: Bash, Read, Write, intent_finder, keyword_info
metadata:
  author: AscentKorea
  category: output
  tags: report, related queries
---

# lm-queryfinder-report — Query Opportunity Analysis Report

## Prerequisites

- **ListeningMind MCP connector must be connected** — data comes only from the 4 MCP tools
  (`intent_finder` · `keyword_info` · `cluster_finder` · `path_finder`).
- Allow outbound network access to `fonts.googleapis.com` (fonts · falls back to system fonts if blocked).
- python3 (standard library) required · no pip install needed.

## Execution

When the user asks for a query opportunity analysis, **you must Read
`references/query-opportunity.md` first**, then execute from Step 0 in order.
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

If the seed is already given, proceed with it. If market or report language is missing,
ask once — there is no default.

**Never ask for an API key** — data comes from the MCP connector. If an MCP tool call fails
with "tool not found", the connector is not connected: ask the user to connect the
ListeningMind MCP connector and stop. **Do not invent data.**

## Output

`{WORKDIR}/query-opportunity-report.html` — a self-contained HTML file (dashboard↔A4 toggle · printable PDF).
`{WORKDIR}` is `tmp/reports/listeningmind-query-opportunity-{seed}-{timestamp}/` inside the running project.

---

## MCP call protocol

Data comes from the **ListeningMind MCP tools**. Because the caller is **you (the LLM)**
and not code, two things are your responsibility: **① check the cache ② secure the
response file**.

### Discover SKILL_DIR dynamically (at the top of every Bash command)

```bash
SKILL_DIR=$(find ~/.claude/skills ~/.claude/plugins /mnt/skills /mnt/user-data \
    ~/.codex/skills ~/.gemini/skills ~/.config/skills ./skills . \
    -maxdepth 4 -type d -name lm-queryfinder-report 2>/dev/null \
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

The aggregator (`_shared/render/query_aggregate.py`) reads the MCP response as-is.
So the response must sit in the file **raw and unprocessed**.

**Rule · pass files around by path only.** Both `mcp_cache.py store --file` and
`query_aggregate.py --raw` take a path and read it themselves. You do not need to pull the
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

