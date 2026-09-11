## 前提条件の確認

`{SKILL_DIR}/_shared/render/{path_aggregate.py,render_report.py,components.py,components_path.py}`、
`{SKILL_DIR}/_shared/{styles,labels,templates}` が揃って存在している必要があります。
python3(標準ライブラリ)のみを使用します。レポートは zip の customer-analysis と同じカードシェルの上に
検索ジャーニーのフロー図・経路カード・ハブカードを載せた形です(外部 JS への依存なし)。

このレポートは ListeningMind **PathFinder(パスファインダー)** エージェントの分析フレーム —
検索行動を**有向グラフ(顧客検索ジャーニー/CDJ)** として捉え、**主要経路(Top 5)** と
**核心的な分岐点(Hub, Top 3)** を導き出すフレーム — を移植したものです。

<!-- 原本の分析フレームのスナップショット: references/prompts/agent_path.framework.kr.md
     (ascentkorea-hubble-ai-api prompt_builder.py:56-109 DEFAULT_PROMPTS["path"])。
     本番運用のプロンプトは gpt_prompt DB の `agent_path` 行であり、リポジトリには
     公開されていないため、リポジトリ内 fallback のフレームワークをスナップショットとして保存する。
     ステップ 3 のプロンプトは、このフレーム(構造の把握 → Top5 経路(3 つのフロータイプ) → Hub&Branch 3 個)を
     JSON 出力形に翻案したものである。チャット専用マークアップ(:k[]/:::accordion)と「数値の明示」
     規則は意図的に除外(数値は Python が埋める)。 -->

**PathFinder のデータ契約**: 公開版の `path_finder` は純粋な経路(`data: List[List[str]]`)のみを
返し、ノード指標がありません。本番エージェントが見る内部の `PathDataDTO`(paths + info +
intent)を再現するため、**2 回呼び出し**ます — `path_finder`(ジャーニー構造)+
`keyword_info`(経路内の固有ノードの検索ボリューム・意図・月次推移)。こうすることで queryfinder と同じ
「**数値は Python が実 API から計算する**」原則が成立し、経路・ハブのランキングは本番エージェントと
同じく `volume`(月間平均検索ボリューム)を第 1 の指標として使います。

## 実行手順

### ステップ 0 — 入力の収集 + 作業フォルダ

データは **ListeningMind MCP ツール**で取得します。**API キーを尋ねないでください** —
環境変数・`.env`・DB などからキーを探そうともしないでください。

必要な入力は 3 つだけです:

> 検索ジャーニー分析を開始します。
> 1. **シードキーワード** — すでにいただいていれば省略
> 2. **国** — 既定は `jp`(特に指定がなければ jp で進めます)
> 3. **時点** — 既定は `curr`(現在)。過去との比較は `3m`/`6m`/`9m`/`12m`

シードがすでに与えられていればそのまま進めます。

**MCP コネクタが無い場合** · ステップ 1 のツール呼び出しが「ツールが見つかりません」で失敗します。
そのときはユーザーに **ListeningMind MCP コネクタの接続**を依頼して中断してください。
データを作り出さないでください。

確保できたら:

```bash
SAFE_SEED=$(echo "<SEED>" | tr ' /\\:*?"<>|' '_')
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
WORKDIR="$PWD/tmp/reports/listeningmind-path-opportunity-${SAFE_SEED}-${TIMESTAMP}"
mkdir -p "$WORKDIR"
echo "作業フォルダ: $WORKDIR"
```

以降 `{WORKDIR}` は上の絶対パスに置き換えます。

### ステップ 1 — データ収集(MCP 2 回呼び出し)

> **呼び出しごとに例外なく 3 ステップ**(SKILL.md §Step 4):
> ① `mcp_cache.py lookup` → ②(ミスなら)MCP 呼び出し + 応答ファイルの確保 + `store` → ③ `log_event.py --type tool_call`
>
> ① が **exit 0** ならファイルはすでに埋まっているので **MCP を呼ばずに** ③ へ進みます
> (`--cached --used-credits-delta 0`)。**exit 2** なら ② に進みます。

**1a. 検索ジャーニー(経路)** — `path_finder`(応答の `data` = 経路の配列 `List[List[str]]`)

```bash
# ① キャッシュ確認
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup path_finder \
  --params '{"keyword":"<SEED>","gl":"<GL>","time_point":"<TIME_POINT>","limit":300}' \
  --out "{WORKDIR}/lm_path.json"
```

