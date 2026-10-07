---
name: lm-brand-competition
description: >-
  Starts from a single brand name, finds every product category that brand spans,
  and judges each category on two axes — who owns the name (share of search) and
  where the search journey goes — producing a single-file Category Map HTML report.
  Below each category sit demand facets (occasion, use, feature, form, grade), showing
  where demand splits inside one category. Uses only ListeningMind MCP's intent_finder,
  path_finder and keyword_info, so it runs on the Standard plan.
  Use it when the user asks for "brand competition analysis",
  "competitive landscape", "who are our competitors", "category map for a brand",
  "share of search vs competitors", "which categories is this brand in", or the same
  requests in Korean — "브랜드 경쟁 구도", "우리 브랜드 경쟁사 찾아줘", "카테고리별 경쟁사",
  "브랜드 카테고리 지도", "자사 vs 경쟁사 검색 점유", "세부 수요별 경쟁" — or in Japanese —
  「ブランド競争構図」「競合ブランドの発見」「カテゴリ別の競合」「ブランドのカテゴリマップ」
  「指名検索シェアの比較」. GSC-based category entry diagnosis is out of scope (lm-cep-entry);
  the journey before and after a brand is lm-brand-journey.
allowed-tools: Bash, Read, Write, WebFetch, WebSearch, intent_finder, path_finder, keyword_info
metadata:
  author: AscentKorea
  category: analysis
  tags: brand competition, category map, share of search, demand facets
---

# lm-brand-competition — Brand Competition · Category Map

It starts from **one brand name**. There is no reason a brand has a single competitive
situation — **the rival is different in every position**, and that is the picture this
skill produces.

| Axis | What it measures | Source |
| :---- | :---- | :---- |
| **Naming axis** | **Share of search** — that brand's slice of the category's combined branded query volume (Unclaimed = branded share under 10%) | `intent_finder` + `keyword_info` |
| **Journey axis** | Branded queries appearing anywhere across the search journeys of that category | `path_finder` |

Both use the **2x rule between our brand and the leading rival.** A large number on our
side alone is not Leading. `references/judging-rules.md` **is the single source of truth**
for thresholds, boundaries and data states.

**The points where you ask a human are fixed** — Step 0 (opening questions) and Step 7
(deep-dive targets), plus Step 2-b (scope) only when there are more than 10 categories.
Between those, run to the end without asking.

## Prerequisites

- **The ListeningMind MCP connector must be connected.** Search data comes **only** from
  the MCP tools. Never use another source, and never invent numbers.
- **python3** (standard library only · no pip).
- Network egress for `fonts.googleapis.com` (the report falls back to system fonts if blocked).
- **No API key is requested.** The connector handles authentication.
- `web_fetch` / `web_search` are used once, in Step 2-c, to read the brand's official store.
  They touch no search data — they only separate "Trailing" from "we do not sell it".

If `intent_finder` · `path_finder` · `keyword_info` are not in the session's tool list,
stop and tell the user to connect the connector. Do not fabricate data.

## Execution

When the user asks for a brand competition analysis, **read `references/brand-competition.md`
first** and run Step 0 onward in order. Do not skip steps.

- Thresholds, boundaries, data states → read `references/judging-rules.md`.
- `config.json`, screen layout and colours → read `references/report-spec.md`.
- Results that look wrong, known limits → read `references/limits.md`. **Skim it before collecting.**

## Two runtime inputs: TARGET MARKET and REPORT LANGUAGE

1. **TARGET MARKET (`gl`)** — the search market to analyse: `kr`, `jp` or `us`.
   It goes to the ListeningMind MCP tools and to the renderer as `--gl <MARKET>`.
2. **REPORT LANGUAGE (`lang`)** — the language of the report and of the whole conversation:
   `kr` (Korean), `jp` (Japanese) or `us` (English). It goes to the renderer as `--lang <LANG>`.

**The two are independent.** Analysing the US market and reporting in Japanese
(`--gl us --lang jp`) is a valid, expected combination. Never infer one from the other.

Search terms stay in the market's own language. When the two differ, Step 9-b builds a
translation map and the report carries a **"Translate keywords"** toggle — see `references/limits.md` §13.

## Inputs (ask the user in chat at Step 0)

| Item | Default | Note |
| :---- | :---- | :---- |
| Brand name | (required) | one name · the whole run starts here |
| TARGET MARKET | `kr` | `kr` · `jp` · `us` |
| REPORT LANGUAGE | same as market | `kr` · `jp` · `us` |
| Rivals that must be covered | none | measured in every category, ahead of automatic discovery |
| Categories that must be covered | none | included even without evidence, flagged as specified |
| Official store URL | found by `web_search` | Step 2-c reads it to label what we actually sell |

If the brand name is given and nothing else is mentioned, **proceed on the defaults — do not
ask again.**

## Output

`{WORKDIR}/brand-competition-report.html` — a self-contained HTML file
(Dashboard ↔ A4 toggle · printable to PDF).
`{WORKDIR}` is `tmp/reports/listeningmind-brand-competition-{brand}-{timestamp}/`
inside the running project.

Tell the user the path when it is done. Do not paste the report body into chat; a short
summary of 3–5 findings plus the self-check of Step 11 is what belongs in the message.

