#!/usr/bin/env python3
"""HKJC SpeedPro（速勢能量）只向前收集器 —— 純資料收集，唔郁任何評分。

點解要有：HKJC 只喺 `current/` 公布 SpeedPro，**冇歷史檔**。試過用日期路徑攞
舊場次，返嚟係一頁 ~4368 bytes 嘅 HTML 錯誤頁。即係話：每一個冇即時存低嘅
場次，就永遠攞唔返。將來想量 SpeedPro 有冇用，唯一嘅語料就係呢度今日開始
儲落嚟嗰批。

收咩：
  sg_index              —— 場次清單、racedate、lastupdatetime
  sg_race_N             —— 能量需求、近五仗能量、狀態評分（0-3）、SpeedPRO 能量差
  fg_race_N             —— 逐仗步速／走位／評述／事故／健康
  <excelch> / <excelen> —— 能量表 xls（~30KB）

儲喺邊：
  <HK data root>/_speedpro_snapshots/<YYYY-MM-DD>_<ST|HV>/<UTC 時間戳>/
    sg_index.json, sg_race_N.json, fg_race_N.json, *.xls, manifest.json
  <HK data root>/_speedpro_snapshots/<YYYY-MM-DD>_<ST|HV>/fetch_log.jsonl

規矩：
  * 每次抓取一個資料夾，**永不覆蓋**。先寫去 `.partial-*` 再 rename，半截唔會
    扮成一份完整快照。
  * 內容同上一份一樣（signature 相同）就唔再抄多份，只係喺 fetch_log.jsonl
    加一行。內容有變（例如賽前更新退出馬／能量）就照存新版本。
  * sg 檔每個 ~1MB 係因為 base64 賽道圖。任何以 `data:` 開頭嘅字串值會換成
    `<stripped data-uri ...>` 標記（保留 mime、長度、sha256 頭 16 位，圖有冇
    變照樣睇得出），其餘欄位原封不動。
  * `current/` 可能仲係上一個場次（HKJC 未更新）。傳咗 `--date` 而 racedate
    對唔上，就**拒絕**存落錯日期，exit 3。
  * 資料夾以 `_` 開頭：所有場次掃描器都用 `^YYYY-MM-DD` 認場次，
    race_compliance_scan 亦會將名入面有 `snapshot` 嘅子樹當凍結，所以唔會
    被當成一個場次。

Exit code：0 = 已存／同上一份一樣；3 = current/ 唔係要求嗰個場次（或未出）；
1 = 抓取／解析失敗。排程只會記 log，**永遠唔會**因為呢度失敗而擋賽前流程。

用法：
  collect_speedpro.py                                  # 存 current/ 入面嗰個場次
  collect_speedpro.py --date 2026-10-14 --course HV    # 驗證係呢個場次先存
  collect_speedpro.py --date 2026-10-14 --dry-run      # 只抓同驗證，唔寫檔
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

BASE_URL = "https://consvc.hkjc.com/-/media/Sites/JCRW/SpeedPro/current/"
SNAPSHOT_DIRNAME = "_speedpro_snapshots"
FETCH_LOG = "fetch_log.jsonl"
SCHEMA_VERSION = 1
HEADERS = {
    # 同 extract_starter_pdf.py 一樣嘅 UA；consvc 係 CDN 靜態檔，唔使 curl_cffi。
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://racing.hkjc.com/",
}
COURSE_CODES = {
    "sha tin": "ST", "shatin": "ST", "沙田": "ST", "st": "ST",
    "happy valley": "HV", "happyvalley": "HV", "跑馬地": "HV", "hv": "HV",
}

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_NOT_CURRENT = 3

Fetcher = Callable[[str], bytes]


class SpeedProError(RuntimeError):
    """抓取或者解析失敗 —— exit 1。"""

    exit_code = EXIT_FAILED


class NotCurrentMeeting(SpeedProError):
    """`current/` 唔係要求嗰個場次（上一場未落架，或者今場未出）—— exit 3。"""

    exit_code = EXIT_NOT_CURRENT


# ── 解析 ────────────────────────────────────────────────────────────────────

def decode_json(raw: bytes, *, name: str = "?") -> Any:
    """HKJC 啲檔以 UTF-8 BOM 開頭，一定要 utf-8-sig。

    日期路徑／唔存在嘅檔返嚟係 HTML 錯誤頁（HTTP 200 都有可能），所以見到
    `<` 開頭就當失敗，唔好俾 json 個錯誤訊息扮成「格式改咗」。
    """
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SpeedProError(f"{name}: 唔係 UTF-8（{exc}）") from exc
    stripped = text.lstrip()
    if not stripped:
        raise SpeedProError(f"{name}: 空檔")
    if stripped.startswith("<"):
        raise SpeedProError(
            f"{name}: 返咗 HTML 唔係 JSON（{len(raw)} bytes）—— 多數係錯誤頁"
        )
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SpeedProError(f"{name}: JSON 解析失敗：{exc}") from exc


def strip_data_uris(value: Any) -> Tuple[Any, int]:
    """將所有 `data:` 開頭嘅字串換成細標記；回傳 (新值, 換咗幾多個)。"""
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        count = 0
        for key, item in value.items():
            out[key], n = strip_data_uris(item)
            count += n
        return out, count
    if isinstance(value, list):
        items = []
        count = 0
        for item in value:
            new, n = strip_data_uris(item)
            items.append(new)
            count += n
        return items, count
    if isinstance(value, str) and value.startswith("data:"):
        mime = value[5:].split(";", 1)[0].split(",", 1)[0] or "unknown"
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
        return f"<stripped data-uri {mime} len={len(value)} sha256={digest}>", 1
    return value, 0


def parse_racedate(index: dict) -> date:
    """`"racedate": "14/10/2026 10:50 PM"` → date(2026, 10, 14)。"""
    raw = str(index.get("racedate") or "").strip()
    if not raw:
        raise SpeedProError("sg_index 冇 racedate")
    try:
        return datetime.strptime(raw.split()[0], "%d/%m/%Y").date()
    except ValueError as exc:
        raise SpeedProError(f"sg_index racedate 認唔到：{raw!r}") from exc


def race_numbers(index: dict) -> List[int]:
    """兩個語言嘅清單取併集 —— 一邊漏咗一場唔應該令我哋少存一場。"""
    numbers = set()
    for lang in ("zh-hk", "en-us"):
        for entry in index.get(lang) or []:
            try:
                numbers.add(int(str(entry.get("race")).strip()))
            except (TypeError, ValueError, AttributeError):
                continue
    if not numbers:
        raise SpeedProError("sg_index 冇任何場次")
    return sorted(numbers)


def _race_info(payload: dict) -> dict:
    """sg 檔分 zh-hk / en-us 兩層；fg 檔冇。兩種都攞到 RaceInfoEng。"""
    for holder in (payload.get("zh-hk"), payload.get("en-us"), payload):
        if isinstance(holder, dict) and isinstance(holder.get("RaceInfoEng"), dict):
            return holder["RaceInfoEng"]
    return {}


def course_code(payload: dict) -> Optional[str]:
    for holder in (payload.get("zh-hk"), payload.get("en-us"), payload):
        if not isinstance(holder, dict):
            continue
        for key in ("RaceInfoEng", "RaceInfoChi"):
            info = holder.get(key)
            if isinstance(info, dict):
                name = str(info.get("Racecourse") or "").strip().lower()
                if name in COURSE_CODES:
                    return COURSE_CODES[name]
    return None


def race_date_of(payload: dict) -> Optional[date]:
    raw = str(_race_info(payload).get("Date") or "").strip()
    try:
        return datetime.strptime(raw, "%d/%m/%Y").date()
    except ValueError:
        return None


def runners_of(sg_payload: dict) -> List[dict]:
    for lang in ("zh-hk", "en-us"):
        holder = sg_payload.get(lang)
        if isinstance(holder, dict) and isinstance(holder.get("SpeedPRO"), list):
            return holder["SpeedPRO"]
    return []


# ── 抓取 ────────────────────────────────────────────────────────────────────

def make_fetcher(*, timeout: float = 20.0, retries: int = 3,
                 backoff: float = 2.0) -> Fetcher:
    """requests GET，有 timeout、有 backoff 重試，永遠唔會吊死。"""
    import requests

    session = requests.Session()
    session.headers.update(HEADERS)

    def fetch(url: str) -> bytes:
        last: Optional[str] = None
        for attempt in range(1, retries + 1):
            try:
                response = session.get(url, timeout=(min(timeout, 10.0), timeout))
                if response.status_code == 200:
                    return response.content
                last = f"HTTP {response.status_code}"
                # 404 唔會因為等多陣就出現，唔好嘥時間重試
                if response.status_code in (403, 404, 410):
                    break
            except requests.RequestException as exc:
                last = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(backoff * (2 ** (attempt - 1)))
        raise SpeedProError(f"GET {url} 失敗：{last}")

    return fetch


# ── 儲存 ────────────────────────────────────────────────────────────────────

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dump(payload: Any) -> bytes:
    # 冇 BOM、保留中文；欄位次序照原本。
    return json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8")


def signature_of(files: Dict[str, bytes]) -> str:
    listing = sorted((name, _sha256(data)) for name, data in files.items())
    return _sha256(json.dumps(listing).encode("utf-8"))


def latest_manifest(meeting_root: Path) -> Optional[Tuple[Path, dict]]:
    """最新一份**有 manifest** 嘅快照（人手存嘅 `manual_*` 冇 manifest，唔計）。"""
    best: Optional[Tuple[str, Path, dict]] = None
    if not meeting_root.is_dir():
        return None
    for manifest in meeting_root.glob("*/manifest.json"):
        if manifest.parent.name.startswith("."):
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        key = str(data.get("fetched_at_utc") or "")
        if best is None or key > best[0]:
            best = (key, manifest.parent, data)
    return (best[1], best[2]) if best else None


def _append_log(meeting_root: Path, entry: dict) -> None:
    meeting_root.mkdir(parents=True, exist_ok=True)
    with (meeting_root / FETCH_LOG).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def collect(
    *,
    data_root: Path,
    expected_date: Optional[date] = None,
    expected_course: Optional[str] = None,
    dry_run: bool = False,
    fetcher: Optional[Fetcher] = None,
    now: Optional[datetime] = None,
    base_url: str = BASE_URL,
) -> dict:
    """抓一次、驗證、去重、存檔。回傳結果 dict；失敗就 raise SpeedProError。"""
    fetch = fetcher or make_fetcher()
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    index_raw = fetch(base_url + "sg_index")
    index = decode_json(index_raw, name="sg_index")
    if not isinstance(index, dict):
        raise SpeedProError("sg_index 唔係 JSON object")
    racedate = parse_racedate(index)
    if expected_date is not None and racedate != expected_date:
        raise NotCurrentMeeting(
            f"current/ 而家係 {racedate.isoformat()} 嘅場次，唔係 "
            f"{expected_date.isoformat()} —— 拒絕存落錯日期"
            f"（lastupdatetime={index.get('lastupdatetime')!r}）"
        )

    files: Dict[str, bytes] = {}
    raw_sha: Dict[str, str] = {}
    stripped_total = 0
    missing: List[str] = []
    races = race_numbers(index)
    course: Optional[str] = None
    runners = 0
    scratched = 0

    files["sg_index.json"] = _dump(index)
    raw_sha["sg_index.json"] = _sha256(index_raw)

    for race in races:
        # sg 係核心：缺一場就成份唔存（半份快照會扮成「嗰場冇數據」）
        name = f"sg_race_{race}"
        raw = fetch(base_url + name)
        payload = decode_json(raw, name=name)
        if not isinstance(payload, dict):
            raise SpeedProError(f"{name} 唔係 JSON object")
        file_date = race_date_of(payload)
        if file_date is not None and file_date != racedate:
            # current/ 更新到一半：index 同 race 檔講緊唔同場次
            raise SpeedProError(
                f"{name} 日期 {file_date.isoformat()} 同 sg_index {racedate.isoformat()} "
                "對唔上 —— current/ 可能更新緊，遲啲再試"
            )
        course = course or course_code(payload)
        race_runners = runners_of(payload)
        runners += len(race_runners)
        scratched += sum(1 for r in race_runners if isinstance(r, dict) and r.get("scratched"))
        clean, n = strip_data_uris(payload)
        stripped_total += n
        files[f"{name}.json"] = _dump(clean)
        raw_sha[f"{name}.json"] = _sha256(raw)

        # fg 係補充（逐仗評述）：缺咗照記低，唔好連 sg 都唔存
        name = f"fg_race_{race}"
        try:
            raw = fetch(base_url + name)
            payload = decode_json(raw, name=name)
        except SpeedProError as exc:
            missing.append(f"{name}: {exc}")
            continue
        course = course or course_code(payload)
        clean, n = strip_data_uris(payload)
        stripped_total += n
        files[f"{name}.json"] = _dump(clean)
        raw_sha[f"{name}.json"] = _sha256(raw)

    for key in ("excelch", "excelen"):
        excel = str(index.get(key) or "").strip()
        if not excel:
            continue
        if "/" in excel or excel.startswith("."):
            missing.append(f"{key}: 檔名唔安全 {excel!r}")
            continue
        try:
            raw = fetch(base_url + excel)
        except SpeedProError as exc:
            missing.append(f"{excel}: {exc}")
            continue
        if raw.lstrip()[:1] == b"<":
            missing.append(f"{excel}: 返咗 HTML 錯誤頁（{len(raw)} bytes）")
            continue
        files[excel] = raw
        raw_sha[excel] = _sha256(raw)

    if course is None:
        raise SpeedProError("認唔到場地（RaceInfoEng.Racecourse）")
    if expected_course and expected_course.upper() != course:
        raise NotCurrentMeeting(
            f"current/ 係 {racedate.isoformat()} {course}，唔係 {expected_course.upper()}"
        )

    signature = signature_of(files)
    meeting_key = f"{racedate.isoformat()}_{course}"
    meeting_root = data_root / SNAPSHOT_DIRNAME / meeting_key
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    result = {
        "meeting": meeting_key,
        "racedate": racedate.isoformat(),
        "course": course,
        "fetched_at_utc": now.isoformat(timespec="seconds"),
        "lastupdatetime": index.get("lastupdatetime"),
        "races": len(races),
        "runners": runners,
        "scratched": scratched,
        "signature": signature,
        "missing": missing,
        "dry_run": dry_run,
    }

    previous = latest_manifest(meeting_root)
    if previous and previous[1].get("signature") == signature:
        result.update(status="duplicate", snapshot=str(previous[0]))
        if not dry_run:
            _append_log(meeting_root, {
                "fetched_at_utc": result["fetched_at_utc"],
                "status": "duplicate",
                "same_as": previous[0].name,
                "signature": signature,
                "lastupdatetime": index.get("lastupdatetime"),
            })
        return result

    if dry_run:
        result.update(status="would_save", snapshot=str(meeting_root / stamp))
        return result

    destination = meeting_root / stamp
    suffix = 1
    while destination.exists():   # 同一秒抓兩次：加後綴，永不覆蓋
        destination = meeting_root / f"{stamp}-{suffix}"
        suffix += 1
    partial = meeting_root / f".partial-{destination.name}-{os.getpid()}"
    manifest_files = [
        {
            "name": name,
            "size": len(files[name]),
            "sha256": _sha256(files[name]),
            "raw_sha256": raw_sha.get(name),
        }
        for name in sorted(files)
    ]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "platform": "hkjc",
        "source": base_url,
        "meeting": meeting_key,
        "racedate": racedate.isoformat(),
        "course": course,
        "fetched_at_utc": result["fetched_at_utc"],
        "sg_index_lastupdatetime": index.get("lastupdatetime"),
        "sg_index_racedate": index.get("racedate"),
        "sg_index_expiredate": index.get("expiredate"),
        "races": len(races),
        "runners": runners,
        "scratched": scratched,
        "data_uris_stripped": stripped_total,
        "missing": missing,
        "signature": signature,
        "previous_snapshot": previous[0].name if previous else None,
        "files": manifest_files,
        "immutable_snapshot": True,
    }
    try:
        partial.mkdir(parents=True)
        for name in sorted(files):
            (partial / name).write_bytes(files[name])
        (partial / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.rename(partial, destination)
    except OSError as exc:
        # 半截嘅 .partial-* 唔可以留低扮快照
        shutil.rmtree(partial, ignore_errors=True)
        raise SpeedProError(f"寫入 {destination} 失敗：{exc}") from exc
    _append_log(meeting_root, {
        "fetched_at_utc": result["fetched_at_utc"],
        "status": "saved",
        "snapshot": destination.name,
        "signature": signature,
        "lastupdatetime": index.get("lastupdatetime"),
    })
    result.update(status="saved", snapshot=str(destination))
    return result


# ── CLI ─────────────────────────────────────────────────────────────────────

def _default_data_root() -> Path:
    repo = Path(__file__).resolve().parents[5]
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from wongchoi_paths import HK_RACING

    return Path(HK_RACING)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--date", type=date.fromisoformat,
                        help="預期場次日期 YYYY-MM-DD；current/ 唔係呢日就拒絕存（exit 3）")
    parser.add_argument("--course", choices=("ST", "HV"), type=str.upper,
                        help="預期場地；對唔上就拒絕存（exit 3）")
    parser.add_argument("--data-root", type=Path,
                        help="HK data root（預設讀 .wongchoi_hk_data_root）")
    parser.add_argument("--dry-run", action="store_true", help="只抓同驗證，唔寫檔")
    parser.add_argument("--timeout", type=float, default=20.0, help="每個請求嘅 timeout 秒數")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--json", action="store_true", help="結果以 JSON 印出")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        data_root = args.data_root or _default_data_root()
        result = collect(
            data_root=data_root,
            expected_date=args.date,
            expected_course=args.course,
            dry_run=args.dry_run,
            fetcher=make_fetcher(timeout=args.timeout, retries=max(1, args.retries)),
        )
    except SpeedProError as exc:
        label = "NOT_CURRENT" if exc.exit_code == EXIT_NOT_CURRENT else "FAILED"
        print(f"SpeedPro {label}: {exc}", file=sys.stderr)
        return exc.exit_code
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"SpeedPro {result['status']}: {result['meeting']} "
            f"{result['races']} 場／{result['runners']} 匹（退出 {result['scratched']}）"
            f"｜lastupdatetime {result['lastupdatetime']}｜{result['snapshot']}"
        )
        for item in result["missing"]:
            print(f"  ⚠️ 缺：{item}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
