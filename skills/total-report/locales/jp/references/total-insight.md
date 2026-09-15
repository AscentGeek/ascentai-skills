## 前提条件の確認

`{SKILL_DIR}/_shared/render/{render_report.py,components.py,components_total.py,query_aggregate.py,path_aggregate.py,cluster_aggregate.py,components_path.py,components_cluster.py}`、
`{SKILL_DIR}/_shared/{styles,labels,templates}` が揃って存在している必要があります。
python3(標準ライブラリ)のみを使用します。レポートは zip の customer-analysis のカードシェルの上に
**外枠 4 タブ**(統合サマリー / クエリ / ジャーニー / クラスタ)を載せた**一つの自己完結型 HTML** であり、
タブ 2〜4 は兄弟スキル(query/path/cluster)のダッシュボード本文を**そのまま**埋め込み、
タブ 1 はこのスキルだけが作る**統合サマリー** — 3 ファインダーを合わせて初めて出てくる**6 つのクロスインサイトモジュール**
(カバレッジギャップ · ハブの役割 · ペルソナ×ジャーニー · 収益リーク · 転換コリドー · 優先度バックログ)です。

このレポートは ListeningMind **3 ファインダー** — QueryFinder(intent_finder) · PathFinder(path_finder) ·
ClusterFinder(cluster_finder) — を**それぞれの原本の分析フレームのまま**回したうえで、その結果を
横断して一つの消費者検索ジャーニー(オーディエンス → 意図 → ジャーニー)として統合します。

<!-- プロヴェナンス(provenance):
     タブ 2〜4 のステップ 3 の分析プロンプトは、それぞれ本番の原本を移植したものです —
       · query  : agent_query  v0.4.7 (references/prompts/agent_query.1958.kr.md)
       · path   : agent_path   framework (references/prompts/agent_path.framework.kr.md)
       · cluster: agent_cluster v0.7.0 (references/prompts/agent_cluster.v0.7.0.kr.md)
     この統合レポートの各ファインダーのステップ(1〜4)は、兄弟の参照ドキュメント
     (references/{query-opportunity,path-opportunity,cluster-landscape}.md)の
     同じステップをそのまま呼び出します — ここで再記述せず、そのドキュメントに委譲します。

     ★ ステップ 5「統合分析」のプロンプトには本番の原本がありません(新規著作)。★
     3 ファインダーの個別の原本プロンプトと違い、gpt_prompt DB やリポジトリ内の DEFAULT_PROMPTS に
     対応する行がありません。このスキルの 6 つのクロスインサイトモジュール(カバレッジギャップ /
     ハブの役割 / ペルソナ×ジャーニー / 収益リーク / 転換コリドー / 優先度バックログ)と統合サマリーのために、
     このドキュメント内にインラインで新規に書き起こしたものであり、3 ファインダー共通の規律(数値の断定禁止・
     マークアップ禁止・データの根拠のみ)だけを継承します。
     運用プロンプトへ昇格・更新される場合は、このインライン規則を唯一の出典(SSOT)としてください。

     ★ 数値・構造・座標 = Python、定性 1 行 = LLM(id でマージ)★
     統合の数値・座標・項目ごとの安定 id は total_aggregate.py が lm_total_facts.json に
     すでに計算済みです。LLM(ステップ 5)はその **id に対応する定性ノートだけ**を lm_total.json
     に書きます — 自由なキーワード・数値の著作は禁止。ノートのキー契約:
       overview(文字列) · hubNotes[{id,rx}] · cellNotes[{id,note}] ·
       bridgeNotes[{id,note}] · backlogNotes[{id,title,body}]。
     id は facts の hub#/cell#/bridge#/bl# をそのまま使います。レンダラー
     (components_total)は facts+notes を **id でマージ**するため、facts に無い id の
     ノートは静かに無視されます(別途ハルシネーションフィルタは不要) — 存在しない項目をノートで
     作り出すことはできません。逆にノートの無い facts の項目は数値だけがレンダリングされます。 -->

## 実行手順

### ステップ 0 — 入力の収集 + 作業フォルダ

