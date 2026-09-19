## Check the prerequisites

`{SKILL_DIR}/_shared/render/{render_report.py,components.py,components_total.py,query_aggregate.py,path_aggregate.py,cluster_aggregate.py,components_path.py,components_cluster.py}` and
`{SKILL_DIR}/_shared/{styles,labels,templates}` must all be present.
Only python3 (standard library) is used. The report is **one self-contained HTML** that puts
**four outer tabs** (integrated summary / query / journey / cluster) on top of the zip
customer-analysis card shell. Tabs 2–4 embed the sibling skills' (query/path/cluster) dashboard
bodies **verbatim**, and tab 1 is the **integrated summary** that only this skill produces — the
**six cross-report insight modules** that appear only once the three finders are combined
(coverage gaps · hub roles · persona × journey · revenue leaks · conversion corridors ·
prioritised backlog).

This report runs the ListeningMind **three finders** — QueryFinder (intent_finder) ·
PathFinder (path_finder) · ClusterFinder (cluster_finder) — **each with its own original analysis
frame**, then synthesises the results across them into a single consumer search journey
(audience → intent → journey).

<!-- Provenance:
     The snapshots referenced below live in the source repository only — they are not shipped
     inside this skill. They are diff material for maintainers, not runtime input.

     The Step 3 analysis prompts for tabs 2–4 are each ported from a production original —
       · query  : agent_query  v0.4.7 (skills/queryfinder-report/prompts/agent_query.1958.kr.md)
       · path   : agent_path   framework (skills/pathfinder-report/prompts/agent_path.framework.kr.md)
       · cluster: agent_cluster v0.7.0 (skills/clusterfinder-report/prompts/agent_cluster.v0.7.0.kr.md)
     Each finder step (1–4) in this integrated report calls the identical step in the sibling
     reference documents (references/{query-opportunity,path-opportunity,cluster-landscape}.md) —
     it is delegated there, not restated here.

     ★ The Step 5 "integrated analysis" prompt has NO production original (newly authored). ★
     Unlike the three finders' individual prompts, there is no corresponding row in the gpt_prompt
     DB or in the in-repo DEFAULT_PROMPTS. It was written inline in this document for this skill's
     six cross-report insight modules (coverage gaps / hub roles / persona × journey /
     revenue leaks / conversion corridors / prioritised backlog) and the integrated summary, and it
     inherits only the three finders' shared discipline (no numeric claims, no markup, evidence only).
     If it is ever promoted to a production prompt, treat this inline rule set as the SSOT.

     ★ Numbers, structure and coordinates = Python; one qualitative line = LLM (merged by id) ★
     total_aggregate.py has already computed the integrated numbers, coordinates and stable per-item
     ids into lm_total_facts.json. The LLM (Step 5) writes **only the qualitative notes keyed to
     those ids** into lm_total.json — it must not author free keywords or numbers. The note contract:
       overview (string) · hubNotes[{id,rx}] · cellNotes[{id,note}] ·
       bridgeNotes[{id,note}] · backlogNotes[{id,title,body}].
     The ids are the facts' hub#/cell#/bridge#/bl# verbatim. The renderer (components_total) merges
     facts and notes **by id**, so a note for an id that is not in facts is silently ignored (no
     separate hallucination filter is needed) — you cannot conjure an item that does not exist.
     Conversely, a facts item with no note simply renders with its numbers only. -->

## Execution procedure

### Step 0 — Collect inputs + create the working folder

Data comes from the **ListeningMind MCP tools**. **Never ask for an API key** —
do not even look for a key in environment variables, `.env`, a DB or anywhere else.

You need three inputs, and **TARGET MARKET and REPORT LANGUAGE are independent of each other**
(analyzing the US market and writing the report in Japanese is a valid combination):

