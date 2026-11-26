# Search Context v2 · Execution procedure

Only the current time point is examined. The deliverable is a **summary + marketing to-dos + path map**, and the path
analysis is run by the user **inside the page** (using the user's Claude and the ListeningMind connector, with results
saved). Numbers are computed by `scripts/sc.py`; you (the LLM) write only the summary and the marketing to-dos in Step 5.

At the very start of every Bash command, locate `SKILL_DIR` using the SKILL.md method.

## Step 0 — Check the inputs + working folder
**Personal data comes first** · If the user's message contains personal data such as a phone number · email address · ID, card or account number, stop here and ask them to resend the sentence with the personal data removed (0 MCP calls · SKILL.md "user_query").
**Decide the HOST first** · `claude` if you are Claude, `chatgpt` if you are ChatGPT. Do not ask the user.
**Connector name (`LM_SERVER`)** · The display name of the ListeningMind connector as it appears in this conversation's tool list (e.g. `ListeningMind`, `ListeningMind MCP Server`). Pass it to Step 6.
Inputs you need: seed · TARGET MARKET (`gl`) · REPORT LANGUAGE (`lang`) · PATHS (path count 100 · 200 · 300, default 300).
If the market and language are not clear, ask once, in a single question, and **ask for the path count in that same question** (e.g. "How many paths should I look at — 100 · 200 · 300? The default is 300.").
If only the path count is missing and the market and language are clear, do not ask separately — proceed with 300.
State the cost briefly (including the path count): "<PATHS> paths · report approx. 5 Lima · path analysis 0.1 Lima per SERP". Do not list out the individual calls.

```bash
SAFE=$(echo "<SEED>" | tr ' /\\:*?"<>|' '_')
WORKDIR="$PWD/tmp/reports/listeningmind-search-context-${SAFE}-$(date +%Y%m%d-%H%M%S)"; mkdir -p "$WORKDIR/serp"
```

## Step 1 — Paths (path_finder × 1, current time point)
Fetch **as many paths as the PATHS value set in Step 0 (100 · 200 · 300, default 300), and use every path you received for the summary, the marketing analysis and the initial map** (Step 3 `--show <PATHS>`).
Pass `limit` as PATHS. A different limit returns a different bundle of paths from the server (limit 100 ≠ the first 100 of limit 300), so never truncate a response fetched with a different limit.
In the page, the view can be narrowed to "100 / 200 / 300 paths" within the range received (no extra calls).
`mcp_cache.py lookup path_finder --params '{"keyword":"<SEED>","gl":"<MARKET>","time_point":"curr","limit":<PATHS>}' --out "{WORKDIR}/lm_path.json"`
→ On a miss, call `path_finder` with the same parameters + `"response_format":"download_url"` + `user_query` + `"is_skills":true` + `skill_desc`,
download it to `{WORKDIR}/lm_path.json` with `fetch_download.py`, then `store` (SKILL.md protocol).

## Step 2 — Search volume (keyword_info × 1)
```bash
python3 {SKILL_DIR}/scripts/sc.py kwparams --paths "{WORKDIR}/lm_path.json" --gl <MARKET> --out "{WORKDIR}/kw_params.json"
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup keyword_info --params-file "{WORKDIR}/kw_params.json" --out "{WORKDIR}/lm_nodes.json"
```
On a miss, call with the contents of `kw_params.json` + `"response_format":"download_url"` + `user_query` + `"is_skills":true` + `skill_desc`, download it, then `store`.

## Step 3 — Plan
```bash
python3 {SKILL_DIR}/scripts/sc.py plan --paths "{WORKDIR}/lm_path.json" --nodes "{WORKDIR}/lm_nodes.json" \
  --seed "<SEED>" --gl <MARKET> --lang <REPORT_LANGUAGE> --date <YYYY-MM-DD> --show <PATHS> --out "{WORKDIR}/plan.json"
```
This prints the keywords whose SERPs to look at (E1 = the seed, E2… = the main branches after the seed). The path count is based on `--show` (= PATHS, default 300).

## Step 4 — SERP (serp × number of E codes)
One `{WORKDIR}/serp/serp_<code>.json` per code. Call `serp` as `{"keyword":…,"gl":…,"num":10,"response_format":"download_url","user_query":…,"is_skills":true,"skill_desc":{"name":"__SKILL_NAME__","version":"__SKILL_VERSION__"}}` **one at a time, in sequence**,
and download each with `fetch_download.py … --collected-at "<the response's collected_at>"` (if a file for the same keyword was already downloaded in this conversation, copy it).
```bash
python3 {SKILL_DIR}/scripts/sc.py serp-trim --plan "{WORKDIR}/plan.json" --serp-dir "{WORKDIR}/serp" --out "{WORKDIR}/evidence.json"
python3 {SKILL_DIR}/scripts/sc.py brief --plan "{WORKDIR}/plan.json" --evidence "{WORKDIR}/evidence.json" --out "{WORKDIR}/brief.md"
```