データは **ListeningMind MCP ツール**で取得します。**API キーを尋ねないでください** —
環境変数・`.env`・DB などからキーを探そうともしないでください。

必要な入力:

> 統合検索インサイト分析を開始します。
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
WORKDIR="$PWD/tmp/reports/listeningmind-total-insight-${SAFE_SEED}-${TIMESTAMP}"
mkdir -p "$WORKDIR/q" "$WORKDIR/p" "$WORKDIR/c"
echo "作業フォルダ: $WORKDIR"
```

以降 `{WORKDIR}` は上の絶対パスに置き換えます。ファインダーごとの成果物は
`{WORKDIR}/q`(クエリ)· `{WORKDIR}/p`(ジャーニー)· `{WORKDIR}/c`(クラスタ)に入れ、
統合の成果物(`lm_total.json`、最終 HTML)は `{WORKDIR}` の直下に置きます。

> **`<GL>`・`<SEED>`・`<TIME_POINT>`・`<YYYY-MM-DD>`(=`$(date +%F)`)** は全ステップで同じ値に
> 置き換えます。`<GL>` は現在 `jp` のみ対応(ラベル JSON が jp のみ提供)。

### ステップ 1 — 3 ファインダーのデータ収集(部分的な失敗時は優雅に縮小)

3 ファインダーの**構造の取得を先に終わらせ**、検索ボリューム・意図の補強(`keyword_info`)は**キーワードをまとめて
1 回だけ**呼び出します。

> **なぜまとめるのか** · ファインダーごとに個別に呼ぶと、同じシードで重なるキーワードを重複して取得することに
> なります。実測(シード「伝統酒」)では単純合計 719 件 → 和集合 644 件で **75 件(10%)** が
> 重複でした。シードが狭いほど重なりは大きくなります。1 回だけ呼べば重複が消え、
> キャッシュのヒット率も上がります。

**1-A. 構造の取得(ファインダーごとに 1 コールずつ)** — 兄弟ドキュメントの 1a ブロックをそのまま使い、保存パスだけ変えます。

> **3 つのファインダーは一度に 1 つずつ順番に呼び出します。** ListeningMind MCP は同時リクエスト上限が 1 のため、
> まとめて呼ぶと後の呼び出しが `429 concurrent request limit` で失敗します。前の呼び出しの保存まで終えてから次を呼びます。

| ファインダー | 必須度 | MCP ツール | 参照(1a そのまま) | 保存 |
|---|---|---|---|---|
| クエリ | **必須** | `intent_finder` | `references/query-opportunity.md` §1a | `{WORKDIR}/q/lm_keyword_list.json` |
| ジャーニー | 推奨 | `path_finder` | `references/path-opportunity.md` §1a | `{WORKDIR}/p/lm_path.json` |
| クラスタ | 任意(プラン) | `cluster_finder` | `references/cluster-landscape.md` §1a | `{WORKDIR}/c/lm_cluster.json` |

各呼び出しは兄弟ドキュメントと同じく **3 ステップ**(`mcp_cache.py lookup` → MCP 呼び出し + 応答ファイルの
確保 + `store` → `log_event.py --type tool_call`)を経ます。保存パスだけ上の表のとおりに変えます。

**1-B. キーワードの和集合 → `keyword_info` を 1 回** — 成功したファインダーの結果からキーワードを集めます。

```bash
python3 - "{WORKDIR}" <<'MKPARAM' > "{WORKDIR}/kw_params.json"
import json, sys
from pathlib import Path

W = Path(sys.argv[1])
seen, kws = set(), []          # 登場順を維持 · 前方(クエリ)が上限に先に入るように

def add(k):
    if isinstance(k, str) and k.strip() and k not in seen:
        seen.add(k); kws.append(k.strip())

# クエリ · 検索ボリューム順にすでにソートされている
f = W / "q/lm_keyword_list.json"
if f.exists():
    for k in (json.loads(f.read_text(encoding="utf-8")).get("data") or []):
        add(k if isinstance(k, str) else (k or {}).get("keyword"))