> Starting the integrated search insight analysis.
> 1. **Seed keyword** — skip if you already gave it
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
WORKDIR="$PWD/tmp/reports/listeningmind-total-insight-${SAFE_SEED}-${TIMESTAMP}"
mkdir -p "$WORKDIR/q" "$WORKDIR/p" "$WORKDIR/c"
echo "working folder: $WORKDIR"
```

From here on, replace `{WORKDIR}` with that absolute path. Each finder's outputs go into
`{WORKDIR}/q` (query) · `{WORKDIR}/p` (journey) · `{WORKDIR}/c` (cluster), and the integrated
outputs (`lm_total.json`, the final HTML) sit in the `{WORKDIR}` root.

> **`<MARKET>` · `<REPORT_LANGUAGE>` · `<SEED>` · `<TIME_POINT>` · `<YYYY-MM-DD>` (= `$(date +%F)`)**
> keep the same value across every step.

### Step 1 — Collect the three finders' data (degrade gracefully on partial failure)

**Finish the structural queries first**, then enrich search volume and intent with a **single**
`keyword_info` call over the merged keyword set.

> **Why merge them** · calling per finder re-queries keywords that overlap for the same seed.
> Measured on the seed "전통주": 719 keywords when summed naively, 644 as a union — **75 (10%)**
> were duplicates. The narrower the seed, the bigger the overlap. One call removes the duplicates
> and raises the cache hit rate.

**1-A. Structural queries (one call per finder)** — use the sibling documents' 1a blocks as they
are, changing only the save path.

> **Call the three finders one at a time, in order.** The ListeningMind MCP allows only one
> concurrent request, so calling them together makes the later calls fail with
> `429 concurrent request limit`. Finish storing one response before calling the next.

| Finder | Requirement | MCP tool | Reference (1a verbatim) | Save to |
|---|---|---|---|---|
| Query | **Required** | `intent_finder` | `references/query-opportunity.md` §1a | `{WORKDIR}/q/lm_keyword_list.json` |
| Journey | Recommended | `path_finder` | `references/path-opportunity.md` §1a | `{WORKDIR}/p/lm_path.json` |
| Cluster | Optional (plan) | `cluster_finder` | `references/cluster-landscape.md` §1a | `{WORKDIR}/c/lm_cluster.json` |

Each call goes through the same **three steps** as in the sibling documents (`mcp_cache.py lookup`
→ call MCP + secure the response file + `store` → `log_event.py --type tool_call`). Only the save
path changes, per the table above.

**1-B. Union of keywords → one `keyword_info` call** — gather the keywords from whichever finders
succeeded.

```bash
python3 - "{WORKDIR}" <<'MKPARAM' > "{WORKDIR}/kw_params.json"
import json, sys
from pathlib import Path

W = Path(sys.argv[1])
seen, kws = set(), []          # preserve order so the query keywords hit the cap first

def add(k):
    if isinstance(k, str) and k.strip() and k not in seen:
        seen.add(k); kws.append(k.strip())

# Query · already sorted by search volume
f = W / "q/lm_keyword_list.json"
if f.exists():
    for k in (json.loads(f.read_text(encoding="utf-8")).get("data") or []):
        add(k if isinstance(k, str) else (k or {}).get("keyword"))

# Journey · the nodes that appear on the routes
f = W / "p/lm_path.json"
if f.exists():
    d = json.loads(f.read_text(encoding="utf-8"))
    for path in (d.get("data") or (d.get("result") or {}).get("paths") or []):
        for k in (path if isinstance(path, list) else []):
            add(k)

# Cluster · community members + both ends of every edge
f = W / "c/lm_cluster.json"
if f.exists():
    data = json.loads(f.read_text(encoding="utf-8")).get("data") or {}
    for members in (data.get("communities") or {}).values():
        for k in (members if isinstance(members, list) else []):
            add(k)
    for r in (data.get("rels") or []):
        if isinstance(r, dict):
            for fld in ("from", "to", "source", "target"):
                add(r.get(fld))
        elif isinstance(r, list):
            for k in r:
                add(k)

kws = kws[:1000]               # keyword_info maxItems=1000
print(json.dumps({"keywords": kws, "gl": "<MARKET>", "data_type": "all"}, ensure_ascii=False))
MKPARAM

# ① check the cache
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --out "{WORKDIR}/lm_keyword_info.json"

# On a miss, call the keyword_info MCP tool with the contents of kw_params.json + user_query,
# secure the response as {WORKDIR}/lm_keyword_info.json, then:

