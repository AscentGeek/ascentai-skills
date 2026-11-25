#!/usr/bin/env python3
"""fetch_download.py · response_format=download_url 로 받은 MCP 결과 파일을 내려받아 검증한다.

MCP 도구 응답의 download 블록(browser_download_url, sha256, item_count)을 그대로 넘긴다.
  python3 scripts/fetch_download.py --url <browser_download_url> --sha256 <sha256> \
      --expect <item_count> --out "{WORKDIR}/lm_path_a.json"

- sha256 이 다르면 파일을 지우고 실패(exit 1) · 다시 내려받는다(도구를 다시 부르지 않는다).
- serp 는 수집 시각(collected_at)이 파일이 아니라 도구 응답에만 온다 · --collected-at 으로 넘기면 봉투로 감싼다.
- 내려받은 파일이 봉투({"result","data"...})가 아니라 data 배열만이어도 그대로 둔다.
  context.py 와 mcp_cache.py 는 두 형태를 모두 읽는다.
exit 0 성공 · 1 실패
"""
import argparse, hashlib, json, sys, time, urllib.request
from pathlib import Path

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True); p.add_argument("--sha256", required=True)
    p.add_argument("--expect", type=int); p.add_argument("--out", required=True)
    p.add_argument("--collected-at", help="serp 처럼 수집 시각이 응답 메타에만 있을 때 · 봉투로 감싸 함께 저장")
    a = p.parse_args()
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for i in range(3):
        try:
            with urllib.request.urlopen(a.url, timeout=60) as r:
                body = r.read()
            break
        except Exception as e:  # 네트워크 일시 오류 · 잠시 후 재시도
            last = e; time.sleep(2 * (i + 1))
    else:
        print(f"❌ 내려받기 실패 · {last}", file=sys.stderr)
        print("  → 네트워크(github.com) 허용 여부를 확인하세요. MCP 도구를 다시 부르지 마세요.", file=sys.stderr)
        return 1
    h = hashlib.sha256(body).hexdigest()
    if h != a.sha256.strip().lower():
        print(f"❌ sha256 불일치 · 받은 {h[:12]}… ≠ 기대 {a.sha256[:12]}…", file=sys.stderr)
        return 1
    try:
        d = json.loads(body)
    except json.JSONDecodeError as e:
        print(f"❌ JSON 이 아닙니다 · {e}", file=sys.stderr); return 1
    n = len(d) if isinstance(d, list) else len(d.get("data") or []) if isinstance(d, dict) else 0
    if a.expect is not None and n != a.expect:
        print(f"⚠ 레코드 {n}건 · item_count {a.expect}건과 다릅니다 (봉투 모양 차이일 수 있음 · 내용 확인)")
    if isinstance(d, list) and a.collected_at:
        body = json.dumps({"result": "OK", "collected_at": a.collected_at, "data": d}, ensure_ascii=False).encode("utf-8")
    out.write_bytes(body)
    print(f"✓ {out.name} · {len(body):,} bytes · 레코드 {n}건 · sha256 확인")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