## Step 5 — Summary + marketing to-dos (LLM) → `marketing_raw.json`
Read brief.md and write **short**. The user does not want a lot of content.
- `summary`: 2~3 sentences. Where the people searching this seed right now are heading, and what they are comparing or verifying.
- `actions`: 3~5 items. Things a marketer can do right away. Each item has `title` (one line), `why` (1~2 sentences of path·SERP evidence. The report does not show how E numbers map to the SERP source, so never use numbers like `E2-AI` or `E3-1` — state the source in words instead, e.g. `"Nike shoes" AI overview, "Nike" organic result #3 (Hankyung)`),
  `how` (1~2 sentences of concrete execution: content, SERP visibility, product page, ad keywords, price visibility, etc.), `keywords` (1~4 keywords exactly as they appear in brief.md).
- Principles: never invent a fact or keyword that is not in brief.md. Do not assert numbers as definitive (the path count is a sample). If the evidence is weak, say "estimated". Output language = REPORT LANGUAGE; keywords stay in the original.

```json
{"summary": "…", "actions": [{"title": "…", "why": "… (\"Nike\" organic result #3 (Hankyung))", "how": "…", "keywords": ["…"]}]}
```

## Step 6 — Render + check
```bash
python3 {SKILL_DIR}/scripts/sc.py render --plan "{WORKDIR}/plan.json" --evidence "{WORKDIR}/evidence.json" \
  --analysis "{WORKDIR}/marketing_raw.json" --lang <REPORT_LANGUAGE> --host <HOST> --lm-server "<LM_SERVER>" --out "{WORKDIR}/report.html"
python3 {SKILL_DIR}/scripts/check_report.py "{WORKDIR}/report.html"
```
`check_report.py` checks only the features that match the HOST recorded in the HTML (for chatgpt: request-text copying instead of saving and connecting to Claude, and that no Claude guidance appears in the visible text).
If there is even one ✗, do not hand it over. If `⚠ 경로에 없는 키워드를 뺐습니다` ("Removed keywords that are not on a path") appears, fix that action's keywords.

## Step 7 — Publish (the step that turns on in-page path analysis)
Path analysis and saving only work in an **artifact published on Claude.ai** (the page uses the user's Claude, the ListeningMind connector and the store).
- If the Artifact tool is available on Claude.ai: first check the runtime contract with `Artifact` action `capabilities`,
  then copy the file to `/mnt/user-data/outputs/<folder>/index.html` and publish with these capabilities.
  ```json
  {"sample": {}, "mcp": {"servers": [{"server": "ListeningMind", "tools": ["serp"]}]}, "db": {}, "user": {}}
  ```
  The page reads the `serp` response in the shape of a `{"gl","keyword","num"}` input and `payload.data[]` (type `ai_overview` · `organic_results`).
  Confirm that shape with a real `serp` call from Step 4 in this conversation before publishing.
- A Claude environment without the Artifact tool (Claude Code etc.): hand over the HTML file and explain that the map is visible but path analysis only works once it is published on Claude.ai.
- **HOST = chatgpt**: there is no publish step. Hand over `report.html` as a download. Explain that selecting a path in the page and pressing the "Copy path analysis request" (경로 분석 요청 복사) button, or typing a question,
  copies the request text, which they can then paste into the ChatGPT conversation. The path analysis request makes ChatGPT look up SERPs through the ListeningMind connector's `serp`, so
  the ListeningMind connector must be connected in ChatGPT. There is no save feature (the answers stay in the ChatGPT conversation).

### Getting the data when running on ChatGPT
`fetch_download.py` downloads files from github.com. ChatGPT's code execution environment may have outbound networking blocked, so
**when HOST = chatgpt, check before the first call with `python3 -c "import urllib.request;urllib.request.urlopen('https://github.com',timeout=5)"`**,
and if it is blocked, call without `response_format` from the start (json body) and write the full raw response to a file per the SKILL.md rule for "when the response arrives in the body".
To avoid paying for the same data twice, if you have already called with download_url, do not call again — tell the user instead.

## Step 8 — Tell the user (REPORT LANGUAGE)
Report just one or two lines of summary and the titles of the marketing to-dos, and explain that "clicking a keyword on the map to select a path and then pressing 'Path analysis' (경로 분석) runs the analysis and saves it".
Also mention that a permission prompt for using Claude and ListeningMind appears on the first analysis, and that path analysis costs 0.1 Lima per SERP.
Report the cost of this report as the sum of the responses' `cost_detail.total_cost`.
