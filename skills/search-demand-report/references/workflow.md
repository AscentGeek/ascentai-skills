# lm-search-demand-report · Procedure

Put the `SKILL_DIR` discovery block from SKILL.md at the top of every Bash command.

```bash
WORKDIR="tmp/reports/listeningmind-demand-shift-<SEED>-$(date +%Y%m%d%H%M%S)"; mkdir -p "$WORKDIR"
R="$SKILL_DIR/_shared/render"; CACHE="$SKILL_DIR/scripts/mcp_cache.py"
```

## Step 0 · Fix the inputs

Seed · TARGET MARKET `gl` (kr/jp/us) · REPORT LANGUAGE `lang` (kr/jp/us) · **chat language = the language of the user's
message** (SKILL.md "Chat language" · independent of the seed, gl and the documents · applies to every chat line from here on).
If the request does not make both `gl` and `lang` explicit, ask once in a single short question — do not guess them from the
seed's language or the user's language, and make no MCP call until both are fixed. Do not ask for the mode — code decides it
at Step 1.5 from the related-query mix.

## Every MCP call

Only `intent_finder` · `cluster_finder` · `keyword_info`. **Never call path_finder or trend_finder.**
Every call follows SKILL.md "MCP call protocol" — no exceptions:

```bash
# ① cache · exit 0 = hit (skip the call) · exit 2 = miss
python3 "$CACHE" lookup intent_finder --params '<PARAMS>' --out "$WORKDIR/lm_intent_seed.json"
# ② miss → call the tool with <PARAMS> + "response_format":"download_url" + "is_skills":true + "user_query":"<user's words verbatim>"
#    → fetch the URL, verify, store
python3 "$R/fetch_dl.py" --url "<download.browser_download_url>" --out "$WORKDIR/lm_intent_seed.json" \
  --sha256 <download.sha256> --items <download.item_count> --tool intent_finder --params '<PARAMS>'
```

- `<PARAMS>` = the parameter JSON in the tables below, **without** `user_query`, `response_format` and `is_skills`. Use the same string in ① and ②.
- One call at a time — the account allows 1 concurrent request (`Too Many Requests` otherwise; wait and retry).
- keyword_info takes up to 1,000 keywords per call; split only above that. **Never trim a bundle.**

## Step 1 · Seed related queries

| File | Tool · parameters |
|---|---|
| `lm_intent_seed.json` | intent_finder `{"keywords":["<SEED>"],"gl":"<gl>","limit":1000,"sort":"volume_avg","order":"desc","volume_threshold":0}` |

## Step 1.5 · seed.json (you · M1) → mode and fitness check (code) — `ask.md`

Write seed.json. Pick the mode by looking at the related queries; code makes the final call.

intent_finder files hold **plain query strings** in `data` (already sorted by volume · no volume numbers, no dicts —
`r.get(...)` fails). Read them like this:

```bash
python3 -c "import json,sys; print('\n'.join(json.load(open(sys.argv[1]))['data'][:150]))" "$WORKDIR/lm_intent_seed.json"
```

```json
{"seed":"나이키 러닝화","gl":"kr","mode":"entity","brand":["나이키","nike"],"item":["러닝화"],
 "upper":"러닝화","heads":["화","운동화"]}
```

- `gl` = market (kr · jp · us · **always write it**). The classification dictionary differs per market (method-v5.12 ·
  `_shared/render/ds_market.py`). Without it the kr dictionary is used and jp · us queries are misclassified.
- `upper` = the finder input for sections 1 and 2. **entity → the target category** (나이키 러닝화 → 러닝화 · 나이키 → 러닝화) ·
  **category → the parent category** (러닝화 → 운동화 · 전기압력밥솥 → 밥솥).
- `item` holds only the seed's item name and its spacing variants. Synonyms are chosen with evidence at Step 3 (M3a).
- A brand-only seed (나이키 · bhc) gets `"itemOptional": true` and the brand's main category in item. If the brand sells several item
  categories, also write `"brandItems": ["러닝화", "운동화", "바람막이"]` (2 or more → narrowing).
- If you judge it an industry or area word (뷰티 · 패션 · 가전 · 운동), write `"seedType": "domain"` (code signals catch it too).
- **If the item is not footwear, write `"generic": []`** (M1). Otherwise footwear words (‘필라테스 신발’ · ‘헬스 운동화’) leak into the target and comparison set.
- A narrowed seed keeps `scope` (scope.md §6) — check then skips the broad-seed test. **Do not put the broad seed (뷰티) in upper** —
  use the narrowest parent that covers substitutes and adjacent items (향수 → 프래그런스).