ミスなら **`path_finder` MCP ツール**を以下のパラメータで呼び出します:

```json
{"keyword": "<SEED>", "gl": "<GL>", "time_point": "<TIME_POINT>", "limit": 300,
 "user_query": "<ユーザー発話の原文そのまま>"}
```

> `limit`(経路数)は既定 300。`time_point` はステップ 0 で受け取った値(既定 `curr`)。
> 応答の `data` の各内部配列が**一つの順序を持つ検索ジャーニー**(q0 → q1 → q2 …)です。
>
> `user_query` はキャッシュキーから除外されるため `--params` には入れません(上の lookup を参照)。

応答を `{WORKDIR}/lm_path.json` として確保したうえでキャッシュに格納します
(応答が大きくホストがファイルに保存した場合はそのパスを `cp` · 本文で返った場合は heredoc —
SKILL.md §応答ファイルの規則を参照):

```bash
# ② キャッシュ保存
python3 {SKILL_DIR}/scripts/mcp_cache.py store path_finder \
  --params '{"keyword":"<SEED>","gl":"<GL>","time_point":"<TIME_POINT>","limit":300}' \
  --file "{WORKDIR}/lm_path.json"

# ③ tool_call の発行
python3 "$SKILL_DIR/scripts/log_event.py" --type tool_call --session-id "$SID" \
  --tool path_finder \
  --request-body '{"keyword":"<SEED>","gl":"<GL>","time_point":"<TIME_POINT>","limit":300}' \
  --used-credits-delta <cost_detail.total_cost> \
  --used-credits-cumulative <used_credits> \
  --intent journey_analysis
```

**1b. ノードの検索ボリューム補強** — 経路に登場した**固有キーワード**を抽出して `keyword_info`
(`data_type=all` → `ads_metrics`・`intents`・`monthly_volume` を含む)でノードごとの指標を取得します:

```bash
python3 - "{WORKDIR}/lm_path.json" <<'MKPARAM' > "{WORKDIR}/kw_params.json"
import json, sys
d = json.load(open(sys.argv[1]))
data = d.get("data") or (d.get("result", {}) or {}).get("paths") or []
# 経路に登場した順に固有キーワードを収集 (keyword_info maxItems=1000 の上限)
seen, kws = set(), []
for path in data:
    for kw in (path if isinstance(path, list) else []):
        if isinstance(kw, str) and kw.strip() and kw not in seen:
            seen.add(kw); kws.append(kw.strip())
kws = kws[:1000]
print(json.dumps({"keywords": kws, "gl": "<GL>", "data_type": "all"}, ensure_ascii=False))
MKPARAM

# ① キャッシュ確認
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --out "{WORKDIR}/lm_nodes.json"
```

ミスなら **`keyword_info` MCP ツール**を `kw_params.json` の内容 + `user_query` で
呼び出し、応答を `{WORKDIR}/lm_nodes.json` として確保したうえで保存します:

```bash
# ② キャッシュ保存
python3 {SKILL_DIR}/scripts/mcp_cache.py store keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --file "{WORKDIR}/lm_nodes.json" --expect <data 配列の長さ>

# ③ tool_call の発行
python3 "$SKILL_DIR/scripts/log_event.py" --type tool_call --session-id "$SID" \
  --tool keyword_info --request-body "$(cat "{WORKDIR}/kw_params.json")" \
  --used-credits-delta <cost_detail.total_cost> \
  --used-credits-cumulative <used_credits> \
  --intent journey_analysis
```

- どちらの応答も `result` が `FAILED` か、ツール呼び出しが失敗した場合は中断・報告してください
  (コネクタ・シード・gl を確認)。作り出さないでください。
- `path_finder` の `data`(経路)が空の場合は、シード/国/時点を確認して中断します。
- `keyword_info` が一部のキーワードを返せなくても進行できます(該当ノードは検索ボリューム 0 でレンダリング —
  経路の構造は維持)。ただし大半が 0 ならノードの検索ボリューム補強が失敗しているので gl を再確認してください。

### ステップ 2 — ジャーニーグラフの集計

```bash
python3 {SKILL_DIR}/_shared/render/path_aggregate.py context \
  --paths "{WORKDIR}/lm_path.json" --nodes "{WORKDIR}/lm_nodes.json" \
  --seed "<SEED>" --gl <GL> --date <YYYY-MM-DD> --time-point <TIME_POINT> \
  --out "{WORKDIR}/lm_path_result.json"
```

