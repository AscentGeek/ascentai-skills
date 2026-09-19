## Check the prerequisites

`{SKILL_DIR}/_shared/render/{path_aggregate.py,render_report.py,components.py,components_path.py}` and
`{SKILL_DIR}/_shared/{styles,labels,templates}` must all be present.
Only python3 (standard library) is used. The report puts a search journey flow diagram, route cards
and hub cards on top of the same card shell as the zip customer-analysis (no external JS dependency).

This report ports the analysis frame of the ListeningMind **PathFinder** agent — reading search
behaviour as a **directed graph (the consumer search journey / CDJ)** and deriving the
**main routes (top 5)** and the **key branch points (hubs, top 3)**.

<!-- NOTE: the snapshot below lives in the source repository only — it is not
     shipped inside this skill. It is diff material for maintainers, not runtime input.
     Snapshot: skills/pathfinder-report/prompts/agent_path.framework.kr.md
     (ascentkorea-hubble-ai-api prompt_builder.py:56-109 DEFAULT_PROMPTS["path"]).
     The production prompt is the `agent_path` row in the gpt_prompt DB and is not exposed in this
     repository, so the in-repo fallback framework is kept as the snapshot.
     The Step 3 prompt is a JSON-output adaptation of that frame (understand the structure →
     top 5 routes across 3 flow types → 3 hubs and branches). The chat-only markup
     (:k[]/:::accordion) and the "state exact numbers" rule are deliberately excluded
     (numbers are filled in by Python). -->

**PathFinder data contract**: the public `path_finder` returns only the bare routes
(`data: List[List[str]]`) with no node metrics. To reproduce the internal `PathDataDTO`
(paths + info + intent) that the production agent sees, we make **two calls** —
`path_finder` (the journey structure) and `keyword_info` (search volume, intent and monthly trend
for the unique nodes on those routes). That keeps the same principle as queryfinder —
**numbers are computed by Python from the real API** — and route and hub ranking use `volume`
(average monthly search volume) as the primary metric, exactly like the production agent.

## Execution procedure

### Step 0 — Collect inputs + create the working folder

Data comes from the **ListeningMind MCP tools**. **Never ask for an API key** —
do not even look for a key in environment variables, `.env`, a DB or anywhere else.

You need four inputs, and **TARGET MARKET and REPORT LANGUAGE are independent of each other**
(analyzing the US market and writing the report in Japanese is a valid combination):

> Starting the search journey analysis.
> 1. **Seed keyword** — skip if you already gave it
> 2. **TARGET MARKET (`gl`)** — the search market to analyze: `kr` · `jp` · `us`
> 3. **REPORT LANGUAGE (`lang`)** — the language of the report: `kr` (Korean) · `jp` (Japanese) · `us` (English)
> 4. **Time point** — `curr` (current) by default; for a comparison with the past, `3m`/`6m`/`9m`/`12m`

If the seed is already given, proceed with it. If the market or the report language is not explicit
in the user's request, **ask once, in a single short question, and do not guess.** There is no
default for either — never derive the report language from the market or the market from the report
language. **Fix both values before any tool call.** The time point defaults to `curr` when
unspecified, so it does not need to be asked for.

From this point on, `<MARKET>` is the value of TARGET MARKET and `<REPORT_LANGUAGE>` is the value of
REPORT LANGUAGE. **Conduct the whole conversation with the user in REPORT LANGUAGE**
(`kr` → Korean, `jp` → Japanese, `us` → English).

**If the MCP connector is missing** · the tool call in Step 1 fails with "tool not found".
In that case, ask the user to **connect the ListeningMind MCP connector** and stop.
Do not invent data.

Once you have the inputs:

```bash
SAFE_SEED=$(echo "<SEED>" | tr ' /\\:*?"<>|' '_')
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
WORKDIR="$PWD/tmp/reports/listeningmind-path-opportunity-${SAFE_SEED}-${TIMESTAMP}"
mkdir -p "$WORKDIR"
echo "working folder: $WORKDIR"
```

From here on, replace `{WORKDIR}` with that absolute path.

### Step 1 — Collect the data (2 MCP calls)

> **Every call is three steps, without exception** (SKILL.md §Step 4):
> ① `mcp_cache.py lookup` → ② (on a miss) call MCP + secure the response file + `store` → ③ `log_event.py --type tool_call`
>
> If ① exits **0**, the file is already filled: **do not call MCP**, go straight to ③
> (`--cached --used-credits-delta 0`). If it exits **2**, go to ②.

**1a. Search journeys (routes)** — `path_finder` (response `data` = an array of routes, `List[List[str]]`)

