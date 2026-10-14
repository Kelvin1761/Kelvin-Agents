#!/usr/bin/env python3
"""Punters GraphQL 抓取器：慢、少、全 cache、一被拒即停。

節奏規則（2026-10-13 定，唔好為咗快而改細）：
- 每個網絡請求之間 12–20 秒隨機間隔（2026-10-13 撞過一次 Failed to fetch 後由 8–15 放慢）；
- 每 20–30 個請求停 1–3 分鐘；
- 每個 run 有請求上限（預設 250）；
- 單線程，同一時間只有一個 Chrome；
- HTTP 401/403/429/5xx、GraphQL 權限錯誤 → 即刻停，唔重試，留 `stop_reason`。

cache：每個 (operation, variables) 一個 JSON（sha1），喺 repo 外。
cache 有嘢就**永遠唔出網**，所以中斷後重跑只會補未攞嘅。
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import time
from pathlib import Path

from punters_session import PuntersNotLoggedIn, PuntersRefused, PuntersSession

CACHE_DIR = Path(os.environ.get("WC_PUNTERS_CACHE", "")) if os.environ.get("WC_PUNTERS_CACHE") \
    else Path.home() / ".cache" / "wongchoi" / "punters_cache"

Q_MEETINGS = """query meetingsIndexByStartEndTime($startDate: String, $endDate: String) {
  meetings(startDate: $startDate, endDate: $endDate) {
    id slug venue { name }
    events { id eventNumber
      selections { id competitorNumber barrierNumber status selectionResult officialMargin
        ratingOfficial
        competitor { id name slug }
        prediction { normSpeedMeasure speedMeasureRatingName barrierSpeedRating closingSpeedRating
          modelOutput modelRank width length winningChance speedMeasure finishSpeed } } } } }"""

Q_SECTIONALS = """query getSectionalsBySelectionIds($selectionIds: [String!]!, $limit: Int) {
  competitorForms(selectionIds: $selectionIds, limit: $limit) {
    count selectionId
    forms { id isTrial statusAbv finishPosition eventStarters meetingDate meetingName
      eventDistance eventDistanceUnit trackType trackCondition trackConditionRating
      eventNumber eventNameForm groupType finishTime venue { name }
      margin secondMarginDecimal weight barrier barrierRow barrierHandicap
      prizeMoney startingWinPriceDecimal daysSinceLastRun isFirstUp isSecondUp isThirdUp
      videoComment videoNote stewardsReport
      jockey { id name } trainer { id name }
      winnerName secondName thirdName
      formLine { places { finishPosition competitorName competitorId details } }
      sectionalTimeSummary { earlySpeed midSpeed lateSpeed averageSpeed averageTime }
      sectionalTime { l800 { split speed } l600 { split speed } l400 { split speed }
                      l200 { split speed } finish { split speed } } } } }"""

# 改任何 query 都要升呢個版本號：cache key 包含佢，否則舊 cache（缺欄位）會被當新嘢用。
# v2（2026-10-13）：加評述、頭馬距離、負磅、檔位、SP、騎練名、賽績線。
# v3（2026-10-13）：剷走 `isTrial:false` —— 同網站完整往績 query 一樣，賽事＋試閘一齊返，
#   用 `isTrial` 分；試閘段速零額外請求。limit 加到 15 因為試閘會佔位。
# meetings v2（2026-10-13）：加 Punters speed map 預測（`prediction`）同官方評分。
#   ⚠️ 舊賽事嘅 prediction 未證實係賽前版 —— 過洩漏檢查之前唔准入模型。
QUERY_VERSION = {"meetingsIndexByStartEndTime": 2, "getSectionalsBySelectionIds": 3}

FORM_LIMIT = 15          # 同網站自己個 Sectionals tab 差唔多；夠計近期段速


class StopFetching(RuntimeError):
    """要停低成個 run（被拒、登入失效、到上限）。"""


class PuntersFetcher:
    def __init__(self, max_requests: int = 250, cache_dir: Path = CACHE_DIR,
                 cache_only: bool = False, log=None):
        self.max_requests = max_requests
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_only = cache_only
        self.log = log or (lambda m: print(f"   {m}", flush=True))
        self.requests_made = 0
        self.cache_hits = 0
        self.stop_reason: str | None = None
        self._session: PuntersSession | None = None
        self._last = 0.0
        self._next_long_pause = random.randint(20, 30)

    # -- lifecycle --------------------------------------------------------
    def __enter__(self):
        return self

    def __exit__(self, *_):
        if self._session:
            self._session.__exit__(None, None, None)
            self._session = None
        return False

    def _ensure_session(self) -> PuntersSession:
        if self._session is None:
            self._session = PuntersSession(log=self.log).__enter__()
            self._session.ensure_on_site("https://www.punters.com.au/form-guide/")
            self._session.page.wait_for_timeout(random.randint(5000, 9000))
            self._last = time.time()
        return self._session

    # -- cache ------------------------------------------------------------
    def _key(self, op: str, variables: dict) -> Path:
        ver = QUERY_VERSION.get(op, 1)
        raw = op + json.dumps(variables, sort_keys=True) + ("" if ver == 1 else f"#v{ver}")
        return self.cache_dir / f"{op}_{hashlib.sha1(raw.encode()).hexdigest()}.json"

    def cached(self, op: str, variables: dict) -> dict | None:
        p = self._key(op, variables)
        if p.exists() and p.stat().st_size > 0:
            return json.loads(p.read_text())
        return None

    # -- pacing -----------------------------------------------------------
    def _pace(self) -> None:
        if self.requests_made and self.requests_made >= self._next_long_pause:
            pause = random.uniform(60, 180)
            self.log(f"☕ 長停 {pause:.0f}s（已發 {self.requests_made} 個請求）")
            time.sleep(pause)
            self._next_long_pause = self.requests_made + random.randint(20, 30)
        wait = random.uniform(12, 20) - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)

    # -- request ----------------------------------------------------------
    def query(self, op: str, query: str, variables: dict) -> dict | None:
        hit = self.cached(op, variables)
        if hit is not None:
            self.cache_hits += 1
            return hit
        if self.cache_only:
            return None
        if self.stop_reason:
            raise StopFetching(self.stop_reason)
        if self.requests_made >= self.max_requests:
            self.stop_reason = f"到達本 run 上限 {self.max_requests} 個請求"
            raise StopFetching(self.stop_reason)
        s = self._ensure_session()
        self._pace()
        try:
            data = s.graphql(query, variables, op)
        except (PuntersRefused, PuntersNotLoggedIn) as e:
            self.stop_reason = f"{type(e).__name__}: {e}"
            raise StopFetching(self.stop_reason) from e
        finally:
            self._last = time.time()
            self.requests_made += 1
        if data.get("errors"):
            msg = json.dumps(data["errors"], ensure_ascii=False)[:400]
            # 權限／登入類錯誤 = 停；其他 GraphQL 錯誤唔寫 cache，交返 caller。
            if any(w in msg.lower() for w in ("auth", "forbidden", "subscri", "premium", "permission", "rate")):
                self.stop_reason = f"GraphQL 權限錯誤：{msg}"
                raise StopFetching(self.stop_reason)
            self.log(f"⚠️ GraphQL errors（唔 cache）：{msg}")
            return data
        data["_query_version"] = QUERY_VERSION.get(op, 1)
        tmp = self._key(op, variables).with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False))
        tmp.replace(self._key(op, variables))   # atomic：中途殺 process 唔會留半個檔
        return data

    def meetings(self, date: str) -> dict | None:
        return self.query("meetingsIndexByStartEndTime", Q_MEETINGS,
                          {"startDate": date, "endDate": date})

    def sectionals(self, selection_ids: list[str], limit: int = FORM_LIMIT) -> dict | None:
        return self.query("getSectionalsBySelectionIds", Q_SECTIONALS,
                          {"selectionIds": sorted(selection_ids), "limit": limit})
