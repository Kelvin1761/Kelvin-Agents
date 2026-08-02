#!/usr/bin/env python3
"""把瀏覽器攞到嘅頁面搬落 `SportsbetFormFetcher` 個 cache。

**點解要呢件嘢。** curl_cffi 會俾 sportsbetform 403（首頁、`/{date}/` 索引頁一直
都係，賽事頁喺請求密咗之後亦都會），但瀏覽器 session 照通。呢個 bridge 令兩邊
夾得埋：**攞頁面行瀏覽器（慢、逐版），parse 同寫檔行 Python（離線、快）**。

做法：跑一個只聽 127.0.0.1 嘅小 server，瀏覽器逐版 POST 上嚟，佢用**同一條
cache path 公式**（sha1(url)）寫落 `.sportsbet_cache/`。之後
`sb_backfill_archive.py --run` 全程 cache 命中，一個網絡請求都唔會出。

⚠️ 呢個唔係用嚟「扮人」避開偵測。節奏保守 + 撞到 403 即刻停，係**尊重**個限制，
   唔係繞過佢。瀏覽器嗰邊個 loop 見到任何非 200 就會停低，唔會 retry 撞落去。

用法：
    python3 sb_browser_bridge.py --port 8787          # 開住佢，喺瀏覽器度餵頁面
    python3 sb_browser_bridge.py --port 8787 --status # 睇下 cache 有幾多版
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from claw_sportsbet_form import BASE, CACHE_DIR  # noqa: E402

MIN_BYTES = 5000        # 同 fetcher 一致 —— 細過呢個多數係攔截頁


def cache_path(url: str) -> Path:
    """一定要同 `SportsbetFormFetcher._cache_path` 完全一樣，否則寫咗都攞唔返。"""
    return Path(CACHE_DIR) / (hashlib.sha1(url.encode()).hexdigest() + ".html")


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        # 瀏覽器由 sportsbetform origin 打過嚟，所以要開 CORS。
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")

    def do_OPTIONS(self):                      # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):                          # noqa: N802
        """`/jobs` → 仲未落 cache 嘅 [meetingId, raceId]；`/wait?ms=` → 慢慢先答。

        由 bridge 出 job list（而唔係喺瀏覽器度貼 836 個 ID）有兩個好處：
        cache 已經有嘅自動唔會再攞，而且中途斷咗重新攞一次 `/jobs` 就係續跑。

        ⚠️ `/wait` 存在嘅原因：**Chrome 會 throttle 背景 tab 嘅 `setTimeout`**
        （clamp 到大約一分鐘一次）。我哋設 18–25 秒，實際變成每版 ~100 秒，
        822 版即係 23 個鐘。改成 await 一個慢慢先回應嘅請求，個 timer 唔喺
        瀏覽器度，就唔會被 throttle —— 節奏返返我哋自己揀嗰個。
        """
        path = urlparse(self.path).path
        if path == "/wait":
            import time
            q = parse_qs(urlparse(self.path).query)
            ms = min(int((q.get("ms") or ["20000"])[0]), 120000)
            time.sleep(ms / 1000.0)
            self.send_response(200)
            self._cors()
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        if path != "/jobs":
            self.send_response(404)
            self._cors()
            self.end_headers()
            return
        import json
        from sb_backfill_archive import load_meeting_ids
        q = parse_qs(urlparse(self.path).query)
        only = (q.get("only") or [""])[0].lower()
        jobs = []
        for name, v in sorted(load_meeting_ids().items(), key=lambda kv: kv[1]["date"]):
            if only and only not in name.lower():
                continue
            for rid in v["races"]:
                url = f"{BASE}/{v['meetingId']}/{rid}/"
                if not cache_path(url).exists():
                    jobs.append([v["meetingId"], rid])
        body = json.dumps(jobs).encode()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):                         # noqa: N802
        q = parse_qs(urlparse(self.path).query)
        url = (q.get("url") or [""])[0]
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        ok, msg = self._store(url, body)
        self.send_response(200 if ok else 400)
        self._cors()
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(msg.encode())

    def _store(self, url, body):
        if not url.startswith(BASE):
            return False, f"唔係 {BASE} 嘅 URL"
        if len(body) < MIN_BYTES:
            # 細版通常係攔截／錯誤頁。寧可唔存，也好過落一個毒 cache ——
            # 之後 parse 出零條往績，而且靜靜咁。
            return False, f"太細（{len(body)} bytes），當攔截頁唔存"
        p = cache_path(url)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
        return True, f"ok {len(body)}"

    def log_message(self, fmt, *args):         # 靜啲，自己印
        pass


def serve(port):
    n0 = len(list(Path(CACHE_DIR).glob("*.html"))) if Path(CACHE_DIR).exists() else 0
    print(f"bridge 聽緊 http://127.0.0.1:{port}  →  {CACHE_DIR}")
    print(f"cache 而家有 {n0} 版。Ctrl-C 收工。")
    # threading：`/wait` 會瞓住，單線程會連 POST 都塞住
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


def main():
    ap = argparse.ArgumentParser(description="瀏覽器 → cache bridge")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()
    if args.status:
        n = len(list(Path(CACHE_DIR).glob("*.html"))) if Path(CACHE_DIR).exists() else 0
        print(f"cache：{n} 版 → {CACHE_DIR}")
        return 0
    try:
        serve(args.port)
    except KeyboardInterrupt:
        print("\n收工")
    return 0


if __name__ == "__main__":
    sys.exit(main())