```bash
# ① check the cache
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup path_finder \
  --params '{"keyword":"<SEED>","gl":"<MARKET>","time_point":"<TIME_POINT>","limit":300}' \
  --out "{WORKDIR}/lm_path.json"
```

On a miss, call the **`path_finder` MCP tool** with these parameters:

```json
{"keyword": "<SEED>", "gl": "<MARKET>", "time_point": "<TIME_POINT>", "limit": 300,
 "user_query": "<the user's utterance, verbatim>"}
```

> `limit` (the number of routes) defaults to 300. `time_point` is the value collected in Step 0
> (`curr` by default). Each inner array in the response's `data` is **one ordered search journey**
> (q0 → q1 → q2 …).
>
> `user_query` is excluded from the cache key, so do not put it in `--params` (see the lookup above).

Secure the response as `{WORKDIR}/lm_path.json` and store it in the cache (if the host saved the
response to a file because it was large, `cp` that path; if it arrived in the body, use a heredoc —
see SKILL.md §Response file rules):

```bash
# ② store in the cache
python3 {SKILL_DIR}/scripts/mcp_cache.py store path_finder \
  --params '{"keyword":"<SEED>","gl":"<MARKET>","time_point":"<TIME_POINT>","limit":300}' \
  --file "{WORKDIR}/lm_path.json" --expect <length of the data array>

# ③ emit tool_call
python3 "$SKILL_DIR/scripts/log_event.py" --type tool_call --session-id "$SID" \
  --tool path_finder \
  --request-body '{"keyword":"<SEED>","gl":"<MARKET>","time_point":"<TIME_POINT>","limit":300}' \
  --used-credits-delta <cost_detail.total_cost> \
  --used-credits-cumulative <used_credits> \
  --intent journey_analysis
```

**1b. Enrich the nodes with search volume** — pull the **unique keywords** that appear on the routes
and get per-node metrics from `keyword_info` (`data_type=all` → includes `ads_metrics`, `intents`
and `monthly_volume`):

```bash
python3 - "{WORKDIR}/lm_path.json" <<'MKPARAM' > "{WORKDIR}/kw_params.json"
import json, sys
d = json.load(open(sys.argv[1]))
data = d.get("data") or (d.get("result", {}) or {}).get("paths") or []
# Collect unique keywords in the order they appear on the routes (keyword_info maxItems=1000).
seen, kws = set(), []
for path in data:
    for kw in (path if isinstance(path, list) else []):
        if isinstance(kw, str) and kw.strip() and kw not in seen:
            seen.add(kw); kws.append(kw.strip())
kws = kws[:1000]
print(json.dumps({"keywords": kws, "gl": "<MARKET>", "data_type": "all"}, ensure_ascii=False))
MKPARAM

# ① check the cache
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --out "{WORKDIR}/lm_nodes.json"
```

On a miss, call the **`keyword_info` MCP tool** with the contents of `kw_params.json` plus
`user_query`, secure the response as `{WORKDIR}/lm_nodes.json`, then store it:

```bash
# ② store in the cache
python3 {SKILL_DIR}/scripts/mcp_cache.py store keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --file "{WORKDIR}/lm_nodes.json" --expect <length of the data array>

# ③ emit tool_call
python3 "$SKILL_DIR/scripts/log_event.py" --type tool_call --session-id "$SID" \
  --tool keyword_info --request-body "$(cat "{WORKDIR}/kw_params.json")" \
  --used-credits-delta <cost_detail.total_cost> \
  --used-credits-cumulative <used_credits> \
  --intent journey_analysis
```

- If either response has `result` = `FAILED`, or a tool call fails, stop and report
  (check the connector, the seed and the market). Do not invent anything.
- If `path_finder`'s `data` (the routes) is empty, check the seed, market and time point, and stop.
- It is fine if `keyword_info` does not return every keyword — those nodes render with volume 0 and
  the route structure is preserved. But if most of them are 0, the node enrichment failed: re-check
  the market.

### Step 2 — Aggregate the journey graph

```bash
python3 {SKILL_DIR}/_shared/render/path_aggregate.py context \
  --paths "{WORKDIR}/lm_path.json" --nodes "{WORKDIR}/lm_nodes.json" \
  --seed "<SEED>" --gl <MARKET> --date <YYYY-MM-DD> --time-point <TIME_POINT> \
  --out "{WORKDIR}/lm_path_result.json"
```

`lm_path_result.json` holds the nodes (volume, intent), the edges (derived from route adjacency),
the hubs (branch count) and the journey flow diagram (`flowTree`), plus the LLM analysis inputs:
`pathsText` (candidate routes), `hubsCsv` (candidate hubs) and `nodesCsv`. Read
`{WORKDIR}/lm_path_result.json` and use the `pathsText` and `hubsCsv` values inside it as the input
to Step 3.

