## 前提条件の確認

`{SKILL_DIR}/_shared/render/{query_aggregate.py,render_report.py,components.py}`、
`{SKILL_DIR}/_shared/{styles,labels,templates}` が揃って存在している必要があります。
python3(標準ライブラリ)のみを使用します。レポートは zip の customer-analysis と同じカード形式です。

このレポートは ListeningMind **QueryFinder(インテントファインダー)** の実際の分析プロンプト
(agent_query v0.4.7)の分析フレームを移植し、関連クエリを**検索目的**と**ブランド/ノンブランド**に
まとめてカードで提示します。

<!-- 原本プロンプトのスナップショット: references/prompts/agent_query.1958.kr.md (v0.4.7, 2026-07-01)
     + agent_system_prompt.1758.kr.md — gpt_prompt DB(intent-finder-dev)から 2026-07-20 export。
     ステップ3のプロンプトがこの原本の分析フレーム(ターゲット/意図キーワードの分解・意図タイプ・
     Top5 検索目的・Top5 ブランド/ノンブランド・volume_avg 専用・上位 1,000 件キャップ)を
     JSON 出力形に翻案したものであることを照合・検証する際は、このスナップショットと diff してください。
     チャット専用マークアップ(:k[]/:::accordion/➊)と「正確な数値の明示」規則は意図的に除外
     (数値は Python が埋める — 決定 1)。
     kbf フィールドは原本に無いスキル独自の拡張(zip persona-card スキーマ由来)です。
     運用プロンプトの更新有無は四半期に一度 gpt_prompt の KR 最新アクティブ行と再照合。 -->

## 実行手順

### ステップ 0 — 入力の収集 + 作業フォルダ

データは **ListeningMind MCP ツール**で取得します。**API キーを尋ねないでください** —
環境変数・`.env`・DB などからキーを探そうともしないでください。

必要な入力は 2 つだけです:

> クエリ機会分析を開始します。
> 1. **シードキーワード** — すでにいただいていれば省略
> 2. **国** — 既定は `jp`(特に指定がなければ jp で進めます)

シードがすでに与えられていればそのまま進めます。

**MCP コネクタが無い場合** · ステップ 1 のツール呼び出しが「ツールが見つかりません」で失敗します。
そのときはユーザーに **ListeningMind MCP コネクタの接続**を依頼して中断してください。
データを作り出さないでください。

確保できたら:

```bash
SAFE_SEED=$(echo "<SEED>" | tr ' /\\:*?"<>|' '_')
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
WORKDIR="$PWD/tmp/reports/listeningmind-query-opportunity-${SAFE_SEED}-${TIMESTAMP}"
mkdir -p "$WORKDIR"
echo "作業フォルダ: $WORKDIR"
```

以降 `{WORKDIR}` は上の絶対パスに置き換えます。

### ステップ 1 — データ収集(MCP 2 回呼び出し)

関連キーワードの**一覧**とキーワードの**詳細**でツールが分かれています。
`intent_finder` で関連キーワードの文字列一覧を受け取り、その一覧を `keyword_info` に渡して
検索ボリューム・意図・月次推移を含む詳細を受け取り、`lm_query.json` として保存します。

> **呼び出しごとに例外なく 3 ステップ**(SKILL.md §Step 4):
> ① `mcp_cache.py lookup` → ②(ミスなら)MCP 呼び出し + 保存 + `store` → ③ `log_event.py --type tool_call`
>
> ① が **exit 0** ならファイルはすでに埋まっているので **MCP を呼ばずに** ③ へ進みます
> (`--cached --used-credits-delta 0`)。**exit 2** なら ② に進みます。

**1a. 関連キーワードの一覧** — `intent_finder`

```bash
# ① キャッシュ確認
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup intent_finder \
  --params '{"keywords":["<SEED>"],"gl":"<GL>","limit":1000,"sort":"volume_avg","order":"desc","volume_threshold":0}' \
  --out "{WORKDIR}/lm_keyword_list.json"
```

ミスなら **`intent_finder` MCP ツール**を以下のパラメータで呼び出します:

```json
{"keywords": ["<SEED>"], "gl": "<GL>", "limit": 1000,
 "sort": "volume_avg", "order": "desc", "volume_threshold": 0,
 "user_query": "<ユーザー発話の原文そのまま>"}
```

