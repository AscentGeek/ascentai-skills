---
name: lm-clusterfinder-report
description: >-
  Analyzes the co-search clusters of a seed keyword with ListeningMind MCP
  (cluster_finder · keyword_info) and generates a "Search Cluster Landscape"
  rich HTML report (dashboard/A4). Using the ClusterFinder agent's analysis frame,
  it groups keyword clusters by search purpose and presents each cluster's hub
  (representative) keyword and the From→To exploration flows between clusters as
  cards plus a hub keyword summary table.
  Use it when the user asks for "search cluster landscape", "clusterfinder report",
  "cluster analysis", "{category} clusters", "search cluster report", or the same
  requests in Korean — "검색 클러스터 지형 분석", "클러스터파인더 리포트", "클러스터 분석",
  "{카테고리} 클러스터", "검색 클러스터 리포트" — or in Japanese —
  「検索クラスタ地形分析」「クラスタファインダーレポート」「クラスタ分析」
  「{カテゴリ}のクラスタ」「検索クラスタレポート」.
allowed-tools: Bash, Read, Write, cluster_finder, keyword_info
metadata:
  author: AscentKorea
  category: output
  tags: report, search clusters
---

# lm-clusterfinder-report — Search Cluster Landscape Report

## Prerequisites

- **ListeningMind MCP connector must be connected** — data comes only from the 4 MCP tools
  (`intent_finder` · `keyword_info` · `cluster_finder` · `path_finder`).
- Allow outbound network access to `fonts.googleapis.com` (fonts · falls back to system fonts if blocked).
- python3 (standard library) required · no pip install needed.

## Execution

When the user asks for a search cluster landscape, **you must Read
`references/cluster-landscape.md` first**, then execute from Step 0 in order.
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
   Korean for `kr`, Japanese for `jp`, English for `us`) ClusterFinder accepts **a single keyword** only.
2. **TARGET MARKET (`gl`)**: `kr` · `jp` · `us`
3. **REPORT LANGUAGE (`lang`)**: `kr` · `jp` · `us`

If the seed is already given, proceed with it. If market or report language is missing,
ask once — there is no default.

**Never ask for an API key** — data comes from the MCP connector. If an MCP tool call fails
with "tool not found", the connector is not connected: ask the user to connect the
ListeningMind MCP connector and stop. **Do not invent data.**

## Output

`{WORKDIR}/cluster-landscape-report.html` — a self-contained HTML file (dashboard↔A4 toggle · printable PDF).
`{WORKDIR}` is `tmp/reports/listeningmind-cluster-landscape-{seed}-{timestamp}/` inside the running project.

- **Search Clusters tab** · purpose cluster cards + hub keyword summary table
- **Flows & Insights tab** · From→To exploration flows + overall implications, key insights and recommended actions

---

## MCP call protocol

Data comes from the **ListeningMind MCP tools**. Because the caller is **you (the LLM)**
and not code, two things are your responsibility: **① check the cache ② secure the
response file**.

### Discover SKILL_DIR dynamically (at the top of every Bash command)

