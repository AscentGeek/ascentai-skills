---
name: lm-search-context
description: >-
  Search Context analysis · Reads the consumer search paths that run through a single
  keyword (the seed) with ListeningMind MCP (path_finder · keyword_info · serp), and
  produces a short summary, a marketing to-do list, and a path map page. The user clicks
  a keyword on the map to pick a path, and right inside the page that path's search
  purpose is analyzed and saved on SERP evidence (AI overview + organic results 1-3).
  Use it when the user asks for "search context analysis", "search path map",
  "search intent from paths and SERP", or the same requests in Korean —
  "서치 컨텍스트", "Search Context 분석", "검색 맥락 분석", "이 키워드 왜 검색해?",
  "이 키워드 앞뒤로 뭘 검색해?", "검색 경로 맵", "경로 분석", "검색 목적 분석",
  "SERP 기반 검색 의도 분석", "키워드 마케팅 할 일" — or in Japanese —
  「検索コンテキスト分析」「検索経路マップ」「このキーワードの前後の検索」.
  If the user only wants the whole path structure or a top-level journey report, use
  lm-pathfinder-report instead.
allowed-tools: Bash, Read, Write, path_finder, keyword_info, serp
metadata:
  author: AscentKorea
  category: output
  tags: report, search context, search intent, serp
---

# lm-search-context — Search Context analysis

One keyword is an intersection that many search paths run through. Look at a single path and
the purpose seems singular, but in reality different contexts overlap (what the user was
looking for before, and where they go next). This skill collects every path running through
the **focus keyword** at two time points to read the branches and shifts in that context, and
connects the representative paths end to end with SERP evidence to interpret the search purpose.

## Prerequisites

- **ListeningMind MCP connector must be connected** — data comes only from the three tools
  `path_finder` · `keyword_info` · `serp`. If a tool call fails with "tool not found", ask the
  user to connect the connector and stop.
- python3 (standard library) only. No pip install needed.
- **Never ask for an API key.** Do not use one even if the user offers it. **Do not invent data.**
- If the request contains personal data (phone numbers · email · ID / card / account numbers, etc.),
  stop before calling MCP and ask for the request again (see "user_query" below).

## Execution

When a request comes in, **Read `references/workflow.md` first**, then execute from Step 0 in order.
`{SKILL_DIR}` is the absolute path of the directory this SKILL.md sits in.

## What it produces (v2)

- Looks at **the current time point only**. No comparison against the past.
- Keep the output light: **summary (2-3 sentences) + marketing to-dos (3-5) + path map**.
- **The user picks the path count (PATHS) from 100 · 200 · 300, and the default is 300.** Fetch
  that many and use them all for the summary, the marketing analysis and the initial map.
  In the page the view can be narrowed to 100 · 200 · 300 within the fetched range (no extra calls).
- **The main feature is picking a path on the map and analyzing it.** Clicking a keyword selects
  the path from the seed to that keyword, and pressing "Analyze path" (경로 분석) makes the page
  fetch a SERP (AI overview + organic 1-3) for each keyword on the path and **analyze it directly
  with the user's Claude**.
  The "Ask · Analyze path" (질문·경로 분석) chat below the map also takes questions about the path
  data on the spot (the user's Claude answers from this page's path data).
  If Claude or the ListeningMind connector is not connected, guide the user through connecting and
  granting permission. Analyses and conversations are saved and can be revisited.
- **Build the HTML for the running tool** (`render --host`, workflow.md Step 0 · 6 · 7):
  - `claude` · published to Claude.ai, the page answers path analyses and questions directly through
    the user's Claude and the ListeningMind connector, and saves them.
  - `chatgpt` · the page cannot call an LLM itself, so "Copy path analysis request" (경로 분석 요청 복사)
    and the question input **copy a request text** containing the path data, which the user pastes into
    the ChatGPT conversation (the SERPs for the path analysis are fetched by the ListeningMind connector
    attached to ChatGPT). The Claude connection guidance and the save feature do not appear.
- The required feature list is in `references/report-features.md`; verify with `scripts/check_report.py`.

## Running tool (HOST) · decide it yourself, do not ask

HOST is whichever LLM tool you — the one running this skill — are. Claude (claude.ai · Claude Code, etc.)
is `claude`, ChatGPT is `chatgpt`. Do not ask the user. Always pass it to Step 6 `render` as `--host`
(omitting it makes `auto` guess from the file system, but being explicit is the default).

## Inputs (confirm all at once at Step 0)

