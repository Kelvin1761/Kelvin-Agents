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
  html = html.replace('"__DATA_PLACEHOLDER__"', JSON.stringify(dashboardData).replaceAll("<", "\\u003c"));
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
      nbaStats, nbaRecords, nbaDashboard, nbaSelectRows, nbaShortDate,
      nbaShouldAutoRefresh, checkForNewSnapshot,
      setFetchForTest: (fn) => { fetch = fn; },
      setReloadForTest: (fn) => { window.location.reload = fn; },
      resetSnapshotClockForTest: () => { lastSnapshotCheckAt = 0; },
      setVisibilityForTest: (value) => { document.visibilityState = value; },
      setFocusedElementForTest: (value) => { document.activeElement = value; },
      setSeenAutoVersionForTest: (value) => { sessionStorage.setItem('wc_nba_auto_version', value); },
      calcProfit,
      mergeBetStateMaps,
      renderSilk: typeof renderSilk === "function" ? renderSilk : null,
      hkjcHorseProfileUrl,
      getRaceBettingCandidates,
      renderSingleAnalystView,
      renderBetCard,
      renderMobileRoiRecord,
      renderDesktopRoiHorse,
      isBetRaceExpanded,
      toggleBetRace,
      setCurrentViewForTest: (view) => { currentView = view; },
      renderDashboard,
      loadBettingState,
      showSport,
      setSelectedMeetingForTest: (meeting) => { selectedMeeting = meeting; },
      setRoiLedgerForTest: (records) => { roiLedger = records; },
      setRoiRegionForTest: (region) => { roiRegionFilter = region; },
      setActiveRegionForTest: (region) => { activeRegion = region; roiRegionFilter = region; },
      regionMeetings: typeof regionMeetings === "function" ? regionMeetings : null,
      normaliseSportKey: typeof normaliseSportKey === "function" ? normaliseSportKey : null,
      setLocalStorageForTest: (key, value) => { localStorage.setItem(key, JSON.stringify(value)); },
      getFilteredROI,
      renderHorseCard,
      renderAuFullTimeStatus,
      renderDimensionStrip: typeof renderDimensionStrip === "function" ? renderDimensionStrip : null,
      renderTrackworkTimeline: typeof renderTrackworkTimeline === "function" ? renderTrackworkTimeline : null,
      buildHorseAnalysisSections,
      parseChronologySeries,
      renderChronologySeries,
      formatRichSection,
      renderDataReadoutItem,
      renderSubScoreDetails,
      sanitizeBattlefieldOverviewText,
      renderBattlefieldOverview,
      parseBattlefieldOverview,
      speedMapSvgFromTable,
      renderTrackGeometry,
      renderSportsWorkspace: typeof renderSportsWorkspace === "function" ? renderSportsWorkspace : null,
      renderHistoryCard: typeof renderHistoryCard === "function" ? renderHistoryCard : null,
      renderInlineBetDraft: typeof renderInlineBetDraft === "function" ? renderInlineBetDraft : null,
      calculateSportsRoi: typeof calculateSportsRoi === "function" ? calculateSportsRoi : null,
      setSportsLedgerForTest: (records) => { sportsBetLedger = records; },
      setSportsTabForTest: (tab) => { activeSportsTab = tab; },
      setSportsTab: typeof setSportsTab === "function" ? setSportsTab : null,
      getInitialSportFromUrl: typeof getInitialSportFromUrl === "function" ? getInitialSportFromUrl : null,
      sportsBetDraftFromSource: typeof sportsBetDraftFromSource === "function" ? sportsBetDraftFromSource : null,
      setLocationSearchForTest: (search) => { window.location.search = search; },
      isNewerSnapshot: typeof isNewerSnapshot === "function" ? isNewerSnapshot : null,
      formatSnapshotStamp: typeof formatSnapshotStamp === "function" ? formatSnapshotStamp : null,
      sportsPickLines: typeof sportsPickLines === "function" ? sportsPickLines : null,
      sportsLegParts: typeof sportsLegParts === "function" ? sportsLegParts : null,
      sportsAnalysisCards: typeof sportsAnalysisCards === "function" ? sportsAnalysisCards : null,
      sportsHistory: typeof sportsHistory === "function" ? sportsHistory : null,
      renderSportsHistory: typeof renderSportsHistory === "function" ? renderSportsHistory : null,
      hasLiveSportsFeed: typeof hasLiveSportsFeed === "function" ? hasLiveSportsFeed : null,
      sportsFeedExpired: typeof sportsFeedExpired === "function" ? sportsFeedExpired : null,
      sportsReferencePicks: typeof sportsReferencePicks === "function" ? sportsReferencePicks : null,
      calibrationBadge: typeof calibrationBadge === "function" ? calibrationBadge : null,
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

test("dimension strip reconciles to the raw score; score ledger is gone", () => {
  const { renderDimensionStrip } = loadTemplateFunctions();
  const html = renderDimensionStrip({
    score_raw_total: 66.50,
    score_adjustments: [{ key: "sip_boost", label: "SIP 輕磅好檔修正", raw: 1.0 }],
    dimension_details: [
      { name: "檔位與走位", score: 70, weight_pct: 50, impact: 3.0, ranking_weighted: true },
      { name: "騎練訊號", score: 66, weight_pct: 50, impact: 2.5, ranking_weighted: true },
    ],
  });
  assert.match(html, /原始總分 <b>66\.50<\/b>/);
  assert.match(html, /各維度影響 5\.50/);
  assert.match(html, /SIP 輕磅好檔修正 \+1\.0/);
  // impact comes from the engine (raw ruler), not display score × weight
  assert.match(html, /\+<b>3\.0<\/b>/);
  const template = fs.readFileSync(new URL("../static_template.html", import.meta.url), "utf8");
  assert.doesNotMatch(template, /renderScoreLedger|查看全部評分|場內百分位/);
});