- `near` (category · optional · method-v5.11) — nearby-market (substitute · adjacent) candidates. Write it only when classify.md at
  Step 3a reports too few near candidates (keyword-method M5-0).

```bash
python3 "$R/ds_classify.py" check --seed "$WORKDIR/seed.json" --intent "$WORKDIR/lm_intent_seed.json" --out "$WORKDIR/fit.json"
# exit 0 = go on (code fills modeReason · composition in seed.json)
# exit 10 · kind broad / brandwide = Step 1.6 narrowing · kind topic / mode = ask.md fixed question, then stop
```

**Check order: broad seed → topic → mode.** Broad comes first — an area word that is also a topic (‘운동’) goes to narrowing, not to
the topic question. Even after a topic answer (fit.asked) the broad test is not skipped. When rewriting seed.json, keep `seedType` · `scope`.

## Step 1.6 · Narrowing the seed (kind broad · brandwide) — `scope.md`

scope.json (candidates · with `"gl"`) → keyword_info · intent_finder (all candidates at once · 2 MCP calls, each with the 2 steps above)
→ `ds_scope.py score` → fixed question (once · **note → input format and examples → evidence table → options** · scope-v2 · options and
examples are search terms as typed, `삼성 냉장고`, never `삼성 > 냉장고`) → rewrite seed.json for the chosen item (record `scope`)
→ reuse lm_intent_seed.json via `ds_scope.py extract` (call intent_finder if too few) → **restart from Step 1.5.**
Never run Step 2 onward on a broad seed. If the user names a direction for the candidates (activity / item …), use it.

## Step 2 · Upper term · inside collection

| File | Tool · parameters | Purpose |
|---|---|---|
| `lm_cluster_seed.json` (category · required) | cluster_finder `{"keyword":"<SEED>","gl":"<gl>","data_type":"all","hop":2,"limit":1000,"orientation":"UNDIRECTED","time_point":"curr"}` | **first source for section 1 candidates** — other items searched together with the seed. Unaffected when the upper term mixes meanings (상의 → 상의하다). If the plan blocks it, skip it and say so in chat |
| `lm_cluster.json` | cluster_finder `{"keyword":"<upper>","gl":"<gl>","data_type":"all","hop":2,"limit":1000,"orientation":"UNDIRECTED","time_point":"curr"}` | section 1 candidates · analysis-target same-meaning candidates. **If the plan blocks it, skip it** (continue without the file) |
| `lm_intent_external.json` | intent_finder `["<upper>"]` | section 1 candidates · analysis-target same-meaning candidates (supplements cluster · main source without cluster) |
| `lm_intent_internal.json` (entity) | intent_finder `["<brand> <item>"]` — own brand + target category. Skip if it equals the seed | section 2 product-line candidates · spellings without the brand |
| `lm_intent_sku.json` (entity · optional) | intent_finder with several chosen line names (`["나이키 페가수스","나이키 보메로"]`) | generation / model queries inside each line (they become line queries, not sub-SKUs) |

cluster_finder has no `item_count` in its envelope — leave out `--items` for it. Only skip a cluster call when the failure is the
plan (`Not Authenticated` · `Invalid API Key`); retry `Too Many Requests`; stop on `Insufficient Lima` · `Account Locked`.

## Step 3 · Keyword-set classification (code → your choices → code) · `keyword-method.md` required

**3a · propose (code)**

```bash
python3 "$R/ds_classify.py" propose --seed "$WORKDIR/seed.json" --intent "$WORKDIR"/lm_intent_*.json \
  --cluster "$WORKDIR/lm_cluster.json" --cluster-seed "$WORKDIR/lm_cluster_seed.json" \
  --out "$WORKDIR/classify.json" --brief "$WORKDIR/classify.md"
```

Leave out `--cluster` · `--cluster-seed` for clusters you could not get. If you fetched `lm_intent_near.json` (M5-0), it is picked up by `lm_intent_*.json`.

