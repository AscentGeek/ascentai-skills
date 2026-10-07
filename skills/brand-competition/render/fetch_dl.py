#!/usr/bin/env python3
"""fetch_dl.py · `response_format="download_url"` 응답을 받아 회차 폴더에 저장한다.

**왜 `curl` 이 아니라 이걸 쓰나**

① 내려받은 파일은 봉투가 아니라 **payload** 다 — `intent_finder` · `keyword_info` 는
   **맨 리스트**로 온다(실측 2026-10-02). 그런데 판정·점검·렌더 스크립트는 **14군데**에서
   `json.load(...)["data"]` 로 읽는다. 맨 리스트를 그대로 두면 거기서 죽는다. 그래서 받을 때
   `{"data": [...]}` 로 감싼다 — 읽는 쪽 14군데를 고치는 것보다 **입구 한 곳**이 안전하다.
② **sha256 과 건수를 대조한다.** 손으로 `curl` 하면 이 둘을 건너뛴다.
③ 어디서 받았는지를 `_download` 로 파일에 남긴다 — 나중에 숫자의 출처를 되짚을 수 있다.

사용
  python3 fetch_dl.py --url "<download_url>" --out "<회차>/data/cat/<이름>.json" \\
      [--sha256 <sha256>] [--items <item_count>] \\
      [--tool keyword_info --params-file <회차>/work/brandkw_0.params.json]

  `--sha256` · 봉투의 `download.sha256`. 주면 대조한다.
  `--items`  · 봉투의 `download.item_count`. **요청 키워드 수가 아니다** — `keyword_info` 는
               미수록 키워드를 빼고 표기 변형 행을 더해서 돌려준다(600 요청 → 601 행 실측).
  `--tool`/`--params-file` · 함께 주면 `mcp_cache.py store` 까지 이어서 돌린다. 「호출당 2단계」의
               store 를 따로 치지 않아도 된다. 캐시 키는 요청 파라미터라 **보낸 그대로** 넘긴다.

어긋나면 **저장하지 않고 `<out>.partial` 로 남긴다** — 무엇이 왔는지 봐야 하므로 지우지 않는다.
받다가 잘린 것이면 **같은 URL 로 다시 받으면 되고 크레딧이 들지 않는다.**

exit · 0 성공 / 1 실패 / 2 인자 오류
"""
import argparse, datetime, hashlib, json, os, subprocess, sys, urllib.error, urllib.request

# 빌드가 평탄화한 zip 안에서 이 파일은 _shared/render/, mcp_cache.py 는 scripts/ 에 있다.
# 같은 폴더로 보면 5단계가 통째로 죽는다.
HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(os.path.dirname(HERE))
SCRIPTS = os.path.join(PKG_ROOT, "scripts")
sys.path.insert(0, SCRIPTS)
import mcp_cache  # _core/scripts/mcp_cache.py · 콘텐츠 블록 벗기기를 한 자리에서 쓴다


def main():
    p = argparse.ArgumentParser(description="download_url → 파일 · sha256·건수 대조")
    p.add_argument("url_pos", nargs="?", metavar="URL", help="내려받기 URL (--url 과 같다)")
    p.add_argument("--url")
    p.add_argument("--out", required=True, help="저장할 경로")
    p.add_argument("--sha256", help="봉투의 download.sha256")
    p.add_argument("--items", "--expect", type=int, default=None, dest="items",
                   help="봉투의 download.item_count")
    p.add_argument("--tool", choices=["intent_finder", "keyword_info",
                                      "cluster_finder", "path_finder"],
                   help="주면 mcp_cache store 까지 이어서 돌린다")
    p.add_argument("--params", help="MCP 요청 파라미터 JSON 문자열")
    p.add_argument("--params-file", help="MCP 요청 파라미터 JSON 파일 경로")
    a = p.parse_args()

    url = a.url or a.url_pos
    if not url:
        print("❌ URL 이 없습니다 · fetch_dl.py --url <URL> --out <경로>", file=sys.stderr)
        return 2
    if a.tool and not (a.params or a.params_file):
        print("❌ --tool 을 주면 --params 또는 --params-file 도 필요합니다", file=sys.stderr)
        return 2

    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    part = a.out + ".partial"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "lm-brand-competition/fetch_dl"})
        with urllib.request.urlopen(req, timeout=180) as r:
            raw = r.read()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        print(f"❌ 내려받기 실패 · {e}", file=sys.stderr)
        print("  → URL 에 유효기간이 있습니다. 만료면 도구를 다시 부르는 수밖에 없습니다.",
              file=sys.stderr)
        return 1

    with open(part, "wb") as f:
        f.write(raw)
    sha = hashlib.sha256(raw).hexdigest()

    if a.sha256 and sha != a.sha256.strip().lower():
        print(f"❌ sha256 불일치 · 기대 {a.sha256} · 실제 {sha}", file=sys.stderr)
        print(f"  저장하지 않고 {part} 로 남겨 둡니다 · 같은 URL 로 다시 받으세요"
              "(크레딧이 들지 않습니다).", file=sys.stderr)
        return 1

    try:
        d = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        print(f"❌ JSON 이 아닙니다 · {e} · {part} 로 남겨 둡니다", file=sys.stderr)
        print(f"  앞 200바이트 · {raw[:200]!r}", file=sys.stderr)
        print("  → CSV·gzip 이면 형식을 확인하고 사람에게 알리세요. 요약해서 넘기지 마세요.",
              file=sys.stderr)
        return 1

    d = mcp_cache.unwrap_content_blocks(d)
    # 맨 리스트든 봉투든 **항상 {"data": ...} 모양으로** 맞춘다 (읽는 쪽 14군데가 그걸 본다)
    env = d if (isinstance(d, dict) and "data" in d) else {"data": d}
    n = len(env["data"]) if isinstance(env["data"], (list, dict)) else 0

    if a.items is not None and n != a.items:
        print(f"❌ 건수 불일치 · 기대 {a.items:,} · 실제 {n:,}", file=sys.stderr)
        print(f"  저장하지 않고 {part} 로 남겨 둡니다 · 받다가 잘렸습니다. 같은 URL 로 다시"
              " 받으세요(크레딧이 들지 않습니다).", file=sys.stderr)
        return 1
    if n < 1:
        print(f"❌ 레코드 0건 · 저장하지 않고 {part} 로 남겨 둡니다", file=sys.stderr)
        return 1

    env["_download"] = dict(url=url, sha256=sha, size_bytes=len(raw), items=n,
                            fetched_at=datetime.datetime.now(
                                datetime.timezone.utc).isoformat(timespec="seconds"))
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(env, f, ensure_ascii=False)
    os.remove(part)
    print(f"✓ {os.path.basename(a.out)} · {n:,}건 · {len(raw):,}바이트 · sha256 {sha[:16]}"
          f"{' 일치' if a.sha256 else ''}")

    if a.tool:
        sys.stdout.flush()
        cmd = [sys.executable, os.path.join(SCRIPTS, "mcp_cache.py"), "store", a.tool,
               "--file", a.out]
        cmd += (["--params-file", a.params_file] if a.params_file else ["--params", a.params])
        if a.items is not None:
            cmd += ["--expect", str(a.items)]
        return subprocess.call(cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