1. **Seed keyword** — written in the target market's language (e.g. `robot vacuum` for `us`, `패딩` for `kr`)
2. **TARGET MARKET (`gl`)** — `kr` · `jp` · `us`
3. **REPORT LANGUAGE (`lang`)** — `kr` · `jp` · `us` (independent of the market. Never infer one from the other)
4. **PATHS (path count)** — `100` · `200` · `300`, **default 300**

If market or report language is not explicit in the request, **ask once, briefly** and do not guess.
When you do, **ask for the path count in the same question** (options 100 · 200 · 300, marked
"default 300"). If the user does not pick a path count, or market and language are already clear so
you do not ask, proceed with 300 and write "300 paths" (경로 300개) in the start notice. If the user
names a number outside 100 · 200 · 300, snap it to the nearest value and say so.

## Output

`{WORKDIR}/report.html` (a single HTML file · light/dark). On Claude.ai, declare capabilities and
publish it as an artifact; on ChatGPT, hand it over as an HTML file.

## Data call cost (tell the user up front)

Tell the user with these two lines (translated into REPORT LANGUAGE).

- **One report: about 5 Lima**
- **Path analysis: 0.1 Lima per SERP**

Do not list the call breakdown or per-tool unit prices to the user.
(For reference · the report fetches at most 6 SERPs up front. Path analysis uses one SERP per keyword
on the path, and SERPs already fetched — including the initial ones — are not fetched again.
Amounts are based on actual charges as of 2026-11-24. When reporting cost after a run, use the sum of
`cost_detail.total_cost` from the responses.)

---

## MCP call protocol (same as lm-pathfinder-report)

Data comes from the **ListeningMind MCP tools**. Because the caller is **you (the LLM)** and not code,
two things are your responsibility: ① check the cache ② secure the response file.

### Discover SKILL_DIR (at the top of every Bash command)

```bash
SKILL_DIR=$(find ~/.claude/skills ~/.claude/plugins /mnt/skills /mnt/user-data \
    ~/.codex/skills ~/.gemini/skills ~/.config/skills ./skills . \
    -maxdepth 4 -type d -name lm-search-context 2>/dev/null \
    | grep -v '\.trash' | head -1)
[ -z "$SKILL_DIR" ] && echo "❌ skill path not found" >&2
echo "SKILL_DIR=$SKILL_DIR"
```

If it comes back empty, find the directory this SKILL.md actually sits in and use that.
Never hardcode a `cd` afterwards.

### 2 steps per call (no exceptions)

```bash
# ① Before the call · check the cache
python3 "$SKILL_DIR/scripts/mcp_cache.py" lookup <tool> \
  --params '<MCP parameter JSON>' --out "{WORKDIR}/<file>.json"
```

- **exit 0 = hit** · the file is already filled → **do not call MCP.**
- **exit 2 = miss** · go to ②.

```bash
# ② Call MCP → dump the raw response verbatim to a file → store it in the cache
python3 "$SKILL_DIR/scripts/mcp_cache.py" store <tool> \
  --params '<exactly the same JSON as in ①>' --file "{WORKDIR}/<file>.json" \
  --expect <length of the envelope's data array>
```

`--params` must be **identical character for character** in ① and ② for the cache to hit on the next run.

### Response file rules (the most important part)

The aggregator script reads the MCP response **unprocessed**.

- **Pass files around by path only.** Do not pull the contents into your context and rewrite them
  (records drop out of large responses).
- **No summarizing · excerpting · restructuring.** **Do not drop a single record.**
- **The host saving the result to a file is the default case.** Instead of a body you get
  `Tool result too large for context, stored at /mnt/user-data/tool_results/....json` (Claude.ai) or
  `Error: result (N characters) exceeds maximum allowed tokens. Output has been saved to …/tool-results/….txt` (Claude Code).
  Do not be fooled by the leading `Error:` or the `.txt` extension — the content is the raw JSON.
  **Do not call the tool again**; just `cp "<saved path>" "{WORKDIR}/<file>.json"`.
- **Only when the response arrived in the body**, write the entire raw text with a heredoc:
  ```bash
  cat > "{WORKDIR}/<file>.json" <<'DUMP_EOF'
  <the entire raw MCP response JSON>
  DUMP_EOF
  ```
- **Absolutely forbidden** · because the response is large, ① reducing the number of keywords queried,
  ② lowering the path `limit`, or ③ summarizing/excerpting records. If reducing scope seems unavoidable,
  do not proceed — tell the user.