**3a′ · Nearby market (category · method-v5.11 · keyword-method M5-0)** — if classify.md shows `⚠ 가까움 후보 n개 < 4` (fewer than 4 near candidates):
write 4–8 substitute · adjacent items (with why) into seed.json `near` → intent_finder `{"keywords":[all near names],"gl":"<gl>","limit":<near count × 300>,"volume_threshold":0}`
→ `lm_intent_near.json` → propose again.
Each candidate shows `[가까움 / 근거 약함 / 영역만] 함께 언급 N · 비교 언급 N` (near / weak evidence / same area only · co-mentions · comparison mentions).
In category mode, candidates with the most `시드 cluster 등장 N` (times the name sits in the searched-for slot among nodes searched with the seed) come first.
`classify.md` lists [1 시장 흐름] comparison candidates · [1 분석 대상] same-meaning candidates · [2 내부 동향] candidates (category also lists topic candidates).

**3b · picks.json (you · M3a · M5 · M5a · M8)** — choose only from the candidate lists. Record a rule number for everything chosen and dropped.

**M5a (optional)** — only when you want to add a comparison target's representative spelling (English · short form). A section 1 bundle is
spelling × representative item name, so one spelling makes two combinations. Pick from classify.md's
**[1 시장 흐름] 비교 대상별 유사의도 후보** (overlapping names · English spellings) into `synonyms.pick`; known spellings not in the
candidates go to `synonyms.analyst`; dropped ones to `synonyms.skip`. Without a record the name alone is used
(`"external": {"pick": ["아디다스", "아식스"]}` is fine).

```json
"external": {"pick": [{"name": "호카", "synonyms": {"pick": ["호카오네오네", "hoka"], "analyst": [], "skip": {"호카 본디": "M5a 제품명"}}},
                      {"name": "아디다스", "synonyms": {"pick": [], "analyst": ["adidas"], "skip": {"아디다스 제로": "M5a 제품명"}}}], "skip": {}}
```

```json
{"synonyms": {"pick": [], "analyst": ["pilates"], "skip": {"신발": "M3a 관련 품목", "1:1": "M3a 의도어 → 2"}},
 "external": {"pick": [{"name": "요가", "variants": ["요가", "yoga"]}, {"name": "홈트", "variants": ["홈트", "홈트레이닝"]}, "헬스"],
              "skip": {"근력 운동": "M5-1 하위 수준(홈트 안)", "운동화": "M5-1 품목"}},
 "internal": {"pick": [], "topics": [{"name": "기구", "variants": ["기구", "바렐"]}, "..."],
              "catchall": {"name": "지역·브랜드 검색", "split": true, "variants": ["근처", "학원", "스튜디오", "센터"], "...": "keyword-method.md"},
              "skip": {}}}
```

- **Analysis target (M3 · M3a):** only the names that call the seed (spelling variants · English). Queries with something attached (1:1 · 학원 · 근처)
  are not the target → section 2. Without cluster, put the spellings you think of in `analyst` — only those with keyword_info values remain.
- **Section 1 confirmation (M5-7):** if a chosen comparison target is '근거 약함' (weak evidence) or '영역만' (same area only), or there are
  fewer than 4 near ones, show the comparison markets and evidence once before plan and ask with buttons (이대로 / 가까운 것만 / 직접 고치기 —
  as is / near only / edit it myself). Otherwise do not ask.
- **Section 1 comparison set (M5 · M6):** names at the same level only; spelling variants as `variants` (plan sends those not in the finders to
  verify). **Candidates with seed-cluster evidence (count ≥ 2) first.** With fewer than 4, call one more cluster on another upper term whose
  meaning does not mix (M5-4a · `lm_cluster_alt.json` passed as `--cluster`) → (category) still fewer than 4 near → the substitute · adjacent
  candidates of 3a′ (`lm_intent_near.json`) · (entity) only when still fewer than 3, your own candidates (`lm_intent_analyst.json` · source analyst).
  If you used analyst, say in chat in one line that "n comparison targets are Claude's candidates, not data".
- **Section 2 intent change (M8):** entity = product lines. category = topics (`topics`) + the search-for bundle (`catchall` · `split: true` ·
  split into region names / brand names / nearby · school searches). `pick` (fixed brand bundle) is not used. With fewer than 3 topics,
  check your candidates with intent_finder into `lm_intent_analyst_internal.json` → propose again.

**3c · plan (code · M3 · M6 · M9)**

```bash
python3 "$R/ds_classify.py" plan --seed "$WORKDIR/seed.json" --intent "$WORKDIR"/lm_intent_*.json \
  --cluster "$WORKDIR/lm_cluster.json" --cluster-seed "$WORKDIR/lm_cluster_seed.json" --picks "$WORKDIR/picks.json" --out "$WORKDIR/plan.json"
```

