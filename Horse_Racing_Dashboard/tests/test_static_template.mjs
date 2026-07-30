import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";


const EMPTY_DASHBOARD_DATA = {
  meetings: [],
  races: {},
  consensus: {},
  roi: {},
};

function loadTemplateFunctions(dashboardData = EMPTY_DASHBOARD_DATA) {
  let html = fs.readFileSync(new URL("../static_template.html", import.meta.url), "utf8");
  html = html.replace('"__DATA_PLACEHOLDER__"', JSON.stringify(dashboardData));
  const scriptMatch = html.match(/<script>\s*([\s\S]*?)<\/script>/);
  assert.ok(scriptMatch, "static template script should exist");

  const storage = new Map();
  const storageApi = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: (key) => storage.delete(key),
  };
  const context = vm.createContext({
    AbortSignal,
    Date,
    Headers,
    JSON,
    Map,
    Math,
    Number,
    Object,
    Promise,
    Set,
    String,
    URL,
    clearInterval: () => {},
    clearTimeout: () => {},
    console,
    document: {
      activeElement: null,
      addEventListener: () => {},
      getElementById: () => null,
      querySelectorAll: () => [],
    },
    fetch: async () => new Response("{}", { status: 200 }),
    localStorage: storageApi,
    sessionStorage: storageApi,
    setInterval: () => 1,
    setTimeout: () => 1,
    window: {
      addEventListener: () => {},
      location: { protocol: "https:" },
      prompt: () => null,
      scrollTo: () => {},
    },
  });
  const source = `${scriptMatch[1]}
    globalThis.__dashboardTest = {
      calcProfit,
      mergeBetStateMaps,
      renderSilk: typeof renderSilk === "function" ? renderSilk : null,
      hkjcHorseProfileUrl,
      getRaceBettingCandidates,
      renderSingleAnalystView,
      renderBetCard,
      renderMobileRoiRecord,
      renderDesktopRoiHorse,
      defaultExpandedBetRaces,
      renderDashboard,
      setSelectedMeetingForTest: (meeting) => { selectedMeeting = meeting; },
      setRoiLedgerForTest: (records) => { roiLedger = records; },
      setRoiRegionForTest: (region) => { roiRegionFilter = region; },
      setLocalStorageForTest: (key, value) => { localStorage.setItem(key, JSON.stringify(value)); },
      getFilteredROI,
      renderHorseCard,
      buildHorseAnalysisSections,
      parseChronologySeries,
      renderChronologySeries,
      formatRichSection,
      renderDataReadoutItem,
      sanitizeBattlefieldOverviewText,
      renderBattlefieldOverview,
      renderSportsWorkspace: typeof renderSportsWorkspace === "function" ? renderSportsWorkspace : null,
      renderHistoryCard: typeof renderHistoryCard === "function" ? renderHistoryCard : null,
      renderInlineBetDraft: typeof renderInlineBetDraft === "function" ? renderInlineBetDraft : null,
      calculateSportsRoi: typeof calculateSportsRoi === "function" ? calculateSportsRoi : null,
      setSportsLedgerForTest: (records) => { sportsBetLedger = records; },
      setSportsTabForTest: (tab) => { activeSportsTab = tab; },
      getInitialSportFromUrl: typeof getInitialSportFromUrl === "function" ? getInitialSportFromUrl : null,
      sportsBetDraftFromSource: typeof sportsBetDraftFromSource === "function" ? sportsBetDraftFromSource : null,
      setLocationSearchForTest: (search) => { window.location.search = search; },
      isNewerSnapshot: typeof isNewerSnapshot === "function" ? isNewerSnapshot : null,
      formatSnapshotStamp: typeof formatSnapshotStamp === "function" ? formatSnapshotStamp : null,
    };
  `;
  vm.runInContext(source, context);
  return context.__dashboardTest;
}

test("raw template explains that a generated dashboard must be opened", () => {
  const html = fs.readFileSync(new URL("../static_template.html", import.meta.url), "utf8");
  assert.match(html, /呢個係 Dashboard 原始模板/);
  assert.match(html, /Open Dashboard\.html/);
});

test("template ships the head tags iOS needs to install it as a standalone app", () => {
  const html = fs.readFileSync(new URL("../static_template.html", import.meta.url), "utf8");
  // Without viewport-fit=cover every env(safe-area-inset-*) below resolves to 0
  // and the fixed bottom bars sit under the iPhone home indicator.
  assert.match(html, /<meta name="viewport" content="[^"]*viewport-fit=cover/);
  assert.match(html, /<link rel="manifest" href="manifest\.webmanifest">/);
  assert.match(html, /<meta name="apple-mobile-web-app-capable" content="yes">/);
  assert.match(html, /<link rel="apple-touch-icon" href="icon-180\.png">/);
  assert.match(html, /<meta name="theme-color" content="#1E40AF">/);
  // Relative, not root-absolute: the same HTML is opened off disk as
  // "Open Dashboard.html", where a leading "/" would break.
  assert.doesNotMatch(html, /href="\/(?:manifest\.webmanifest|icon-\d+\.png)"/);
  // file:// has no service worker; registering there throws.
  assert.match(html, /navigator\.serviceWorker && window\.location\.protocol !== 'file:'/);
  // viewport-fit=cover also extends the viewport up behind the status bar, so the
  // header must pay the top inset or the title sits under the Dynamic Island.
  assert.match(html, /\.app-header \{ padding-top: calc\(var\(--space-m\) \+ env\(safe-area-inset-top\)\); \}/);
  assert.match(html, /\.app-header \{ flex-wrap:wrap; justify-content:space-between;[^}]*env\(safe-area-inset-top\)/);
});