### Fetch large responses with `download_url` (the default for keyword_info · serp)

`keyword_info` (hundreds of keywords) and `serp` (about 20~30KB per call × max 8 calls) have large
responses: taking them in the body eats a lot of context, and copying them through a heredoc risks
dropping records. Call these two tools **with `"response_format": "download_url"` and fetch them with
`scripts/fetch_download.py`** (`path_finder` uses the same approach).

```bash
python3 "$SKILL_DIR/scripts/fetch_download.py" \
  --url "<the response's download.browser_download_url>" --sha256 "<download.sha256>" \
  --expect <download.item_count> --out "{WORKDIR}/<file>.json"
# for serp the collection time is not in the file, only in the response meta, so always add --collected-at "<the response's collected_at>"
```

- The script verifies sha256. On failure, **do not call the tool again** — only redo the download.
- The downloaded file contains just the `data` array (no envelope). `sc.py` · `mcp_cache.py` read both shapes.
- If the download is blocked by network policy (github.com blocked), do not simply drop `response_format`
  and call again — tell the user the situation and ask how to proceed (it would buy the same data twice).
- `response_format` · `user_query` · `is_skills` · `skill_desc` are excluded from the cache key.
  A different delivery method still counts as the same data.

### Session cache

`~/.lima-agents/mcp-cache/<session>/` · within the same conversation, the same `(tool + parameters)`
is not called again. `path_finder` hits directly when the parameters match a sibling skill such as
lm-pathfinder-report.
To bypass the cache, set `LIMA_MCP_REFRESH=1`.

### user_query · record what the user asked

The MCP tools accept `user_query`. Put the **verbatim user message** that triggered the call into
**every call** (no translation, summary or rewording).

```json
"user_query": "<the user's message, verbatim>"
```

**Stop if there is personal data.** If the user's message contains personal data — phone numbers ·
email addresses · national ID or other ID numbers · card numbers · account numbers — **stop without
calling a single MCP tool.** Ask the user to resend the request with the personal data removed.
Do not strip or mask the personal data yourself and proceed with that sentence in `user_query`
(it conflicts with the verbatim rule — use the original the user resends).
A name alone, with no contact details or numbers, does not count as personal data.

> It is not attached automatically and is not part of the cache key — do not put it in
> `mcp_cache.py --params`.

### is_skills · mark the call as a skill call

The MCP tools accept `is_skills`. It defaults to `false`, so send it **as `true` on every call**
(the data and the billing are the same).

```json
"is_skills": true
```

> It is not attached automatically and is not part of the cache key — do not put it in
> `mcp_cache.py --params`.

### skill_desc · record which skill and version made the call

The MCP tools accept `skill_desc`. Put the object below into **every call**, **as a JSON object and
not a string**, next to `"is_skills": true`. The version must match `metadata.version` at the head of
this file.

```json
"skill_desc": {"name": "__SKILL_NAME__", "version": "__SKILL_VERSION__"}
```

> It is not attached automatically and is not part of the cache key — do not put it in
> `mcp_cache.py --params`.

### One call at a time

**Never call two MCP tools at the same time (in parallel).** Even when calling `serp` for several
keywords, call them one after another. Concurrent calls hit the rate limit (`Too Many Requests`).

### Failed calls

If the response's `result` is not `OK` (`FAILED`, etc.) or a tool error comes back, read the `reason`
and act as follows. Do not guess at or invent a cause.

- `Too Many Requests` — rate limited. Wait a moment and **call the same call once more**. If it fails
  again, stop and report the reason as given.
- `Insufficient Lima` — the balance is exhausted. Retrying will not help. Stop, report the reason as
  given, and say a top-up is needed.
- `Account Locked` — the plan has expired. Stop and report the reason as given (it is not a balance problem).
- `Not Authenticated` · `Invalid API Key` — the key is wrong, or the tool is outside the plan. Stop,
  report the reason as given, and ask the user to check the connector and the plan.
- `Internal Server Error` · `Service Unavailable` · any other failure — a server-side failure. Do not
  attribute it to billing. Stop and report the reason as given.
- **Never store a failed response in the cache** (`mcp_cache.py store` rejects it too). Do not move on
  to the next step or invent data.
- If one `serp` fails, you can proceed without just that evidence (`serp-trim` marks it as
  "No SERP" (SERP 없음)). If `path_finder` · `keyword_info` fail, the report cannot be built, so stop.
- State only costs confirmed from the response's `cost_detail.total_cost`, and never state the remaining balance.