> **`volume_threshold` は必ず `0`** — ListeningMind の Web UI と同じく関連キーワードを
> **全量**収集します。上げると月間平均検索ボリュームがその値未満のキーワードが切り捨てられ、
> 地形が歪みます(例: `100` なら検索ボリューム 100 未満のロングテールが丸ごと欠落)。件数は
> `limit:1000` + 以降の上位 1,000 件の上限ですでに制限されているので、下限で追加で切らないでください。
>
> `user_query` はキャッシュキーから除外されるため `--params` には入れません(上の lookup を参照)。

応答の原文をそのまま保存し、キャッシュに格納します(`data` = キーワード文字列の配列、検索ボリューム順にソート済み):

```bash
cat > "{WORKDIR}/lm_keyword_list.json" <<'DUMP_EOF'
<intent_finder 応答 JSON の原文全体>
DUMP_EOF

# ② キャッシュ保存 · --expect にエンベロープの data 配列の長さを入れて照合
python3 {SKILL_DIR}/scripts/mcp_cache.py store intent_finder \
  --params '{"keywords":["<SEED>"],"gl":"<GL>","limit":1000,"sort":"volume_avg","order":"desc","volume_threshold":0}' \
  --file "{WORKDIR}/lm_keyword_list.json" --expect <data 配列の長さ>

# ③ tool_call の発行
python3 "$SKILL_DIR/scripts/log_event.py" --type tool_call --session-id "$SID" \
  --tool intent_finder \
  --request-body '{"keywords":["<SEED>"],"gl":"<GL>","limit":1000,"volume_threshold":0}' \
  --used-credits-delta <cost_detail.total_cost> \
  --used-credits-cumulative <used_credits> \
  --intent query_expansion
```

**1b. キーワードの詳細** — `keyword_info` · 上の一覧の**上位 1,000 件**
(本番 QueryFinder と同じ上限 — `ai-context-intent` size=1000 / `MAX_KEYWORDS=1000`)

まず一覧から上位 1,000 件を取り出してパラメータファイルを作ります:

```bash
python3 - "{WORKDIR}/lm_keyword_list.json" <<'MKPARAM' > "{WORKDIR}/kw_params.json"
import json, sys
d = json.load(open(sys.argv[1]))
# 本番と同じく上位 1,000 件すべてを詳細取得する (keyword_info maxItems=1000)。
# 200 件などに切ると総検索ボリューム・グループ合算が過少集計され本番とずれる。
kws = [k for k in d.get("data", []) if isinstance(k, str)][:1000]
print(json.dumps({"keywords": kws, "gl": "<GL>", "data_type": "all"}, ensure_ascii=False))
MKPARAM

# ① キャッシュ確認
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --out "{WORKDIR}/lm_query.json"
```

ミスなら **`keyword_info` MCP ツール**を `kw_params.json` の内容 + `user_query` で
呼び出します。**`data_type` は必ず `all`**、**キーワードは上位 1,000 件すべて**です。

> **規模を勝手に減らさないでください。** 応答が大きいという理由で 300 件に切ったり
> `data_type` を `ads_metrics` に下げたりすると、総検索ボリューム・グループ合算が過少集計になり、
> 月次推移チャートが空になって本番とずれます。応答が大きい場合は下の**経路 A** で
> 処理すればよいので、取得範囲を狭める理由はありません。

応答の受け取り方は、応答のサイズによって 2 つに分かれます。

#### 経路 A — 応答が大きくホストがファイルに保存した場合(1,000 件は大抵こちら)

ツールの結果が本文の代わりに次のような案内で返ることがあります:

```
Tool result too large for context, stored at
/mnt/user-data/tool_results/ListeningMind_keyword_info_<id>.json.
Use grep to search for specific content or head/tail to read portions.
```

**これは失敗ではありません。応答の全体がすでにそのファイルに入っています。**
書き写す必要はなく、**そのパスをそのまま渡せば済みます**:

> 保存ファイルがエンベロープではなく `[{"type":"text","text":"<JSON 文字列>"}]` のラッパーで
> 包まれていることがあります(実測 · claude.ai Web コンテナ)。`mcp_cache.py store` が
> **自動で外して正規化**するので手を加えないでください。外した後のレコード数が
> `--expect` と照合されます。

