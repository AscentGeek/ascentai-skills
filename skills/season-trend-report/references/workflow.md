# workflow — Season & Trend Analysis run order

The MCP tools used are `intent_finder` · `cluster_finder` · `keyword_info` only. Do not call path_finder or trend_finder.
Every MCP call follows SKILL.md's **2 steps (cache lookup → fetch_dl)** and carries `"response_format": "download_url"`, `"is_skills": true`,
`"skill_desc": <the object in SKILL.md ### skill_desc>` and `user_query` (the user's words verbatim).
**Call MCP tools one at a time.**

## Step 0 · Prepare

1. Fix the seed. It is the one query the user named (e.g. `후드티`, `홍삼`, `hoodie`). If there are several, ask once to pick one.
2. Fix the **target market `<gl>`** and the **report language `<lang>`** (`kr` · `jp` · `us` each · independent).
   If the request does not make both explicit, ask once in one short question. No MCP call before both are fixed.
3. Create the working folder.

```bash
SKILL_DIR=...   # the discovery command in SKILL.md
R="$SKILL_DIR/_shared/render"; CACHE="$SKILL_DIR/scripts/mcp_cache.py"
WORKDIR="tmp/reports/listeningmind-season-trend-<SEED>-$(date +%Y%m%d%H%M%S)"; mkdir -p "$WORKDIR"
```

## Step 1 · intent_finder (related queries)

| File | Parameters (`--params`) |
|---|---|
| `lm_intent_seed.json` | `{"keywords":["<SEED>"],"gl":"<gl>","limit":1000,"sort":"volume_avg","order":"desc","volume_threshold":0}` |

The intent_finder file holds **plain query strings** in `data` (already sorted by volume · no volume numbers, no dicts —
`r.get(...)` fails). To look at it:

```bash
python3 -c "import json,sys; print('\n'.join(json.load(open(sys.argv[1]))['data'][:150]))" "$WORKDIR/lm_intent_seed.json"
```

If there are fewer than 30 results, the seed is too narrow or not a searched term → tell the user and ask for another wording.

## Step 2 · cluster_finder (co-searched queries)

| File | Parameters (`--params`) |
|---|---|
| `lm_cluster_seed.json` | `{"keyword":"<SEED>","gl":"<gl>","data_type":"all","hop":2,"limit":1000,"orientation":"UNDIRECTED","time_point":"curr"}` |

If the plan blocks it, skip it (one line in chat). Run fetch_dl without `--items`.

## Step 3 · Query list → keyword_info

```bash
python3 "$R/st_prepare.py" --intent "$WORKDIR/lm_intent_seed.json" \
  --cluster "$WORKDIR/lm_cluster_seed.json" --gl <gl> --out-dir "$WORKDIR"
```

For each `kw_params_1.json`, `kw_params_2.json` … it prints, call keyword_info **one at a time, in order**.
The content of each file is the `<PARAMS>` as is. Name the saved files `lm_keyword_info_1.json`, `lm_keyword_info_2.json` ….

```bash
P=$(cat "$WORKDIR/kw_params_1.json")
python3 "$CACHE" lookup keyword_info --params "$P" --out "$WORKDIR/lm_keyword_info_1.json"
# exit 2 → keyword_info(<P> + response_format download_url + is_skills true + skill_desc + user_query) → fetch_dl.py --tool keyword_info --params "$P"
```

## Step 4 · config.json → build (refine at most 3 times)

Read `references/config.md` and write `$WORKDIR/config.json` (with `"gl"` and `"lang"` from Step 0). Decide the relevance
filter by scanning the queries in `kw_list.json`.

```bash
python3 "$R/st_build.py" --config "$WORKDIR/config.json" --list "$WORKDIR/kw_list.json" \
  --kw "$WORKDIR"/lm_keyword_info_*.json --out-dir "$WORKDIR"
```

Refine from the output.

1. Top 50 of `off.txt` — if a relevant query was dropped, fix rel/exc.
2. "미분류 전체" (all unclassified) in the output — read **every** query, not only the top. The output already leaves out the
   bare seed query and its spelling variants (`후드티` · `후디`), which are unclassified by design. For each query:
   - It fits an existing theme → add its word to that theme's regex. Generic words count too (`30대` → target, `면|원단` → material,
     `싼|세일` → price), as do brand and person names (`준지` → street brand).
   - Several queries share something no theme covers (e.g. `ucla|하버드|뉴욕` → university · city logos) → add a theme.
   - Neither → leave it unclassified. Do not stretch a theme to take it.
   Keep refining while the build prints the ⚠️ unclassified warning (more than 10% of volume or 20% of queries).
3. Query count per theme — if under 10, consider merging it into another theme or dropping it.
4. Check with the top queries in facts.md that no string with another meaning slipped into a theme (e.g. a `스파이더` rule catching `스파이더맨`).

If there is nothing to fix, go to Step 5. **Do not repeat more than 3 times.** Do not call MCP again (filters and themes apply after the lookup).

## Step 5 · narrative.json

Read `$WORKDIR/facts.md` and write `$WORKDIR/narrative.json` following `references/narrative.md`, **in the report language `<lang>`**.
facts.md headings are Korean (code output for you to read) — that does not change the language you write in.

- `years_trends` (0–5 key trends, empty if none): read **all three** branches of facts.md "주요 트렌드 재료" (key-trend material) before grouping.
  Before grouping, check the opposite branch and the per-theme lists so the title is not over-generalised — reflect the result
  only in the title and scope; do not write counter-example sentences.
- If facts.md "확인할 것" (to check) lists a month, do not build a trend from the queries that spiked together in that month.

## Step 6 · Render

```bash
OUT="$WORKDIR/season-trend-report.html"
python3 "$R/st_render.py" --data "$WORKDIR/data.json" --narrative "$WORKDIR/narrative.json" \
  --facts "$WORKDIR/facts.md" --out "$OUT"
```

- exit 4 = banned word → fix narrative.json and render again.
- "facts.md 에서 찾지 못한 숫자" (number not found in facts.md) warning → keep it if it is a ratio you computed; otherwise replace it with a facts.md number.
- claude.ai: publish `$WORKDIR/season-trend-report.html` as an Artifact. If the user wants the file, present_files.
- Claude Code / Desktop: give the path.

## Step 7 · Chat summary

In the language the user wrote in, briefly:

- Seasonal pattern in one or two lines (the months seasonal keywords cluster in · a notable flow in the calendar by theme)
- Trends in one or two lines (2–3 key trends)
- Risers and fallers in one line (2–3 large keywords up on both QoQ and YoY · 2–3 down)
- One line if there were queries that spiked together in the same month
- One line on where we are now
- The number of MCP calls made (state cost only if confirmed)