### Step 3 — PathFinder analysis (LLM) → lm_paths_raw.json

Analyze `pathsText` (candidate routes) and `hubsCsv` (candidate hubs) from `lm_path_result.json`
yourself, following the rules below, and save the result **as JSON only** to
`{WORKDIR}/lm_paths_raw.json`.

---

#### Analysis rules (Search Journey Analyst)

You are a search journey insight analyst. Your goal is to read the **search journeys (routes)**
consumers take from keyword to keyword and the **key branch points (hubs)**, and to reveal where
they converge toward conversion and where they drop off.

**Input**:
- `pathsText`: the candidate journeys. Each line = `N. A → B → C …  (combined volume N)`,
  in descending order of volume.
- `hubsCsv`: the candidate hubs. `name,volume,out_degree,path_count,downstream`.
  `out_degree` = how many next keywords branch off this one (the branch count). Higher means a more
  important branch point.
- `nodesCsv`: the node table (for reference). `id,name,volume,volume_trend,intent,out_degree,path_count,outgoing`.

**Global rules**:
- **Evidence only**: never invent a keyword or a fact that is not in the input above.
- **No numeric claims (important)**: do **not** assert numbers in prose — no "the largest",
  "N of them", "N times more". The code fills numbers into the badges and chips as facts, so you
  write **qualitative interpretation only** (why this journey, where it splits, where it leaks or
  converges, how to act on it).
- **Markup**: only `<strong>...</strong>` is allowed, for a key noun phrase that needs emphasis.
  Never use any other markup (`:k[]`, `:::accordion`, `➊`, code blocks, tables).
- **Output language** = REPORT LANGUAGE (`<REPORT_LANGUAGE>`): `kr` → Korean, `jp` → Japanese,
  `us` → English. This is the report's language, not the market's — when they differ, the keywords
  stay in the market's language while everything you write is in REPORT LANGUAGE.
- `path`, `keyword` and `evidenceKeywords` must use **only keyword strings that actually appear in
  the input**, verbatim (no translating, altering or inventing). The code strips keywords that do not
  appear, so anything you invent simply disappears from the report.

**① Analysis overview (overview)**
- One or two sentences (roughly 100–200 characters) on the core insight running through the whole
  journey graph. Prose, no subheadings.
- Summarize along which axis the journeys split and where they converge or leak. It is placed on the
  cover as the data-based summary.

**② Top 5 main routes (topPaths)** — at most 5
- Pick 5 representative journeys from `pathsText` and label each with a **flow type**:
  1. **Converging toward conversion** → `flowType: "conversion"`
  2. **Stalling in comparison or verification** → `flowType: "comparison"`
  3. **Leaking to risk or distrust** → `flowType: "risk"` (**at most 2**)
- Each route:
  - `flowType`: one of the three (`conversion` | `comparison` | `risk`)
  - `path`: the journey's keyword sequence (the exact strings from the input, order preserved) —
    at least 2 (one transition or more)
  - `intent`: one line on the intent of the customer travelling this route (qualitative)
  - `leakOrMerge`: the point where customers **leave** the route, or where routes **merge** and the
    route gets stronger (qualitative)
  - `action`: one or two sentences on how to fix or reinforce it (qualitative)
  - `evidenceKeywords`: the supporting keywords/hubs for this route (2–4, from the input only)

