## 前提条件の確認

`{SKILL_DIR}/_shared/render/{cluster_aggregate.py,render_report.py,components.py,components_cluster.py}`、
`{SKILL_DIR}/_shared/{styles,labels,templates}` が揃って存在している必要があります。
python3(標準ライブラリ)のみを使用します。レポートは zip の customer-analysis と同じカード形式 +
クラスタ専用の**ハブキーワード要約表**・**From→To フロー**セクションを加えたものです。

このレポートは ListeningMind **ClusterFinder(クラスタファインダー)** の実際の分析プロンプト
(agent_cluster v0.7.0)の分析フレームを移植し、同時検索キーワードのクラスタを**検索目的**で
まとめ、各クラスタの**ハブ(代表)キーワード**とクラスタ間の**探索フロー**をカードで提示します。

<!-- 原本プロンプトのスナップショット: references/prompts/agent_cluster.v0.7.0.kr.md
     (v.0.7.0_cf_KR_0602、単一キーワード 4 セクション: 分析概要 / Top3 検索目的クラスタ /
     Top3 From→To フロー / インサイト)。この 3 ステップのプロンプトは原本の 4 セクションを
     JSON 出力形に翻案したものである(セクション1→overview、セクション2→clusterGroups、
     セクション3→flows、セクション4→ステップ 5 の actions)。
     チャット専用マークアップ(:k[]/:c[]{#}/:::accordion/➊)と「正確な数値の明示」規則は
     意図的に除外 — 数値・ハブ・フローのエッジは Python が実データから埋める(数値ポリシー)。
     マルチキーワード(agent_cluster_multiple)・クラスタのドリルダウン(GEO/ペルソナ/広告コピー)は
     現在のスキル範囲から除外(単一シード専用)。運用プロンプト更新時は gpt_prompt DB の
     type='agent_cluster' locale='KR' の最新アクティブ行と再照合。 -->

## 実行手順

### ステップ 0 — 入力の収集 + 作業フォルダ

データは **ListeningMind MCP ツール**で取得します。**API キーを尋ねないでください** —
環境変数・`.env`・DB などからキーを探そうともしないでください。

必要な入力は 2 つだけです:

> 検索クラスタ地形分析を開始します。
> 1. **シードキーワード** — すでにいただいていれば省略(クラスタファインダーは**単一キーワード**のみ受け付けます)
> 2. **国** — 既定は `jp`(特に指定がなければ jp で進めます)

シードがすでに与えられていればそのまま進めます。

**MCP コネクタが無い場合** · ステップ 1 のツール呼び出しが「ツールが見つかりません」で失敗します。
そのときはユーザーに **ListeningMind MCP コネクタの接続**を依頼して中断してください。
データを作り出さないでください。

確保できたら:

```bash
SAFE_SEED=$(echo "<SEED>" | tr ' /\\:*?"<>|' '_')
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
WORKDIR="$PWD/tmp/reports/listeningmind-cluster-landscape-${SAFE_SEED}-${TIMESTAMP}"
mkdir -p "$WORKDIR"
echo "作業フォルダ: $WORKDIR"
```

以降 `{WORKDIR}` は上の絶対パスに置き換えます。

### ステップ 1 — データ収集(MCP 2 回呼び出し)

cluster_finder は**同時検索グラフ**(クラスタ + エッジ)のみを返し、**検索ボリューム・意図は含みません。**
そのため ① `cluster_finder` でクラスタ・エッジを受け取り、② その中のキーワードを `keyword_info`
に渡して検索ボリューム・意図を付与します。

> **呼び出しごとに例外なく 3 ステップ**(SKILL.md §Step 4):
> ① `mcp_cache.py lookup` → ②(ミスなら)MCP 呼び出し + 応答ファイルの確保 + `store` → ③ `log_event.py --type tool_call`
>
> ① が **exit 0** ならファイルはすでに埋まっているので **MCP を呼ばずに** ③ へ進みます
> (`--cached --used-credits-delta 0`)。**exit 2** なら ② に進みます。

**1a. クラスタグラフ** — `cluster_finder`

```bash
# ① キャッシュ確認
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup cluster_finder \
  --params '{"keyword":"<SEED>","gl":"<GL>","data_type":"all","hop":2,"limit":1000,"orientation":"UNDIRECTED","time_point":"curr"}' \
  --out "{WORKDIR}/lm_cluster.json"
```

ミスなら **`cluster_finder` MCP ツール**を以下のパラメータで呼び出します:

```json
{"keyword": "<SEED>", "gl": "<GL>", "data_type": "all", "hop": 2, "limit": 1000,
 "orientation": "UNDIRECTED", "time_point": "curr",
 "user_query": "<ユーザー発話の原文そのまま>"}
```

> `data_type` は必ず **`all`** — `communities`(クラスタの dict)と `rels`(エッジの配列)を一緒に
> 受け取ってはじめて、ハブ(次数中心性)・フロー(クラスタ間の移動)を計算できます。`communities` だけ
> 受け取ると(`data_type` の既定値)フロー分析が空になり、`rels` だけ受け取るとクラスタが空になりカードを作れません。
> `limit` は**関係(エッジ)数**の上限(キーワード数ではありません)、`hop` はグラフ探索の深さ(1〜3)です。
>
> `user_query` はキャッシュキーから除外されるため `--params` には入れません(上の lookup を参照)。

応答を `{WORKDIR}/lm_cluster.json` として確保したうえでキャッシュに格納します
(応答が大きくホストがファイルに保存した場合はそのパスを `cp` · 本文で返った場合は heredoc —
SKILL.md §応答ファイル規則を参照):

```bash
# ② キャッシュ保存
python3 {SKILL_DIR}/scripts/mcp_cache.py store cluster_finder \
  --params '{"keyword":"<SEED>","gl":"<GL>","data_type":"all","hop":2,"limit":1000,"orientation":"UNDIRECTED","time_point":"curr"}' \
  --file "{WORKDIR}/lm_cluster.json" --expect <rels の長さ + communities の数>

# ③ tool_call の発行
python3 "$SKILL_DIR/scripts/log_event.py" --type tool_call --session-id "$SID" \
  --tool cluster_finder \
  --request-body '{"keyword":"<SEED>","gl":"<GL>","data_type":"all","hop":2,"limit":1000}' \
  --used-credits-delta <cost_detail.total_cost> \
  --used-credits-cumulative <used_credits> \
  --intent perception_mapping
```

**1b. キーワードの詳細** — 上の `communities` の**すべてのキーワード**(重複除去、上位 1,000 件)を
`keyword_info`(`data_type=all` → `ads_metrics`・`intents` を含む)で検索ボリューム・意図を取得:

```bash
python3 - "{WORKDIR}/lm_cluster.json" <<'MKPARAM' > "{WORKDIR}/kw_params.json"
import json, sys
d = json.load(open(sys.argv[1]))
comm = (d.get("data") or {}).get("communities") or {}
# communities の値(各クラスタのキーワードリスト)を展開して重複除去、上位 1,000 件。
seen, kws = set(), []
for members in comm.values():
    for k in (members or []):
        if isinstance(k, str) and k not in seen:
            seen.add(k); kws.append(k)
kws = kws[:1000]  # keyword_info maxItems=1000
print(json.dumps({"keywords": kws, "gl": "<GL>", "data_type": "all"}, ensure_ascii=False))
MKPARAM

# ① キャッシュ確認
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --out "{WORKDIR}/lm_keyword_info.json"
```

ミスなら **`keyword_info` MCP ツール**を `kw_params.json` の内容 + `user_query` で
呼び出し、応答を `{WORKDIR}/lm_keyword_info.json` として確保したうえで保存します:

```bash
# ② キャッシュ保存
python3 {SKILL_DIR}/scripts/mcp_cache.py store keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --file "{WORKDIR}/lm_keyword_info.json" --expect <data 配列の長さ>

# ③ tool_call の発行
python3 "$SKILL_DIR/scripts/log_event.py" --type tool_call --session-id "$SID" \
  --tool keyword_info --request-body "$(cat "{WORKDIR}/kw_params.json")" \
  --used-credits-delta <cost_detail.total_cost> \
  --used-credits-cumulative <used_credits> \
  --intent perception_mapping
```

- どちらの応答も `result` が `FAILED` か、ツール呼び出しが失敗した場合は中断・報告してください
  (コネクタ・シード・gl・プランを確認)。作り出さないでください。
- `communities` が空の場合(クラスタ 0 個)は中断・報告します。

### ステップ 2 — クラスタコンテキストの集計

```bash
python3 {SKILL_DIR}/_shared/render/cluster_aggregate.py context \
  --cluster "{WORKDIR}/lm_cluster.json" \
  --keyword-info "{WORKDIR}/lm_keyword_info.json" \
  --seed "<SEED>" --gl <GL> --date <YYYY-MM-DD> \
  --out "{WORKDIR}/lm_cluster_result.json"
```

このスクリプトが 2 つの応答を融合して:
- 各キーワードに**クラスタ文字**(0→A、1→B…)を割り当て、
- `rels` から**ハブキーワード**(次数中心性=degree が最多、同率・不在時は検索ボリューム最多)をクラスタごとに計算し、
- 各キーワード・クラスタの **outgoing**(他クラスタへの接続)を計算し、
- LLM 分析に渡す **`csv`**(カラム `n,v,c,h,o,i`)を作ります。

`{WORKDIR}/lm_cluster_result.json` を読み、その中の `csv` の値をステップ 3 の分析入力として使います。

### ステップ 3 — ClusterFinder 分析(LLM)→ lm_groups_raw.json

以下の規則(agent_cluster v0.7.0 の移植)に従って `lm_cluster_result.json` の `csv` を直接分析し、
結果を **JSON のみ**で `{WORKDIR}/lm_groups_raw.json` に保存します。

---

#### 分析規則(データインサイトアナリスト — クラスタファインダー)

あなたは検索データのインサイトアナリストです。リスニングマインド クラスタファインダーの結果
(同時検索クラスタ)をもとに、**単一キーワード市場の内部**にある検索意図、ユーザーの移動経路、
市場構造を解釈します。

**入力**: `csv` の各行 = `n, v, c, h, o, i`
- `n` = キーワード、`v` = **月間平均検索ボリューム**(検索ボリュームは常にこの値を使います)。
- `c` = このキーワードが属する**クラスタ文字**(A、B、C…)。同時検索でまとまったトピックのクラスタです。
- `h` = **ハブキーワードかどうか**(`TRUE`=このクラスタの代表/中心キーワード)。
- `o` = このキーワードが接続する**他のクラスタ文字**(`|` 区切り)。クラスタ間の移動経路の根拠です。
- `i` = 代表的な検索意図(情報探索/ナビゲーション/商業調査/取引)。

**全体規則**:
- **データの根拠のみ**: csv に無いキーワード・クラスタ・数値を作り出さないでください。
- **数値の断定を避ける(重要)**: 検索ボリューム・比率・順位のような**数値をテキストで断定しないでください**
  (「最も大きい」「〇〇件」「N 倍」は禁止)。数値・ハブ・フローのエッジはレポートのバッジ・表・チップに
  コードが実測値を埋めるので、あなたは**定性的な解釈**(なぜこうまとまるのか、どんな意図か)だけを書きます。
- **マークアップ禁止**: `:k[]`、`:c[]{#}`、`:::accordion`、`➊➋➌`、コードブロック、表などの特殊マークアップを
  絶対に使わないでください。純粋なテキスト文字列のみを JSON の値に入れます。
- **クラスタの参照は文字で**: `memberClusters`・`path` には csv に実在するクラスタ文字
  (A、B、C…)のみを入れます。**キーワードの原文**(`hubKeyword`)は csv の `n` の値をそのまま使います。
- **出力言語** = 分析市場(`<GL>`)の言語。jp → 日本語。
- ターゲット顧客は年齢・性別の推定ではなく、**検索行動タイプ**(ブランド比較型、価格検討型、機能検証型、
  情報入門型、購入直前型など)で記述します。人口統計の断定は禁止です。

**① 分析の概要(overview)**
- このキーワード市場を貫く核心的な構造を 1〜2 文(100〜200 字)。どの検索意図の軸が強いか、
  主要クラスタの性格と需要の重心を記述。小見出しなしで記述。
- この文はレポート表紙の「背景と目的」の下に**データに基づく要約文**として載ります。

**② Top 3 検索目的クラスタ(clusterGroups)** — 最大 5 つ(核心 3 つを推奨)
- **ハブの特定**: `h=TRUE` のキーワードがそのクラスタの代表です。
- **意図に基づく統合**: 意味的に近い検索目的を持つ**複数のクラスタを一つのグループにまとめます**
  (例: ブランドラインナップの探索、おすすめ・比較、価格・購入、使い方・お手入れ、口コミなど)。
  クラスタ 1 つだけのグループも可能ですが、近い意図は必ず一緒にまとめてください。
- 各グループ:
  - `title`: 検索目的名(明確かつ具体的に、例: 「ブランドラインナップ・価格の探索」)
  - `character`: このグループの性格/ターゲットの検索行動タイプ(例: 「ブランド比較型」)
  - `memberClusters`: この目的にまとまる**クラスタ文字の一覧**(例: `["B","C"]`)
  - `who`: このクラスタを検索する人たちの文脈・心理を 1〜2 文(定性)
  - `insight`: マーケティング・コンテンツ観点の攻略示唆を 1〜2 文(定性)

**③ Top 3 From → To フロー(flows)** — 最大 5 つ(核心 3 つを推奨)
- ハブキーワードの `o`(outgoing)カラムから、**実際に接続がある経路のみ**を使います。
- 各フロー:
  - `hubKeyword`: 起点となるハブキーワード(csv の `n` の原文)
  - `character`: この移動の性格(例: 「候補の探索 → ブランドの確定」)
  - `path`: 移動する**クラスタ文字の順序**(例: `["D","B"]` = D→B)。2 つ以上。
  - `insight`: なぜこの転換が起きるのかの解釈を 1〜2 文(定性)

---

#### 出力形式 — JSON only(Markdown・マークアップ禁止)

```json
{
  "overview": "このキーワード市場を貫く核心的な構造 1〜2 文",
  "clusterGroups": [
    {
      "title": "検索目的名",
      "character": "ブランド比較型",
      "memberClusters": ["B", "C"],
      "who": "このクラスタを検索する人たちの文脈 1〜2 文",
      "insight": "攻略の示唆 1〜2 文"
    }
  ],
  "flows": [
    {
      "hubKeyword": "ハブキーワードの原文",
      "character": "移動の性格",
      "path": ["D", "B"],
      "insight": "なぜこの転換が起きるのか 1〜2 文"
    }
  ]
}
```

上の JSON を `{WORKDIR}/lm_groups_raw.json` に保存します。

### ステップ 4 — グループの後処理(検索ボリューム合算・ハブ・フローの検証)

```bash
python3 {SKILL_DIR}/_shared/render/cluster_aggregate.py groups \
  --raw-groups "{WORKDIR}/lm_groups_raw.json" \
  --context "{WORKDIR}/lm_cluster_result.json" \
  --out "{WORKDIR}/lm_groups.json"
```

このスクリプトが各グループの `volume_avg` の合算・ソート、代表キーワード(検索ボリュームのラベルを含む)、
グループヘッダーのバッジ用 `volumeLabel`(合算検索ボリューム)・`memberCount`(キーワード数)・`clusterCount`(統合されたクラスタ数)、
**ハブキーワード要約表**(`hubTable`)、**From→To フロー**(`flows`、各経路のクラスタのハブキーワード +
ハブの `connectivity`(接続性=つないでいるクラスタ数)を含む)をコードで計算して保存し、
ステップ 3 の `overview` は表紙の要約文としてそのまま通します。(数値・ハブ・フローのエッジ・接続性はここで実測値が埋まります。)
さらに**ハルシネーションの遮断**: `memberClusters`・`path` のうち実在しないクラスタ文字、csv に無いキーワードは
ここで除去され、実在のクラスタ/キーワードが一つも無いグループは丸ごと捨てられます。
ステップ 3 の結果がこのフィルタで空になる(グループ 0 個)とスクリプトがエラーで停止するので、ステップ 3 をやり直してください。

### ステップ 5 — インサイト・実行提案(LLM)→ lm_actions.json

`{WORKDIR}/lm_groups.json` のグループ・フローをもとに(agent_cluster ④ インサイトに相当)、以下の JSON を
`{WORKDIR}/lm_actions.json` に保存します。出力言語は gl のマッピング(jp→日本語)。**数値の断定は禁止**
(ステップ 3 と同じ)、マークアップ禁止。

- `synthesis`: クラスタ地形・フローを横断する総評を 2〜3 文
- `insights`: 詳細インサイトを**ちょうど 3 つ** `{"title","body"}` — データから見つかった市場構造・
  探索の仕方を根拠とする論理的な結論。title は核心キーワードをもとに短く、body は 1〜2 文。
- `now`: 今すぐ試せる実行提案を 2〜3 つ `{"title","body"}`(特定のクラスタ/フローに応える)
- `future`: 今後注目すべき機会を 2〜3 つ `{"title","body"}`

```json
{
  "synthesis": "総評 2〜3 文",
  "insights": [{"title": "核心キーワードに基づく見出し", "body": "構造に基づく結論 1〜2 文"}],
  "now": [{"title": "実行提案の見出し", "body": "実行内容 1〜2 文"}],
  "future": [{"title": "機会の見出し", "body": "機会の説明 1〜2 文"}]
}
```

### ステップ 6 — HTML レンダリング

```bash
python3 {SKILL_DIR}/_shared/render/render_report.py --skill cluster-landscape \
  --groups "{WORKDIR}/lm_groups.json" \
  --actions "{WORKDIR}/lm_actions.json" \
  --meta "{WORKDIR}/lm_cluster_result.json" \
  --category "<SEED>" --gl <GL> --date <YYYY-MM-DD> \
  --out "{WORKDIR}/cluster-landscape-report.html"
```

### ステップ 7 — ユーザーへの案内

```
✅ 検索クラスタ地形分析レポートの生成が完了しました: {WORKDIR}/cluster-landscape-report.html
ブラウザで開くと検索目的クラスタのカード · ハブキーワード要約表 · From→To フローとインサイトを
ダッシュボード/A4 ビューで確認でき、Cmd+P で A4 PDF として保存できます。
macOS ですぐ開く: open {WORKDIR}/cluster-landscape-report.html
```
