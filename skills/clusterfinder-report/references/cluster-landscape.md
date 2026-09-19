## Check the prerequisites

`{SKILL_DIR}/_shared/render/{cluster_aggregate.py,render_report.py,components.py,components_cluster.py}` and
`{SKILL_DIR}/_shared/{styles,labels,templates}` must all be present.
Only python3 (standard library) is used. The report uses the same card format as the zip
customer-analysis, plus two cluster-only sections: a **hub keyword summary table** and the
**From→To flows**.

This report ports the analysis frame of ListeningMind **ClusterFinder**'s real analysis prompt
(agent_cluster v0.7.0): it groups co-searched keyword clusters by **search purpose** and presents
each cluster's **hub (representative) keyword** and the **exploration flows** between clusters as cards.

<!-- NOTE: the snapshot below lives in the source repository only — it is not
     shipped inside this skill. It is diff material for maintainers, not runtime input.
     Snapshot: skills/clusterfinder-report/prompts/agent_cluster.v0.7.0.kr.md
     (v.0.7.0_cf_KR_0602, single keyword, 4 sections: analysis overview / top 3 purpose clusters /
     top 3 From→To flows / insights). The Step 3 prompt is a JSON-output adaptation of those
     4 sections (section 1 → overview, section 2 → clusterGroups, section 3 → flows,
     section 4 → the Step 5 actions).
     The chat-only markup (:k[]/:c[]{#}/:::accordion/➊) and the "state exact numbers" rule are
     deliberately excluded — numbers, hubs and flow edges are filled in by Python from the real
     data (decision 1).
     Multi-keyword mode (agent_cluster_multiple) and cluster drill-down (GEO / persona / ad copy)
     are out of scope for this skill (single seed only). When the production prompt is updated,
     diff against the latest active row in the gpt_prompt DB with type='agent_cluster' locale='KR'. -->

## Execution procedure

### Step 0 — Collect inputs + create the working folder

Data comes from the **ListeningMind MCP tools**. **Never ask for an API key** —
do not even look for a key in environment variables, `.env`, a DB or anywhere else.

You need three inputs, and **TARGET MARKET and REPORT LANGUAGE are independent of each other**
(analyzing the US market and writing the report in Japanese is a valid combination):

> Starting the search cluster landscape analysis.
> 1. **Seed keyword** — skip if you already gave it (ClusterFinder accepts **a single keyword** only)
> 2. **TARGET MARKET (`gl`)** — the search market to analyze: `kr` · `jp` · `us`
> 3. **REPORT LANGUAGE (`lang`)** — the language of the report: `kr` (Korean) · `jp` (Japanese) · `us` (English)

If the seed is already given, proceed with it. If the market or the report language is not explicit
in the user's request, **ask once, in a single short question, and do not guess.** There is no
default for either — never derive the report language from the market or the market from the report
language. **Fix both values before any tool call.**

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
WORKDIR="$PWD/tmp/reports/listeningmind-cluster-landscape-${SAFE_SEED}-${TIMESTAMP}"
mkdir -p "$WORKDIR"
echo "working folder: $WORKDIR"
```

From here on, replace `{WORKDIR}` with that absolute path.

### Step 1 — Collect the data (2 MCP calls)

`cluster_finder` returns only the **co-search graph** (cluster communities + edges); it carries
**no search volume and no intent**. So ① call `cluster_finder` for the communities and edges, then
② pass the keywords inside them to `keyword_info` to attach search volume and intent.

> **Every call is three steps, without exception** (SKILL.md §Step 4):
> ① `mcp_cache.py lookup` → ② (on a miss) call MCP + secure the response file + `store` → ③ `log_event.py --type tool_call`
>
> If ① exits **0**, the file is already filled: **do not call MCP**, go straight to ③
> (`--cached --used-credits-delta 0`). If it exits **2**, go to ②.

**1a. Cluster graph** — `cluster_finder`

```bash
# ① check the cache
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup cluster_finder \
  --params '{"keyword":"<SEED>","gl":"<MARKET>","data_type":"all","hop":2,"limit":1000,"orientation":"UNDIRECTED","time_point":"curr"}' \
  --out "{WORKDIR}/lm_cluster.json"
```

On a miss, call the **`cluster_finder` MCP tool** with these parameters:

```json
{"keyword": "<SEED>", "gl": "<MARKET>", "data_type": "all", "hop": 2, "limit": 1000,
 "orientation": "UNDIRECTED", "time_point": "curr",
 "user_query": "<the user's utterance, verbatim>"}
```

> `data_type` must be **`all`** — you need both `communities` (the cluster dict) and `rels` (the
> edge array) to compute the hubs (connection centrality) and the flows (movement between clusters).
> With `communities` only (the `data_type` default) the flow analysis comes back empty; with `rels`
> only the communities are empty and no cards can be built.
> `limit` caps the number of **relations (edges)**, not keywords, and `hop` is the graph traversal
> depth (1–3).
>
> `user_query` is excluded from the cache key, so do not put it in `--params` (see the lookup above).

Secure the response as `{WORKDIR}/lm_cluster.json` and store it in the cache (if the host saved the
response to a file because it was large, `cp` that path; if it arrived in the body, use a heredoc —
see SKILL.md §Response file rules):

```bash
# ② store in the cache
python3 {SKILL_DIR}/scripts/mcp_cache.py store cluster_finder \
  --params '{"keyword":"<SEED>","gl":"<MARKET>","data_type":"all","hop":2,"limit":1000,"orientation":"UNDIRECTED","time_point":"curr"}' \
  --file "{WORKDIR}/lm_cluster.json" --expect <length of rels + number of communities>

# ③ emit tool_call
python3 "$SKILL_DIR/scripts/log_event.py" --type tool_call --session-id "$SID" \
  --tool cluster_finder \
  --request-body '{"keyword":"<SEED>","gl":"<MARKET>","data_type":"all","hop":2,"limit":1000}' \
  --used-credits-delta <cost_detail.total_cost> \
  --used-credits-cumulative <used_credits> \
  --intent perception_mapping
```

**1b. Keyword detail** — query search volume and intent for **every keyword** in the `communities`
above (deduplicated, top 1,000) through `keyword_info` (`data_type=all` → includes `ads_metrics`
and `intents`):

```bash
python3 - "{WORKDIR}/lm_cluster.json" <<'MKPARAM' > "{WORKDIR}/kw_params.json"
import json, sys
d = json.load(open(sys.argv[1]))
comm = (d.get("data") or {}).get("communities") or {}
# Flatten the community values (each cluster's keyword list), dedupe, take the top 1,000.
seen, kws = set(), []
for members in comm.values():
    for k in (members or []):
        if isinstance(k, str) and k not in seen:
            seen.add(k); kws.append(k)
kws = kws[:1000]  # keyword_info maxItems=1000
print(json.dumps({"keywords": kws, "gl": "<MARKET>", "data_type": "all"}, ensure_ascii=False))
MKPARAM

# ① check the cache
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --out "{WORKDIR}/lm_keyword_info.json"
```

On a miss, call the **`keyword_info` MCP tool** with the contents of `kw_params.json` plus
`user_query`, secure the response as `{WORKDIR}/lm_keyword_info.json`, then store it:

```bash
# ② store in the cache
python3 {SKILL_DIR}/scripts/mcp_cache.py store keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --file "{WORKDIR}/lm_keyword_info.json" --expect <length of the data array>

# ③ emit tool_call
python3 "$SKILL_DIR/scripts/log_event.py" --type tool_call --session-id "$SID" \
  --tool keyword_info --request-body "$(cat "{WORKDIR}/kw_params.json")" \
  --used-credits-delta <cost_detail.total_cost> \
  --used-credits-cumulative <used_credits> \
  --intent perception_mapping
```

- If either response has `result` = `FAILED`, or a tool call fails, stop and report
  (check the connector, the seed, the market and the plan). Do not invent anything.
- If `communities` is empty (zero clusters), stop and report.

### Step 2 — Aggregate the cluster context

```bash
python3 {SKILL_DIR}/_shared/render/cluster_aggregate.py context \
  --cluster "{WORKDIR}/lm_cluster.json" \
  --keyword-info "{WORKDIR}/lm_keyword_info.json" \
  --seed "<SEED>" --gl <MARKET> --date <YYYY-MM-DD> \
  --out "{WORKDIR}/lm_cluster_result.json"
```

This script fuses the two responses and:
- assigns a **cluster letter** to each keyword (0→A, 1→B, …),
- computes each cluster's **hub keyword** from `rels` (highest connection centrality = degree; ties
  and absences fall back to highest search volume),
- computes the **outgoing** links (connections to other clusters) per keyword and per cluster,
- builds the **`csv`** (columns `n,v,c,h,o,i`) that goes into the LLM analysis.

Read `{WORKDIR}/lm_cluster_result.json` and use the `csv` value inside it as the input to Step 3.

### Step 3 — ClusterFinder analysis (LLM) → lm_groups_raw.json

Analyze the `csv` from `lm_cluster_result.json` yourself, following the rules below (ported from
agent_cluster v0.7.0), and save the result **as JSON only** to `{WORKDIR}/lm_groups_raw.json`.

---

#### Analysis rules (search data insight analyst — ClusterFinder)

You are a search data insight analyst. Working from ListeningMind ClusterFinder results
(co-search communities), you interpret the search intent, the user movement paths and the market
structure **inside a single keyword's market**.

**Input**: each `csv` row = `n, v, c, h, o, i`
- `n` = keyword, `v` = **average monthly search volume** (always use this value for volume).
- `c` = the **cluster letter** this keyword belongs to (A, B, C, …) — a topic community grouped by co-search.
- `h` = **is it the hub keyword** (`TRUE` = the representative/central keyword of that cluster).
- `o` = the **other cluster letters** this keyword connects to (pipe-separated). This is the evidence
  for movement between clusters.
- `i` = the dominant search intent (information seeking / navigation / commercial research / transaction).

**Global rules**:
- **Evidence only**: never invent a keyword, cluster or number that is not in the csv.
- **No numeric claims (important)**: do **not** assert numbers in prose — no "the largest",
  "N searches", "N times more". Numbers, hubs and flow edges are filled in as facts by the code in
  the report's badges, tables and chips, so you write **qualitative interpretation only**
  (why these group together, what intent they carry).
- **No markup**: never use `:k[]`, `:c[]{#}`, `:::accordion`, `➊➋➌`, code blocks, tables or any other
  special markup. Put plain text strings into the JSON values.
- **Refer to clusters by letter**: `memberClusters` and `path` take only cluster letters that
  actually exist in the csv (A, B, C, …). A **keyword string** (`hubKeyword`) must be copied verbatim
  from the csv's `n` value.
- **Output language** = REPORT LANGUAGE (`<REPORT_LANGUAGE>`): `kr` → Korean, `jp` → Japanese,
  `us` → English. This is the report's language, not the market's — when they differ, the keywords
  stay in the market's language while everything you write is in REPORT LANGUAGE.
- Describe the target customer as a **search behaviour type** (brand comparer, price checker,
  feature verifier, newcomer gathering information, about to buy, …), never as an age or gender
  estimate. Demographic assertions are forbidden.

**① Analysis overview (overview)**
- One or two sentences (roughly 100–200 characters) on the core structure running through this
  keyword market: which search intent axis is strong, what the main clusters are like, where the
  weight of demand sits. Prose, no subheadings.
- This sentence is placed on the report cover under "Background & Purpose" as the
  **data-based summary**.

**② Top 3 purpose clusters (clusterGroups)** — at most 5 (3 core ones recommended)
- **Identify the hub**: the keyword with `h=TRUE` represents that cluster.
- **Merge by intent**: group **several clusters into one** when they share a semantically similar
  search purpose (brand line-up exploration, recommendation and comparison, price and purchase,
  how-to and care, reviews, …). A group of a single cluster is allowed, but similar intents must
  always be merged.
- Each group:
  - `title`: the name of the search purpose (clear and specific, e.g. "Brand line-up and price exploration")
  - `character`: the nature of the group / its target search behaviour type (e.g. "Brand comparer")
  - `memberClusters`: the **list of cluster letters** merged into this purpose (e.g. `["B","C"]`)
  - `who`: one or two sentences on the context and mindset of the people searching this cluster (qualitative)
  - `insight`: one or two sentences of marketing/content implication (qualitative)

**③ Top 3 From → To flows (flows)** — at most 5 (3 core ones recommended)
- Use **only routes that actually have a connection**, taken from the hub keyword's `o` (outgoing) column.
- Each flow:
  - `hubKeyword`: the hub keyword the flow starts from (the csv's `n`, verbatim)
  - `character`: the nature of the movement (e.g. "Exploring candidates → settling on a brand")
  - `path`: the **order of cluster letters** travelled (e.g. `["D","B"]` = D→B). Two or more.
  - `insight`: one or two sentences on why this transition happens (qualitative)

---

#### Output format — JSON only (no markdown, no markup)

```json
{
  "overview": "One or two sentences on the core structure of this keyword market",
  "clusterGroups": [
    {
      "title": "Name of the search purpose",
      "character": "Brand comparer",
      "memberClusters": ["B", "C"],
      "who": "One or two sentences on the context of the people searching this cluster",
      "insight": "One or two sentences of implication"
    }
  ],
  "flows": [
    {
      "hubKeyword": "The hub keyword, verbatim",
      "character": "The nature of the movement",
      "path": ["D", "B"],
      "insight": "One or two sentences on why this transition happens"
    }
  ]
}
```

Save that JSON to `{WORKDIR}/lm_groups_raw.json`.

### Step 4 — Post-process the groups (sum volumes · verify hubs and flows)

```bash
python3 {SKILL_DIR}/_shared/render/cluster_aggregate.py groups \
  --raw-groups "{WORKDIR}/lm_groups_raw.json" \
  --context "{WORKDIR}/lm_cluster_result.json" \
  --out "{WORKDIR}/lm_groups.json"
```

This script sums and sorts each group's `volume_avg`, picks the representative keywords (with their
volume labels), computes the group header badges — `volumeLabel` (summed volume), `memberCount`
(number of keywords) and `clusterCount` (number of merged clusters) — and builds the
**hub keyword summary table** (`hubTable`) and the **From→To flows** (`flows`, including each path
cluster's hub keyword and the hub's `connectivity`, i.e. how many clusters it links). It then passes
Step 3's `overview` through as the cover summary. (Numbers, hubs, flow edges and connectivity are all
filled in here as facts.)

It also **blocks hallucination**: cluster letters in `memberClusters` or `path` that do not exist,
and keywords that are not in the csv, are removed here, and a group left with no real cluster and no
real keyword is discarded entirely. If Step 3's output is emptied by this filter (zero groups), the
script stops with an error — redo Step 3.

### Step 5 — Insights and recommended actions (LLM) → lm_actions.json

Working from the groups and flows in `{WORKDIR}/lm_groups.json` (this is agent_cluster's section ④),
save the JSON below to `{WORKDIR}/lm_actions.json`. Write it in REPORT LANGUAGE
(`<REPORT_LANGUAGE>`). **No numeric claims** (same rule as Step 3) and no markup.

- `synthesis`: two or three sentences of overall assessment across the cluster landscape and flows
- `insights`: **exactly 3** detailed insights `{"title","body"}` — logical conclusions grounded in the
  market structure and exploration patterns found in the data. Keep `title` short and keyword-led,
  `body` to one or two sentences.
- `now`: 2–3 actions to try right away `{"title","body"}` (each answering a specific cluster or flow)
- `future`: 2–3 opportunities to watch `{"title","body"}`

```json
{
  "synthesis": "Two or three sentences of overall assessment",
  "insights": [{"title": "Keyword-led title", "body": "Structure-based conclusion, 1–2 sentences"}],
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
python3 {SKILL_DIR}/_shared/render/cluster_aggregate.py keywords \
  --groups "{WORKDIR}/lm_groups.json" --category "<SEED>" \
  --out "{WORKDIR}/kw_to_translate.json"
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
python3 {SKILL_DIR}/_shared/render/render_report.py --skill cluster-landscape \
  --groups "{WORKDIR}/lm_groups.json" \
  --actions "{WORKDIR}/lm_actions.json" \
  --meta "{WORKDIR}/lm_cluster_result.json" \
  --category "<SEED>" --gl <MARKET> --lang <REPORT_LANGUAGE> --date <YYYY-MM-DD> \
  --out "{WORKDIR}/cluster-landscape-report.html"
# If you did Step 5.5, append --translations "{WORKDIR}/lm_keyword_tr.json"
```

`--gl` is the market that was analyzed; `--lang` is the language the report is rendered in. Pass both
— they are set independently in Step 0.

### Step 7 — Tell the user

Write the message in REPORT LANGUAGE. In English it reads:

```
✅ Search cluster landscape report created: {WORKDIR}/cluster-landscape-report.html
Open it in a browser to see the purpose cluster cards, the hub keyword summary table and the
From→To flows and insights in dashboard or A4 view; Cmd+P saves it as an A4 PDF.
Open it on macOS: open {WORKDIR}/cluster-landscape-report.html
```