test("dimension bars follow the dimension score, not its contribution", () => {
  const { renderDimensionStrip } = loadTemplateFunctions();
  const html = renderDimensionStrip({
    dimension_details: [
      { name: "檔位與走位", score: 50, weight_pct: 27.4, impact: -2.0, ranking_weighted: true },
      { name: "同程表現", score: 75.8, weight_pct: 2, impact: 0.3, ranking_weighted: true },
    ],
  });
  // 75.8 − 60 = 15.8 of a 40-point half-track → 19.75%; the +0.3 impact stays as the number
  assert.match(html, /left:50%;width:19\.75%;background:#059669/);
  assert.match(html, /right:50%;width:12\.5%;background:#DC2626/);
  assert.match(html, /\+<b>0\.3<\/b>/);
  assert.match(html, /條長 = 維度分數/);
});

test("reconciliation line uses the typical-horse baseline when the engine gives one", () => {
  const { renderDimensionStrip } = loadTemplateFunctions();
  const html = renderDimensionStrip({
    score_raw_total: 65.0, score_impact_baseline: 63.5,
    dimension_details: [{ name: "級數優勢", score: 58.5, weight_pct: 14.3, impact: -0.2, ranking_weighted: true },
                        { name: "檔位與走位", score: 70, weight_pct: 27.4, impact: 1.7, ranking_weighted: true }],
  });
  assert.match(html, /＝ 典型馬 63\.50 \+ 各維度影響 1\.50/);
});

test("horse card preview shows the total score", () => {
  const { renderHorseCard } = loadTemplateFunctions();
  const html = renderHorseCard({ horse_number: 1, horse_name: "嘉嘉友福", final_grade: "B",
                                 ability_score: 70.1, score_raw_total: 65.8391, dimension_details: [] });
  assert.match(html, /總分 <b>70\.1<\/b>/);
  assert.match(html, /原始總分 65\.84/);
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
  for (const sport of ["hkjc", "au", "nba", "tennis", "portfolio"]) {
    assert.match(html, new RegExp(`id="tabbar-${sport}"[^>]*onclick="showSport\\('${sport}'\\)"`));
  }
  // render() has to drive both navs off the same active sport.
  assert.match(html, /const tab = document\.getElementById\(`tabbar-\$\{sport\}`\);/);
  assert.match(html, /aria-current/);
  // The tab bar owns the bottom edge; the betting bar and back-to-top stack off
  // --tabbar-total so nothing overlaps the tab bar or the home indicator.
  assert.match(html, /:root \{ --tabbar-h: 0px; --tabbar-total: 0px; \}/);
  assert.match(html, /--tabbar-total: calc\(88px \+ env\(safe-area-inset-bottom\)\)/);
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
  assert.match(sw, /request\.mode === "navigate"/);
  assert.match(sw, /self\.clients\.claim\(\)/);
  // The silks are cross-origin; without them an offline racecard loses every colour cue.
  assert.match(sw, /"images\.puntcdn\.com"/);
  assert.match(sw, /RUNTIME_CACHE_HOSTS\.includes\(url\.hostname\)/);
});

test("cache-first navigation is paired with an eviction on manual reload", () => {
  const sw = fs.readFileSync(new URL("../pwa/sw.js", import.meta.url), "utf8");
  const html = fs.readFileSync(new URL("../static_template.html", import.meta.url), "utf8");
  // Cache-first: the cached shell is consulted before the network.
  const navBlock = sw.slice(sw.indexOf('request.mode === "navigate"'), sw.indexOf('Rule 3'));
  assert.ok(
    navBlock.indexOf("cache.match") < navBlock.indexOf("fetch(request)"),
    "navigation must check the cache before hitting the network",
  );
  // Cache-first is only safe because the reload path evicts the shell first —
  // otherwise the refresh button hands back the snapshot it is meant to replace.
  assert.match(html, /async function reloadSnapshot\(\)/);
  assert.match(html, /cache\.delete\(req\)/);
  assert.match(html, /window\.location\.reload\(\)/);
  // The shell must be identified by the cached RESPONSE's content-type. The Cache API
  // reads every stored request back as mode 'no-cors', so keying eviction on
  // mode === 'navigate' silently never matches, and keying on pathname '/' alone
  // misses the shell whenever it was opened as '/index.html'.
  assert.match(html, /content-type[\s\S]{0,40}includes\('text\/html'\)/);
  assert.doesNotMatch(html, /req\.mode === 'navigate'/);
  // And the version has to move, or activate() keeps the old strategy's cache.
  // Asserted as a pattern rather than a pinned literal: a pinned version fails
  // on exactly the change it is asking for (bumping when the strategy changes),
  // which is what happened when /analysis/ caching was added in v3.
  assert.match(sw, /const CACHE_VERSION = "wongchoi-v\d+"/);
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
  // 數據判讀 moved off the preview card and became a chapter of 完整分析
  // (2026-09-02): the ranking-matrix strip now says what the card version said.
  // It is kept as a chapter rather than dropped, or the readout would vanish
  // entirely on this fallback path.
  assert.equal(sections.length, 5);
  assert.equal(sections.filter((section) => section.title === "評級矩陣").length, 1);
  const readoutSection = sections.find((section) => section.title === "數據判讀");
  assert.ok(readoutSection, "數據判讀 should survive as a chapter");
  assert.equal(readoutSection.rows.length, 6, "the chapter carries the structured rows");
  assert.match(sections.find((section) => section.title === "評級矩陣").content, /第一段評級。[\s\S]*第二段評級。/);

  const html = renderHorseCard(horse, 1);
  // The rows still render through renderDataReadout -- inside the document now,
  // collapsed behind its own toggle, rather than on the card.
  assert.match(html, /data-readout--complete/);
  // Bound the check to the preview half of the card: a greedy [\s\S]* would
  // match the readout inside 完整分析 further down and always "fail".
  const previewHalf = html.split("horse-card__expand-btn")[0];
  assert.doesNotMatch(previewHalf, /data-readout/);
  assert.equal((html.match(/data-readout__item/g) || []).length, 6);
  assert.doesNotMatch(html, /長理由六/);
  assert.equal((html.match(/data-readout__reason/g) || []).length, 5);
  assert.doesNotMatch(html, /data-readout__more|另有 \d+ 項/);
  assert.match(html, /horse-silk horse-silk--sm/);
  assert.match(html, /https:\/\/example\.test\/G292\.gif/);
  assert.match(html, /horse-card__expand-btn" aria-expanded="false"/);
  assert.match(html, /5 個章節/);
  assert.match(html, /analysis-document/);
  assert.match(html, /analysis-document__nav/);
  assert.match(html, /rich-heading rich-heading--5">細節標題/);
  assert.equal((html.match(/analysis-document__section analysis-document__section--/g) || []).length, 5);
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

test("all races including newly arriving tail races stay open unless manually closed", () => {
  const context = loadTemplateFunctions();
  context.setCurrentViewForTest("test");
  for (let rn = 1; rn <= 9; rn++) assert.equal(context.isBetRaceExpanded(rn), true);
  context.toggleBetRace(8);
  assert.equal(context.isBetRaceExpanded("8"), false);
  assert.equal(context.isBetRaceExpanded(9), true);
  assert.equal(context.isBetRaceExpanded(10), true);
  context.toggleBetRace("8");
  assert.equal(context.isBetRaceExpanded(8), true);
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
  const { renderSportsWorkspace, setSportsTabForTest } = loadTemplateFunctions(data);
  setSportsTabForTest("archive");
  const nba = renderSportsWorkspace("nba");
  const tennis = renderSportsWorkspace("tennis");

  assert.match(nba, /NYK @ ATL/);
  assert.match(nba, /原始賠率未存檔/);
  assert.match(nba, /NBA Reflector observation log/);
  assert.doesNotMatch(nba, /onclick="openSportsBetModal/);
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

test("sport URL state accepts HKJC AU NBA tennis and portfolio", () => {
  const { getInitialSportFromUrl, setLocationSearchForTest } = loadTemplateFunctions();
  setLocationSearchForTest("?sport=tennis");
  assert.equal(getInitialSportFromUrl(), "tennis");
  setLocationSearchForTest("?sport=nba");
  assert.equal(getInitialSportFromUrl(), "nba");
  setLocationSearchForTest("?sport=portfolio");
  assert.equal(getInitialSportFromUrl(), "portfolio");
  setLocationSearchForTest("?sport=au");
  assert.equal(getInitialSportFromUrl(), "au");
  // Old links (?sport=horses) and unknown values open the HKJC tab.
  setLocationSearchForTest("?sport=horses");
  assert.equal(getInitialSportFromUrl(), "hkjc");
  setLocationSearchForTest("?sport=football");
  assert.equal(getInitialSportFromUrl(), "hkjc");
});

test("HKJC and AU racing tabs each list only their own meetings", () => {
  const data = {
    ...EMPTY_DASHBOARD_DATA,
    meetings: [
      { date: "2026-10-11", venue: "ShaTin", region: "hkjc", analysts: ["Kelvin"] },
      { date: "2026-10-11", venue: "Randwick", region: "au", analysts: ["Kelvin"] },
      { date: "2026-10-07", venue: "HappyValley", region: "hkjc", analysts: ["Kelvin"] },
    ],
  };
  const { regionMeetings, setActiveRegionForTest, renderDashboard } = loadTemplateFunctions(data);
  assert.equal(JSON.stringify(regionMeetings("hkjc").map(m => m.venue)), '["ShaTin","HappyValley"]');
  assert.equal(JSON.stringify(regionMeetings("au").map(m => m.venue)), '["Randwick"]');
  setActiveRegionForTest("au");
  const html = renderDashboard();
  assert.match(html, /Randwick/);
  assert.doesNotMatch(html, /ShaTin|HappyValley/);
  // selectMeeting(i) indexes the full meetings array, so the AU card must keep index 1.
  assert.match(html, /selectMeeting\(1\)/);
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
    // Not yet started: a pick whose match has begun is expired, whatever date it carries.
    start_time_utc: "2099-01-01T00:00:00Z",
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

test("modals are native dialogs with a teardown that does not trust close events", () => {
  const html = fs.readFileSync(new URL("../static_template.html", import.meta.url), "utf8");

  // All three modals go through the one helper, as real <dialog> in the top layer.
  assert.match(html, /const dialog = document\.createElement\('dialog'\);/);
  assert.match(html, /if \(typeof dialog\.showModal === 'function'\) dialog\.showModal\(\);/);
  assert.match(html, /dialog\.roi-modal-dialog::backdrop/);
  assert.doesNotMatch(html, /roi-modal-backdrop/, "the hand-rolled overlay class must be gone");
  for (const id of ["sportsBetModal", "betAuditModal", "roi-edit-backdrop"]) {
    assert.ok(html.includes(`openModalDialog('${id}'`), `${id} must open via openModalDialog`);
  }

  // Measured: one engine's close() sets open=false but fires NEITHER cancel NOR close.
  // So teardown must be explicit, and Esc must be handled directly rather than left to
  // the native close request — otherwise the node leaks and the ROI editor keeps state.
  assert.match(html, /finishModalDialog\(dialog\);\s*\n\}/);
  assert.match(html, /if \(event\.key === 'Escape'\) \{\s*\n\s*event\.preventDefault\(\);\s*\n\s*closeModalDialog\(id\);/);
  // Idempotent, so an Esc-fired event plus an explicit close cannot run cleanup twice.
  assert.match(html, /if \(!dialog \|\| dialog\._wcFinished\) return;/);

  // The money-entry paths must be untouched by the conversion.
  assert.match(html, /onsubmit="saveSportsBet\(event,'\$\{esc\(record\.id\)\}',true\)"/);
  assert.match(html, /onsubmit="saveRoiRecord\(event\)"/);
});

test("off-screen analysis prose is skipped, but searchable text is not", () => {
  const html = fs.readFileSync(new URL("../static_template.html", import.meta.url), "utf8");
  assert.match(html, /\.analysis-document__section \{ content-visibility: auto; contain-intrinsic-size: auto 900px; \}/);
  // Safari does not expose content skipped this way to find-in-page, so it must never
  // be applied to what you would actually search for: horse names, ratings, jockeys.
  for (const selector of ["\\.horse-card", "\\.horse-card__name", "\\.data-readout", "\\.battlefield-ranking"]) {
    assert.doesNotMatch(
      html,
      new RegExp(`${selector} \\{[^}]*content-visibility`),
      `content-visibility must not be applied to ${selector} — it would hide it from find-in-page`,
    );
  }
});

test("view transitions animate real view changes only, never the bet-sync tick", () => {
  const html = fs.readFileSync(new URL("../static_template.html", import.meta.url), "utf8");
  // render() must gate on the view key changing. Without this the 15s /api/sync poll
  // would cross-fade the whole page while you are reading a racecard.
  assert.match(html, /const viewKey = `\$\{activeSport\}\|\$\{currentView\}`/);
  assert.match(html, /viewChanged = lastRenderedViewKey !== null && lastRenderedViewKey !== viewKey/);
  assert.match(html, /if \(viewChanged && !reduceMotion && typeof document\.startViewTransition === 'function'\)/);
  // Feature-detected and motion-respecting, with a plain render as the fallback path.
  assert.match(html, /matchMedia\('\(prefers-reduced-motion: reduce\)'\)\.matches/);
  assert.match(html, /function renderNow\(main\)/);
  // Only #app-main is named, so the header and tab bar do not animate.
  assert.match(html, /#app-main \{ view-transition-name: app-main; \}/);
  assert.match(html, /::view-transition-old\(app-main\)/);
});

test("the mobile race switcher sticks, and nothing upstream re-breaks it", () => {
  const html = fs.readFileSync(new URL("../static_template.html", import.meta.url), "utf8");
  const css = fs.readFileSync(new URL("../frontend/src/index.css", import.meta.url), "utf8");

  // Compact one-row scroller on mobile, sticky to the top.
  assert.match(html, /\.race-pills \{\s*position: sticky; top: 0;/);
  assert.match(html, /flex-wrap: nowrap; overflow-x: auto/);
  assert.match(html, /\.race-pill__name \{ display: none; \}/);
  // Active pill is brought into view — on R7 of 9 it starts off-screen right.
  assert.match(html, /race-pill--active'\);[\s\S]{0,160}scrollIntoView/);

  // Sticky dies silently if ANY ancestor is a scroll container. Both of these were
  // scroll containers before and both had to change; if either regresses, the sticky
  // bar stops sticking with no error anywhere.
  assert.match(css, /\.app-main \{[^}]*overflow-x: clip;/);
  assert.doesNotMatch(css, /\.app-main \{[^}]*overflow: hidden;/);
  assert.match(css, /html, body \{[^}]*overflow-y: visible;/);
  assert.doesNotMatch(css, /html, body \{[^}]*overflow-y: auto;/);
});

test("a valid feed that passed nothing falls back to history instead of blanking", () => {
  const historyCase = {
    id: "tennis-old", event_date: "2026-07-23", event_name: "Baez vs Hanfmann",
    market: "Sebastian Baez Aces", selection: "Over 1.5", odds: 1.88, outcome: "lost", metrics: {},
  };
  const data = {
    ...EMPTY_DASHBOARD_DATA,
    sports_history: { nba: [], tennis: [historyCase] },
    sports_feed: {
      sports: {
        // The exact shape that broke it: analysis ran fine, evidence gate passed nothing.
        tennis: { validation_status: "valid", recommendations: [], coverage: null, strategy: null },
      },
    },
  };
  const { sportsHistory, renderSportsHistory } = loadTemplateFunctions(data);

  assert.equal(sportsHistory("tennis").length, 1, "must fall back to history, not return the empty live list");
  const html = renderSportsHistory("tennis");
  // And it has to say today is a no-bet day, or the old case reads as today's pick.
  assert.match(html, /今日冇合格建議/);
  assert.match(html, /唔應該落注/);
  assert.match(html, /Baez vs Hanfmann/);
  // The no-bet answer comes before the diagnostics, not after them.
  assert.ok(html.indexOf("今日冇合格建議") < html.indexOf("history-grid"));
});

test("coverage and strategy diagnostics stay collapsed so picks are not buried", () => {
  const data = {
    ...EMPTY_DASHBOARD_DATA,
    sports_history: { nba: [], tennis: [{ id: "t", event_name: "M", metrics: {} }] },
    sports_feed: {
      sports: {
        tennis: {
          validation_status: "valid",
          recommendations: [],
          coverage: { fixtures_found: 10, sportsbet_priced_matches: 1, modelled_matches: 1, priced_ratio: 0.1 },
          strategy: { status: "RESEARCH_ONLY", enabled_families: [], families: { player_aces: { scorecard_settled: 3 } } },
        },
      },
    },
  };
  const { renderSportsHistory } = loadTemplateFunctions(data);
  const html = renderSportsHistory("tennis");
  // Both diagnostics still present — but inside one collapsed block, not stacked open.
  assert.match(html, /<details class="sports-diagnostics">/);
  assert.match(html, /資料覆蓋同策略狀態/);
  assert.match(html, /今日賽程 10 場/);
  assert.match(html, /RESEARCH_ONLY/);
  const iDetails = html.indexOf('class="sports-diagnostics"');
  assert.ok(html.indexOf("今日賽程 10 場") > iDetails, "coverage must sit inside the collapsed block");
  assert.ok(html.indexOf("RESEARCH_ONLY") > iDetails, "strategy must sit inside the collapsed block");
});

test("a feed with real recommendations still wins over history", () => {
  const live = {
    id: "tennis-live", event_date: "2026-07-31", start_time_utc: "2099-01-01T00:00:00Z",
    event_name: "Live Match",
    market: "Player Aces", selection: "Over 3.5", odds: 1.9, outcome: "pending", metrics: {},
  };
  const data = {
    ...EMPTY_DASHBOARD_DATA,
    sports_history: { nba: [], tennis: [{ id: "old", event_name: "Old Match", metrics: {} }] },
    sports_feed: { sports: { tennis: { validation_status: "valid", recommendations: [live] } } },
  };
  const { sportsHistory, renderSportsHistory } = loadTemplateFunctions(data);
  assert.equal(sportsHistory("tennis")[0].id, "tennis-live");
  const html = renderSportsHistory("tennis");
  assert.doesNotMatch(html, /今日冇合格建議/);
  assert.doesNotMatch(html, /Old Match/);
});

test("a snapshot whose picks have already started is not today's picks", () => {
  // 2026-10-20: the NBA tab offered 10-15 preseason combos, with a confirm button,
  // five days after they tipped off.  The CDN snapshot can be days old; the browser
  // has to judge expiry again on every render.
  const stale = {
    id: "nba:old", sport: "nba", event_date: "2000-01-01", event_name: "OLD @ GAME",
    market: "Same Game Multi", selection: "stale combo", odds: 3.4, outcome: "pending",
    decision: "BET", bet_type: "combo", legs: [], metrics: {},
  };
  const data = {
    ...EMPTY_DASHBOARD_DATA,
    sports_history: { nba: [{ id: "archive", event_name: "Archive Case", metrics: {} }], tennis: [] },
    sports_feed: { sports: { nba: {
      validation_status: "valid", analysis_run_id: "nba:2000-01-01", recommendations: [stale],
    } } },
  };
  const { hasLiveSportsFeed, sportsFeedExpired, renderSportsHistory } = loadTemplateFunctions(data);
  assert.equal(hasLiveSportsFeed("nba"), false);
  assert.equal(sportsFeedExpired("nba"), true);
  const html = renderSportsHistory("nba");
  assert.match(html, /已經開賽／過期/);
  assert.doesNotMatch(html, /stale combo/);
  assert.doesNotMatch(html, /今日冇合格建議/);
});

test("on the same day a started NBA game drops out of today's picks and an unstarted one stays", () => {
  // 2026-10-21: BOS@DET tipped 06:00 and still offered 確認落注 at noon, because the page
  // only compared dates.  start_time_utc is judged against the clock on every render.
  const pick = (id, start) => ({
    id, sport: "nba", event_date: sydneyDateForTest(), event_name: id, market: "Same Game Multi",
    selection: id, odds: 3.4, outcome: "pending", decision: "BET", bet_type: "combo",
    legs: [], metrics: {}, start_time_utc: start,
  });
  const started = pick("started", "2000-01-01T00:00:00Z");
  const upcoming = pick("upcoming", "2099-01-01T00:00:00Z");
  const data = {
    ...EMPTY_DASHBOARD_DATA,
    sports_feed: { sports: { nba: {
      validation_status: "valid", analysis_run_id: "nba:" + sydneyDateForTest(),
      recommendations: [started, upcoming],
    } } },
  };
  const { sportsHistory } = loadTemplateFunctions(data);
  assert.deepEqual([...sportsHistory("nba").map((item) => item.id)], ["upcoming"]);
});

function sydneyDateForTest() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Australia/Sydney" }).format(new Date());
}

test("live NBA picks carry the calibration notice and flag only legs at 70%+", () => {
  const combo = {
    id: "nba:cal", sport: "nba", event_date: "2099-01-01", start_time_utc: "2099-01-01T00:00:00Z",
    event_name: "AAA @ BBB", market: "Same Game Multi", selection: "combo", odds: 3.4, outcome: "pending",
    decision: "BET", bet_type: "combo", metrics: {},
    legs: [
      { selection: "High P (AAA) PTS 10+", market: "Player PTS", odds: 1.3, metrics: { model_probability: 0.77 } },
      { selection: "Low P (BBB) REB 6+", market: "Player REB", odds: 1.8, metrics: { model_probability: 0.60 } },
      { selection: "No P (BBB) AST 4+", market: "Player AST", odds: 1.5 },
    ],
  };
  const data = { ...EMPTY_DASHBOARD_DATA, sports_feed: { sports: { nba: {
    validation_status: "valid", analysis_run_id: "nba:2099-01-01", recommendations: [combo] } } } };
  const { renderSportsHistory } = loadTemplateFunctions(data);
  const html = renderSportsHistory("nba");
  assert.match(html, /校準提示（離線量度，唔係利潤結論）/);
  assert.match(html, /EXP-20261021-05／06/);
  assert.equal((html.match(/pick-leg__calib/g) || []).length - (html.match(/\.pick-leg__calib/g) || []).length, 1);
  assert.match(html, /High P \(AAA\) PTS 10\+<em class="pick-leg__calib"/);
  assert.doesNotMatch(html, /Low P \(BBB\) REB 6\+<em/);
});

test("the calibration notice is NBA-only and never shown on history or tennis", () => {
  const history = { ...EMPTY_DASHBOARD_DATA, sports_history: { nba: [{ id: "h", event_name: "Old", metrics: { model_probability: 0.9 } }], tennis: [] } };
  const nbaHistory = loadTemplateFunctions(history).renderSportsHistory("nba");
  assert.doesNotMatch(nbaHistory, /校準提示/);
  const tennisLive = { ...EMPTY_DASHBOARD_DATA, sports_feed: { sports: { tennis: {
    validation_status: "valid", analysis_run_id: "tennis:2099-01-01",
    recommendations: [{ id: "t", sport: "tennis", event_date: "2099-01-01", start_time_utc: "2099-01-01T00:00:00Z",
      event_name: "A vs B", market: "Match Winner", selection: "A", odds: 1.8, outcome: "pending",
      decision: "BET", bet_type: "single", legs: [], metrics: { model_probability: 0.9 } }] } } } };
  const tennisHtml = loadTemplateFunctions(tennisLive).renderSportsHistory("tennis");
  assert.doesNotMatch(tennisHtml, /校準提示/);
  assert.doesNotMatch(tennisHtml, /pick-leg__calib"/);
});

test("an exporter-expired NBA snapshot says the analysis is not out yet", () => {
  const data = {
    ...EMPTY_DASHBOARD_DATA,
    sports_feed: { sports: { nba: {
      validation_status: "expired", analysis_run_id: "nba:2026-10-15", recommendations: [],
    } } },
  };
  const { sportsFeedExpired } = loadTemplateFunctions(data);
  assert.equal(sportsFeedExpired("nba"), true);
});

test("a firewall-blocked NBA day shows a blocked notice instead of picks", () => {
  const data = {
    ...EMPTY_DASHBOARD_DATA,
    sports_history: { nba: [{ id: "archive", event_name: "Archive Case", metrics: {} }], tennis: [] },
    sports_feed: { sports: { nba: {
      validation_status: "blocked", analysis_run_id: "nba:2026-10-21",
      warnings: ["nba_firewall_blocked:BOS_DET"], recommendations: [],
    } } },
  };
  const { renderSportsHistory } = loadTemplateFunctions(data);
  const html = renderSportsHistory("nba");
  assert.match(html, /今日 NBA 分析未通過發佈檢查/);
  assert.match(html, /2026-10-21/);
  assert.doesNotMatch(html, /今日冇合格建議/);
});

test("tennis reference picks render as reference, never as a bet to place", () => {
  const reference = {
    id: "tennis:reference:1", sport: "tennis", category: "reference_model_edge",
    event_date: "2099-01-01", start_time_utc: "2099-01-01T00:00:00Z",
    event_name: "A vs B", market: "Match Winner", selection: "A", odds: 2.4,
    outcome: "pending", decision: "BET", bet_type: "single", legs: [], metrics: {},
  };
  const started = { ...reference, id: "tennis:reference:2", start_time_utc: "2000-01-01T00:00:00Z" };
  const data = {
    ...EMPTY_DASHBOARD_DATA,
    sports_feed: { sports: { tennis: {
      validation_status: "valid", recommendations: [], reference_picks: [reference, started],
    } } },
  };
  const { sportsReferencePicks, renderSportsHistory } = loadTemplateFunctions(data);
  assert.deepEqual([...sportsReferencePicks("tennis").map((item) => item.id)], ["tennis:reference:1"]);
  const html = renderSportsHistory("tennis");
  assert.match(html, /參考：模型 edge 單（1 個，唔係正式建議）/);
  assert.match(html, /未過正式落注閘/);
  assert.doesNotMatch(html, /tennis:reference:2/);
});

test("a bare over/under line is joined to its subject, a self-describing pick is not", () => {
  const { sportsPickLines } = loadTemplateFunctions();
  // Spread the vm-realm result into this realm: deepStrictEqual compares prototypes,
  // and objects built inside the vm carry a different Object.prototype.
  const lines = (item) => ({ ...sportsPickLines(item) });
  // Tennis puts the subject in market and the side in selection — "Over 1.5" alone
  // tells you nothing about what to back.
  assert.deepEqual(
    lines({ market: "Sebastian Baez Aces", selection: "Over 1.5" }),
    { kicker: "", headline: "Sebastian Baez Aces · Over 1.5" },
  );
  for (const bare of ["Under 5.5", "O2.5", "u 1.5"]) {
    assert.match(sportsPickLines({ market: "Total Games", selection: bare }).headline, /^Total Games · /);
  }
  // NBA selections already name the player and the line; market is a category.
  assert.deepEqual(
    lines({ market: "Player Points", selection: "Jalen Brunson 25+" }),
    { kicker: "Player Points", headline: "Jalen Brunson 25+" },
  );
  assert.equal(sportsPickLines({ market: "", selection: "Solo pick" }).headline, "Solo pick");
  assert.equal(sportsPickLines({ market: "Only market", selection: "" }).headline, "Only market");
  assert.equal(sportsPickLines({}).headline, "—");
});

test("combo legs are parsed out of both object and pre-formatted string form", () => {
  const { sportsLegParts } = loadTemplateFunctions();
  const parts = (leg) => ({ ...sportsLegParts(leg) });
  assert.deepEqual(
    parts("Sebastian Baez aces Over 1.5 @ 1.88 · LOST"),
    { label: "Sebastian Baez aces Over 1.5", odds: 1.88, status: "lost" },
  );
  assert.deepEqual(
    parts({ event_name: "A vs B", market: "aces", selection: "Over 5.5", odds: 1.95, status: "won" }),
    { label: "A vs B · aces · Over 5.5", odds: 1.95, status: "won" },
  );
  // No price and no status must not corrupt the label.
  assert.deepEqual(parts("Plain leg"), { label: "Plain leg", odds: null, status: null });
  assert.equal(sportsLegParts({}).label, "未命名 leg");
});

test("a combo shows every leg with its own price, not just the combined odds", () => {
  const { renderHistoryCard } = loadTemplateFunctions();
  const html = renderHistoryCard({
    id: "tennis-combo", event_date: "2026-07-23", event_name: "3-match Prop Combo",
    market: "Aces Combo", selection: "Baez O1.5 + Buse O5.5 + Halys O5.5",
    bet_type: "combo", odds: 6.23, outcome: "lost", metrics: {},
    legs: [
      "Sebastian Baez aces Over 1.5 @ 1.88 · LOST",
      "Buse/Etcheverry total aces Over 5.5 @ 1.95 · WON",
      "Halys/Navone total aces Over 5.5 @ 1.70 · WON",
    ],
  }, "tennis");

  assert.match(html, /3 腳 combo/);
  assert.equal((html.match(/class="pick-leg\b/g) || []).length, 3, "one row per leg");
  for (const price of ["1.88", "1.95", "1.70"]) assert.ok(html.includes(price), `leg price ${price} must show`);
  assert.match(html, /合併賠率[\s\S]*6\.23/);
  // Per-leg results, so a 2/3 combo reads as a loss for an identifiable reason.
  assert.match(html, /pick-leg--lost/);
  assert.match(html, /pick-leg--won/);
});

test("a review-only observation is never presented as something to bet", () => {
  const { renderHistoryCard } = loadTemplateFunctions();
  const html = renderHistoryCard({
    id: "nba-obs", event_date: "2026-04-24", event_name: "CLE @ TOR",
    market: "Bench Player Props", selection: "Bench minutes assumption",
    odds: null, outcome: "review", metrics: {},
  }, "nba");

  assert.match(html, /觀察筆記/);
  assert.match(html, /唔係投注建議/);
  assert.match(html, /pick-block--note/);
  // The 落注 label must be absent — that word is what tells the user to back it.
  assert.doesNotMatch(html, /🎯 落注/);
});

test("cards lead with the fixture and fold model commentary away", () => {
  const { renderHistoryCard } = loadTemplateFunctions();
  const html = renderHistoryCard({
    id: "t1", event_date: "2026-07-23", event_name: "Baez vs Hanfmann",
    market: "Sebastian Baez Aces", selection: "Over 1.5", odds: 1.88,
    outcome: "lost", metrics: {}, insight: "why", risk: "risk", actual: "0 aces",
  }, "tennis");

  // Fixture, then the pick, then the collapsed prose — in that document order.
  const iFixture = html.indexOf("history-card__event");
  const iPick = html.indexOf("pick-block__headline");
  const iMore = html.indexOf("history-card__more");
  assert.ok(iFixture < iPick && iPick < iMore, "fixture → pick → details");
  assert.match(html, /<details class="history-card__more">/);
  assert.match(html, /Sebastian Baez Aces · Over 1\.5/);
  assert.match(html, /賠率 <strong>1\.88<\/strong>/);
  // Prose is present but inside the collapsed block.
  assert.ok(html.indexOf("why") > iMore);
  assert.ok(html.indexOf("risk") > iMore);
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
  setSportsTabForTest("bets");
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
              player_exact_set_score: { scorecard_settled: 8 },
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
  assert.match(html, /Player Aces 15\/120/);
  assert.match(html, /Player Exact Set Score 8\/120/);
  assert.match(html, /分析已完成，但未有通過模型及風控門檻/);
});


// ── 形勢推演：預測起步位圖 ────────────────────────────────────────────────
// 2026-09-02：`parseBattlefieldOverview` 會將**每一個** markdown 表由 notes 度
// 剷走，只留返「項目/內容」同「排名/馬號」兩個佢認得嘅。所以新加嘅預測起步位表
// 如果冇喺呢度認住，喺 dashboard 就會完全消失（表被剷、又冇人畫返出嚟）。
const SPEEDMAP_OVERVIEW = `## [第一部分] 🗺️ 戰場全景

| 項目 | 內容 |
|:---|:---|
| 賽事格局 | Race 3 / 1200m / TEST |
| 出馬數 | 8 |

**🏃 形勢推演**

| 預測定位 | 馬號 | 馬名 | 我哋 | 官方 | 混合 |
|---:|---:|---|---:|---:|---:|
| 1 | 4 | African Daisy | 1.8 | 1 | 1 |
| 2 | 2 | Regimental Colours | 4.5 | 4 | 2 |
| 3 | 7 | Catahoula | 6.8 | 2 | 3 |

> 「我哋」= 近仗起步位加權平均（越細 = 越前）；「官方」= Sportsbet Speedmap 預測定位序；「混合」= 30% 官方 + 70% 我哋（場內 z-score）。
- 前置馬唔多，邊匹願意主動搶位會直接影響前中段落位。

**📊 全場綜合戰力排名**

| 排名 | 馬號 | 馬名 | 綜合戰力分 | Grade |
|---:|---:|---|---:|---|
| 1 | 4 | African Daisy | 79.9 | A- |
`;

test("預測起步位表唔會靜靜消失", () => {
  const api = loadTemplateFunctions();
  const overview = api.parseBattlefieldOverview(SPEEDMAP_OVERVIEW);
  assert.ok(overview.speedmap, "要認得預測定位表");
  // vm context 出嚟嘅 Array 唔同 realm，deepEqual 會因為 prototype 唔同而失敗
  assert.equal(JSON.stringify(overview.speedmap.headers),
               JSON.stringify(["預測定位", "馬號", "馬名", "我哋", "官方", "混合"]));
  assert.equal(overview.speedmap.rows.length, 3);
  // 認得之後表就要由 notes 剷走，唔可以又出圖又出表
  assert.ok(!/\|\s*預測定位/.test(overview.notes));
  // 2026-09-02: 四句固定樣板（未納入步速預測 / 前置馬唔多 / 留後馬若入直路 /
  // 「資料」=…）應 Kelvin 要求剷走。第一句尤其唔可以留 —— 佢寫住「未納入步速
  // 預測」，而個圖就喺佢上面，兩者互相矛盾。
  assert.doesNotMatch(overview.notes, /前置馬唔多|未納入步速預測|留後馬若入直路|評分建基於幾多真數據/);
});

test("預測起步位畫成圖，而且標返兩個來源嘅分歧", () => {
  const api = loadTemplateFunctions();
  const overview = api.parseBattlefieldOverview(SPEEDMAP_OVERVIEW);
  const svg = api.speedMapSvgFromTable(overview.speedmap);
  assert.match(svg, /speedmap-forecast/);
  assert.match(svg, /African Daisy/);
  assert.match(svg, /官方 Speedmap/);
  // Catahoula 我哋 6.8 / 官方 2 —— 分歧 4.8，一定要標出嚟
  assert.match(svg, /分歧 4\.8/);
});

test("battlefield 整體出到個圖", () => {
  const api = loadTemplateFunctions();
  const html = api.renderBattlefieldOverview(SPEEDMAP_OVERVIEW, []);
  assert.match(html, /speedmap-forecast/);
  assert.match(html, /African Daisy/);
  // 圖例已經講咗「混合 = 30% 官方」，唔好再喺 notes 出多次同一句
  assert.equal((html.match(/近仗起步位加權平均/g) || []).length, 0);
});

test("冇預測起步位表嘅舊報告照樣行", () => {
  const api = loadTemplateFunctions();
  const overview = api.parseBattlefieldOverview(`## [第一部分] 🗺️ 戰場全景

| 項目 | 內容 |
|:---|:---|
| 出馬數 | 8 |

- 形勢推演暫時以跑法分佈為主。
`);
  assert.equal(overview.speedmap, null);
  assert.equal(api.speedMapSvgFromTable(overview.speedmap || { headers: [], rows: [] }), "");
});


// ── 賽道幾何條 ────────────────────────────────────────────────────────────
// 數據由 payload 嚟（`meeting.track_geometry`），唔係由報告文字 parse ——
// 所以舊報告唔使重新渲染都有。96 個場地得 85 個有數，另外 11 個要留白唔好出空格。
test("賽道幾何有數就顯示", () => {
  const api = loadTemplateFunctions();
  const html = api.renderTrackGeometry({
    circumference_m: 2087, straight_m: 491, direction: "anticlockwise",
    classification: "Metropolitan", surface: "Turf",
  });
  assert.match(html, /2087m/);
  assert.match(html, /491m/);
  assert.match(html, /逆時針/);
  assert.match(html, /Metropolitan/);
});

test("賽道幾何冇數就唔出格，唔好出空欄", () => {
  const api = loadTemplateFunctions();
  assert.equal(api.renderTrackGeometry(null), "");
  assert.equal(api.renderTrackGeometry({}), "");
  // Broome 呢類：兩個來源加人手都查唔到
  assert.equal(api.renderTrackGeometry({ circumference_m: 0, straight_m: 0 }), "");
});

test("只有周長冇直路都出得（Hawkesbury 呢類）", () => {
  const api = loadTemplateFunctions();
  const html = api.renderTrackGeometry({ circumference_m: 2070, straight_m: 0, direction: "clockwise" });
  assert.match(html, /2070m/);
  assert.match(html, /順時針/);
  assert.ok(!/直路/.test(html), "冇直路數據就唔應該出「直路」");
});

test("battlefield 會將賽道幾何畫埋入去", () => {
  const api = loadTemplateFunctions();
  const html = api.renderBattlefieldOverview(SPEEDMAP_OVERVIEW, [],
    { circumference_m: 1805, straight_m: 173, direction: "anticlockwise" });
  assert.match(html, /1805m/);
  assert.match(html, /173m/);
  // 冇傳幾何嘅時候唔可以爆
  assert.doesNotThrow(() => api.renderBattlefieldOverview(SPEEDMAP_OVERVIEW, []));
});


test("trackwork timeline lists gallops and trials with times and the 從化 stay", () => {
  const { renderTrackworkTimeline } = loadTemplateFunctions();
  const html = renderTrackworkTimeline({ trackwork_timeline: {
    window_days: 21, gallops: 3, trials: 1, trotting: 18, swimming: 18, gallop_trend: "放緩",
    race_jockey_involved: true, readiness: 95,
    conghua_stay: { from: "2026-09-20", to: "2026-10-08", days: 19 },
    work: [{ date: "2026-09-28", type: "試閘", location: "從化 草地", time: 56.9, sectionals: [21.3, 22.3], rider: "潘明輝", gear: "" }],
  }});
  assert.match(html, /晨操時間線/);
  assert.match(html, /從化 2026-09-20 → 2026-10-08（19 日/);
  assert.match(html, /試閘<\/td><td>從化 草地<\/td><td>56\.9<\/td><td>21\.3 \/ 22\.3/);
  assert.equal(renderTrackworkTimeline({}), "");
});


test("bet summary floats only with confirmed bets and separates pending from settled", () => {
  const meeting = { date: "2026-10-14", venue: "HappyValley", region: "hkjc", analysts: ["Kelvin"] };
  const horses = [1, 2].map(n => ({horse_number:n, horse_name:`Horse ${n}`, final_grade:"A"}));
  const data = { meetings:[meeting], races:{"2026-10-14|HappyValley":{meeting, races_by_analyst:{Kelvin:[{
    race_number:9, horses, top_picks:horses.map((h,i)=>({...h,rank:i+1,grade:"A"})),
  }]}}}, consensus:{}, roi:{} };
  const context = loadTemplateFunctions(data);
  context.setSelectedMeetingForTest(meeting);
  let html = context.renderDashboard();
  assert.match(html, /已確認 0 注/);
  assert.doesNotMatch(html, /class="bp-bar bp-bar--fixed"/);
  const state = {
    "bet|2026-10-14|HappyValley|9|1":{confirmed:true,odds:2,result:1},
    "bet|2026-10-14|HappyValley|9|2":{confirmed:true,odds:3,result:null},
  };
  context.setLocalStorageForTest("bets_2026-10-14_HappyValley", state);
  context.loadBettingState();
  html = context.renderDashboard();
  assert.match(html, /class="bp-bar bp-bar--fixed"/);
  assert.match(html, /已確認 2 注/);
  assert.match(html, /1 注待賽果/);
  assert.match(html, /\+\$1\.00/);
  state["bet|2026-10-14|HappyValley|9|2"].scratched = true;
  context.setLocalStorageForTest("bets_2026-10-14_HappyValley", state);
  context.loadBettingState();
  html = context.renderDashboard();
  assert.match(html, /已確認 1 注/);
  assert.match(html, /全部已結算/);
});



test("region switches load that meeting's confirmed bets", () => {
  const hk = {date:"2026-10-14",venue:"HappyValley",region:"hkjc",analysts:["Kelvin"]};
  const au = {date:"2026-10-14",venue:"Ascot",region:"au",analysts:["Kelvin"]};
  const race = {race_number:1,horses:[{horse_number:1,horse_name:"Test",final_grade:"A"}],top_picks:[{horse_number:1,horse_name:"Test",grade:"A",rank:1}]};
  const context = loadTemplateFunctions({meetings:[hk,au],races:{
    "2026-10-14|HappyValley":{meeting:hk,races_by_analyst:{Kelvin:[race]}},
    "2026-10-14|Ascot":{meeting:au,races_by_analyst:{Kelvin:[race]}},
  },consensus:{},roi:{}});
  context.setLocalStorageForTest("bets_2026-10-14_HappyValley",{
    "bet|2026-10-14|HappyValley|1|1":{confirmed:true,odds:2,result:null},
  });
  context.showSport("hkjc");
  assert.match(context.renderDashboard(), /已確認 1 注/);
  context.showSport("au");
  assert.match(context.renderDashboard(), /已確認 0 注/);
  context.showSport("hkjc");
  assert.match(context.renderDashboard(), /已確認 1 注/);
});


test("AU full-time banner distinguishes published legacy and captured new predictions", () => {
  const { renderAuFullTimeStatus } = loadTemplateFunctions();
  const legacy = renderAuFullTimeStatus({});
  assert.match(legacy, /2026-10-16/);
  assert.match(legacy, /發布時模型/);
  const current = renderAuFullTimeStatus({ full_time_speed: { status: "ready", covered: 4, field_size: 10 }});
  assert.match(current, /4\/10/);
  assert.match(current, /缺資料嘅馬今項維持中性/);
  assert.doesNotMatch(current, /發布時模型/);
});


test("horse card shows captured full-time index and actual contribution, not an invented speed score", () => {
  const { renderHorseCard } = loadTemplateFunctions();
  const horse = { horse_number: 1, horse_name: "Time Horse", full_time_speed: {
    status: "observed", context_index: 101.25, latest_kmh: 61.23, contribution: -0.4,
  }};
  const current = renderHorseCard(horse);
  assert.match(current, /101\.25/);
  assert.match(current, /61\.23 km\/h/);
  assert.match(current, /-0\.40 分/);
  const missing = renderHorseCard({ ...horse, full_time_speed: { status: "no_matched_formal_runs" }});
  assert.match(missing, /今項中性 0 分/);
  assert.doesNotMatch(renderHorseCard({ horse_number: 1, horse_name: "Legacy" }), /全程情境指數/);
});


test("speed signal scores stay separate from signed seconds in the value", () => {
  const { renderSubScoreDetails } = loadTemplateFunctions();
  for (const [line, score, tone, label] of [
    ["· 最快第一段（-0.17s） +2.0　第一段曾快過標準", "+2.0", "up", "頭段速度（-0.17s）"],
    ["· 頭段速度（+0.90s） -2.0　第一段明顯慢", "-2.0", "down", "頭段速度（+0.90s）"],
    ["· 頭段速度（+0.10s） 0　第一段接近標準", "0", "flat", "頭段速度（+0.10s）"],
    ["· 步速修正等級（近 3 仗修正平均: +1.4s） +0.7　接近標準平均", "+0.7", "up", "步速修正等級（近 3 仗修正平均: +1.4s）"],
    ["· L400 絕對值（23.86s） 0　末段一般（23.6–24.0s）", "0", "flat", "L400 絕對值（23.86s）"],
    ["· 頭段速度(-0.17s) +2.0 第一段曾快過標準", "+2.0", "up", "頭段速度(-0.17s)"],
  ]) {
    const html = renderSubScoreDetails([{ text: line }], "");
    assert.ok(html.includes(`dim-adj--${tone}`), html);
    assert.ok(html.includes(`<span class="dim-adj__num">${score}</span>`), html);
    assert.ok(html.includes(label), html);
    assert.doesNotMatch(html, /最快第一段/);
  }
});

test("SGM quote expiry stops an already-rendered static recommendation", () => {
  const now = Date.now();
  const item = { id: "nba:quote", sport: "nba", event_date: "2099-01-01", event_name: "BOS @ LAL",
    market: "Same Game Multi", selection: "quoted combo", odds: 2, odds_status: "sportsbet_sgm_quoted",
    outcome: "pending", decision: "BET", bet_type: "combo", legs: [], metrics: {},
    sgm_quote: { captured_at: new Date(now - 400000).toISOString() },
    quote_expires_at: new Date(now - 100000).toISOString(), start_time_utc: "2099-01-01T00:00:00Z" };
  const data = { ...EMPTY_DASHBOARD_DATA, sports_feed: { sports: { nba: {
    validation_status: "valid", recommendations: [item] } } } };
  const { hasLiveSportsFeed, renderHistoryCard, renderInlineBetDraft } = loadTemplateFunctions(data);
  assert.equal(hasLiveSportsFeed("nba"), false);
  assert.doesNotMatch(renderHistoryCard(item, "nba"), /onsubmit=/);
  assert.match(renderInlineBetDraft(item, "nba"), /SGM 報價已過期/);
  const fresh = { ...item, sgm_quote: { captured_at: new Date(now - 1000).toISOString() },
    quote_expires_at: new Date(now + 299000).toISOString() };
  assert.match(renderHistoryCard(fresh, "nba"), /onsubmit=/);
  assert.match(renderHistoryCard(fresh, "nba"), /Sportsbet SGM 報價/);
});

test("expired SGM remains visible as analysis without any confirmation form", () => {
  const now = Date.now();
  const item = { id: "nba:analysis", sport: "nba", validation_status: "valid", event_date: "2099-01-01", event_name: "BKN @ CLE",
    market: "Same Game Multi", selection: "Verified two-leg SGM", odds: 3.5, odds_status: "sportsbet_sgm_quoted",
    outcome: "pending", decision: "BET", bet_type: "combo", legs: [{ selection: "First Star 20+" }, { selection: "Second Star 5+" }], metrics: {},
    sgm_quote: { captured_at: new Date(now-400000).toISOString() }, quote_expires_at: new Date(now-100000).toISOString(), start_time_utc: "2099-01-01T00:00:00Z" };
  const data = { ...EMPTY_DASHBOARD_DATA, sports_feed: { sports: { nba: { validation_status: "valid", recommendations: [item] } } } };
  const api=loadTemplateFunctions(data);
  assert.equal(api.hasLiveSportsFeed("nba"), false);
  const cards=api.sportsHistory("nba");
  assert.equal(cards.length,1);
  assert.equal(cards[0].analysis_only,true);
  assert.equal(cards[0].decision,"OBSERVE");
  const html=api.renderSportsHistory("nba");
  assert.match(html,/已保存 SGM 分析/);
  assert.match(html,/快照賠率（非即時）/);
  assert.match(html,/First Star 20\+/);
  assert.doesNotMatch(html,/onsubmit=/);
  assert.match(api.renderInlineBetDraft(cards[0],"nba"),/SGM 報價已過期/);
});

test("a blocked current feed may show proven published analysis without claiming live picks", () => {
  const card={ id:"nba:saved",sport:"nba",event_name:"BKN @ CLE",event_date:"2099-01-01",analysis_only:true,
    decision:"OBSERVE",outcome:"pending",bet_type:"combo",selection:"Saved SGM",odds:3.5,metrics:{},
    legs:[{selection:"Verified Player 20+"},{selection:"Other Player 5+"}],published_at:"2026-10-24T00:00:00Z" };
  const api=loadTemplateFunctions({...EMPTY_DASHBOARD_DATA,sports_feed:{sports:{nba:{validation_status:"blocked",recommendations:[],analysis_cards:[card]}}}});
  assert.equal(api.hasLiveSportsFeed("nba"),false);
  assert.equal(api.sportsHistory("nba").length,1);
  const html=api.renderSportsHistory("nba");
  assert.match(html,/已驗證賽前 SGM 分析/);
  assert.doesNotMatch(html,/onsubmit=/);
  assert.doesNotMatch(html,/呢批係真實 Reflector 案例/);
});


test("malformed or future SGM quotes cannot become saved analysis", () => {
  const now=Date.now();
  const base={id:"nba:bad",sport:"nba",validation_status:"valid",odds_status:"sportsbet_sgm_quoted",decision:"BET",event_date:"2099-01-01",start_time_utc:"2099-01-01T00:00:00Z"};
  for (const quote of [
    {sgm_quote:{captured_at:"invalid"},quote_expires_at:new Date(now-1000).toISOString()},
    {sgm_quote:{captured_at:new Date(now+1000).toISOString()},quote_expires_at:new Date(now+300000).toISOString()},
    {sgm_quote:{captured_at:new Date(now-1000).toISOString()},quote_expires_at:"invalid"},
  ]) {
    const api=loadTemplateFunctions({...EMPTY_DASHBOARD_DATA,sports_feed:{sports:{nba:{validation_status:"valid",recommendations:[{...base,...quote}]}}}});
    assert.equal(api.sportsAnalysisCards("nba").length,0);
    assert.equal(api.hasLiveSportsFeed("nba"),false);
  }
});


test("a completed NBA NO BET run explains zero qualified SGM above historical cases", () => {
  const api=loadTemplateFunctions({...EMPTY_DASHBOARD_DATA,
    sports_feed:{sports:{nba:{validation_status:"blocked",analysis_run_id:"nba:2026-10-25",warnings:["no_validated_nba_combos"],source_files:["Game_BKN_CLE_Full_Analysis.md"],recommendations:[]}}},
    sports_history:{nba:[{id:"old",sport:"nba",event_name:"old game",outcome:"review",legs:[],metrics:{}}]}});
  const html=api.renderSportsHistory("nba");
  assert.match(html,/2026-10-25 冇合格建議/);
  assert.match(html,/分析已完成/);
  assert.doesNotMatch(html,/分析未通過發佈檢查/);
});


test("latest NBA analysis replaces historical fallback even when no BET qualifies", () => {
  const latest={event_date:"2099-10-25",coverage:{analysed_games:1,review_candidates:1},games:[{
    game_tag:"BKN_CLE",event_name:"BKN @ CLE",status:"analysed",status_reason:"賽前分析已保存。",market_count:100,positive_ev_count:5,formal_sgm_count:0,
    report_markdown:"LATEST FULL GAME REPORT",player_markets:[{player:"Actual Star",market:"pts",line:20,odds:1.5,model_probability:.6,l10_hit_rate:.8,expected_value:-.1}],
    diagnostics:{player_candidates:90,positive_edge_candidates:5,positive_edge_and_l10_50:1,banker_funnel:{fallback:{remaining:{recent_hits:12,nonnegative_edge:0,reflector:0}}}},
    review_candidates:[{label:"較低倍率",analysis_only:true,decision:"OBSERVE",odds:1.8,quote_status:"expired",model_probability:.5,expected_value:-.1,
      reasons:["未通過正式投注閘"],legs:[{selection:"Actual Star PTS 20+",odds:1.5},{selection:"Another Star REB 5+",odds:1.4}]}]}]};
  const api=loadTemplateFunctions({...EMPTY_DASHBOARD_DATA,sports_feed:{sports:{nba:{analysis_run_id:"nba:2099-10-25",validation_status:"blocked",recommendations:[],latest_analysis:latest}}},
    sports_history:{nba:[{id:"old",event_name:"OLD APRIL CASE",legs:[],metrics:{},outcome:"review"}]}});
  api.setSportsTab("roi");
  const html=api.renderSportsWorkspace("nba");
  assert.match(html,/賽前分析/);assert.match(html,/BKN @ CLE/);assert.match(html,/Actual Star PTS 20\+/);
  assert.match(html,/LATEST FULL GAME REPORT/);assert.match(html,/已過期，需刷新/);assert.match(html,/SGM 候選/);
  assert.match(html,/穩膽 fallback：近期命中率合格 12 腿/);assert.match(html,/同時非負 edge 0 腿/);
  assert.match(html,/真實組合價 ≥2.0/);
  assert.doesNotMatch(html,/OLD APRIL CASE/);assert.doesNotMatch(html,/Reflector/);assert.doesNotMatch(html,/onsubmit=/);
  api.setSportsTab("archive");assert.match(api.renderSportsWorkspace("nba"),/OLD APRIL CASE/);
  api.setSportsTab("roi");assert.match(api.renderSportsWorkspace("nba"),/LATEST FULL GAME REPORT/);
});

test("latest NBA view includes unopened and insufficient-data games", () => {
  const latest={event_date:"2099-10-25",coverage:{analysed_games:0,pending_games:2},games:[
    {event_name:"MIL @ PHI",status:"waiting_player_markets",status_reason:"球員市場未開"},
    {event_name:"MIA @ CHA",status:"data_insufficient",status_reason:"資料未達完整分析要求"}]};
  const api=loadTemplateFunctions({...EMPTY_DASHBOARD_DATA,sports_feed:{sports:{nba:{validation_status:"blocked",recommendations:[],latest_analysis:latest}}}});
  api.setSportsTab("roi");
  const html=api.renderSportsWorkspace("nba");
  assert.match(html,/MIL @ PHI/);assert.match(html,/MIA @ CHA/);assert.match(html,/等候開盤/);assert.match(html,/資料不足/);
});


test("NBA dashboard embeds periods and counts only verified paper results", () => {
  const day=new Intl.DateTimeFormat('en-CA',{timeZone:'Australia/Sydney'}).format(new Date());
  const row=(id,state,odds,legs)=>({id,day,event_name:'BOS @ NYK',stake:1,odds,state,legs});
  const legs=[{player:'<script>alert(1)</script>',stat:'PTS',line:20,state:'won',actual:25},{player:'Other',stat:'REB',line:6,state:'lost',actual:4}];
  const api=loadTemplateFunctions({...EMPTY_DASHBOARD_DATA,sports_feed:{sports:{nba:{tracking:{status:'valid',records:[row('a','won',2.5,[legs[0]]),row('b','lost',2.2,legs),row('c','pending',2.4,[{...legs[0],state:'pending'}]),row('d','unpriced',2.3,[{...legs[0],state:'void'}])]}}}}});
  const rows=api.nbaRecords(), metrics=api.nbaStats(rows);
  assert.equal(metrics.n,4);assert.equal(metrics.decided,2);assert.equal(metrics.wins,1);
  assert.equal(metrics.profit,.5);assert.equal(metrics.roi,25);
  assert.equal(metrics.legN,3);assert.equal(metrics.legWins,2);
  const html=api.renderSportsWorkspace('nba');
  assert.doesNotMatch(html,/class="dashboard-periods"|setNbaPeriod/);assert.match(html,/\+25%/);
  assert.match(html,/每注 \$1/);assert.doesNotMatch(html,/<script>alert/);
  assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/示範結算/);
});

test("missing NBA evidence shows unavailable rather than a zero-return claim",()=>{
  const api=loadTemplateFunctions(EMPTY_DASHBOARD_DATA),html=api.renderSportsWorkspace('nba');
  assert.match(html,/紀錄暫未能讀取/);assert.doesNotMatch(html,/ROI<\/span>/);
});



test("expired saved Kawhi Barrett analysis never appears above the latest slate",()=>{
 const card={id:'nba:2099-10-26:TOR_MIN:combo:1',sport:'nba',event_date:'2099-10-26',event_name:'TOR @ MIN',analysis_only:true,decision:'OBSERVE',validation_status:'analysis_only',odds_status:'published_snapshot_price',odds:3.5,legs:[{selection:'Kawhi Leonard REB 6+'},{selection:'RJ Barrett PTS 20+'}]};
 const api=loadTemplateFunctions({...EMPTY_DASHBOARD_DATA,sports_feed:{sports:{nba:{validation_status:'blocked',recommendations:[],analysis_cards:[card],latest_analysis:{event_date:'2099-10-26',coverage:{analysed_games:1},games:[{event_name:'TOR @ MIN',status:'analysed',market_count:0,formal_sgm_count:0,review_candidates:[],player_markets:[]}]}}}}});
 api.setSportsTabForTest('roi');const html=api.renderSportsWorkspace('nba');
 assert.match(html,/TOR @ MIN/);assert.doesNotMatch(html,/Kawhi Leonard|RJ Barrett|已驗證 SGM/);
 assert.equal(api.sportsAnalysisCards('nba').length,1); // Archived evidence remains intact.
});


test("Sydney history labels preserve winter dates without a hard-coded DST offset",()=>{
 const api=loadTemplateFunctions(EMPTY_DASHBOARD_DATA);
 assert.match(api.nbaShortDate('2026-07-25'),/25\/7/);
 assert.match(api.nbaShortDate('2026-10-25'),/25\/10/);
});


test("NBA refreshes read-only tracking views while preserving drafts and preventing edge reload loops",()=>{
 const api=loadTemplateFunctions(EMPTY_DASHBOARD_DATA);
 api.showSport('nba');api.setVisibilityForTest('visible');
 assert.equal(api.nbaShouldAutoRefresh('new-version'),true);
 api.setSportsTabForTest('archive');assert.equal(api.nbaShouldAutoRefresh('new-version'),true);
 api.setSportsTabForTest('bets');assert.equal(api.nbaShouldAutoRefresh('new-version'),false);
 api.setSportsTabForTest('roi');assert.equal(api.nbaShouldAutoRefresh('new-version'),false);
 api.setSportsTabForTest('history');api.setFocusedElementForTest({tagName:'INPUT'});
 assert.equal(api.nbaShouldAutoRefresh('new-version'),false);
 api.setFocusedElementForTest(null);api.setSeenAutoVersionForTest('new-version');
 assert.equal(api.nbaShouldAutoRefresh('new-version'),false);
 assert.equal(api.nbaShouldAutoRefresh('next-version'),true);
 api.setVisibilityForTest('hidden');assert.equal(api.nbaShouldAutoRefresh('next-version'),false);
});


test("a newly deployed result refreshes NBA tracking once and stores the selected view",async()=>{
 const api=loadTemplateFunctions({...EMPTY_DASHBOARD_DATA,meta:{generated_at:'2000-01-01T00:00:00'}});
 api.showSport('nba');api.setSportsTabForTest('archive');api.setVisibilityForTest('visible');
 let reloads=0;api.setReloadForTest(()=>{reloads++});
 api.setFetchForTest(async()=>new Response(JSON.stringify({generated_at:'2000-01-02T00:00:00'}),{status:200}));
 await api.checkForNewSnapshot();assert.equal(reloads,1);
 api.resetSnapshotClockForTest();await api.checkForNewSnapshot();assert.equal(reloads,1);
});


test("history has embedded week month all only, never today's dashboard heading",()=>{
 const api=loadTemplateFunctions({...EMPTY_DASHBOARD_DATA,sports_feed:{sports:{nba:{tracking:{status:'valid',records:[]}}}}});
 api.setSportsTabForTest('archive');const html=api.renderSportsWorkspace('nba');
 assert.match(html,/歷史投注表現/);assert.match(html,/累積淨利/);assert.doesNotMatch(html,/今日投注表現|setNbaPeriod\('history','day'\)/);
 for(const period of ['week','month','all']) assert.ok(html.includes("setNbaPeriod('history','"+period+"')"));
 assert.match(html,/class="dashboard-periods"/);
});

test("research candidates including unquoted legs are tracked without invented ROI",()=>{
 const day=new Intl.DateTimeFormat('en-CA',{timeZone:'Australia/Sydney'}).format(new Date());
 const api=loadTemplateFunctions({...EMPTY_DASHBOARD_DATA,sports_feed:{sports:{nba:{tracking:{status:'valid',records:[{id:'r',day,event_name:'BOS @ NYK',stake:1,odds:null,state:'unpriced',tracking_kind:'research',legs:[{player:'Test',stat:'PTS',line:20,state:'won',actual:25}]}]}}}}});
 const stats=api.nbaStats(api.nbaRecords());assert.equal(stats.n,1);assert.equal(stats.legWins,1);assert.equal(stats.roi,null);assert.equal(stats.sgm,100);
 const html=api.renderSportsWorkspace('nba');assert.match(html,/研究候選/);assert.match(html,/待核價/);assert.match(html,/expanded-legs/);assert.doesNotMatch(html,/累積淨利|dashboard-chart|查看 1 腳及賽果/);assert.match(html,/球衣/);assert.doesNotMatch(html,/null 倍/);
});