# ジャーニー · 経路に登場するノード
f = W / "p/lm_path.json"
if f.exists():
    d = json.loads(f.read_text(encoding="utf-8"))
    for path in (d.get("data") or (d.get("result") or {}).get("paths") or []):
        for k in (path if isinstance(path, list) else []):
            add(k)

# クラスタ · 群集の構成員 + エッジの両端
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
print(json.dumps({"keywords": kws, "gl": "<GL>", "data_type": "all"}, ensure_ascii=False))
MKPARAM

# ① キャッシュ確認
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --out "{WORKDIR}/lm_keyword_info.json"

# ミスなら keyword_info MCP ツールを kw_params.json の内容 + user_query で呼び出し、
# 応答を {WORKDIR}/lm_keyword_info.json として確保したうえで:

# ② キャッシュ保存
python3 {SKILL_DIR}/scripts/mcp_cache.py store keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --file "{WORKDIR}/lm_keyword_info.json" --expect <data 配列の長さ>

# ③ tool_call の発行
python3 "$SKILL_DIR/scripts/log_event.py" --type tool_call --session-id "$SID" \
  --tool keyword_info --request-body "$(cat "{WORKDIR}/kw_params.json")" \
  --used-credits-delta <cost_detail.total_cost> \
  --used-credits-cumulative <used_credits> \
  --intent market_scan
```

> 上限(1,000)に達した場合は**クエリのキーワードが先に**入ります(検索ボリュームの降順)。クエリが必須
> ファインダーであり、切り捨てに最も敏感だからです。

**1-C. ファインダーごとに振り分ける** — ジャーニー・クラスタは和集合のファイルを**そのまま**渡しても構いません。
2 つの集計スクリプトは `{キーワード: 値}` のマッピングを作ったうえで自分の構造(経路・群集)にあるキーワードだけを
取り出して使うため、余分が混ざっても結果は変わりません。

**クエリだけは絞り込む必要があります** — `query_aggregate context` は受け取ったレコードを**すべて**関連クエリとして
扱うため、ジャーニー・クラスタから来たキーワードが混ざると一覧が汚染されます。

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

# クエリの一覧にあるキーワードだけを残す
want = set()
f = W / "q/lm_keyword_list.json"
if f.exists():
    for k in (json.loads(f.read_text(encoding="utf-8")).get("data") or []):
        want.add(k if isinstance(k, str) else (k or {}).get("keyword"))

out = dict(info) if isinstance(info, dict) else {}
out["data"] = [r for r in rows if kw_of(r) in want]
(W / "q/lm_query.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
print(f"クエリ {len(out['data'])} 件 / 和集合 {len(rows)} 件")
PY

# ジャーニー・クラスタは和集合をそのまま使う (余分なキーワードは集計が無視する)
cp "{WORKDIR}/lm_keyword_info.json" "{WORKDIR}/p/lm_nodes.json"
cp "{WORKDIR}/lm_keyword_info.json" "{WORKDIR}/c/lm_keyword_info.json"
```

収集結果のファイル名(兄弟と同一 · ステップ 2 の集計がこの名前をそのまま受け取ります):
- クエリ: `{WORKDIR}/q/lm_keyword_list.json`、`{WORKDIR}/q/lm_query.json`
- ジャーニー: `{WORKDIR}/p/lm_path.json`、`{WORKDIR}/p/lm_nodes.json`
- クラスタ: `{WORKDIR}/c/lm_cluster.json`、`{WORKDIR}/c/lm_keyword_info.json`

