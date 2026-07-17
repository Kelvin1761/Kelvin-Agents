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
      renderHorseCard,
      buildHorseAnalysisSections,
      parseChronologySeries,
      renderChronologySeries,
      formatRichSection,
      renderDataReadoutItem,
      sanitizeBattlefieldOverviewText,
      renderBattlefieldOverview,
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
