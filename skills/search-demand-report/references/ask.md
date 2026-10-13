# Mode check · seed-fit check and fixed question (ask-v2)

This skill assumes the seed is **something people buy** (a brand · product · item). A seed that is a goal or topic, such as 다이어트 (diet), or a seed whose mode is doubtful,
produces a wrong 01 comparison group and a wrong 02 breakdown if run as is. So **check it in code right after Step 1, and if it is flagged, ask once in a fixed format.**
When to ask, the format, the options and how to handle the answer are fixed below. Do not improvise a different question.

## 1. When to ask — the code decides

```bash
python3 "$R/ds_classify.py" check --seed "$WORKDIR/seed.json" --intent "$WORKDIR/lm_intent_seed.json" --out "$WORKDIR/fit.json"
# exit 0 = continue · exit 10 = show the question below and stop
```

| kind | Condition (FIT constants · ds_classify.py) | Meaning |
|---|---|---|
| `topic` | category mode · share of related queries combined with purchase-exploration terms (price · lowest price · discount · buy · recommendation · comparison · ranking · brand · types · reviews · value for money, etc.) < 10% · and the share combined with method · meal plan · effect · recipe terms is at least that | Not a thing people buy but a goal or topic (다이어트, diet) |
| `mode` | The mode in seed.json differs from the mode judged from the related-query composition (keyword-method M0) · or the composition cannot decide | entity but queries containing the brand < 50% (generic word · homonym) · category but one brand is half or more, or fewer than 2 brands |

Calibration from real data: 러닝화 purchase exploration 16.7% · 전기압력밥솥 18.9% · 쿠쿠 밥솥 8.5% (entity · brand contained 100%) · bhc 5.9% (entity) → continue / 다이어트 5.7%, method-combined 8.2% → ask.

**If kind is `broad` · `brandwide`, go to `scope.md` (narrowing the seed), not this document.** The broad-seed check runs before the topic check (v5). Below covers only topic · mode.
The mark that a topic question was answered (fit.asked) applies only to topic · mode questions — it does not skip broad-seed narrowing.

**On exit 10, make no further MCP calls** (except the 2 verification calls in scope.md). The intent · cluster data already received is reused as is after the answer.

## 2. How to ask — fixed format

On claude.ai use the button-style question tool (ask_user_input); if it is not available, write the same content as text. Do not change the order. Write wording and buttons in the language the user wrote in (translate the fixed wording faithfully in meaning · do not translate search terms).

1. **One-line summary** — "‘{시드}’는 {사는 물건이 아니라 목표·주제 / 모드가 의심스러운} 시드라 진행 방식을 정해야 합니다. 지금까지 MCP {N}회 호출." (“‘{seed}’ is a seed that {is a goal or topic, not a thing people buy / has a doubtful mode}, so we need to decide how to proceed. MCP calls so far: {N}.”)
2. **Evidence table** — the signals from fit.json as is (metric · value · threshold).
3. **Three options** — the fixed wording per kind below. For each option, one line on what happens to 01 · 02.
4. **One recommendation with a one-line reason.**
5. Ask **only once**. If there is no answer, do not proceed with the recommendation; wait.

### kind = topic

| Choice | Wording | 1 Market flow comparison | 2 Target keyword intent change |
|---|---|---|---|
| A (recommended) | 주제형으로 진행 (Proceed as a topic) | Other goals · topics at the same position (if there are no finder candidates, analyst lookup) | **By method** (unit = 방법, method) |
| B | 카테고리 규칙 그대로 진행 (Proceed with category rules as is) | Same top-level category (analyst lookup likely) | Intent groups |
| C | 시드를 사는 물건으로 좁혀 다시 시작 (Narrow the seed to a thing people buy and restart) | — | — (get a new seed from the user. e.g. 다이어트 보조제 · 다이어트 식품) |

### kind = mode

| Choice | Wording |
|---|---|
| A (recommended) | 연관 검색어 구성 판정대로 진행 (판정 불가면 seed.json 의 모드) (Proceed with the mode judged from related-query composition; if undecidable, the mode in seed.json) |
| B | seed.json 의 모드 그대로 진행 (Proceed with the mode in seed.json as is) |
| C | 시드를 다시 정해 시작 (브랜드명 + 품목으로) (Choose the seed again and restart, as brand name + item) |

## 3. After the answer

| Answer | Handling |
|---|---|
| topic · A | Leave seed.json as is. In picks.json set `internal.unit` = `"방법"` (2 is by method instead of intent groups). For 02 pick only **proper method names** that attach in front of the seed, as in '○○ 다이어트' (키토 · 스위치온 · 간헐적 단식 · 저탄고지 · 마녀스프). Drop people (홍현희) · food ingredients on their own (두부 · 감자) unless they are a method. For 01 pick other goals · topics by rule P3 (same position · semantic distance). |
| topic · B | Proceed as a normal category. |
| topic · C / mode · C | Start from Step 0 with the new seed. Keep, do not discard, the earlier call results. |
| mode · A / B | Change the mode in seed.json to match the answer, leave `fit`, and run check again (if asked, it passes without asking again) → from Step 2. |

Leave `"fit": {"kind": "...", "asked": true, "answer": "A"}` in seed.json and run check again. check appends "(적합성 점검: {kind} → {답} · {모드} 로 진행)" ("(fit check: {kind} → {answer} · proceeding as {mode})") to the end of modeReason. It appears as is in the mode-decision line at the top of the report.