**優雅な縮小(graceful degradation)の規則**:
- **クエリ(必須)**: `result=FAILED`・HTTP エラー・空の結果なら**全体を中断**(キー・gl・シードの確認を案内)。クエリ無しで統合レポートは作りません。
- **ジャーニー(推奨)**: 失敗したら警告だけ残して**ジャーニー無しで進行**(タブ 3 は「データなし」でレンダリング)。
- **クラスタ(任意)**: **401**=キーのエラー / **402**=支払いが必要 / **403**=プラン・gl・権限の不足(cluster_finder は professional/advance)/ **429**=同時リクエスト制限、あるいは `communities` が空の場合は、警告だけ残して**クラスタ無しで進行**(タブ 4 は「データなし」)。特に 403(プラン)はよくあるので自然に縮小します。
- **ゲート(最低 2 ファインダー)**: 収集が終わったら、**成功したファインダーがクエリを含めて 2 つ以上**であることが継続の条件です。クエリだけ成功(ジャーニー・クラスタがどちらも失敗)した場合は統合する軸が無いので中断し、ジャーニー/クラスタがなぜ空だったのか(プラン・時点・ネットワーク)をユーザーに報告します。成功したファインダーについてのみステップ 2〜6 を進めます。

> どのファインダーについてもデータを**作り出さないでください**。失敗したファインダーはそのまま外せば済みます — レンダラーが
> 無いタブを「データなし」カードとして自然に処理し、統合 A4 でもそのファインダーのページを省きます。

### ステップ 2 — ファインダーごとのコンテキスト集計(`context`)

成功したファインダーそれぞれについて、兄弟ドキュメントの**ステップ 2 の集計**をそのまま実行します(パスだけサブフォルダに)。

```bash
# クエリ
python3 {SKILL_DIR}/_shared/render/query_aggregate.py context \
  --raw "{WORKDIR}/q/lm_query.json" --seed "<SEED>" --gl <GL> --date <YYYY-MM-DD> \
  --out "{WORKDIR}/q/lm_query_result.json"

# ジャーニー (収集成功時)
python3 {SKILL_DIR}/_shared/render/path_aggregate.py context \
  --paths "{WORKDIR}/p/lm_path.json" --nodes "{WORKDIR}/p/lm_nodes.json" \
  --seed "<SEED>" --gl <GL> --date <YYYY-MM-DD> --time-point <TIME_POINT> \
  --out "{WORKDIR}/p/lm_path_result.json"

# クラスタ (収集成功時)
python3 {SKILL_DIR}/_shared/render/cluster_aggregate.py context \
  --cluster "{WORKDIR}/c/lm_cluster.json" --keyword-info "{WORKDIR}/c/lm_keyword_info.json" \
  --seed "<SEED>" --gl <GL> --date <YYYY-MM-DD> \
  --out "{WORKDIR}/c/lm_cluster_result.json"
```

出力された `*_result.json` の LLM 入力(クエリ `csv` / ジャーニー `pathsText`・`hubsCsv` / クラスタ `csv`)をステップ 3 で使います。

### ステップ 3 — ファインダーごとの分析(LLM、原本の分析フレーム)→ `lm_groups_raw.json` / `lm_paths_raw.json`

ファインダーそれぞれを**そのファインダーの原本の分析規則のまま**分析します。規則をここで書き直さず、
兄弟の参照ドキュメントの**ステップ 3「分析規則」**セクションにそのまま従ってください(数値の断定禁止・マークアップ禁止・データの根拠のみ・市場の言語):

- クエリ → `references/query-opportunity.md` §3 **「分析規則(Data Insight Analyst)」**(agent_query v0.4.7 の移植)。入力は `{WORKDIR}/q/lm_query_result.json` の `csv`。出力は `{WORKDIR}/q/lm_groups_raw.json`。
- ジャーニー → `references/path-opportunity.md` §3 **「分析規則(Search Journey Analyst)」**(agent_path framework の移植)。入力は `{WORKDIR}/p/lm_path_result.json` の `pathsText`・`hubsCsv`。出力は `{WORKDIR}/p/lm_paths_raw.json`。
- クラスタ → `references/cluster-landscape.md` §3 **「分析規則(データインサイトアナリスト — クラスタファインダー)」**(agent_cluster v0.7.0 の移植)。入力は `{WORKDIR}/c/lm_cluster_result.json` の `csv`。出力は `{WORKDIR}/c/lm_groups_raw.json`。

各ファインダーの JSON 出力スキーマ・フィールドも兄弟ドキュメントのままです。

### ステップ 4 — ファインダーごとの後処理(`groups`/`paths`、検索ボリューム合算・ハルシネーションフィルタ)