Call keyword_info with the plan's keywords (including target / comparison verify strings and search-for bundle queries · can be hundreds).
**entity:** each comparison target gets `brand spelling × item name (seed item + chosen synonyms)` verify strings (adidas 러닝화 · 아디다스 조깅화 …) —
query all of them (build drops those without values). Keywords you already have may be left out · up to 1,000 per call · several files in
`--kw` · earlier files win:

```bash
python3 - "$WORKDIR/plan.json" > "$WORKDIR/kw_params.json" <<'PY2'
import json,sys
p=json.load(open(sys.argv[1],encoding="utf-8")); ks=[]
for g in [p["target"], p.get("marketTarget") or {}]+p.get("external",[])+p.get("internal",{}).get("parts",[]):
    for k in g.get("keywords",[]) + g.get("broad",[]):   # broad = representative-spelling coverage check (do not drop)
        if k not in ks: ks.append(k)
print(json.dumps({"keywords":ks,"gl":"<gl>","data_type":"all"},ensure_ascii=False))
PY2
```

Use the content of `kw_params.json` as `<PARAMS>` for that keyword_info call (lookup · call · fetch_dl).

## Step 4 · build (code)

```bash
python3 "$R/ds_aggregate.py" build --plan "$WORKDIR/plan.json" --kw "$WORKDIR"/lm_keyword_info*.json \
  --intent "$WORKDIR"/lm_intent_*.json --cluster "$WORKDIR/lm_cluster.json" \
  --gl <gl> --lang <lang> --date "$(date +%F)" --out "$WORKDIR/facts.json" --brief "$WORKDIR/facts.md"
```

It prints one line: `판정 · 외부 N · 내부 N · 측정값 없음 N · finder 미발견 N · 합계 검산 N개 OK` (verdict · external · internal · no value · not in
finder · sum checks OK).
- `⚠ 대표 표기 커버 낮음 <브랜드>` (representative-spelling coverage low · entity) = section 1's representative spellings are under 90% of that
  brand's detailed bundle. Look at the facts.md warning and the large spellings missing from it, add that brand's spelling (M5a · English · short
  form) to picks.external and rerun from plan. Not shown in the report (working check). Only if nothing can be added, mention the limit in one
  section 1 insight line.
- `⚠ 판정 흔들림 (빼면 바뀜: ○○)` (verdict unstable · changes when removed) = removing one comparison target flips the verdict. Not shown in the
  report; before publishing, check that the target is at the same position and level (M5-1) and that the set is not too small. If the set is right,
  publish as is but add one section 1 insight line saying "the conclusion can depend on the comparison targets".
- `⚠ 가까운 시장 근거 없는 비교 대상 ○○` (comparison target without nearby-market evidence) = if you did not get the M5-7 confirmation, choose the set again before the report.
- exit 12 = sum check failed (bundle value ≠ sum of its queries · 12-month period ≠ sum of months · section 2 total ≠ sum of bundles). It is a code
  problem — do not patch by hand; find the cause.
- With fewer than 3 comparison items that have a 4-year change, the verdict is `판정 보류` (no verdict) → add comparison targets (M5-4) and build again.
- If a main keyword of the target, comparison set or inside is missing, fix picks and rerun from plan. Missing minor long-tail is normal.

## Step 5 · Read facts.md

Read **all** of `facts.md` (section order = report order: external → internal). Only the number strings written there may appear in narrative.

## Step 6 · narrative.json (you) → lint

Read `narrative.md` and write it (overview + insights per section only · section 2 cards need `group` · no lead / synthesis / actions).
**Write it in the REPORT LANGUAGE (`lang`).**

```bash
python3 "$R/ds_aggregate.py" lint --facts "$WORKDIR/facts.json" --narrative "$WORKDIR/narrative.json"
```

Fix until it says `lint OK`. Resolve every warning too.

## Step 7 · render + deliver

```bash
python3 "$R/ds_render.py" --facts "$WORKDIR/facts.json" --narrative "$WORKDIR/narrative.json" --out "$WORKDIR/search-demand-report.html"
```

The HTML carries `<meta name="search-demand-report-version" content="…">`. Never hand-edit it.

- claude.ai: publish `$WORKDIR/search-demand-report.html` as an Artifact. If the user wants the file, present_files.
- Claude Code / Desktop: give the path.

The chat answer is a 3–5 sentence summary and the link only, in the user's language. Do not copy the report contents into chat.