```bash
# ホストが保存したパスをそのまま使う (原文の欠落なし)
SAVED="/mnt/user-data/tool_results/ListeningMind_keyword_info_<id>.json"

# レコード数の確認 (本文をコンテキストに読み込まず件数だけ数える)
python3 -c "import json;print(len(json.load(open('$SAVED')).get('data',[])))"

# 作業フォルダへコピー + キャッシュ保存
cp "$SAVED" "{WORKDIR}/lm_query.json"
python3 {SKILL_DIR}/scripts/mcp_cache.py store keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --file "{WORKDIR}/lm_query.json" --expect <上で数えた件数>
```

クレジットはエンベロープから読みます — ファイルが大きくてもこの 2 つの値だけ取り出せば済みます:

```bash
python3 -c "
import json; d=json.load(open('$SAVED'))
print('delta=', (d.get('cost_detail') or {}).get('total_cost'))
print('cumulative=', d.get('used_credits'))"
```

#### 経路 B — 応答がコンテキストにそのまま返った場合(小規模)

応答の原文を**加工せずそのまま**保存します:

```bash
cat > "{WORKDIR}/lm_query.json" <<'DUMP_EOF'
<keyword_info 応答 JSON の原文全体>
DUMP_EOF

python3 {SKILL_DIR}/scripts/mcp_cache.py store keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --file "{WORKDIR}/lm_query.json" --expect <data 配列の長さ>
```

#### ③ tool_call の発行(経路 A・B 共通)

```bash
python3 "$SKILL_DIR/scripts/log_event.py" --type tool_call --session-id "$SID" \
  --tool keyword_info --request-body "$(cat "{WORKDIR}/kw_params.json")" \
  --used-credits-delta <cost_detail.total_cost> \
  --used-credits-cumulative <used_credits> \
  --intent query_expansion
```

> **禁止事項** · 応答が大きいからといって ① キーワード数を減らす ② `data_type` を下げる
> ③ レコードを要約・抜粋して書き写す、のいずれもしないでください。3 つともレポートの数値を
> 静かに壊します。大きい場合は経路 A を使い、`--expect` で件数を照合してください。
> ずれると `store` が拒否します。縮小が避けられないと判断した場合は、
> **進めずにユーザーへ状況を報告**してください。

> 本番との照合: ハブルチャットの QueryFinder(`ascentkorea-hubble-ai-api`)は内部 API
> `ai-context-intent` を **1 回呼び出し**て上位 1,000 件を full metrics で受け取る。この内部
> エンドポイントは公開されていないため、公開ツールでは `intent_finder`(上位 1,000)+
> `keyword_info`(その 1,000 件の詳細)の **2 回呼び出し**で同じ上位 1,000 件のデータセットを再現する。
> (どちらも上位 1,000 件の上限なので、ListeningMind Web UI の全キーワード合計とは異なる場合がある。)

`keyword_info` の応答は最上位に `data`(レコード配列)を持つため、集計スクリプトがそのまま読みます
(変形は不要 — 各レコードに `keyword`・`ads_metrics`・`intents`・`monthly_volume` が含まれます)。

- どちらの応答も `result` が `FAILED` か、ツール呼び出しが失敗した場合は中断・報告してください
  (コネクタ・シード・gl を確認)。作り出さないでください。
- 関連キーワードが 200 件未満なら、ある分だけで次に進みます。

### ステップ 2 — キーワードコンテキストの集計

```bash
python3 {SKILL_DIR}/_shared/render/query_aggregate.py context \
  --raw "{WORKDIR}/lm_query.json" --seed "<SEED>" --gl <GL> --date <YYYY-MM-DD> \
  --out "{WORKDIR}/lm_query_result.json"
```

`lm_query_result.json` にはキーワードごとの `volume_avg`・`intents` と、LLM 分析に渡す `csv` テキストが入っています。
`{WORKDIR}/lm_query_result.json` を読み、その中の `csv` の値をステップ 3 の分析入力として使います。

### ステップ 3 — QueryFinder 分析(LLM)→ lm_groups_raw.json

以下の規則に従って `lm_query_result.json` の `csv`(関連クエリデータ)を直接分析し、
結果を **JSON のみ**で `{WORKDIR}/lm_groups_raw.json` に保存します。

---

#### 分析規則(Data Insight Analyst)

あなたは検索データのインサイトアナリストです。目標は関連クエリデータを分析して**検索意図(検索目的)**
と**ブランド/ノンブランドの地形**、戦略的インサイトを導き出すことです。