成功したファインダーそれぞれについて、兄弟ドキュメントの**ステップ 4 の後処理**をそのまま実行します。このステップで
**数値が実測値で埋まり**(検索ボリューム合算・ハブ・フロー・連結性)、**ハルシネーションのキーワードが除去**されます。

```bash
# クエリ → q/lm_groups.json
python3 {SKILL_DIR}/_shared/render/query_aggregate.py groups \
  --raw-groups "{WORKDIR}/q/lm_groups_raw.json" --context "{WORKDIR}/q/lm_query_result.json" \
  --out "{WORKDIR}/q/lm_groups.json"

# ジャーニー → p/lm_paths.json (収集成功時)
python3 {SKILL_DIR}/_shared/render/path_aggregate.py paths \
  --raw-paths "{WORKDIR}/p/lm_paths_raw.json" --context "{WORKDIR}/p/lm_path_result.json" \
  --out "{WORKDIR}/p/lm_paths.json"

# クラスタ → c/lm_groups.json (収集成功時)
python3 {SKILL_DIR}/_shared/render/cluster_aggregate.py groups \
  --raw-groups "{WORKDIR}/c/lm_groups_raw.json" --context "{WORKDIR}/c/lm_cluster_result.json" \
  --out "{WORKDIR}/c/lm_groups.json"
```

> どのファインダーでも後処理が「グループ 0 個」でエラー停止した場合は、そのファインダーのステップ 3 をやり直します(兄弟ドキュメントと同じ)。

**ファインダーごとのインサイト・実行(`lm_actions.json`)も今のうちに作ります** — タブ 2〜4 は各ファインダーのレポート本文を
そのまま埋め込むため、各ファインダーの**ステップ 5**(兄弟ドキュメント §5、`synthesis`・`insights`(3)・`now`・`future`)を
実行して以下に保存します:

- クエリ: `{WORKDIR}/q/lm_actions.json`(`references/query-opportunity.md` §5)
- ジャーニー: `{WORKDIR}/p/lm_actions.json`(`references/path-opportunity.md` §5)
- クラスタ: `{WORKDIR}/c/lm_actions.json`(`references/cluster-landscape.md` §5)

### ステップ 5 — 統合集計(Python)+ 統合ノート(LLM)→ `lm_total_facts.json` + `lm_total.json`

このステップは**2 つの部分**に分かれます。**5-A** の Python 集計スクリプトが 3 ファインダーの結果を横断して**すべての数値・座標・項目 id**
を計算して `lm_total_facts.json` に収め、**5-B** の LLM がその **id に対応する定性ノート 1 行だけ**を `lm_total.json`
に書きます。数値は 5-A が実測値として確定するので、5-B は決して数値を再計算しません(ハルシネーションを根本から遮断)。

#### 5-A. 統合集計(Python)→ `lm_total_facts.json`

成功したファインダーの後処理結果(ステップ 2 の `*_result.json` のメタ + ステップ 4 の `groups`/`paths`)を `total_aggregate.py total`
で横断して集計します。**クエリを含めて最低 2 つのファインダー**が必要で、存在するファインダーのフラグだけを渡します(優雅な縮小)。

```bash
python3 {SKILL_DIR}/_shared/render/total_aggregate.py total \
  --seed "<SEED>" --gl <GL> --date <YYYY-MM-DD> \
  --query-meta    "{WORKDIR}/q/lm_query_result.json"   --query-groups   "{WORKDIR}/q/lm_groups.json" \
  --path-meta     "{WORKDIR}/p/lm_path_result.json"    --path-paths     "{WORKDIR}/p/lm_paths.json" \
  --cluster-meta  "{WORKDIR}/c/lm_cluster_result.json" --cluster-groups "{WORKDIR}/c/lm_groups.json" \
  --out "{WORKDIR}/lm_total_facts.json"
```

