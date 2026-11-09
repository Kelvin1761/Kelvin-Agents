"""Per-horse facts: typed accessors over Logic `_data` and the race context.

No scoring here — only reading, parsing and normalising what the extractor wrote.
"""
import datetime as _dt
import re

from .live_priors import (
    temporal_source_is_safe,
    EMBEDDED_LOGIC_PRIOR,
)
from . import scoring
from .scoring import (clip_score, parse_float, parse_record)



class HorseFacts:
    def _distance_suitability_v2_component(self):
        """Parse the deterministic V2 payload transported by Facts to Logic."""
        text = self._clean(self._value("distance_suitability_v2") or "")
        score_match = re.search(r"今場=.*?\s(\d+(?:\.\d+)?)分", text)
        target_match = re.search(r"目標有效樣本=(\d+(?:\.\d+)?)", text)
        surface_n_match = re.search(r"場地基準有效樣本=(\d+(?:\.\d+)?)", text)
        source_match = re.search(r"採用來源=([^|]+)", text)
        if self._is_happy_valley_context():
            surface = "HV_TURF"
        elif self._is_sha_tin_turf_context():
            surface = "ST_TURF"
        else:
            surface = "ST_AWT"
        score = parse_float(score_match.group(1)) if score_match else None
        return {
            "available": score is not None,
            "score": round(clip_score(score if score is not None else 60.0), 2),
            "surface": surface,
            "target_effective_n": round(float(parse_float(target_match.group(1)) or 0.0), 2) if target_match else 0.0,
            "surface_effective_n": round(float(parse_float(surface_n_match.group(1)) or 0.0), 2) if surface_n_match else 0.0,
            "source": source_match.group(1).strip() if source_match else "missing_neutral",
        }

    def _is_foreign_runner(self):
        """True for a visiting international runner: has real overseas race rows
        but no HKJC form. Such horses must NOT be penalised for missing HK-only
        data (medical/coverage) — absence here is 'data N/A', not 'bad news'."""
        pdf = self.data.get("pdf_overseas_races") or self.horse_data.get("pdf_overseas_races") or []
        real = any(
            isinstance(r, dict) and any(
                str(r.get(k, "-")).strip() not in ("-", "", "N/A", "--")
                for k in ("class_level", "rank", "time", "margin")
            )
            for r in pdf
        )
        if not real:
            return False
        hk_form = str(self._value("last_6_finishes") or "").strip()
        has_hk_form = hk_form not in ("", "N/A") and any(c.isdigit() for c in hk_form)
        return not has_hk_form

    def _rail_label(self):
        """今場賽道（A/B/C/C+3 等），顯示用。由 race_context 讀（賽前 pipeline 注入）；
        冇就回 None。唔入計分。"""
        for k in ("rail", "course_rail", "course_config"):
            v = self._clean(str(self.race_context.get(k) or ""))
            if v and v not in ("N/A", "-", ""):
                return v
        return None

    def _is_happy_valley_context(self):
        text = str(
            self.race_context.get("venue")
            or self.race_context.get("course")
            or self.race_context.get("racecourse")
            or ""
        )
        return any(token in text for token in ("HV", "Happy Valley", "HappyValley", "跑馬地"))

    def _is_early_season_context(self):
        """Frozen shadow phase: September through December, no live effect."""
        raw = str((self.race_context or {}).get("race_date") or "")[:10]
        try:
            return _dt.date.fromisoformat(raw).month in {9, 10, 11, 12}
        except ValueError:
            return False

    def _surface_performance_shadow_component(self):
        """Read the deterministic PIT surface score transported by Facts→Logic.

        The source string is produced by `compute_surface_performance_shadow` and
        carries the target score, effective prior-only sample and provenance.  A
        missing/malformed value is neutral rather than guessed.
        """
        text = self._clean(self._value("surface_performance_shadow") or "")
        score_match = re.search(r"今場=.*?\s(\d+(?:\.\d+)?)分", text)
        target_match = re.search(r"今場=([^|]+?)\s+\d+(?:\.\d+)?分", text)
        target = target_match.group(1).strip() if target_match else ""
        sample_match = re.search(
            r"(?:^|\|)\s*" + re.escape(target) + r"\s+\d+(?:\.\d+)?分\(有效樣本(\d+(?:\.\d+)?)",
            text,
        ) if target else None
        source_match = re.search(r"採用來源=([^|]+)", text)
        score = parse_float(score_match.group(1)) if score_match else None
        effective_n = parse_float(sample_match.group(1)) if sample_match else None
        return {
            "score": round(clip_score(score if score is not None else 60.0), 2),
            "effective_n": round(float(effective_n or 0.0), 2),
            "source": source_match.group(1).strip() if source_match else "missing_neutral",
            "available": score is not None,
        }

    def _latest_run_has_medical_incident(self):
        medical = self._text("medical_flags")
        return bool(re.search(r"(?:^|[;；]\s*)第1仗\s*[:：]\s*⚠️", medical))

    def _prior_l400_median(self):
        """Return a chronology-checked pre-incident L400 median.

        Older Logic files stored the sequence newest-to-oldest while current
        files explicitly store oldest-to-newest.  `raw_l400` is the independent
        latest-run anchor, so only accept a sequence when it matches one end.
        """
        raw_l400 = parse_float(self._value("raw_l400"))
        trend = self._clean(self._value("l400_trend") or "")
        if raw_l400 is None or not trend or trend == "N/A":
            return None
        sequence = trend.split("趨勢", 1)[0]
        values = [
            float(value)
            for value in re.findall(r"(?<!\d)(\d{2}(?:\.\d+)?)(?!\d)", sequence)
            if 18.0 <= float(value) <= 35.0
        ]
        if len(values) < 3:
            return None
        tolerance = 0.03
        if "最舊" in sequence and "最新" in sequence:
            if abs(values[-1] - raw_l400) > tolerance:
                return None
            prior = values[:-1]
            direction = "oldest_to_latest"
        elif abs(values[0] - raw_l400) <= tolerance:
            prior = values[1:]
            direction = "latest_to_oldest"
        elif abs(values[-1] - raw_l400) <= tolerance:
            prior = values[:-1]
            direction = "oldest_to_latest_inferred"
        else:
            return None
        ordered = sorted(prior)
        middle = len(ordered) // 2
        median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2.0
        return {
            "raw_l400": round(raw_l400, 2),
            "prior_median": round(median, 2),
            "prior_runs": len(prior),
            "sequence_direction": direction,
        }

    _LAYOFF_BANDS = (
        (7, "急放上陣"),        # ≤7：極少（2%）
        (20, "較密間隔"),       # 8-20：低於中位
        (35, "正常間隔"),       # 21-35：主流（median 24）
        (60, "短休後復出"),     # 36-60
        (120, "較長休賽"),      # 61-120
        (10**9, "長期休養後首戰"),  # >120：長休復出
    )

    def _layoff_band(self, days):
        for hi, label in self._LAYOFF_BANDS:
            if days <= hi:
                return label
        return "長期休養後首戰"

    def _last_race_date(self):
        """由 recent_6_detail「第1仗(DD/MM/YYYY …)」抽最近一仗日期 → 中文。"""
        iso = self._last_race_iso()
        if not iso:
            return None
        y, mo, d = iso.split("-")
        return f"{y}年{int(mo)}月{int(d)}日"

    def _last_race_iso(self):
        """最近一仗日期（ISO）。recent_6_detail 係「第1仗(DD/MM/YYYY …)」。"""
        m = re.search(r"第1仗\((\d{2})/(\d{2})/(\d{4})", self._text("recent_6_detail"))
        if not m:
            return None
        d, mo, y = m.group(1), m.group(2), m.group(3)
        try:
            return _dt.date(int(y), int(mo), int(d)).isoformat()
        except ValueError:
            return None

    def _days_since_last(self):
        """距今日數 —— 一定要（今仗日期 − 上仗日期），唔可以信 Logic 個欄位。

        `inject_hkjc_fact_anchors.compute_stats` 曾經寫 `races[0]['days_since']`
        落 Facts「休後復出」，而賽績檔嗰個 `日數:` 係**該仗同上一仗之間**嘅間隔
        （`[1] 26/04/2026 | 日數: 20` = 06/04→26/04 隔 20 日），唔係距今日數。
        錯咗一整格。連 `health_readout` 都自我矛盾——同兩行印住「上次出賽：
        2026年4月26日 / 距今：20日」。實測 3,438 個 runner 有 66.5% 個值係錯，
        但賽季中間錯得細（中位 +3 日，因為連續出賽嘅馬「上仗前間隔」≈「距今」）；
        季初／休賽後就錯得大：2026-09-06 一日中位 +41 日（嘉應高昇 20 vs 133），
        觸發 `days_gt_75_pen` 嘅馬由 2 匹變 28 匹（117 匹之中）。

        生成器已修，但 264 個歷史 Logic 仍然帶住舊值，所以引擎自己重算：
        `race_analysis.race_date`（live 由 skeleton 寫入，replay 由
        `rescore_backtest.resolve_meeting_context` 注入）減 recent_6_detail
        第1仗日期。兩邊有一邊缺就退回舊欄位，唔靜靜當 0。
        """
        as_of = str((self.race_context or {}).get("race_date") or "").strip()
        last = self._last_race_iso()
        if as_of and last:
            try:
                delta = (_dt.date.fromisoformat(as_of) - _dt.date.fromisoformat(last)).days
            except ValueError:
                delta = None
            if delta is not None and delta >= 0:
                return float(delta)
        return parse_float(self._value("days_since_last") or self.horse_data.get("days_since_last"))

    def _official_injury_records(self):
        records = self.data.get("official_injury_records") if isinstance(self.data, dict) else None
        return [r for r in records if isinstance(r, dict)] if isinstance(records, list) else []

    def _official_medical_records(self):
        """官方傷患記錄減去淨「表現」覆檢（表現令人失望／難以接受等）。"""
        return [r for r in self._official_injury_records() if not r.get("performance_only")]

    def _parse_recent_runs(self, detail):
        runs = []
        for rank_text, margin_text in re.findall(r":\s*(\d+)名\s+([^|,]+)", str(detail or "")):
            try:
                rank = int(rank_text)
            except ValueError:
                continue
            runs.append(
                {
                    "rank": rank,
                    "margin": self._margin_to_float(margin_text.strip()),
                }
            )
        return runs

    def _margin_to_float(self, value):
        text = str(value or "").strip()
        if not text or text in {"-", "--", "N/A"}:
            return None
        if "平頭馬" in text:
            return 0.0
        if "短馬頭位" in text:
            return 0.05
        if "頭位" in text:
            return 0.1
        if "頸位" in text:
            return 0.25
        if "多個馬位" in text:
            return 8.0

        total = 0.0
        matched = False
        for part in text.split("-"):
            part = part.strip()
            if not part:
                continue
            if "/" in part:
                numerator, denominator = part.split("/", 1)
                try:
                    total += float(numerator) / float(denominator)
                    matched = True
                except ValueError:
                    continue
                continue
            try:
                total += float(part)
                matched = True
            except ValueError:
                continue
        if matched:
            return total
        return None

    def _has_recovery_evidence(self):
        finishes = [int(item) for item in re.findall(r"\b\d+\b", str(self.horse_data.get("last_6_finishes") or ""))[:3]]
        if any(1 <= rank <= 3 for rank in finishes):
            return True
        finish_time_level = self._text("finish_time_adj_level")
        if "仍具競爭力" in finish_time_level or "持續快於標準" in finish_time_level:
            return True
        raw_l400 = parse_float(self._value("raw_l400"))
        return raw_l400 is not None and raw_l400 <= 23.4

    def _weight_trend_span(self, weight_trend):
        match = re.search(r"波幅(\d+(?:\.\d+)?)lb", str(weight_trend or ""))
        if match:
            return float(match.group(1))
        return None

    def _is_jockey_changed(self):
        current_jockey = self._clean(self.horse_data.get("jockey", "") or self._current_declared_jockey())
        rows = self._recent_jockey_history_rows()
        if not current_jockey or not rows:
            return None
        latest = rows[0].get("jockey", "")
        return bool(latest and latest != current_jockey)

    def _formline_summary(self):
        """Concrete 賽績線: every past opponent IN `formline_table` — my finish +
        margin that day, whether the opponent went on to win (form validation)
        and at what class move. Opponents also in today's field are flagged
        同場對手.

        ⚠️ 呢個 docstring 一直寫住「EVERY notable past opponent」，但實際上係
        少於四成。`create_hkjc_logic_skeleton.parse_formline_table` 用
        `int(cols[1])` 做「係唔係數據行」嘅測試，而個表每場只有第一個對手嗰行
        帶 `#`，所以亞軍／季軍嘅續行全部被丟掉 —— 實測 37,265 條對手行只有
        14,580 條（39.1%）入到 Logic。2026-09-06 R3 嘉應高昇 11 條剩 5 條，
        而丟掉嗰批正正係兩隻 ✅✅ 超強組。已修（2026-09-04）；歷史 Logic 仍然
        帶住殘缺嘅表，要重建先補得返。"""
        table = self._value("formline_table")
        if not isinstance(table, list) or not table:
            return None

        def fin(row):
            m = re.match(r"\s*(\d+)", str(row.get("my_finish", "")))
            return int(m.group(1)) if m else 99

        def margin_behind(row):
            """今馬當日負幾多個馬位（正值=落後咁多；贏/領放=0）。
            my_finish 例：'13 (-11-3/4)'→11.75；'5 (-3/4)'→0.75；'1 (...)'→0。"""
            raw = str(row.get("my_finish", ""))
            mm = re.search(r"\(\s*(-?)\s*([\d\-/]+)", raw)
            if not mm:
                return None
            behind = mm.group(1) == "-"
            if not behind:
                return 0.0  # 贏或領放，唔算落後
            tok = mm.group(2)

            def _frac(s):
                if "/" in s:
                    a, b = s.split("/")
                    try:
                        return float(a) / float(b)
                    except (ValueError, ZeroDivisionError):
                        return 0.0
                try:
                    return float(s)
                except ValueError:
                    return 0.0
            parts = tok.split("-")  # '11-3/4' → ['11','3/4']；'3/4' → ['3/4']
            return sum(_frac(p) for p in parts if p)

        def opp_name(row):
            return re.sub(r"^\[\d+\]\s*", "", str(row.get("opponents", "")).split("(")[0]).strip()

        def opp_wins(row):
            m = re.search(r":\s*(\d+)\s*勝", str(row.get("next_performance", "")))
            return int(m.group(1)) if m else 0

        def best_class_rank(text):
            ranks = [self._class_num(tok) for tok in re.split(r"[ /、,]+", str(text or "")) if tok]
            ranks = [r for r in ranks if r is not None]
            return min(ranks) if ranks else None

        today_rank = self._class_num(self.race_context.get("race_class"))
        field = set(self.race_context.get("field_horse_names") or [])
        mine = self.horse_data.get("horse_name")

        opponents = []
        for r in table:
            nm = opp_name(r)
            if not nm:
                continue
            orank = best_class_rank(r.get("next_class"))
            move = ""
            if today_rank is not None and orank is not None:
                move = "升班" if orank < today_rank else ("降班" if orank > today_rank else "同班")
            opp_text = str(r.get("opponents", ""))
            om = re.search(r"\[(\d+)\]", opp_text)
            my_fin = fin(r)
            mgn = margin_behind(r)
            # 「跑得埋堆」先算數：今馬當日 ≤6 名 且 落後 ≤5 個馬位（貼近頭三名）。
            # 跑第13、負11-3/4＝根本冇同對手交手，唔當賽績線驗證（用戶反映）。
            competitive = (my_fin <= 6) and (mgn is None or mgn <= 5.0)
            opponents.append({
                "name": nm,
                "my_fin": my_fin,
                "my_margin": mgn,
                "competitive": competitive,
                "my_finish_raw": str(r.get("my_finish", "")).strip(),
                "wins": opp_wins(r),
                "next_class": str(r.get("next_class", "")).strip(),
                "move": move,
                "is_field": any(f and f != mine and f in opp_text for f in field),
                "opp_fin": (1 if "頭馬" in opp_text else (int(om.group(1)) if om else None)),
                "date": str(r.get("date", "")).strip(),
            })
        # 只計「今馬當日跑得埋堆」而對手其後又贏嘅場次先算已驗證。
        validated = sum(1 for o in opponents if o["wins"] >= 1 and o["competitive"])
        return {"opponents": opponents, "validated": validated, "n": len(table)}

    def _prep_score(self):
        # 初出馬穩定性用嘅備戰分都係晨操；晨操退出排名就一齊中性（EXP-20261029-02）
        if scoring.TRACKWORK_SCORING != "on":
            return 60.0
        digest = self._value("trackwork_digest")
        numbers = re.findall(r"備戰分(\d+(?:\.\d+)?)", str(digest or ""))
        return float(numbers[-1]) if numbers else 60.0

    def _current_jockey_horse_record(self):
        current_jockey = self._clean(self.horse_data.get("jockey", "") or self._current_declared_jockey())
        # SCORING uses the RECENCY window (current jockey's rides within the
        # horse's most recent races, i.e. the 近6場 history table) rather than the
        # full-career combo table. Point-in-time backtest over 16.8k runners shows
        # recency is the stronger predictor (corr 0.129 vs full-career 0.124;
        # strong-bucket top3 38.1% vs 36.4%). The full table is DISPLAY only.
        recent = self._recent_jockey_horse_record(current_jockey)
        if recent is not None:
            return recent
        if self._recent_jockey_history_rows():
            # Recency table present but current jockey absent → no recent signal.
            return None
        # Legacy fallback: no 近6場 table → use full combo table row.
        for row in self._jockey_combo_rows():
            if row["is_current"] or row["jockey"] == current_jockey:
                return {
                    "starts": row["starts"],
                    "wins": row["wins"],
                    "places": row["places"],
                    "avg_finish": row["avg_finish"],
                    "win_rate": row["win_rate"],
                    "place_rate": row["place_rate"],
                }
        return None

    def _recent_jockey_horse_record(self, current_jockey):
        """Current jockey's record over the horse's recent races (近6場 table).

        Returns None when no recency table exists (caller decides fallback) or
        when the current jockey has no completed run in that window.
        """
        rows = self._recent_jockey_history_rows()
        if not rows:
            return None
        finishes = []
        for row in rows:
            if self._clean(row["jockey"]) != current_jockey:
                continue
            match = re.search(r"\d+", str(row["finish"]))
            if not match:
                continue
            value = int(match.group(0))
            if value > 0:
                finishes.append(value)
        if not finishes:
            return None
        starts = len(finishes)
        wins = sum(1 for f in finishes if f == 1)
        shows = sum(1 for f in finishes if f <= 3)
        places = sum(1 for f in finishes if f <= 2)
        return {
            "starts": float(starts),
            "wins": float(wins),
            "places": float(places),
            "avg_finish": round(sum(finishes) / starts, 1),
            "win_rate": round(wins / starts * 100, 1),
            "place_rate": round(shows / starts * 100, 1),
        }

    def _current_declared_jockey(self):
        block = str(self._value("jockey_combo_block") or "")
        match = re.search(r"今場騎師:\s*([^\n]+)", block)
        return match.group(1).strip() if match else ""

    def _jockey_combo_rows(self):
        block = str(self._value("jockey_combo_block") or "")
        rows = []
        for line in block.splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            cols = [col.strip() for col in re.split(r"\s*\|\s*", line.strip().strip("|"))]
            if len(cols) < 8:
                continue
            if cols[0] in {"騎師", "------", "#", "---"}:
                continue
            if cols[0].startswith("#") or cols[0].isdigit():
                continue
            jockey_col = cols[0]
            is_current = "← 今場" in jockey_col
            jockey_name = jockey_col.replace("← 今場", "").strip()
            try:
                rows.append(
                    {
                        "jockey": jockey_name,
                        "starts": float(cols[1]),
                        "wins": float(cols[2]),
                        "places": float(cols[4]),
                        "avg_finish": float(cols[5]),
                        "win_rate": float(re.search(r"-?\d+(?:\.\d+)?", cols[6]).group(0)),
                        "place_rate": float(re.search(r"-?\d+(?:\.\d+)?", cols[7]).group(0)),
                        "is_current": is_current,
                    }
                )
            except (AttributeError, ValueError):
                continue
        return rows

    def _recent_jockey_history_rows(self):
        block = str(self._value("jockey_combo_block") or "")
        rows = []
        for line in block.splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            cols = [col.strip() for col in re.split(r"\s*\|\s*", line.strip().strip("|"))]
            if len(cols) < 5:
                continue
            if cols[0] in {"#", "---"} or cols[0].startswith("---"):
                continue
            if not re.fullmatch(r"\d+", cols[0]):
                continue
            rows.append(
                {
                    "index": int(cols[0]),
                    "date": cols[1],
                    "jockey": cols[2],
                    "finish": cols[3],
                    "note": cols[4],
                }
            )
        rows.sort(key=lambda row: row["index"])
        return rows

    def _best_jockey_for_horse(self, exclude=None):
        exclude = set(exclude or ())
        rows = [row for row in self._jockey_combo_rows() if row["jockey"] not in exclude]
        if not rows:
            return None
        return sorted(
            rows,
            key=lambda row: (
                row["wins"],
                row["places"],
                row["place_rate"],
                row["win_rate"],
                -row["avg_finish"],
                row["starts"],
            ),
            reverse=True,
        )[0]

    def _jockey_trainer_prior(self):
        priors = self._value("jockey_trainer_combo_prior")
        if not isinstance(priors, dict):
            return None
        # Old orchestrators embedded this aggregate into Logic and some 2026-04/05
        # archives were rewritten after the races (same-day and future results).
        # Only a live card may trust it; replays use the guarded prior stack.
        as_of_date = (self.race_context or {}).get("race_date")
        if not temporal_source_is_safe(EMBEDDED_LOGIC_PRIOR, as_of_date):
            return None
        return priors

    def _source_for(self, name):
        return {
            "jockey_score": "jockey",
            "trainer_score": "trainer",
            "draw_score": "barrier",
            "form_score": "last_6_finishes",
            "speed_score": "race_sectional_context",
        }.get(name, "missing_neutral")

    def _value(self, key):
        if key in self.horse_data and self.horse_data.get(key) not in (None, ""):
            return self.horse_data.get(key)
        return self.data.get(key)

    def _text(self, *keys):
        return " ".join(str(self._value(key) or "") for key in keys)

    def _is_debut(self):
        return bool(self.horse_data.get("is_debut") or self.horse_data.get("debut_runner") or self.horse_data.get("career_tag") == "DEBUT")

    def _is_sha_tin_context(self):
        value = self.race_context.get("venue") or self.race_context.get("course") or self.race_context.get("racecourse") or ""
        text = str(value)
        return text in {"ST", "Sha Tin", "ShaTin", "沙田"} or "沙田" in text or "ShaTin" in text or "Sha Tin" in text

    def _is_sha_tin_turf_context(self):
        if not self._is_sha_tin_context():
            return False
        surface = " ".join(
            str(self.race_context.get(key) or "")
            for key in ("venue", "course", "track", "surface", "track_type")
        ).upper()
        return not any(token in surface for token in ("AWT", "ALL WEATHER", "全天候", "泥地"))

    def _clean(self, value):
        text = str(value or "").strip()
        return "資料未完成，中性處理" if "[FILL" in text.upper() else text

    def _season_record(self):
        return parse_record(self.horse_data.get("season_stats") or self._value("season_stats_line"))

    def _same_distance_record(self):
        """同程 (冠-亞-季-其餘) —— starts 係四項總和，唔係第四項（見 parse_record）。"""
        text = self._clean(self.horse_data.get("season_stats") or self._value("season_stats_line") or "")
        match = re.search(r"同程\s*\((\d+)-(\d+)-(\d+)-(\d+)\)", text)
        if not match:
            return None
        wins, seconds, thirds, rest = (int(part) for part in match.groups())
        return {
            "wins": wins,
            "seconds": seconds,
            "thirds": thirds,
            "starts": wins + seconds + thirds + rest,
            "places": wins + seconds + thirds,
        }

    def _formline_strength_signal(self):
        text = self._clean(self._value("formline_strength") or "")
        if "極強" in text:
            return "elite"
        if "強" in text:
            return "strong"
        if "弱" in text:
            return "weak"
        if text and text != "N/A":
            return "neutral"
        return "unknown"

    _MARGIN_FRACTIONS = {"1/2": 0.5, "1/4": 0.25, "3/4": 0.75, "1/8": 0.125,
                         "3/8": 0.375, "5/8": 0.625, "7/8": 0.875}

    def _parse_margin_length(self, text):
        """「4-1/4」「3/4」「2」→ 馬位。「-」「N/A」→ None。"""
        raw = str(text or "").strip()
        m = re.match(r"^(\d+)?\s*-?\s*(\d/\d)?$", raw)
        if not m or (m.group(1) is None and m.group(2) is None):
            return None
        whole = float(m.group(1)) if m.group(1) else 0.0
        return whole + self._MARGIN_FRACTIONS.get(m.group(2) or "", 0.0)

    def _margin_trend_signal(self):
        text = self._clean(self._margin_trend_display() or self._value("margin_trend") or "")
        # 「連勝中」係 scrape_hkjc_horse_profile.compute_margin_trend 帶符號化之後
        # 新增嘅標籤（贏馬個「頭馬距離」係贏幅，唔係落後距離）。冇呢一支嘅話，
        # 六戰六勝會落去 flat，而舊 code 更加會當成「擴大中」扣分。
        if "連勝" in text:
            return "improving"
        if "收窄中" in text:
            return "improving"
        if "擴大中" in text:
            return "worsening"
        return "flat"

    def _recent_finish_list(self):
        form = str(self.horse_data.get("last_6_finishes") or "")
        return [int(item) for item in re.findall(r"\b\d+\b", form)[:6]]

    def _trackwork_markers(self):
        digest = self._clean(self._value("trackwork_digest") or "")
        classification = ""
        trend = ""
        positive = ""
        risk = ""
        if digest:
            classification_match = re.search(r"分類為「([^」]+)」", digest)
            trend_match = re.search(r"操練趨勢([^。；]+)", digest)
            positive_match = re.search(r"正面訊號：([^；。]+)", digest)
            risk_match = re.search(r"風險訊號：([^；。]+)", digest)
            classification = classification_match.group(1) if classification_match else ""
            trend = f"操練趨勢{trend_match.group(1)}" if trend_match else ""
            positive = positive_match.group(1).strip() if positive_match else ""
            risk = risk_match.group(1).strip() if risk_match else ""
        return {
            "classification": classification,
            "trend": trend,
            "positive": positive,
            "risk": risk,
        }