**③ Top 3 key branch points (hubs)** — at most 3
- From the keywords with a high `out_degree` in `hubsCsv`, pick the 3 most important branch points.
- Each hub:
  - `keyword`: the hub keyword (verbatim from the input)
  - `meaning`: one sentence on what this branch means (what is on the customer's mind)
  - `dilemmas`: 2–3 things the customer is weighing here (array of strings)
  - `actions`: 2 actions we can take right away (array of strings)

---

#### Output format — JSON only (no markdown, no commentary)

```json
{
  "overview": "The core insight, 1–2 sentences",
  "topPaths": [
    {
      "flowType": "conversion",
      "path": ["refrigerator", "refrigerator price", "kimchi refrigerator price"],
      "intent": "One line on the intent of the customer travelling this route",
      "leakOrMerge": "Where customers leave or where routes merge",
      "action": "How to fix or reinforce it, 1–2 sentences",
      "evidenceKeywords": ["supporting keyword 1", "supporting keyword 2"]
    }
  ],
  "hubs": [
    {
      "keyword": "refrigerator",
      "meaning": "What this branch means, 1 sentence",
      "dilemmas": ["what the customer is weighing 1", "what the customer is weighing 2"],
      "actions": ["action 1", "action 2"]
    }
  ]
}
```

Save that JSON to `{WORKDIR}/lm_paths_raw.json`.

### Step 4 — Post-process the routes and hubs (sum volumes · filter hallucinations)

```bash
python3 {SKILL_DIR}/_shared/render/path_aggregate.py paths \
  --raw-paths "{WORKDIR}/lm_paths_raw.json" \
  --context "{WORKDIR}/lm_path_result.json" \
  --out "{WORKDIR}/lm_paths.json"
```

This script computes each route's per-node volume chips, combined volume badge and step count, and
each hub's volume, branch count and downstream keywords, saves them in card form, and passes
Step 3's `overview` through as the cover summary.

It also **blocks hallucination**: anything in `path`, `evidenceKeywords` or a hub's `keyword` that is
not a real graph node is removed, and routes left with fewer than 2 real nodes, or hubs that do not
appear, are discarded entirely. If this filter empties Step 3's output completely, the script stops
with an error — redo Step 3.

### Step 5 — Insights and recommended actions (LLM) → lm_actions.json

Working from the routes and hubs in `{WORKDIR}/lm_paths.json`, save the JSON below to
`{WORKDIR}/lm_actions.json`. Write it in REPORT LANGUAGE (`<REPORT_LANGUAGE>`).
**No numeric claims** (same rule as Step 3) and no markup other than `<strong>`.

- `synthesis`: two or three sentences of overall assessment across the journey and branch landscape
- `insights`: **exactly 3** detailed insights `{"title","body"}` — behaviour-based conclusions found
  in the journeys.
- `now`: 2–3 actions to try right away `{"title","body"}`
- `future`: 2–3 opportunities to watch `{"title","body"}`

```json
{
  "synthesis": "Two or three sentences of overall assessment",
  "insights": [{"title": "Title", "body": "Behaviour-based conclusion, 1–2 sentences"}],
  "now": [{"title": "Action title", "body": "What to do, 1–2 sentences"}],
  "future": [{"title": "Opportunity title", "body": "What the opportunity is, 1–2 sentences"}]
}
```

### Step 5.5 — Translate the keywords (only when MARKET language ≠ REPORT LANGUAGE)

The report shows keywords exactly as they are searched in the market. When the report language
differs from the market's language, the reader cannot read them, so build the translations that
back the **"Translate keywords" toolbar button** here. Skip this step when the market language and
REPORT LANGUAGE are the same — the button then does not appear at all.

First extract only the keywords that actually appear on screen:

```bash
python3 {SKILL_DIR}/_shared/render/path_aggregate.py keywords \
  --paths "{WORKDIR}/lm_paths.json" --context "{WORKDIR}/lm_path_result.json" \
  --category "<SEED>" --out "{WORKDIR}/kw_to_translate.json"
```

Read the `keywords` array in that file and translate **every** keyword into REPORT LANGUAGE,
saving `{WORKDIR}/lm_keyword_tr.json` as `{"original": "translation", ...}`.

- Use the **original string as the key**, byte for byte (same spacing, same spelling variants).
  A key that does not match leaves that chip untranslated.
- Do **not** add keywords that are not in the list, and do not drop any.
- **Brand and product names take the form commonly used in REPORT LANGUAGE**
  (e.g. `다이소` → `Daiso` / `ダイソー`). If there is no common form, keep the original.
- These are search terms, not sentences. Keep them short, in the shape someone would type.
- Translate only — never append a gloss or an explanation.

### Step 6 — Render the HTML

```bash
python3 {SKILL_DIR}/_shared/render/render_report.py --skill path-opportunity \
  --paths "{WORKDIR}/lm_paths.json" \
  --actions "{WORKDIR}/lm_actions.json" \
  --meta "{WORKDIR}/lm_path_result.json" \
  --category "<SEED>" --gl <MARKET> --lang <REPORT_LANGUAGE> --date <YYYY-MM-DD> \
  --out "{WORKDIR}/path-opportunity-report.html"
# If you did Step 5.5, append --translations "{WORKDIR}/lm_keyword_tr.json"
```

`--gl` is the market that was analyzed; `--lang` is the language the report is rendered in. Pass both
— they are set independently in Step 0.

### Step 7 — Tell the user

Write the message in REPORT LANGUAGE. In English it reads:

```
✅ Search journey report created: {WORKDIR}/path-opportunity-report.html
Open it in a browser to see the journey flow diagram, the route cards, the hub cards and the
insights in dashboard or A4 view; Cmd+P saves it as an A4 PDF.
Open it on macOS: open {WORKDIR}/path-opportunity-report.html
```