- **ジャーニー/クラスタが失敗した場合**は、該当する `--path-*` または `--cluster-*` の 2 行を外してください(集計スクリプトが自動的に縮小 — 例: クラスタが無ければ転換コリドー・収益リークの一部が減ります)。
- 出力される `lm_total_facts.json` は 8 つのセクション(`meta`・`recap`・`coverage`・`hubDivergence`・`matrix`・`valueLeak`・`bridges`・`backlog`)と**項目ごとの安定 id**(`combo#`,`gap#`,`hub#`,`cell#`,`leak#`,`bridge#`,`bl#`)を含みます。**ここの数値は確定した実測値** — 次の 5-B のノートは触れません。

#### 5-B. 統合ノート(LLM、**新規著作**)→ `lm_total.json`

`lm_total_facts.json` を読み、その **id に対応する定性ノートだけ**を JSON として `{WORKDIR}/lm_total.json` に保存します。

> ⚠ このプロンプトは**本番の原本が無い新規著作**です(上のプロヴェナンスのコメント)。3 ファインダー共通の規律だけを継承します。

**入力**:
- `{WORKDIR}/lm_total_facts.json` — 6 つのクロスモジュールの数値・座標・id(読み取り専用の根拠)。
- (補助)成功したファインダーの `groups`/`paths` — ノートの定性的な文脈の参考用。ここでも**数値は引用のみ、再計算は禁止**。

---

##### 分析規則(統合インサイトノートの作成)

あなたは検索データの統合アナリストです。Python の集計スクリプトが 3 ファインダー(WHO・群集 / WHAT・WHY・意図 / HOW・ジャーニー)を
横断して**6 つのクロス結論モジュール**(カバレッジギャップ · ハブの役割 · ペルソナ×ジャーニー · 収益リーク · 転換コリドー · 優先度
バックログ)をすでに数値で確定させています。あなたの仕事は、その確定した項目に**マーケターがすぐ理解できる 1 行の解釈/処方**を
付けることだけです。

**全体規則**(3 ファインダーと同じ + 統合の特則):
- **id でのみマッピング**: ノートは必ず facts に**実在する id**(`hub#…`,`cell#…`,`bridge#…`,`bl#…`)にだけ付けます。facts に無い id で書いたノートはレンダラーが**静かに捨てます**(存在しない項目は作り出せない) — それでも存在しない id は書かないでください。
- **数値・キーワードの再著作は禁止(重要)**: 検索ボリューム・比率・順位・分散・分岐数のような数値をテキストで断定しないでください(「最も大きい」「〇〇%」「N 倍」「N 個」は禁止)。新しいキーワードを作り出さないでください — 根拠キーワードは facts がすでにチップ・バーに埋めてあります。あなたは**なぜ重要か / 何をするか**だけを書きます。
- **平易な日本語**: マーケターが即座に理解できる文。専門用語(dispersion/outDegree/present-absent/leak_factor など)は表に出さないでください。
- **マークアップ**: 核心となる名詞句は `<strong>…</strong>` のみ許可。それ以外のマークアップ(`:k[]`、`:::accordion`、`➊`、コードブロック、表)は絶対に禁止。
- **出力言語** = 分析市場(`<GL>`)の言語。jp → 日本語。

**① overview**(文字列)— 3 つのレンズを貫く核心構造を 1〜2 文(100〜200 字)。表紙・タブ 1 上部の「統合サマリー」ボックスに載ります。数値の断定なしで記述。

**② hubNotes** `[{id, rx}]` — M2(ハブの役割)の `hub#…` のうち**言うべきことがあるものだけ**。`rx` = このキーワードの役割の不一致がマーケティングに持つ意味 + 処方 1 行(例: 3 か所すべてで核心なら「必ず先取りする」、片方だけで立つなら「その用途に限って運用する」)。

**③ cellNotes** `[{id, note}]` — M3(ペルソナ×ジャーニー)の `cell#…` のうち、特に**空白セル(コンテンツギャップ)**を中心に 1 行。誰が来ているのになぜ受け止められていないのか + 何で埋めるか。

**④ bridgeNotes** `[{id, note}]` — M5(転換コリドー)の `bridge#…` のうち判定が明確なものを中心に 1 行。方向・離脱の判定を実行に翻訳する(上流への配置・CRM・防御など)。