## MCP call protocol

Data comes from the **ListeningMind MCP tools**. Because the caller is **you (the LLM)** and
not code, two things are your responsibility: **① check the cache ② secure the response file.**

### Discover SKILL_DIR dynamically (at the top of every Bash command)

```bash
SKILL_DIR=$(find ~/.claude/skills ~/.claude/plugins /mnt/skills /mnt/user-data \
    ~/.codex/skills ~/.gemini/skills ~/.config/skills ./skills . \
    -maxdepth 4 -type d -name lm-brand-competition 2>/dev/null \
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

- **exit 0 = hit** · the file is already filled → **do not call MCP.** Go straight on.
- **exit 2 = miss** · go to ②.

```bash
# ② Call MCP → dump the raw response verbatim → store it in the cache
python3 {SKILL_DIR}/scripts/mcp_cache.py store <tool> \
  --params '<exactly the same parameter JSON as in ①>' --file "{WORKDIR}/<file>.json" \
  --expect <record count read from the envelope>
```

`--params` **must be identical** in ① and ②. If they differ, the next run will not hit the cache.

### Response file rules (the most important part)

The judging scripts read the MCP response as-is, so it must sit in the file **raw and
unprocessed**. Three ways to get it there — try them from the top.

**① The tool result carries a download URL — fetch it (best)**

```bash
python3 {SKILL_DIR}/_shared/render/fetch_dl.py --url "<URL>" \
  --out "{WORKDIR}/<file>.json" --sha256 <sha256> --items <item_count> \
  --tool <tool> --params-file <the request parameter JSON>
```

It fetches, verifies **sha256 and the record count against the envelope**, wraps the payload
into the `{"data": ...}` shape the scripts expect, and stores it in the cache — in one command.
On a mismatch it does not save; it leaves `<out>.partial` so you can see what arrived, and
**refetching the same URL costs no credits.**

`--items` is the envelope's `item_count`, **not** the number of keywords you requested —
`keyword_info` drops unlisted keywords and adds notation variants (600 requested → 601 rows, measured).

**Do not use `curl`.** The downloaded file is the payload, not the envelope, and
`intent_finder` · `keyword_info` return a **bare list**. The scripts read `json.load(...)["data"]`
in 14 places, so a bare list dies there. `fetch_dl.py` wraps it at the entrance.

**② The host saved it to a file — copy the path**

The tool result arrives as a path instead of a body —
`Tool result too large for context, stored at /mnt/user-data/tool_results/….json`, or in
Claude Code `Error: result (N characters) exceeds maximum allowed tokens. Output has been saved to …`.

**This is not a failure.** Do not be fooled by the leading `Error:` or a `.txt` extension, do not
follow the "read the file to the end" advice, and **do not call the tool again** (it costs credits twice).

```bash
cp "<saved path>" "{WORKDIR}/<file>.json"
```

**③ It arrived in the body — only then, a heredoc**

```bash
cat > "{WORKDIR}/<file>.json" <<'DUMP_EOF'
<the entire raw MCP response JSON>
DUMP_EOF
```

**Absolutely forbidden** · reducing ① the number of keywords queried, ② `limit` or `data_type`,
or ③ summarising/excerpting records because the response is large. All three silently corrupt
the report's numbers. If reducing scope seems unavoidable, **do not proceed — tell the user.**

### Session cache

`~/.lima-agents/mcp-cache/<session>/` · within the same conversation the same
`(tool + parameters)` is never bought twice. **Data another report skill fetched with the same
parameters is reused too.** Set `LIMA_MCP_REFRESH=1` to bypass it.

The cache only works when the host gives a session env var. Without one the skill simply calls
MCP every time — that is deliberate, and better than picking up a neighbouring conversation's data.

### user_query · record the query alongside the call in the history

The MCP tools accept an optional `user_query` parameter and store it in the history (for
query–search correlation analysis). **It is not attached automatically**, so you put it in yourself.

Put in the **user's utterance verbatim** · no translating, summarising or paraphrasing.

> `user_query` is excluded from the cache key, so **do not put it in `mcp_cache.py --params`**.
> Putting it there changes the key on every rewording and the cache stops hitting.

### Credits

One call = one credit. **It is counted per call, not per keyword** — `keyword_info` costs the
same for 12 keywords as for 1,000 (measured), so batching small wastes credits. Report only the
measured `cost_detail.total_cost` from the envelope. **Never state a remaining balance or quota** —
the envelope has no such field.

## Reference files

| File | When to read it |
| :---- | :---- |
| `references/brand-competition.md` | **The procedure.** Step 0 onward — read it before you start |
| `references/judging-rules.md` | **The single source of truth for verdicts.** Thresholds, boundaries, data states |
| `references/report-spec.md` | Writing `config.json`; checking the screen layout and colours |
| `references/limits.md` | Results that look wrong. **Skim it before collecting** |

Scripts ship in two places: `scripts/mcp_cache.py` (shared) and `_shared/render/*.py`
(this skill — `judge.py` · `cep_deep.py` · `check_run.py` · `brandkw.py` · `fetch_dl.py` ·
`modifiers.py` · `pathcand.py` · `kw_extract.py` · `render_report.py`).