# ② store in the cache
python3 {SKILL_DIR}/scripts/mcp_cache.py store keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --file "{WORKDIR}/lm_keyword_info.json" --expect <length of the data array>

# ③ emit tool_call
python3 "$SKILL_DIR/scripts/log_event.py" --type tool_call --session-id "$SID" \
  --tool keyword_info --request-body "$(cat "{WORKDIR}/kw_params.json")" \
  --used-credits-delta <cost_detail.total_cost> \
  --used-credits-cumulative <used_credits> \
  --intent market_scan
```

> When the cap (1,000) is reached, **the query keywords go in first** (descending by volume),
> because query is the required finder and the most sensitive to truncation.

**1-C. Split it back per finder** — the journey and cluster aggregators can take the union file
**as is**. Both build a `{keyword: value}` map and then read only the keywords present in their own
structure (routes, communities), so extra entries change nothing.

**Only the query set must be filtered** — `query_aggregate context` treats **every** record it
receives as a related query, so keywords coming from the journey or cluster finders would pollute
the list.

```bash
python3 - "{WORKDIR}" <<'PY'
import json, sys
from pathlib import Path

W = Path(sys.argv[1])
info = json.loads((W / "lm_keyword_info.json").read_text(encoding="utf-8"))
rows = info.get("data") if isinstance(info.get("data"), list) else (info if isinstance(info, list) else [])

def kw_of(r):
    src = r.get("_source") if isinstance(r.get("_source"), dict) else r
    return src.get("keyword")

# keep only the keywords that are in the query list
want = set()
f = W / "q/lm_keyword_list.json"
if f.exists():
    for k in (json.loads(f.read_text(encoding="utf-8")).get("data") or []):
        want.add(k if isinstance(k, str) else (k or {}).get("keyword"))