**⑤ backlogNotes** `[{id, title, body}]` — M6(優先度バックログ)の `bl#…` の各項目。`title` = マーケター向けの短い実行課題名(名詞句、根拠キーワードに基づく)。`body` = **(任意)**1 行の補足。facts の target・根拠キーワード・バケットを人が読める課題名に移す役割です。

---

##### 出力形式 — JSON only(Markdown・表は禁止、`<strong>` のみ許可)

```json
{
  "overview": "3 つのレンズを貫く統合サマリー 1〜2 文",
  "hubNotes":     [{"id": "hub#0001",   "rx":   "役割の不一致の解釈 + 処方 1 行"}],
  "cellNotes":    [{"id": "cell#p1-s1", "note": "コンテンツギャップのセルの解釈 1 行"}],
  "bridgeNotes":  [{"id": "bridge#C-D", "note": "転換の判定 → 実行 1 行"}],
  "backlogNotes": [{"id": "bl#now-1",   "title": "実行課題名", "body": "(任意) 補足 1 行"}]
}
```

上の JSON を `{WORKDIR}/lm_total.json` に保存します。すべてのコレクションは**任意**(空でも可) — ノートの無い facts の項目は
数値だけがレンダリングされます。**id は必ず facts のものをそのまま**使ってください(誤字があるとそのノートだけ無視されます)。このノートファイルには
自由なキーワード・数値を著作しないでください — 数値はすべて 5-A の `lm_total_facts.json` から来ます。

### ステップ 6 — 統合 HTML のレンダリング(`--skill total-insight`)

`render_report.py` を**統合モード**で呼び出します。`--total`(定性ノート)・`--total-facts`(集計数値)は必須で、
ファインダー 3 種のフラグは**成功して成果物があるファインダーだけ**を渡します(失敗したファインダーのフラグは省略 — そのタブは「データなし」でレンダリング)。

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
  --category "<SEED>" --gl <GL> --date <YYYY-MM-DD> \
  --out "{WORKDIR}/total-insight-report.html"
```

- **必須**: `--total`・`--total-facts`、そしてファインダー 3 種のうち**最低 1 つ**(クエリは常に成功しているので `--query-*` は常に含まれます)。ゲートの規則により、クエリを含めて 2 つ以上が渡ってきます。
- **ジャーニーが失敗した場合**: `--path-paths`・`--path-actions`・`--path-meta` の 3 行を外してください。
- **クラスタが失敗した場合**: `--cluster-groups`・`--cluster-actions`・`--cluster-meta` の 3 行を外してください。
- `--gl` は `jp` のみ対応、`--date` は `$(date +%F)`。

### ステップ 7 — ユーザーへの案内

生成結果を案内します。縮小実行(ファインダーの一部を省略)の場合は、どのタブがデータなしなのかも併せて知らせます。

```
✅ 統合検索インサイトレポートの生成が完了しました: {WORKDIR}/total-insight-report.html
ブラウザで開くと上部の 4 タブ(統合サマリー · クエリ機会 · 検索ジャーニー · クラスタ地形)で
   · タブ 1: 3 ファインダーを合わせて初めて出てくる 6 つのクロスインサイトモジュール(カバレッジギャップ · ハブの役割 · ペルソナ×ジャーニー · 収益リーク · 転換コリドー · 優先度バックログ)+ 統合サマリー
   · タブ 2〜4: 各ファインダーのレポート本文(カード/ハブ表/ジャーニーのフロー図)
をダッシュボード/A4 ビューで確認できます。
A4 ビュー(右上のトグル)は統合 → クエリ → ジャーニー → クラスタの順につながった一つの文書なので、
Cmd+P で印刷すると 4 つのレポートが 1 つの PDF として保存されます(4-in-one)。
macOS ですぐ開く: open {WORKDIR}/total-insight-report.html
```

(ジャーニー・クラスタをプラン/ネットワークの事由で省略した場合は、そのタブが「データが無いためこのタブは生成
されませんでした」と表示され、A4 でもそのファインダーのページが抜けることを併せて案内してください。)