`lm_path_result.json` には、ノード(検索ボリューム・意図)・エッジ(経路の隣接から導出)・ハブ(分岐数)・ジャーニーの
フロー図(flowTree)と、LLM 分析に渡す `pathsText`(候補の経路)・`hubsCsv`(候補のハブ)・`nodesCsv`
が入っています。`{WORKDIR}/lm_path_result.json` を読み、その中の `pathsText`・`hubsCsv` の
値をステップ 3 の分析入力として使います。

### ステップ 3 — PathFinder 分析(LLM)→ lm_paths_raw.json

以下の規則に従って `lm_path_result.json` の `pathsText`(候補の経路)・`hubsCsv`(候補のハブ)を
直接分析し、結果を **JSON のみ**で `{WORKDIR}/lm_paths_raw.json` に保存します。

---

#### 分析規則(Search Journey Analyst)

あなたは検索ジャーニーのインサイトアナリストです。目標は、消費者がキーワードからキーワードへ移動する
**検索ジャーニー(経路)** と**核心的な分岐点(Hub)** を読み解き、どこでコンバージョンに収束し
どこで離脱するのかを明らかにすることです。

**入力**:
- `pathsText`: 候補となるジャーニーの一覧。各行 = `番号. A → B → C …  (合算検索ボリューム N)`。検索ボリュームの降順。
- `hubsCsv`: 候補となるハブの一覧。`name,volume,out_degree,path_count,downstream`。
  `out_degree` = このキーワードから分かれる次のキーワードの数(=分岐数)。大きいほど重要な分岐点。
- `nodesCsv`: ノード表(参考用)。`id,name,volume,volume_trend,intent,out_degree,path_count,outgoing`。

**全体規則**:
- **データの根拠のみ**: 上の入力に無いキーワード・事実を作り出さないでください。
- **数値の断定を避ける(重要)**: 検索ボリューム・順位・分岐数のような**数値をテキストで断定しないでください**
  (「最も大きい」「N 個」「N 倍」は禁止)。数値はコードがバッジ・チップに実測値として埋めます。あなたは
  **定性的な解釈**(なぜこのジャーニーなのか、どこで分かれ離脱/収束するのか、どう攻略するか)だけを書きます。
- **マークアップ**: 強調が必要な核心的な名詞句には `<strong>...</strong>` のみ許可。それ以外のマークアップ
  (`:k[]`、`:::accordion`、`➊`、コードブロック、表)は絶対に使わないでください。
- **出力言語** = 分析市場(`<GL>`)の言語。jp → 日本語。
- `path` と `keyword`・`evidenceKeywords` には、必ず入力に**実際に登場したキーワードの原文**のみを
  使います(翻訳・変形・創作は禁止)。コードが未登場のキーワードを後処理で除去するため、作り出すと
  その項目はレポートから消えます。

**① 分析の概要(overview)**
- ジャーニーグラフ全体を貫く核心的な洞察を 1〜2 文(100〜200 字)。小見出しなしで記述。
- どの軸で分岐するのか、どこへ収束/離脱するのかを要約。表紙のデータに基づく要約文として載ります。

**② 主要経路 Top 5(topPaths)** — 最大 5 つ
- `pathsText` から代表性のあるジャーニーを 5 つ選び、それぞれに**フロータイプ**を付けます:
  1. **コンバージョンへ収束するフロー** → `flowType: "conversion"`
  2. **比較/検証で停滞するフロー** → `flowType: "comparison"`
  3. **リスク/不信で離脱するフロー** → `flowType: "risk"`(**最大 2 つ**)
- 各経路:
  - `flowType`: 上の 3 つのいずれか(`conversion`|`comparison`|`risk`)
  - `path`: ジャーニーのキーワード列(入力の正確な原文の配列、順序を維持)— 最低 2 つ(遷移 1 つ以上)
  - `intent`: この経路をたどる顧客の意図を一行で(定性)
  - `leakOrMerge`: 経路から**抜け出す地点**、または経路が**合流して強くなる地点**(定性)
  - `action`: 解決/強化のアクションを 1〜2 文(定性)
  - `evidenceKeywords`: この経路の根拠キーワード/ハブ(入力にある原文のみ、2〜4 個)