test("mobile bottom tab bar carries every sport and stacks above the betting bar", () => {
  const html = fs.readFileSync(new URL("../static_template.html", import.meta.url), "utf8");
  for (const sport of ["horses", "nba", "tennis", "portfolio"]) {
    assert.match(html, new RegExp(`id="tabbar-${sport}"[^>]*onclick="showSport\\('${sport}'\\)"`));
  }
  // render() has to drive both navs off the same active sport.
  assert.match(html, /const tab = document\.getElementById\(`tabbar-\$\{sport\}`\);/);
  assert.match(html, /aria-current/);
  // The tab bar owns the bottom edge; the betting bar and back-to-top stack off
  // --tabbar-total so nothing overlaps the tab bar or the home indicator.
  assert.match(html, /:root \{ --tabbar-h: 0px; --tabbar-total: 0px; \}/);
  assert.match(html, /--tabbar-total: calc\(64px \+ env\(safe-area-inset-bottom\)\)/);
  assert.match(html, /\.bp-bar--fixed \{ position: fixed; bottom: var\(--tabbar-total\)/);
  assert.match(html, /\.app-main \{ padding-bottom: calc\(92px \+ var\(--tabbar-total\)\); \}/);
  assert.match(html, /\.back-to-top \{ bottom: calc\(72px \+ var\(--tabbar-total\)\)/);
  // Desktop keeps the header switcher; mobile swaps it for the tab bar so the
  // two never both show.
  assert.match(html, /\.app-bottom-nav \{ display: none; \}/);
  assert.match(html, /\.sport-switcher \{ display: none; \}/);
});

test("snapshot staleness only prompts for a strictly newer build", () => {
  const { isNewerSnapshot } = loadTemplateFunctions();
  const loaded = "2026-07-30T22:45:21";
  assert.equal(isNewerSnapshot("2026-07-31T09:12:00", loaded), true);
  // Equal must not prompt — that is the normal steady state on every foreground.
  assert.equal(isNewerSnapshot(loaded, loaded), false);
  // Older must not prompt: a stale Cloudflare edge copy would otherwise send the
  // user into a reload that brings back the very snapshot they already have.
  assert.equal(isNewerSnapshot("2026-07-29T08:00:00", loaded), false);
  for (const junk of [undefined, null, 42, {}, []]) {
    assert.equal(isNewerSnapshot(junk, loaded), false);
    assert.equal(isNewerSnapshot("2026-07-31T09:12:00", junk), false);
  }
});

test("snapshot stamp is string-sliced so a timezone-less build time never shifts", () => {
  const { formatSnapshotStamp } = loadTemplateFunctions();
  assert.equal(formatSnapshotStamp("2026-07-30T22:45:21"), "07-30 22:45");
  // 22:45 must stay 22:45 — parsing this as a Date would re-interpret it as UTC
  // and slide the displayed time by the local offset.
  assert.match(formatSnapshotStamp("2026-01-01T00:30:00"), /^01-01 00:30$/);
  for (const junk of ["", "not-a-date", undefined, null]) {
    assert.equal(formatSnapshotStamp(junk), "—");
  }
});

test("standalone mode has a reload path and a new-analysis notice", () => {
  const html = fs.readFileSync(new URL("../static_template.html", import.meta.url), "utf8");
  // Installed as a PWA there is no address bar, so the only way out of a stale
  // snapshot is an in-page control.
  assert.match(html, /id="snapshot-refresh"[^>]*onclick="reloadSnapshot\(\)"/);
  assert.match(html, /id="snapshot-stamp"/);
  assert.match(html, /id="update-pill"[^>]*hidden/);
  assert.match(html, /onclick="dismissUpdatePill\(\)"/);
  // 369-byte manifest, not the 1.3MB snapshot.
  assert.match(html, /'deploy-manifest\.json'/);
  assert.match(html, /fetch\(SNAPSHOT_MANIFEST_URL, \{ cache: 'no-store' \}\)/);
  // iOS resumes a suspended PWA without re-navigating; this is the only hook
  // that catches "backgrounded since yesterday".
  assert.match(html, /document\.addEventListener\('visibilitychange'/);
  assert.match(html, /document\.visibilityState === 'visible'\) checkForNewSnapshot\(\)/);
  // Dismissing one notice must not suppress the next deploy's notice.
  assert.match(html, /updatePillDismissedFor === remoteGeneratedAt/);
  // The pill has to clear the betting bar on mobile, not cover 匯入投注記錄.
  assert.match(html, /\.update-pill \{ bottom: calc\(100px \+ var\(--tabbar-total\)\)/);
});

test("pwa bundle has a standalone manifest and a service worker that never caches /api", () => {
  const manifest = JSON.parse(
    fs.readFileSync(new URL("../pwa/manifest.webmanifest", import.meta.url), "utf8"),
  );
  assert.equal(manifest.display, "standalone");
  assert.equal(manifest.start_url, "./");
  assert.equal(manifest.theme_color, "#1E40AF");
  assert.ok(
    manifest.icons.some((icon) => icon.sizes === "512x512" && icon.purpose === "maskable"),
    "needs a maskable 512 icon for Android adaptive masks",
  );
  for (const icon of manifest.icons) {
    assert.ok(
      fs.existsSync(new URL(`../pwa/${icon.src}`, import.meta.url)),
      `manifest references a missing icon: ${icon.src}`,
    );
  }

  const sw = fs.readFileSync(new URL("../pwa/sw.js", import.meta.url), "utf8");
  // Serving a cached /api response would silently show wrong money.
  assert.match(sw, /url\.pathname\.startsWith\("\/api\/"\)\) return;/);
  // Navigations must be network-first so a deploy is picked up immediately.
  assert.match(sw, /request\.mode === "navigate"/);
  assert.match(sw, /self\.clients\.claim\(\)/);
});

test("dashboard overview keeps an eleven-race meeting in the dense desktop layout", () => {
  const meeting = { date: "2026-07-15", venue: "HappyValley", region: "hkjc", analysts: ["Kelvin"] };
  const races = Array.from({ length: 11 }, (_, index) => ({
    race_number: index + 1,
    distance: `${1200 + index * 100}m`,
    race_class: `第${index + 1}班`,
    horses_count: 12,
  }));
  const dashboardData = {
    meetings: [meeting],
    races: {
      "2026-07-15|HappyValley": {
        meeting,
        races_by_analyst: { Kelvin: races },
      },
    },
    consensus: {},
    roi: {},
  };
  const { renderDashboard, setSelectedMeetingForTest } = loadTemplateFunctions(dashboardData);

  setSelectedMeetingForTest(meeting);
  const html = renderDashboard();

  assert.match(html, /meeting-card--hkjc/);
  assert.match(html, /meeting-card__flag" aria-hidden="true">🇭🇰/);
  assert.match(html, /meeting-card__country">Hong Kong/);
  assert.doesNotMatch(html, /meeting-card__region-code/);
  assert.doesNotMatch(html, /meeting-card__region-name/);
  assert.match(html, /meeting-card__venue">Happy Valley/);
  assert.match(html, /<span>11 場<\/span>/);
  assert.doesNotMatch(html, /meeting-card__analysts/);
  assert.doesNotMatch(html, />Kelvin</);
  assert.match(html, /race-overview-header/);
  assert.match(html, /全部 11 場 · 點擊查看詳細分析/);
  assert.match(html, /race-board race-board--eleven/);
  assert.equal((html.match(/race-tile__runner-count/g) || []).length, 11);
  assert.equal((html.match(/race-tile__cta/g) || []).length, 11);
});

test("battlefield overview removes auto-position summary and trims ranking columns", () => {
  const { sanitizeBattlefieldOverviewText, renderBattlefieldOverview } = loadTemplateFunctions();
  const source = `[第一部分] 🗺️ 戰場全景

| 項目 | 內容 |
|:---|:---|
| 賽事格局 | 第四班 / 1200mm / HKJC |
| **賽事類型** | **\`[HKJC Wong Choi Auto Python 7D]\`** |
| 天氣 / 場地 | 好地 |
| 分析邊界 | 不使用即市資料 |

**📍 Auto 走位與檔位摘要（不含節奏預測）:**
- 場次: 第 4 場
- 出馬數: 12
- 檔位分較高: 3 匹馬
- 資料完整度較高: 3 匹馬
- Consistency Shadow: 未啟用

**📊 全場綜合戰力排名**

| 排名 | 馬號 | 馬名 | 綜合戰力分 | Grade | 資料完整度 | 風險分 | 情境標記 |
|---:|---:|---|---:|---|---:|---:|---|
| 1 | 5 | 日馳千里 | 67.8 | B- | 83.0 | 67.0 | 模型首選 |
| 2 | 7 | 升升雙息 | 67.8 | B- | 83.0 | 70.0 |  |`;

  const sanitized = sanitizeBattlefieldOverviewText(source);
  const html = renderBattlefieldOverview(source, [{
    horse_number: 5,
    horse_name: "日馳千里",
    horse_name_en: "GIANT LEAP",
    silk_url: "https://example.test/silks/5.png",
  }]);

  assert.doesNotMatch(sanitized, /Auto 走位與檔位摘要|檔位分較高|資料完整度較高|Consistency Shadow/);
  assert.doesNotMatch(html, /賽事類型|天氣 \/ 場地|分析邊界|資料完整度|風險分|情境標記/);
  assert.doesNotMatch(html, /\*\*|1200mm/);
  assert.match(html, /battlefield__race-pattern/);
  assert.match(html, /班次[\s\S]*第四班/);
  assert.match(html, /路程[\s\S]*1200m/);
  assert.match(html, /賽區[\s\S]*香港/);
  assert.match(html, /battlefield-ranking__score/);
  assert.match(html, /日馳千里/);
  assert.match(html, /GIANT LEAP/);
  assert.match(html, /https:\/\/example\.test\/silks\/5\.png/);
  assert.equal((html.match(/<th>/g) || []).length, 5);
});

test("race detail removes duplicate Top Picks panels", () => {
  const template = fs.readFileSync(new URL("../static_template.html", import.meta.url), "utf8");
  const reactPage = fs.readFileSync(new URL("../frontend/src/pages/RaceDetailPage.jsx", import.meta.url), "utf8");
  assert.doesNotMatch(template, /🏆 Top Picks|Top Picks 對比|暫無 Top Picks/);
  assert.doesNotMatch(reactPage, /🏆 Top Picks|Top Picks 對比|暫無 Top Picks/);
});

test("long horse analysis shows every data row and every expanded section", () => {
  const { renderHorseCard, buildHorseAnalysisSections } = loadTemplateFunctions();
  const dataReadout = [
    { band: "➖", label: "評分走勢", value: "38分", trend: "降班", reason: "長理由一" },
    { band: "✅", label: "段速表現", value: "優勢", trend: "+3.0", reason: "長理由二" },
    { band: "➖", label: "休養", value: "21日", trend: "正常", reason: "長理由三" },
    { band: "➖", label: "檔位", value: "4檔", trend: "合適", reason: "長理由四" },
    { band: "➖", label: "路程", value: "1650m", trend: "合適", reason: "長理由五" },
    { band: "⚠️", label: "配備變動", value: "除眼罩", trend: "留意", reason: "長理由六" },
  ];
  const horse = {
    horse_number: 4,
    horse_name: "多利神駒",
    horse_name_en: "OUR LUCKY GLORY",
    silk_url: "https://example.test/G292.gif",
    final_grade: "B-",
    data_readout: dataReadout,
    raw_text: "## 核心分析\n步速合適。\n## 風險\n配備有變。\n## 結論\n值得留意。\n## 數據判讀\n重複數據內容。\n## 評級矩陣\n第一段評級。\n##### 細節標題\n細節內容。\n## 評級矩陣\n第二段評級。",
  };

  const sections = buildHorseAnalysisSections(horse);
  assert.equal(sections[0].title, "結論");
  assert.equal(sections.length, 4);
  assert.equal(sections.filter((section) => section.title === "評級矩陣").length, 1);
  assert.equal(sections.filter((section) => section.title === "數據判讀").length, 0);
  assert.match(sections.find((section) => section.title === "評級矩陣").content, /第一段評級。[\s\S]*第二段評級。/);

  const html = renderHorseCard(horse, 1);
  assert.match(html, /data-readout--complete/);
  assert.equal((html.match(/data-readout__item/g) || []).length, 6);
  assert.doesNotMatch(html, /長理由六/);
  assert.equal((html.match(/data-readout__reason/g) || []).length, 5);
  assert.doesNotMatch(html, /data-readout__more|另有 \d+ 項/);
  assert.match(html, /horse-silk horse-silk--sm/);
  assert.match(html, /https:\/\/example\.test\/G292\.gif/);
  assert.match(html, /horse-card__expand-btn" aria-expanded="false"/);
  assert.match(html, /4 個章節/);
  assert.match(html, /analysis-document/);
  assert.match(html, /analysis-document__nav/);
  assert.match(html, /rich-heading rich-heading--5">細節標題/);
  assert.equal((html.match(/analysis-document__section analysis-document__section--/g) || []).length, 4);
  assert.match(html, /全部內容已展開 · 可用章節索引快速跳讀/);
  assert.doesNotMatch(html, /<details|analysis-topic|syncAnalysisAccordion|數據明細|重複數據內容/);
});

test("odd data readout item spans both desktop columns", () => {
  const css = fs.readFileSync(new URL("../frontend/src/index.css", import.meta.url), "utf8");
  assert.match(css, /\.data-readout__item:last-child:nth-child\(odd\)\s*\{\s*grid-column:\s*1 \/ -1;/);
});

test("data readout splits detail rows, labels trainer-jockey stats, and removes repeated equipment text", () => {
  const { renderHorseCard } = loadTemplateFunctions();
  const html = renderHorseCard({
    horse_number: 4,
    horse_name: "多利神駒",
    data_readout: [
      {
        band: "➖",
        label: "評分走勢",
        value: "今仗38分",
        trend: "降班",
        reason: "上仗第四班→今仗第五班；今仗38分、較上仗40分 -2；季初評分49；近三季最高63·最低40",
      },
      {
        band: "➖",
        label: "騎練組合",
        value: "巴度／蘇偉賢",
        trend: "中性",
        reason: "今仗換上巴度，惟與此馬 5仗0勝2上名、平均4.6名，拍檔31仗勝率6%、上名率26%",
      },
      {
        band: "⚠️",
        label: "配備變動",
        value: "戴上繫舌帶、開縫眼罩；除下--",
        trend: "配備有變",
        reason: "戴上繫舌帶、開縫眼罩；除下--",
      },
    ],
  });

  assert.match(html, /<span>季初評分49<\/span><span>近三季最高63·最低40<\/span>/);
  assert.match(html, /<span>騎練拍檔31仗勝率6%、上名率26%<\/span>/);
  assert.equal((html.match(/戴上繫舌帶、開縫眼罩/g) || []).length, 1);
  assert.doesNotMatch(html, /(?:戴上|除下)--/);
});

test("sectional and pace timelines display oldest to latest without changing the verdict", () => {
  const { parseChronologySeries, renderChronologySeries, formatRichSection, renderDataReadoutItem } = loadTemplateFunctions();
  const parsed = parseChronologySeries("23.39→22.86→24.83→23.55→22.82→22.56 → 趨勢: 衰退中 ⚠️");

  assert.deepEqual([...parsed.points], ["22.56", "22.82", "23.55", "24.83", "22.86", "23.39"]);
  assert.equal(parsed.trend, "衰退中 ⚠️");

  const l400 = renderChronologySeries("23.39→22.86→24.83→23.55→22.82→22.56 → 趨勢: 衰退中 ⚠️", "L400");
  assert.match(l400, /最舊 → 最新/);
  assert.ok(l400.indexOf("22.56s") < l400.indexOf("23.39s"));
  assert.match(l400, /較舊 3 仗平均[\s\S]*22\.98s/);
  assert.match(l400, /最新 3 仗平均[\s\S]*23\.69s/);
  assert.match(l400, /衰退中/);

  const pace = renderChronologySeries("+0.00s→+0.34s[偏快]→+1.74s[偏快]→+0.34s→+0.94s[偏快]→+0.64s", "步速修正");
  assert.ok(pace.indexOf("+0.64s") < pace.indexOf("+0.00s"));
  assert.match(pace, /最新 3 仗平均[\s\S]*\+0\.69s/);

  const rich = formatRichSection(`- **L400 / 能量趨勢:**
- 23.39
- 23.39→22.86→24.83→23.55→22.82→22.56 → 趨勢: 衰退中 ⚠️
- 97→91→79→95→93→92 → 趨勢: 下降 ⚠️
- **步速修正:**
- +0.00s→+0.34s[偏快]→+1.74s[偏快]→+0.34s→+0.94s[偏快]→+0.64s
- ➖ 步速修正後接近平均 (近 3 仗修正平均: +0.69s)`);
  assert.match(rich, /L400 與能量走勢/);
  assert.equal((rich.match(/class="chronology"/g) || []).length, 3);
  assert.match(rich, /chronology__verdict/);
  const firstTrack = rich.match(/chronology__track">([\s\S]*?)<\/div>/)?.[1] || '';
  assert.ok(firstTrack.indexOf("22.56s") < firstTrack.indexOf("23.39s"));

  const futureRich = formatRichSection(`- L400 走勢（最舊 → 最新）: 22.56 → 22.82 → 23.39 → 趨勢: 衰退中 ⚠️
- 步速修正偏差（最舊 → 最新）: +0.64s → +0.34s → +0.00s`);
  assert.equal((futureRich.match(/class="chronology"/g) || []).length, 2);
  assert.ok(futureRich.indexOf("22.56s") < futureRich.indexOf("23.39s"));

  const preview = renderDataReadoutItem({
    band: "⚠️",
    label: "段速趨勢",
    value: "23.39→22.56s",
    trend: "衰退中",
  });
  assert.match(preview, /最舊 22\.56s → 最新 23\.39s · 衰退中/);
});


test("newer local odds draft survives a stale cloud pull", () => {
  const { mergeBetStateMaps } = loadTemplateFunctions();
  const key = "bet|2026-07-15|HappyValley|1|3";

  const merged = mergeBetStateMaps(
    { [key]: { odds: 2, oddsConfirmed: false, updatedAt: 200 } },
    { [key]: { odds: null, oddsConfirmed: false, updatedAt: 100 } },
  );

  assert.equal(merged[key].odds, 2);
});


test("newer remote confirmed state wins record-by-record", () => {
  const { mergeBetStateMaps } = loadTemplateFunctions();
  const key = "bet|2026-07-15|HappyValley|1|3";

  const merged = mergeBetStateMaps(
    { [key]: { odds: 2, oddsConfirmed: false, updatedAt: 100 } },
    { [key]: { odds: 2, oddsConfirmed: true, updatedAt: 200 } },
  );

  assert.equal(merged[key].oddsConfirmed, true);
});


test("pending bet has no realised profit", () => {
  const { calcProfit } = loadTemplateFunctions();

  assert.equal(calcProfit({ confirmed: true, scratched: false, odds: 2, result: null }), null);
  assert.equal(calcProfit({ confirmed: true, scratched: false, odds: 2, result: 1 }), 1);
  assert.equal(calcProfit({ confirmed: true, scratched: false, odds: 2, result: 0 }), -1);
});


test("committed ROI result is not overwritten by stale pending local panel state", () => {
  const meeting = { date: "2026-07-15", venue: "HappyValley", region: "hkjc", analysts: ["Kelvin"] };
  const dashboardData = {
    meetings: [meeting],
    races: {
      "2026-07-15|HappyValley": {
        meeting,
        races_by_analyst: {
          Kelvin: [{
            race_number: 1,
            horses: [{ horse_number: 3, horse_name: "Test Horse" }],
          }],
        },
      },
    },
    consensus: {},
    roi: {
      bets: [{
        date: "2026-07-15",
        venue: "HappyValley",
        region: "hkjc",
        race_number: 1,
        horse_number: 3,
        horse_name: "Test Horse",
        stake: 1,
        odds: 2.5,
        result_position: 2,
        payout: 2.5,
        net_profit: 1.5,
        status: "won",
      }],
    },
  };
  const {
    getFilteredROI,
    setLocalStorageForTest,
    setRoiLedgerForTest,
  } = loadTemplateFunctions(dashboardData);
  const betKey = "bet|2026-07-15|HappyValley|1|3";
  setLocalStorageForTest("bets_2026-07-15_HappyValley", {
    [betKey]: {
      confirmed: true,
      scratched: false,
      odds: 2.5,
      result: null,
      updatedAt: 999,
    },
  });
  setRoiLedgerForTest([{
    ...dashboardData.roi.bets[0],
    _ledger_key: "2026-07-15|HappyValley|1|3",
  }]);

  const filtered = getFilteredROI();
  assert.equal(filtered.total_bets, 1);
  assert.equal(filtered.bets[0].status, "won");
  assert.equal(filtered.bets[0].result_position, 2);
  assert.equal(filtered.total_profit, 1.5);
});


test("ROI tombstone removes a matching pre-baked snapshot record", () => {
  const record = {
    date: "2026-07-15",
    venue: "HappyValley",
    region: "hkjc",
    race_number: 1,
    horse_number: 3,
    horse_name: "Test Horse",
    stake: 1,
    odds: 2.5,
    result_position: 2,
    payout: 2.5,
    net_profit: 1.5,
    status: "won",
  };
  const dashboardData = { meetings: [], races: {}, consensus: {}, roi: { bets: [record] } };
  const { getFilteredROI, setRoiLedgerForTest } = loadTemplateFunctions(dashboardData);
  setRoiLedgerForTest([{
    ...record,
    _ledger_key: "2026-07-15|HappyValley|1|3",
    _deleted: true,
  }]);

  const filtered = getFilteredROI();
  assert.equal(filtered.total_bets, 0);
});


test("pre-baked ROI records receive stable ledger keys for edit and delete actions", () => {
  const record = {
    date: "2026-07-15",
    venue: "HappyValley",
    region: "hkjc",
    race_number: 1,
    horse_number: 3,
    horse_name: "Snapshot Horse",
    stake: 1,
    odds: 2.5,
    result_position: null,
    payout: 0,
    net_profit: 0,
    status: "pending",
  };
  const dashboardData = { meetings: [], races: {}, consensus: {}, roi: { bets: [record] } };
  const { getFilteredROI } = loadTemplateFunctions(dashboardData);

  assert.equal(
    getFilteredROI().bets[0]._ledger_key,
    "2026-07-15|HappyValley|1|3",
  );
});


test("silk renderer is safe and only renders when a URL exists", () => {
  const { renderSilk } = loadTemplateFunctions();

  assert.equal(renderSilk({ horse_name: "No Silk" }), "");
  const html = renderSilk({
    horse_number: 1,
    horse_name: 'Test <Horse>',
    silk_url: 'https://racing.hkjc.com/racing/content/Images/RaceColor/K390.gif',
  }, "sm");
  assert.match(html, /horse-silk--sm/);
  assert.match(html, /K390\.gif/);
  assert.doesNotMatch(html, /Test <Horse>/);
});

test("HKJC horse profile link uses the official registration-year horse id", () => {
  const { hkjcHorseProfileUrl, renderHorseCard } = loadTemplateFunctions();
  assert.equal(
    hkjcHorseProfileUrl({ horse_code: "G292" }),
    "https://racing.hkjc.com/zh-hk/local/information/horse?horseid=HK_2021_G292",
  );
  assert.equal(
    hkjcHorseProfileUrl({ hkjc_horse_id: "HK_2024_K390", horse_code: "K390" }),
    "https://racing.hkjc.com/zh-hk/local/information/horse?horseid=HK_2024_K390",
  );
  assert.equal(
    hkjcHorseProfileUrl({ horse_code: "E114" }),
    "https://racing.hkjc.com/zh-hk/local/information/horse?horseid=HK_2020_E114",
  );
  assert.equal(
    hkjcHorseProfileUrl({
      horse_code: "J503",
      horse_profile_url: "https://racing.hkjc.com/zh-hk/local/information/horse?horseid=HK_2023_J503",
    }),
    "https://racing.hkjc.com/zh-hk/local/information/horse?horseid=HK_2023_J503",
  );
  assert.equal(hkjcHorseProfileUrl({ horse_name: "AU Runner" }), "");

  const hkHtml = renderHorseCard({ horse_number: 4, horse_name: "多利神駒", horse_code: "G292" });
  assert.match(hkHtml, /class="horse-card__official-link"/);
  assert.match(hkHtml, /horseid=HK_2021_G292/);
  assert.match(hkHtml, /target="_blank" rel="noopener noreferrer"/);
  assert.match(hkHtml, />官方馬匹資料 <span/);

  const matrixHtml = renderHorseCard({
    horse_number: 4,
    horse_name: "多利神駒",
    rating_matrix: { dimensions: [{ name: "段速表現", value: "✅", rationale: "優勢" }] },
  });
  assert.doesNotMatch(matrixHtml, /horse-card__section-title">📊 評級矩陣/);
  assert.doesNotMatch(matrixHtml, /✅ 段速表現/);

  const auHtml = renderHorseCard({ horse_number: 4, horse_name: "AU Runner" });
  assert.doesNotMatch(auHtml, /horse-card__official-link/);
});

test("both horse-card renderers keep the rating matrix out of the preview", () => {
  const reactSource = fs.readFileSync(
    new URL("../frontend/src/components/HorseCard.jsx", import.meta.url),
    "utf8",
  );
  const expandedStart = reactSource.indexOf("{expanded && hasAnalysis");
  const matrixRender = reactSource.indexOf("<RatingMatrixTable");

  assert.ok(expandedStart >= 0, "React horse card should have an expanded analysis boundary");
  assert.ok(matrixRender > expandedStart, "React rating matrix must only render after expansion");
});


test("HKJC silk reaches betting candidates and the ranked horse analysis", () => {
  const horse = {
    horse_number: 1,
    horse_name: "摘星聲升",
    horse_name_en: "EMERGING STAR",
    horse_code: "K390",
    silk_url: "https://racing.hkjc.com/racing/content/Images/RaceColor/K390.gif",
    jockey: "巴度",
    trainer: "蘇偉賢",
    final_grade: "A",
  };
  const meeting = { date: "2026-07-15", venue: "跑馬地", region: "hkjc", analysts: ["Kelvin", "Heison"] };
  const dashboardData = {
    meetings: [meeting],
    races: {
      "2026-07-15|跑馬地": {
        meeting,
        races_by_analyst: {
          Kelvin: [{ race_number: 1, horses: [horse], top_picks: [{ rank: 1, horse_number: 1, horse_name: horse.horse_name, grade: "A" }] }],
          Heison: [{ race_number: 1, horses: [horse], top_picks: [] }],
        },
      },
    },
    consensus: {
      "2026-07-15|跑馬地|1": {
        consensus: { consensus_horses: [{ horse_number: 1, horse_name: horse.horse_name, is_top2_consensus: true, kelvin_grade: "A", heison_grade: "A-" }] },
      },
    },
    roi: {},
  };
  const { getRaceBettingCandidates, renderSingleAnalystView, renderBetCard } = loadTemplateFunctions(dashboardData);

  const candidates = getRaceBettingCandidates(meeting, 1, true);
  assert.equal(candidates[0].silk_url, horse.silk_url);
  assert.equal(candidates[0].horse_name_en, "EMERGING STAR");
  const betCard = renderBetCard(candidates[0], meeting, 1);
  assert.match(betCard, /馬號/);
  assert.match(betCard, /EMERGING STAR/);
  assert.match(betCard, /bh-copy/);
  assert.match(betCard, /bh-meta-item/);
  assert.match(renderSingleAnalystView(dashboardData.races["2026-07-15|跑馬地"].races_by_analyst.Kelvin[0], "Kelvin"), /K390\.gif/);
  assert.match(renderSingleAnalystView(dashboardData.races["2026-07-15|跑馬地"].races_by_analyst.Kelvin[0], "Kelvin"), /EMERGING STAR/);
});

test("every race betting panel is expanded by default", () => {
  const context = loadTemplateFunctions();
  const expanded = context.defaultExpandedBetRaces({
    races_by_analyst: {
      Kelvin: [
        { race_number: 1 },
        { race_number: 2 },
        { race_number: 3 },
      ],
    },
  });

  assert.deepEqual([...expanded], [1, 2, 3]);
});

test("mobile betting record keeps each bet readable as a compact card", () => {
  const { renderMobileRoiRecord, renderDesktopRoiHorse } = loadTemplateFunctions();
  const html = renderMobileRoiRecord({
    race: 1,
    num: 4,
    name: "多利神駒",
    name_en: "OUR LUCKY GLORY",
    silk_url: "https://racing.hkjc.com/racing/content/Images/RaceColor/K390.gif",
    jockey: "巴度",
    trainer: "蘇偉賢",
    grade: "B-",
    odds: 3,
    result: null,
    profit: null,
  });

  assert.match(html, /roi-mobile-item/);
  assert.match(html, /R1/);
  assert.match(html, /#4 · 多利神駒/);
  assert.match(html, /巴度/);
  assert.doesNotMatch(html, /蘇偉賢/);
  assert.match(html, /OUR LUCKY GLORY/);
  assert.match(html, /K390\.gif/);
  assert.match(html, /@3/);
  assert.match(html, /待賽果/);

  const desktop = renderDesktopRoiHorse({
    num: 4,
    name: "多利神駒",
    name_en: "OUR LUCKY GLORY",
    silk_url: "https://racing.hkjc.com/racing/content/Images/RaceColor/K390.gif",
  });
  assert.match(desktop, /OUR LUCKY GLORY/);
  assert.match(desktop, /K390\.gif/);
});

test("confirmed bet puts edit odds beside the odds heading", () => {
  const template = fs.readFileSync(new URL("../static_template.html", import.meta.url), "utf8");
  assert.match(template, /bh-step-heading/);
  assert.match(template, /bb-edit--inline/);
  assert.match(template, /bh-step-row bh-step-row--result/);
  assert.match(template, /\.bh-name-en \{[^}]*white-space: nowrap/);
  assert.match(template, /\.bh-grades \{[^}]*padding-left: 108px/);
});

test("multi-sport workspace shows provenance, archived-odds warnings, and add-to-bet actions", () => {
  const history = {
    nba: [{
      id: "nba-nyk-atl-brunson-25",
      event_date: "2026-04-24",
      event_name: "NYK @ ATL",
      market: "Player Points",
      selection: "Jalen Brunson 25+",
      odds: null,
      odds_status: "not_archived",
      outcome: "won",
      actual: "命中",
      metrics: { monte_carlo: 0.229, factor_model: 0.81 },
      insight: "兩個模型訊號衝突，實際命中。",
      provenance: "NBA Reflector observation log",
    }],
    tennis: [{
      id: "tennis-2026-07-23-halys-navone-aces",
      event_date: "2026-07-23",
      event_name: "Quentin Halys vs Mariano Navone",
      market: "Total Aces",
      selection: "Over 5.5",
      odds: 1.7,
      outcome: "won",
      actual: "9 aces",
      metrics: { model_probability: 0.7484, edge: 0.1531 },
      insight: "模型 value bet，賽後命中。",
      provenance: "tennis_wc.db + Tennis Daily Report",
    }],
  };
  const data = { ...EMPTY_DASHBOARD_DATA, sports_history: history };
  const { renderSportsWorkspace } = loadTemplateFunctions(data);
  const nba = renderSportsWorkspace("nba");
  const tennis = renderSportsWorkspace("tennis");

  assert.match(nba, /NYK @ ATL/);
  assert.match(nba, /原始賠率未存檔/);
  assert.match(nba, /NBA Reflector observation log/);
  assert.match(nba, /加入投注單/);
  assert.match(tennis, /Quentin Halys vs Mariano Navone/);
  assert.match(tennis, /1\.70/);
  assert.match(tennis, /模型概率 74\.8%/);
});

test("tennis cards show tier, tour, round and CLV context when available", () => {
  const data = {
    ...EMPTY_DASHBOARD_DATA,
    sports_history: {
      nba: [],
      tennis: [{
        id: "tennis-context",
        event_date: "2026-07-25",
        event_name: "A vs B",
        market: "Match Betting",
        selection: "A",
        odds: 2,
        category: "core_banker",
        outcome: "won",
        metrics: { clv: 0.04 },
        context: { tour: "ATP", round: "QF", tournament: "Sydney Open" },
      }],
    },
  };
  const { renderSportsWorkspace } = loadTemplateFunctions(data);
  const html = renderSportsWorkspace("tennis");
  assert.match(html, /Tier CORE_BANKER/);
  assert.match(html, /ATP/);
  assert.match(html, /QF/);
  assert.match(html, /Sydney Open/);
  assert.match(html, /CLV \+4\.0%/);
});

test("sports ROI excludes pending bets and handles won lost and void results", () => {
  const { calculateSportsRoi } = loadTemplateFunctions();
  const roi = calculateSportsRoi([
    { sport: "tennis", stake: 2, status: "won", profit: 1.4, payout: 3.4 },
    { sport: "tennis", stake: 1, status: "lost", profit: -1, payout: 0 },
    { sport: "tennis", stake: 5, status: "pending", profit: 0, payout: 0 },
    { sport: "tennis", stake: 1, status: "void", profit: 0, payout: 1 },
  ]);

  assert.equal(roi.total_bets, 4);
  assert.equal(roi.settled_bets, 3);
  assert.equal(roi.total_stake, 4);
  assert.equal(roi.total_profit, 0.4);
  assert.equal(roi.roi_pct, 10);
});

test("multi-sport workspace has a single-column mobile contract", () => {
  const template = fs.readFileSync(new URL("../static_template.html", import.meta.url), "utf8");
  assert.match(template, /@media \(max-width: 840px\)[\s\S]*?\.history-grid \{ grid-template-columns:1fr; \}/);
  assert.match(template, /@media \(max-width: 840px\)[\s\S]*?\.sport-switch \{ flex:1;/);
  assert.match(template, /@media \(max-width: 520px\)[\s\S]*?\.sports-modal__grid \{ grid-template-columns:1fr; \}/);
});

test("sport URL state accepts horses NBA tennis and portfolio", () => {
  const { getInitialSportFromUrl, setLocationSearchForTest } = loadTemplateFunctions();
  setLocationSearchForTest("?sport=tennis");
  assert.equal(getInitialSportFromUrl(), "tennis");
  setLocationSearchForTest("?sport=nba");
  assert.equal(getInitialSportFromUrl(), "nba");
  setLocationSearchForTest("?sport=portfolio");
  assert.equal(getInitialSportFromUrl(), "portfolio");
  setLocationSearchForTest("?sport=football");
  assert.equal(getInitialSportFromUrl(), "horses");
});

test("portfolio workspace is backed by the D1 portfolio endpoint", () => {
  const template = fs.readFileSync(new URL("../static_template.html", import.meta.url), "utf8");
  assert.match(template, /id="sport-portfolio"[\s\S]*?showSport\('portfolio'\)/);
  assert.match(template, /const PORTFOLIO_ENDPOINT = [^;]*'\/api\/portfolio'/);
  assert.match(template, /function renderPortfolioWorkspace\(/);
});

test("sports ledger exposes per-leg settlement controls and D1 audit history", () => {
  const template = fs.readFileSync(new URL("../static_template.html", import.meta.url), "utf8");
  assert.match(template, /name="leg_status_\$\{index\}"/);
  assert.match(template, /組合注會按逐腿結果自動結算/);
  assert.match(template, /const AUDIT_ENDPOINT = [^;]*'\/api\/audit'/);
  assert.match(template, /function openBetAudit\(/);
  assert.match(template, />紀錄<\/button>/);
  assert.match(template, /Idempotency-Key/);
});

test("live tennis feed replaces fallback history and keeps combo legs in the bet draft", () => {
  const liveCombo = {
    id: "tennis:combo:live",
    sport: "tennis",
    category: "combo",
    event_date: "2026-07-25",
    event_name: "2-match Combo · 價值膽",
    market: "Tennis Multi",
    selection: "Elina Avanesyan + Otto Virtanen",
    odds: 3.9,
    outcome: "pending",
    decision: "BET",
    bet_type: "combo",
    legs: [
      { selection: "Elina Avanesyan", odds: 2.5 },
      { selection: "Otto Virtanen", odds: 1.56 },
    ],
    metrics: {
      model_probability: 0.75,
      minimum_acceptable_odds: 3.4,
      confidence: 75,
    },
    risk: "逐腳結算",
    provenance: "tennis_wc.db · combo_tracker",
  };
  const data = {
    ...EMPTY_DASHBOARD_DATA,
    sports_history: { nba: [], tennis: [{ id: "fallback-old" }] },
    sports_feed: {
      schema_version: 2,
      sports: {
        nba: { validation_status: "unavailable", recommendations: [] },
        tennis: { validation_status: "valid", recommendations: [liveCombo] },
      },
    },
  };
  const { renderSportsWorkspace, sportsBetDraftFromSource } = loadTemplateFunctions(data);

  const html = renderSportsWorkspace("tennis");
  const draft = sportsBetDraftFromSource(liveCombo, "tennis");

  assert.match(html, /今日建議/);
  assert.match(html, /2-match Combo/);
  assert.match(html, /最低可接受 3\.40/);
  assert.doesNotMatch(html, /fallback-old/);
  assert.equal(draft.bet_type, "combo");
  assert.equal(draft.legs.length, 2);
  assert.equal(draft.legs[1].selection, "Otto Virtanen");
});

test("pending recommendations always show a locked confirmation with extracted odds and editable stake", () => {
  const template = fs.readFileSync(new URL("../static_template.html", import.meta.url), "utf8");
  const { renderHistoryCard } = loadTemplateFunctions();
  const html = renderHistoryCard({
    id: "nba:2026-07-25:NYK_ATL:banker",
    sport: "nba",
    category: "banker",
    event_date: "2026-07-25",
    event_name: "NYK @ ATL",
    market: "Player Points",
    selection: "Jalen Brunson 25+",
    odds: 1.82,
    odds_status: "sportsbet_extracted",
    outcome: "pending",
    decision: "BET",
    bet_type: "single",
    metrics: { stake_units: 1.25 },
  }, "nba");

  assert.match(template, /function renderInlineBetDraft\(/);
  assert.match(template, /function enableInlineBetField\(/);
  assert.doesNotMatch(template, /function toggleInlineBetDraft\(/);
  assert.match(html, /Sportsbet 提取賠率/);
  assert.match(html, /name="actual_odds"[^>]*value="1\.82"[^>]*readonly/);
  assert.match(html, /name="stake"[^>]*value="1\.25"[^>]*readonly/);
  assert.match(html, /aria-label="修改實際賠率"/);
  assert.match(html, /aria-label="修改旺財建議注碼"/);
  assert.match(template, /旺財建議注碼/);
  assert.match(template, /確認落注/);
  assert.doesNotMatch(html, /＋ 加入投注單|收起投注確認/);
});

test("settled historical examples cannot be added as new bets", () => {
  const { renderHistoryCard } = loadTemplateFunctions();
  const html = renderHistoryCard({
    id: "nba-old-case",
    sport: "nba",
    event_date: "2026-04-24",
    event_name: "NYK @ ATL",
    market: "Player Points",
    selection: "Jalen Brunson 25+",
    odds: null,
    outcome: "won",
    decision: "BET",
    metrics: {},
  }, "nba");

  assert.match(html, /舊案例只供檢討/);
  assert.doesNotMatch(html, /inline-bet-confirm|確認落注/);
});

test("saved bet cards update the result inline without editing event metadata", () => {
  const template = fs.readFileSync(new URL("../static_template.html", import.meta.url), "utf8");

  assert.match(template, /function updateSportsBetResult\(/);
  assert.match(template, /function updateSportsComboLegResult\(/);
  assert.match(template, /onchange="updateSportsBetResult\(/);
  assert.match(template, /onchange="updateSportsComboLegResult\(/);
  assert.match(template, /function openSportsOddsEditor\(/);
  assert.match(template, /實際賠率/);
  assert.doesNotMatch(template, /openSportsBetModal\(null,'\$\{esc\(record\.id\)\}'\)/);
});

test("ROI explains that new analysis replaces recommendations but never confirmed ledger records", () => {
  const data = {
    ...EMPTY_DASHBOARD_DATA,
    sports_history: { nba: [], tennis: [] },
    sports_feed: {
      schema_version: 2,
      sports: {
        nba: {
          analysis_run_id: "nba:2026-07-25",
          validation_status: "valid",
          recommendations: [{
            id: "nba-live",
            sport: "nba",
            event_date: "2026-07-25",
            event_name: "NYK @ ATL",
            market: "Player Points",
            selection: "Jalen Brunson 25+",
            odds: 1.82,
            outcome: "pending",
            decision: "BET",
            metrics: {},
          }],
        },
        tennis: { validation_status: "unavailable", recommendations: [] },
      },
    },
  };
  const { renderSportsWorkspace, setSportsTabForTest } = loadTemplateFunctions(data);
  setSportsTabForTest("roi");
  const html = renderSportsWorkspace("nba");

  assert.match(html, /新分析只會替換「今日建議」/);
  assert.match(html, /已確認投注同 ROI 永久保留/);
});

test("tennis workspace shows fixture, Sportsbet and model coverage timestamps", () => {
  const data = {
    ...EMPTY_DASHBOARD_DATA,
    sports_history: { nba: [], tennis: [] },
    sports_feed: {
      schema_version: 2,
      sports: {
        nba: { validation_status: "unavailable", recommendations: [] },
        tennis: {
          analysis_run_id: "tennis:2026-07-29",
          validation_status: "valid",
          recommendations: [],
          strategy: {
            status: "RESEARCH_ONLY",
            raw_scorecard_settled: 15,
            enabled_families: [],
            families: {
              player_aces: { scorecard_settled: 15 },
              player_total_games: { scorecard_settled: 0 },
            },
          },
          coverage: {
            fixtures_found: 102,
            sportsbet_priced_matches: 58,
            singles_candidates: 54,
            modelled_matches: 54,
            unmodelled_priced_matches: 4,
            priced_ratio: 0.5686,
            latest_sportsbet_scrape: "2026-07-29T03:43:50Z",
            latest_analysis: "2026-07-29T03:46:10Z",
          },
        },
      },
    },
  };
  const { renderSportsWorkspace } = loadTemplateFunctions(data);
  const html = renderSportsWorkspace("tennis");

  assert.match(html, /今日賽程 102 場/);
  assert.match(html, /Sportsbet 已開盤 58 場/);
  assert.match(html, /可建模單打 54 場/);
  assert.match(html, /已建模 54 場/);
  assert.match(html, /未入模型 4 場/);
  assert.match(html, /覆蓋 56\.9%/);
  assert.match(html, /最後 Sportsbet 抓取：2026-07-29T03:43:50Z/);
  assert.match(html, /Prop 策略：RESEARCH_ONLY/);
  assert.match(html, /player_aces 15\/120/);
  assert.match(html, /分析已完成，但未有通過模型及風控門檻/);
});