```bash
SKILL_DIR=$(find ~/.claude/skills ~/.claude/plugins /mnt/skills /mnt/user-data \
    ~/.codex/skills ~/.gemini/skills ~/.config/skills ./skills . \
    -maxdepth 4 -type d -name lm-clusterfinder-report 2>/dev/null \
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

### Credits

**MCP (Lima) charges per call — not per returned relation.** Measured 2026-10-08 on the live
connector (seed 등산화, gl=kr, hop=2, data_type=all, response_format=download_url):

| `cluster_finder` limit | relations returned | unique nodes | clusters | payload | cost |
|---|---|---|---|---|---|
| 500 | 499 | 452 | 5 | 35KB | **2 Lima** |
| 2,000 | 1,984 | 1,491 | 15 | 136KB | **2 Lima** |
| 10,000 | **3,240** (saturated) | 2,044 | 18 | 216KB | **2 Lima** |

Consequences, and why this skill requests `limit=10000`:

- **Raising `limit` is free.** Cost did not move while the payload grew 6×. So there is no reason to
  under-request. (The DaaS edition is billed `150 + relations × 50` — **proportional**, a different
  model. Do not carry a conclusion from one edition to the other.)
- **`limit` is a ceiling, not a target.** This seed saturates at 3,240 relations; the remaining
  6,760 simply do not exist in the graph. A larger `limit` never fabricates relations, and a small
  graph costs no more than a large one.
- **A full run is 6–18 Lima**: `cluster_finder` ×1 (2) + `keyword_info` ×(2–8) chunks (2 each).
  Chunk count tracks node count, which varies ~6× across seeds — see §How much of the graph the LLM
  sees for the measured range. Do not quote a single figure as "the" cost.
- Read the actual number from the response envelope's `cost_detail.total_cost` — do not estimate it
  from this table.

> Note: `_core/scripts/mcp_cache.py` carries an older comment claiming "1 credit per call". Every
> call measured on 2026-10-08 returned `total_cost: 2`. Trust the envelope, not the comment.

### How much of the graph the LLM sees

`cluster_finder` at `limit=10000` returns wildly different graph sizes depending on the seed.
Measured 2026-10-12 across 6 seeds and all 3 markets:

| seed | market | relations | nodes | clusters | `keyword_info` chunks |
|---|---|---|---|---|---|
| 노트북 | kr | 1,704 | 1,225 | 12 | 2 |
| 다이어트 | kr | 2,113 | 1,553 | 10 | 2 |
| 脱毛 | jp | 2,115 | 2,000 | 10 | 2 |
| 등산화 | kr | 3,240 | 2,044 | 18 | 3 |
| 무선이어폰 추천 | kr | 5,578 | 2,467 | 28 | 3 |
| running shoes | us | 8,506 | 6,538 | 63 | 7 |
| 나이키 | kr | 9,765 | 7,124 | 76 | 8 |

So a run costs **2 Lima for `cluster_finder` + 2 per `keyword_info` chunk** — roughly 6 Lima on a
narrow seed and **18 Lima on a dense one**. Node count drives everything downstream; do not assume
one seed's shape generalizes.

Beyond ~2,000 nodes the csv handed to the LLM is capped (`KEYWORD_CONTEXT_TOP_N`). The selection is
**not** a plain volume cut, because two things break if it is:

- **Every cluster's hub is reserved first.** A hub is picked by edge degree, not volume, so a
  low-volume hub can sit thousands of rows down. `postprocess_groups()` discards any cluster whose
  hub is missing from the csv — on 나이키 a plain volume cut kept only **21 of 76** hubs, so most
  clusters would have been thrown away. With hubs reserved it is **76 of 76**.
- **Then each cluster is guaranteed `CLUSTER_MIN_KEYWORDS` (6) rows.** A cluster represented by its
  hub alone gives the LLM nothing to characterize it with. This takes clusters with fewer than 3 csv
  members from **9 to 0** on 나이키 and **18 to 0** on running shoes.

The remaining budget is filled by volume desc, so the head is unaffected (top-50 keywords by volume
are retained). `cluster_aggregate.py context` prints how many rows reached the LLM and how many
low-volume keywords were left out — read that line rather than assuming full coverage.

### Runtime · where the minutes go

Measured 2026-10-13 (seed 마그네슘영양제, kr: 7,884 relations / 3,285 nodes / 33 clusters /
4 chunks), total ~17 min:

| stage | who | time |
|---|---|---|
| 1a `cluster_finder` ×1 | MCP | 22s (+0.4s download) |
| **1b `keyword_info` ×4 chunks** | **MCP + agent** | **~10 min (59%)** |
| 2 aggregate | Python | <1s |
| **3 cluster grouping** | **LLM** | **3–6 min (29%)** |
| 4 postprocess | Python | <1s |
| 5 insights | LLM | 1–2 min |
| 6 render | Python | <1s |

**The cost of 1b is the request, not the response.** A 1-keyword call took 9s and a 50-keyword call
35s, while downloading the response file takes 0.1–0.4s. A 1,000-keyword array is ~9,500 tokens the
agent must *emit*; four chunks is ~31,000 tokens of output. Two consequences:

- Shrinking the response is pointless. `data_type=all` returns ~5.7KB per keyword of which the
  aggregator reads 6.3% (`ads_metrics` + `intents`), but the download is already sub-second — and
  `intents` exists only in `all`, so it cannot be narrowed anyway.
- The only real lever is **how many keywords get enriched**, which is why `enrich-plan` caps the
  fetch at `KEYWORD_ENRICH_TOP_N`. Before that cap existed this seed fetched 3,285 keywords while
  only 2,000 could reach the csv — 1,285 (39%) enriched and discarded. Capping it took the run to
  **2 chunks / ~13 min**.

Remaining headroom, if 13 min is still too slow: lowering `KEYWORD_CONTEXT_TOP_N` shortens step 3
(the csv is ~52 bytes/row, so 2,000 rows ≈ 33K tokens of LLM input), and dropping the csv's `i`
column would cut another ~18% of that input — but `intents` is what lets step 3 merge clusters by
search purpose, so that trade is a quality decision, not a free win.

Python stages are never the bottleneck; do not optimize them.

### Concurrency · one call at a time

**The API key's concurrent-request limit is 1.** Two MCP calls issued in parallel fail the second
with `Too Many Requests: Your API key's concurrent request limit is 1` (measured 2026-10-08); the
same request succeeds when retried sequentially. This matters most for the chunked `keyword_info`
calls — **issue them one after another, never in a single parallel batch.**

### user_query · record the query alongside the call in the history

The MCP tools (cluster_finder · keyword_info) accept an optional `user_query` parameter and store it in the history
(for query–search correlation analysis). **It is not attached automatically**, so you put it in yourself.

Put in the **user's utterance verbatim** · no translating, summarizing or paraphrasing.
It is not part of the cache key, so the cache still hits even when the wording changes.

### is_skills · mark the call as skill-routed

The MCP tools accept an optional `is_skills` boolean. It exists so the platform can tell
**skill-driven calls apart from plain prompt calls**. Default is `false`; **a skill run sets it to
`true`.** This skill is a skill run, so **set `is_skills: true` on every call it makes.**

Verified 2026-10-08 on the live connector: `is_skills: true` returned the **same data** (identical
499 relations, 452 nodes and 5-cluster partition) at the **same cost** as `false` — it changes
neither the data nor the billing, only how the call is classified. So there is no downside to
sending it, and omitting it mis-files this skill's calls as prompt calls.

> Like `user_query`, it is **not** part of the cache key — do not put it in `mcp_cache.py --params`.