**③ 核心的な分岐点 Top 3(hubs)** — 最大 3 つ
- `hubsCsv` の `out_degree` が大きいキーワードのうち、最も重要な分岐点を 3 つ選びます。
- 各ハブ:
  - `keyword`: ハブキーワード(入力の原文)
  - `meaning`: この分岐が何を意味するのか(顧客の心理)を 1 文
  - `dilemmas`: 顧客がここで抱える悩みを 2〜3 個(文字列の配列)
  - `actions`: 私たちがすぐ実行できるアクションを 2 個(文字列の配列)

---

#### 出力形式 — JSON only(Markdown・説明は禁止)

```json
{
  "overview": "核心的な洞察 1〜2 文",
  "topPaths": [
    {
      "flowType": "conversion",
      "path": ["冷蔵庫", "冷蔵庫 価格", "キムチ冷蔵庫 価格"],
      "intent": "この経路をたどる顧客の意図を一行で",
      "leakOrMerge": "離脱/合流地点の記述",
      "action": "解決/強化のアクション 1〜2 文",
      "evidenceKeywords": ["根拠キーワード1", "根拠キーワード2"]
    }
  ],
  "hubs": [
    {
      "keyword": "冷蔵庫",
      "meaning": "この分岐の意味(顧客の心理)を 1 文",
      "dilemmas": ["顧客の悩み1", "顧客の悩み2"],
      "actions": ["実行アクション1", "実行アクション2"]
    }
  ]
}
```

上の JSON を `{WORKDIR}/lm_paths_raw.json` に保存します。

### ステップ 4 — 経路/ハブの後処理(検索ボリューム合算・ハルシネーションフィルタ)

```bash
python3 {SKILL_DIR}/_shared/render/path_aggregate.py paths \
  --raw-paths "{WORKDIR}/lm_paths_raw.json" \
  --context "{WORKDIR}/lm_path_result.json" \
  --out "{WORKDIR}/lm_paths.json"
```

このスクリプトが各経路のノードごとの検索ボリュームチップ・合算検索ボリュームバッジ・ステップ数、各ハブの検索ボリューム・分岐数・
downstream キーワードをコードで計算してカード用の形に保存し、ステップ 3 の `overview` は表紙の要約文として
そのまま通します。さらに**ハルシネーションの遮断**: `path`・`evidenceKeywords`・ハブの `keyword` のうち実際のグラフの
ノードでないものは除去され、実在ノードが 2 つ未満の経路/未登場のハブは丸ごと捨てられます。
ステップ 3 の結果がこのフィルタですべて空になるとスクリプトがエラーで停止するので、ステップ 3 をやり直してください。

### ステップ 5 — インサイト・実行提案(LLM)→ lm_actions.json

`{WORKDIR}/lm_paths.json` の経路・ハブをもとに、以下の JSON を `{WORKDIR}/lm_actions.json`
に保存します。出力言語は gl のマッピング(jp→日本語)。**数値の断定は禁止**(ステップ 3 と同じ)、
`<strong>` 以外のマークアップは禁止。

- `synthesis`: ジャーニー・分岐の地形を横断する総評を 2〜3 文
- `insights`: 詳細インサイトを**ちょうど 3 つ** `{"title","body"}` — ジャーニーから見つかった行動に基づく結論。
- `now`: 今すぐ試せる実行提案を 2〜3 つ `{"title","body"}`
- `future`: 今後注目すべき機会を 2〜3 つ `{"title","body"}`

```json
{
  "synthesis": "総評 2〜3 文",
  "insights": [{"title": "見出し", "body": "行動に基づく結論 1〜2 文"}],
  "now": [{"title": "実行提案の見出し", "body": "実行内容 1〜2 文"}],
  "future": [{"title": "機会の見出し", "body": "機会の説明 1〜2 文"}]
}
```

### ステップ 6 — HTML レンダリング

```bash
python3 {SKILL_DIR}/_shared/render/render_report.py --skill path-opportunity \
  --paths "{WORKDIR}/lm_paths.json" \
  --actions "{WORKDIR}/lm_actions.json" \
  --meta "{WORKDIR}/lm_path_result.json" \
  --category "<SEED>" --gl <GL> --date <YYYY-MM-DD> \
  --out "{WORKDIR}/path-opportunity-report.html"
```

### ステップ 7 — ユーザーへの案内

```
✅ 検索ジャーニー分析レポートの生成が完了しました: {WORKDIR}/path-opportunity-report.html
ブラウザで開くと検索ジャーニーのフロー図・経路カード・ハブカードとインサイトをダッシュボード/A4 ビューで確認でき、
Cmd+P で A4 PDF として保存できます。
macOS ですぐ開く: open {WORKDIR}/path-opportunity-report.html
```