**入力**: `csv` の各行 = `keyword, volume_avg, i, n, c, t, trend`
- `volume_avg` = **月間平均検索ボリューム**。検索ボリュームは常にこの値を使います(年間総量・×12 は禁止)。
- `i/n/c/t` = 情報(informational)/ナビゲーション(navigational)/商業調査(commercial)/取引(transactional)の意図比率。
- `trend` = 検索ボリュームの増減トレンド(正=上昇傾向、負=下降傾向)。**上昇傾向のキーワードは
  伸びている需要なのでグルーピング・インサイトで注目**しますが、トレンドへの言及は「上昇傾向/下降傾向」
  のような定性的表現のみとし、数値や倍率は使わないでください。
- `volume_avg` の降順で上位 1,000 件までを分析します(すでにソート・上限適用済み)。

**全体規則**:
- **データの根拠のみ**: csv に無い事実を作り出さないでください。
- **数値の断定を避ける(重要)**: 検索ボリューム・比率・順位のような**数値をテキストで断定しないでください**
  (「最も大きい」「〇〇%」「N 倍」は禁止)。数値はレポートのバッジ・キーワードチップにコードが実測値を
  埋めるので、あなたは**定性的な解釈**(なぜこう検索するのか、どんな意図か、どう攻略するか)だけを書きます。
- **マークアップ禁止**: `:k[]`、`:c[]`、`:::accordion`、`➊➋➌`、コードブロック、表などの特殊マークアップを
  絶対に使わないでください。純粋なテキスト文字列のみを JSON の値に入れます。
- **出力言語** = 分析市場(`<GL>`)の言語。jp → 日本語。
- `memberKeywords` は必ず csv に実際に登場した keyword の原文のみを使います(翻訳・変形は禁止)。

**① 分析の概要(overview)**
- 検索データ全体を貫く核心的な洞察を 1〜2 文(100〜200 字)。小見出しなしで記述。
- この文はレポート表紙の「背景と目的」の下に**データに基づく要約文**としてそのまま載ります。

**② 検索目的 Top 5(intentGroups)** — 最大 5 つ
- 各キーワードを**ターゲットキーワード**(製品・ブランド・カテゴリの名詞)と**意図キーワード**(文脈・状況を表す語)に分解します。
- 意図タイプ: 情報探索型(〜使い方/効果/副作用)、問題解決型(〜問題/故障/エラー)、購入意図型(〜価格/最安値/購入先/割引/中古)、
  間接経験確認型(〜口コミ/レビュー/評価)、情報型(〜とは/定義)、比較型(〜vs/比較)など。
- 意味的に近い意図キーワードを**一つの検索目的グループにまとめます**(グループごとに複数キーワード。キーワード 1 つだけのグループを並べるのは禁止)。
- 各グループ:
  - `title`: 検索目的名(例: 「価格・購入先の比較」「使い方・お手入れ情報の探索」)— 明確かつ具体的に
  - `intentType`: 上の意図タイプから代表を 1 つ(例: 「購入意図型」)
  - `memberKeywords`: この目的に属する csv キーワードの一覧(重要度順)
  - `who`: この検索をする人たちの文脈・心理を 1〜2 文(定性)
  - `insight`: マーケティング・製品観点の攻略示唆を 1〜2 文(定性)
  - `kbf`: (任意)`[{ "factor": "判断/関心の要因", "evidence_keywords": ["根拠キーワード", ...] }]` を 2〜4 個

**③ ブランド/ノンブランド Top 5(brandGroups)** — 最大 5 つ
- csv からブランドキーワード(製品・ブランド名)とノンブランドキーワード(一般カテゴリ)を識別します。ブランドに重みを置きます。
- 各グループ:
  - `name`: **実際のブランド名 1 つ**(例: 「ナイキ」)またはノンブランドのカテゴリ名
  - `kind`: `"brand"` または `"nonbrand"`
  - `memberKeywords`: このブランド/カテゴリにまとまる csv キーワードの一覧
  - `label`: グループの性格を表すラベル(日本語、例: 「高性能ランニングシューズの代表ブランド」)
  - `analysis`: このブランド/ノンブランドについての定性分析・洞察を 1〜2 文

---

#### 出力形式 — JSON only(Markdown・マークアップ禁止)