out = dict(info) if isinstance(info, dict) else {}
out["data"] = [r for r in rows if kw_of(r) in want]
(W / "q/lm_query.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
print(f"query {len(out['data'])} / union {len(rows)}")
PY

# journey and cluster take the union as is (the aggregators ignore the extras)
cp "{WORKDIR}/lm_keyword_info.json" "{WORKDIR}/p/lm_nodes.json"
cp "{WORKDIR}/lm_keyword_info.json" "{WORKDIR}/c/lm_keyword_info.json"
```

Collected file names (identical to the siblings — the Step 2 aggregation expects exactly these):
- Query: `{WORKDIR}/q/lm_keyword_list.json`, `{WORKDIR}/q/lm_query.json`
- Journey: `{WORKDIR}/p/lm_path.json`, `{WORKDIR}/p/lm_nodes.json`
- Cluster: `{WORKDIR}/c/lm_cluster.json`, `{WORKDIR}/c/lm_keyword_info.json`

**Graceful degradation rules**:
- **Query (required)**: on `result=FAILED`, an HTTP error or an empty result, **stop everything**
  (tell the user to check the key, market and seed). No integrated report is produced without query.
- **Journey (recommended)**: on failure, log a warning and **continue without it** (tab 3 renders as
  "no data").
- **Cluster (optional)**: on **401** (key error) / **402** (payment required) / **403** (plan, market
  or permission — `cluster_finder` needs professional/advance) / **429** (concurrency limit), or when
  `communities` comes back empty, log a warning and **continue without it** (tab 4 renders as
  "no data"). 403 (plan) in particular is common, so degrade without fuss.
- **Gate (at least 2 finders)**: once collection is done, **at least two finders including query**
  must have succeeded to continue. If only query succeeded (both journey and cluster failed), there
  is nothing to integrate across — stop, and report to the user why journey/cluster came back empty
  (plan, time point, network). Run Steps 2–6 only for the finders that succeeded.

> Never **invent** data for any finder. A failed finder is simply left out — the renderer handles the
> missing tab as a "no data" card, and the integrated A4 skips that finder's pages.

### Step 2 — Per-finder context aggregation (`context`)

For each finder that succeeded, run the sibling document's **Step 2 aggregation** unchanged
(only the paths move into the subfolders).

```bash
# query
python3 {SKILL_DIR}/_shared/render/query_aggregate.py context \
  --raw "{WORKDIR}/q/lm_query.json" --seed "<SEED>" --gl <MARKET> --date <YYYY-MM-DD> \
  --out "{WORKDIR}/q/lm_query_result.json"

# journey (if collection succeeded)
python3 {SKILL_DIR}/_shared/render/path_aggregate.py context \
  --paths "{WORKDIR}/p/lm_path.json" --nodes "{WORKDIR}/p/lm_nodes.json" \
  --seed "<SEED>" --gl <MARKET> --date <YYYY-MM-DD> --time-point <TIME_POINT> \
  --out "{WORKDIR}/p/lm_path_result.json"

# cluster (if collection succeeded)
python3 {SKILL_DIR}/_shared/render/cluster_aggregate.py context \
  --cluster "{WORKDIR}/c/lm_cluster.json" --keyword-info "{WORKDIR}/c/lm_keyword_info.json" \
  --seed "<SEED>" --gl <MARKET> --date <YYYY-MM-DD> \
  --out "{WORKDIR}/c/lm_cluster_result.json"
```

Use the LLM inputs from the resulting `*_result.json` files in Step 3 (query `csv` / journey
`pathsText` and `hubsCsv` / cluster `csv`).

### Step 3 — Per-finder analysis (LLM, the original frames) → `lm_groups_raw.json` / `lm_paths_raw.json`

Analyze each finder **exactly by that finder's original analysis rules**. Do not restate the rules
here — follow the **Step 3 "Analysis rules"** section of the sibling reference document (no numeric
claims, no markup, evidence only, written in REPORT LANGUAGE):

- Query → `references/query-opportunity.md` §3 **"Analysis rules (Data Insight Analyst)"**
  (ported from agent_query v0.4.7). Input: the `csv` in `{WORKDIR}/q/lm_query_result.json`.
  Output: `{WORKDIR}/q/lm_groups_raw.json`.
- Journey → `references/path-opportunity.md` §3 **"Analysis rules (Search Journey Analyst)"**
  (ported from the agent_path framework). Input: `pathsText` and `hubsCsv` in
  `{WORKDIR}/p/lm_path_result.json`. Output: `{WORKDIR}/p/lm_paths_raw.json`.
- Cluster → `references/cluster-landscape.md` §3 **"Analysis rules (search data insight analyst —
  ClusterFinder)"** (ported from agent_cluster v0.7.0). Input: the `csv` in
  `{WORKDIR}/c/lm_cluster_result.json`. Output: `{WORKDIR}/c/lm_groups_raw.json`.

Each finder's JSON output schema and fields are also exactly as in the sibling documents.

### Step 4 — Per-finder post-processing (`groups`/`paths` · sum volumes · filter hallucinations)

For each finder that succeeded, run the sibling document's **Step 4 post-processing** unchanged.
This is where **numbers are filled in as facts** (summed volume, hubs, flows, connectivity) and
**hallucinated keywords are removed**.

```bash
# query → q/lm_groups.json
python3 {SKILL_DIR}/_shared/render/query_aggregate.py groups \
  --raw-groups "{WORKDIR}/q/lm_groups_raw.json" --context "{WORKDIR}/q/lm_query_result.json" \
  --out "{WORKDIR}/q/lm_groups.json"

# journey → p/lm_paths.json (if collection succeeded)
python3 {SKILL_DIR}/_shared/render/path_aggregate.py paths \
  --raw-paths "{WORKDIR}/p/lm_paths_raw.json" --context "{WORKDIR}/p/lm_path_result.json" \
  --out "{WORKDIR}/p/lm_paths.json"

# cluster → c/lm_groups.json (if collection succeeded)
python3 {SKILL_DIR}/_shared/render/cluster_aggregate.py groups \
  --raw-groups "{WORKDIR}/c/lm_groups_raw.json" --context "{WORKDIR}/c/lm_cluster_result.json" \
  --out "{WORKDIR}/c/lm_groups.json"
```

> If any finder's post-processing stops with a "zero groups" error, redo that finder's Step 3
> (same as in the sibling documents).

**Produce each finder's insights and actions (`lm_actions.json`) now too** — tabs 2–4 embed each
finder report's body verbatim, so run each finder's **Step 5** (sibling document §5:
`synthesis` · `insights` (3) · `now` · `future`) and save to:

- Query: `{WORKDIR}/q/lm_actions.json` (`references/query-opportunity.md` §5)
- Journey: `{WORKDIR}/p/lm_actions.json` (`references/path-opportunity.md` §5)
- Cluster: `{WORKDIR}/c/lm_actions.json` (`references/cluster-landscape.md` §5)

### Step 5 — Integrated aggregation (Python) + integrated notes (LLM) → `lm_total_facts.json` + `lm_total.json`

This step has **two parts**. In **5-A** the Python aggregator computes **every number, coordinate and
item id** across the three finders into `lm_total_facts.json`; in **5-B** the LLM writes **only the
one-line qualitative note for each of those ids** into `lm_total.json`. 5-A fixes the numbers as
facts, so 5-B must never recompute a number (this removes hallucination at the source).

#### 5-A. Integrated aggregation (Python) → `lm_total_facts.json`

Aggregate across the successful finders' post-processed results (the Step 2 `*_result.json` metadata
plus the Step 4 `groups`/`paths`) with `total_aggregate.py total`. **At least two finders including
query** are required, and you pass only the flags for the finders that exist (graceful degradation).

```bash
python3 {SKILL_DIR}/_shared/render/total_aggregate.py total \
  --seed "<SEED>" --gl <MARKET> --date <YYYY-MM-DD> \
  --query-meta    "{WORKDIR}/q/lm_query_result.json"   --query-groups   "{WORKDIR}/q/lm_groups.json" \
  --path-meta     "{WORKDIR}/p/lm_path_result.json"    --path-paths     "{WORKDIR}/p/lm_paths.json" \
  --cluster-meta  "{WORKDIR}/c/lm_cluster_result.json" --cluster-groups "{WORKDIR}/c/lm_groups.json" \
  --out "{WORKDIR}/lm_total_facts.json"
```

- **If journey or cluster failed**, drop the corresponding `--path-*` or `--cluster-*` pair of
  arguments (the aggregator scales down automatically — without cluster, for example, parts of the
  conversion corridors and revenue leaks shrink).
- The resulting `lm_total_facts.json` holds 8 sections (`meta` · `recap` · `coverage` ·
  `hubDivergence` · `matrix` · `valueLeak` · `bridges` · `backlog`) and **stable per-item ids**
  (`combo#`, `gap#`, `hub#`, `cell#`, `leak#`, `bridge#`, `bl#`). **The numbers here are settled
  facts** — the 5-B notes do not touch them.

#### 5-B. Integrated notes (LLM, **newly authored**) → `lm_total.json`

Read `lm_total_facts.json` and save **only the qualitative notes keyed to its ids** as JSON to
`{WORKDIR}/lm_total.json`.

> ⚠ This prompt is a **new authorship with no production original** (see the provenance comment
> above). It inherits only the three finders' shared discipline.

**Input**:
- `{WORKDIR}/lm_total_facts.json` — the numbers, coordinates and ids of the six cross-report modules
  (read-only evidence).
- (Supporting) the successful finders' `groups`/`paths` — qualitative context for the notes. Here too,
  **quote numbers only; never recompute them**.

---

##### Analysis rules (writing the integrated insight notes)

You are an integrated search data analyst. The Python aggregator has already settled, in numbers,
the **six cross-report conclusion modules** (coverage gaps · hub roles · persona × journey ·
revenue leaks · conversion corridors · prioritised backlog) across the three finders
(WHO · clusters / WHAT · WHY · intent / HOW · journey). Your only job is to attach **one line of
interpretation or prescription that a marketer can act on** to those settled items.

**Global rules** (the same as the three finders, plus integration-specific ones):
- **Map by id only**: a note must attach to an id that **actually exists** in facts
  (`hub#…`, `cell#…`, `bridge#…`, `bl#…`). A note written against an id that is not in facts is
  **silently discarded** by the renderer (you cannot conjure an item that does not exist) — but do
  not write non-existent ids anyway.
- **No re-authoring numbers or keywords (important)**: do not assert search volume, share, rank,
  spread or branch counts in prose ("the largest", "N%", "N times", "N of them" are forbidden), and
  do not invent new keywords — the supporting keywords are already filled into the chips and bars by
  facts. You write **why it matters and what to do**, nothing else.
- **Plain language**: sentences a marketer understands immediately. Never expose internal jargon
  (dispersion, outDegree, present-absent, leak_factor and so on).
- **Markup**: only `<strong>…</strong>` is allowed, for a key noun phrase. Never use any other markup
  (`:k[]`, `:::accordion`, `➊`, code blocks, tables).
- **Output language** = REPORT LANGUAGE (`<REPORT_LANGUAGE>`): `kr` → Korean, `jp` → Japanese,
  `us` → English.

**① overview** (string) — one or two sentences (roughly 100–200 characters) on the core structure
running through all three lenses. It goes into the "Integrated Summary" box on the cover and at the
top of tab 1. Prose, with no numeric claims.

**② hubNotes** `[{id, rx}]` — for the `hub#…` items in M2 (hub roles), **only those worth commenting
on**. `rx` = what this keyword's role mismatch means for marketing, plus a one-line prescription
(e.g. core in all three lenses → "claim it outright"; strong in one lens only → "run it for that use
case only").

**③ cellNotes** `[{id, note}]` — for the `cell#…` items in M3 (persona × journey), one line each,
focused on the **empty cells (content gaps)**: who arrives, why they are not served, and what to fill in.

**④ bridgeNotes** `[{id, note}]` — for the `bridge#…` items in M5 (conversion corridors), one line
each, focused on the ones with a clear verdict. Translate the direction and leak verdict into action
(place upstream, CRM, defend, and so on).

**⑤ backlogNotes** `[{id, title, body}]` — one per `bl#…` item in M6 (prioritised backlog).
`title` = a short action name for a marketer (a noun phrase, based on the supporting keywords).
`body` = **(optional)** one line of elaboration. The job here is to turn the facts' target, supporting
keywords and bucket into a task name a human can read.

---

##### Output format — JSON only (no markdown, no tables; only `<strong>` allowed)

```json
{
  "overview": "Integrated summary across the three lenses, 1–2 sentences",
  "hubNotes":     [{"id": "hub#0001",   "rx":   "Role-mismatch reading + one-line prescription"}],
  "cellNotes":    [{"id": "cell#p1-s1", "note": "One-line reading of the content-gap cell"}],
  "bridgeNotes":  [{"id": "bridge#C-D", "note": "Conversion verdict → one-line action"}],
  "backlogNotes": [{"id": "bl#now-1",   "title": "Action name", "body": "(optional) one-line elaboration"}]
}
```

Save that JSON to `{WORKDIR}/lm_total.json`. Every collection is **optional** (it may be empty) — a
facts item with no note simply renders with its numbers. **Use the facts' ids verbatim** (a typo only
loses that one note). Do not author free keywords or numbers in this note file — every number comes
from 5-A's `lm_total_facts.json`.

### Step 5.5 — Translate the keywords (only when MARKET language ≠ REPORT LANGUAGE)

The report shows keywords exactly as they are searched in the market. When the report language
differs from the market's language, the reader cannot read them, so build the translations that
back the **"Translate keywords" toolbar button** here. Skip this step when the market language and
REPORT LANGUAGE are the same — the button then does not appear at all.

Extract the on-screen keywords from **each finder that succeeded** and merge them:

```bash
python3 {SKILL_DIR}/_shared/render/query_aggregate.py keywords \
  --groups "{WORKDIR}/q/lm_groups.json" --category "<SEED>" \
  --out "{WORKDIR}/q/kw.json"
# journey (if it succeeded)
python3 {SKILL_DIR}/_shared/render/path_aggregate.py keywords \
  --paths "{WORKDIR}/p/lm_paths.json" --context "{WORKDIR}/p/lm_path_result.json" \
  --category "<SEED>" --out "{WORKDIR}/p/kw.json"
# cluster (if it succeeded)
python3 {SKILL_DIR}/_shared/render/cluster_aggregate.py keywords \
  --groups "{WORKDIR}/c/lm_groups.json" --category "<SEED>" \
  --out "{WORKDIR}/c/kw.json"

python3 - "{WORKDIR}" <<'PY' > "{WORKDIR}/kw_to_translate.json"
import json, sys
from pathlib import Path
W = Path(sys.argv[1]); seen, out = set(), []
for sub in ("q", "p", "c"):
    f = W / sub / "kw.json"
    if not f.exists():
        continue
    for k in json.loads(f.read_text(encoding="utf-8")).get("keywords", []):
        if k not in seen:
            seen.add(k); out.append(k)
print(json.dumps({"keywords": out}, ensure_ascii=False, indent=2))
PY
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

### Step 6 — Render the integrated HTML (`--skill total-insight`)

Call `render_report.py` in **integrated mode**. `--total` (the qualitative notes) and `--total-facts`
(the aggregated numbers) are required; pass the three finder flag groups **only for the finders that
succeeded and produced output** (omit a failed finder's flags — that tab renders as "no data").

```bash
python3 {SKILL_DIR}/_shared/render/render_report.py --skill total-insight \
  --total          "{WORKDIR}/lm_total.json" \
  --total-facts    "{WORKDIR}/lm_total_facts.json" \
  --query-groups   "{WORKDIR}/q/lm_groups.json" \
  --query-actions  "{WORKDIR}/q/lm_actions.json" \
  --query-meta     "{WORKDIR}/q/lm_query_result.json" \
  --path-paths     "{WORKDIR}/p/lm_paths.json" \
  --path-actions   "{WORKDIR}/p/lm_actions.json" \
  --path-meta      "{WORKDIR}/p/lm_path_result.json" \
  --cluster-groups "{WORKDIR}/c/lm_groups.json" \
  --cluster-actions "{WORKDIR}/c/lm_actions.json" \
  --cluster-meta   "{WORKDIR}/c/lm_cluster_result.json" \
  --category "<SEED>" --gl <MARKET> --lang <REPORT_LANGUAGE> --date <YYYY-MM-DD> \
  --out "{WORKDIR}/total-insight-report.html"
# If you did Step 5.5, append --translations "{WORKDIR}/lm_keyword_tr.json"
```

- **Required**: `--total` and `--total-facts`, plus **at least one** of the three finder groups
  (`--query-*` is always present, since query always succeeded). The gate rule guarantees at least
  two including query.
- **If journey failed**: drop the `--path-paths` · `--path-actions` · `--path-meta` lines.
- **If cluster failed**: drop the `--cluster-groups` · `--cluster-actions` · `--cluster-meta` lines.
- `--gl` is the market that was analyzed; `--lang` is the language the report is rendered in. Pass
  both — they are set independently in Step 0. `--date` is `$(date +%F)`.

### Step 7 — Tell the user

Report what was produced. If the run was degraded (a finder was skipped), say which tabs have no data.
Write the message in REPORT LANGUAGE. In English it reads:

```
✅ Integrated search insight report created: {WORKDIR}/total-insight-report.html
Open it in a browser and use the four tabs at the top (Integrated Summary · Query Opportunity ·
Search Journey · Cluster Landscape):
   · Tab 1: the six cross-report insight modules that only appear once the three finders are combined
     (coverage gaps · hub roles · persona × journey · revenue leaks · conversion corridors ·
     prioritised backlog), plus the integrated summary
   · Tabs 2–4: each finder report's body (cards / hub table / journey flow diagram)
in dashboard or A4 view.
The A4 view (toggle at the top right) is one continuous document — integrated, then query, then
journey, then cluster — so Cmd+P saves all four reports as a single PDF (4-in-one).
Open it on macOS: open {WORKDIR}/total-insight-report.html
```

(If journey or cluster was skipped for plan or network reasons, also mention that the tab shows
"This tab was not generated because there was no data" and that the finder's pages are missing from
the A4 view.)