```json
{
  "overview": "核心的な洞察 1〜2 文",
  "intentGroups": [
    {
      "title": "検索目的名",
      "intentType": "購入意図型",
      "memberKeywords": ["キーワード1", "キーワード2"],
      "who": "この検索をする人たちの文脈 1〜2 文",
      "insight": "攻略の示唆 1〜2 文",
      "kbf": [{"factor": "要因", "evidence_keywords": ["根拠キーワード1"]}]
    }
  ],
  "brandGroups": [
    {
      "name": "実際のブランド名",
      "kind": "brand",
      "memberKeywords": ["キーワード1"],
      "label": "グループの性格ラベル",
      "analysis": "定性分析 1〜2 文"
    }
  ]
}
```

上の JSON を `{WORKDIR}/lm_groups_raw.json` に保存します。

### ステップ 4 — グループの後処理(検索ボリューム合算・根拠キーワード)

```bash
python3 {SKILL_DIR}/_shared/render/query_aggregate.py groups \
  --raw-groups "{WORKDIR}/lm_groups_raw.json" \
  --context "{WORKDIR}/lm_query_result.json" \
  --out "{WORKDIR}/lm_groups.json"
```

このスクリプトが各グループの `volume_avg` の合算・ソートと根拠キーワード(evidence、検索ボリュームのラベルを含む)、
グループヘッダーのバッジ用 `volumeLabel`(合算検索ボリューム)・`memberCount`(キーワード数)をコードで計算して
カード用の形に保存し、ステップ 3 の `overview` は表紙の要約文としてそのまま通します。
(数値はここで実測値が埋まります。)
さらに**ハルシネーションの遮断**: `memberKeywords`・`kbf.evidence_keywords` のうち csv に無いキーワードは
ここで除去され、実在のキーワードが一つも無いグループ/kbf 行は丸ごと捨てられます。
ステップ 3 の結果がこのフィルタで空になる(グループ 0 個)とスクリプトがエラーで停止するので、ステップ 3 をやり直してください。

### ステップ 5 — インサイト・実行提案(LLM)→ lm_actions.json

`{WORKDIR}/lm_groups.json` のグループをもとに、以下の JSON を `{WORKDIR}/lm_actions.json` に保存します。
出力言語は gl のマッピング(jp→日本語)。**数値の断定は禁止**(ステップ 3 と同じ)、マークアップ禁止。

- `synthesis`: 検索目的・ブランド地形を横断する総評を 2〜3 文
- `insights`: 詳細インサイトを**ちょうど 3 つ** `{"title","body"}` — データから見つかった
  ユーザー行動を根拠とする論理的な結論。title は核心キーワードをもとに短く、
  body は 1〜2 文。(単なる列挙は禁止 — グループ分析の結果から導く)
- `now`: 今すぐ試せる実行提案を 2〜3 つ `{"title","body"}`(特定の検索目的/ブランドに応える)
- `future`: 今後注目すべき機会を 2〜3 つ `{"title","body"}`

```json
{
  "synthesis": "総評 2〜3 文",
  "insights": [{"title": "核心キーワードに基づく見出し", "body": "行動に基づく結論 1〜2 文"}],
  "now": [{"title": "実行提案の見出し", "body": "実行内容 1〜2 文"}],
  "future": [{"title": "機会の見出し", "body": "機会の説明 1〜2 文"}]
}
```

(`summary` フィールドは廃止 — synthesis と重複するためレンダリングされません。入れても無視されます。)

### ステップ 6 — HTML レンダリング

```bash
python3 {SKILL_DIR}/_shared/render/render_report.py --skill query-opportunity \
  --groups "{WORKDIR}/lm_groups.json" \
  --actions "{WORKDIR}/lm_actions.json" \
  --meta "{WORKDIR}/lm_query_result.json" \
  --category "<SEED>" --gl <GL> --date <YYYY-MM-DD> \
  --out "{WORKDIR}/query-opportunity-report.html"
```

### ステップ 7 — ユーザーへの案内

```
✅ クエリ機会分析レポートの生成が完了しました: {WORKDIR}/query-opportunity-report.html
ブラウザで開くと検索目的・ブランドのカードとインサイトをダッシュボード/A4 ビューで確認でき、
Cmd+P で A4 PDF として保存できます。
macOS ですぐ開く: open {WORKDIR}/query-opportunity-report.html
```
