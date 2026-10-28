# NBA dashboard implementation

Goal: deliver approved blue dashboard with Hong Kong font, automatic SVG jerseys,
history-only embedded periods, $1 model tracking, and verified game-result updates.

- [x] Scope all NBA styling; retain Tennis/racing and actual D1 ledger workflows.
- [x] Rebuild first formal banker or current steady research candidate from hash-verified pre-tip snapshots; never product-of-leg prices; label research separately.
- [x] Freeze one $1 model entry per date/game; use canonical verified Final settlements. Void stays unpriced; a verified known miss remains a loss even if another player is unresolved.
- [x] Today-only panel and history week/month/all counts, separate SGM/leg accuracy, dollar P&L, progress and history; reduced-motion support.
- [x] Source-based polling: first check tip+150m, 15m retry, skip fully settled games; bounded 8h automatic window, later nightly recovery.
- [x] Existing postgame job has a 900s cheap local timer, but no provider call until due. Fetch detailed boxes only for due tags; merge cached other games atomically.
- [x] Preserve 18:30/21:30 Sydney archive jobs and shared schedule lock; per-quarter control-plane slots prevent duplicate work. No new launchd label.
- [x] Targeted tracking, XSS, timing/finality and UI tests; real-data export smoke.
- [x] Visible read-only NBA tracking views auto-load newly deployed results, preserve period/view, protect drafts and avoid edge-cache reload loops.
- [x] Expired saved SGM cards (including Kawhi/RJ) no longer prepend to latest analysis; actual and historical records remain intact.
- [x] Browser/mobile verification on real data (320/375/390px), empty-state and populated fixture tests.
- [ ] Complete clean-SHA release gate and exact-scope release (integrated main 102d8d5e).
- [ ] Verify deployed SHA, page, installed timer and runtime health.

Runtime: no actual sportsbook wagers and no automated D1 POST/apply. The model and
EV thresholds are unchanged. History lacking publication evidence is not backfilled
as a bet; legacy cases remain separately accessible. Cached cold history survives
other-domain deploys; locally covered dates remain authoritative.

Expected results: the first current steady research selection (or formal banker when absent) appears once, at its original quote;
verified game outcomes update simulated $1 performance without waiting for all games
to finish. No missing source, partial box score or overtime is counted as a loss.

Rollback: the active production SHA captured in Central's immutable release manifest;
Central's runtime installer snapshots/restores existing plists. D1 and prediction
artifacts are not modified by dashboard rendering. Production gate and activation
must pass before claiming deployment.

User scope update: research OBSERVE candidates join model simulation, without changing live EV release gates. Freeze the first per-game publication; missing real SGM quotes contribute leg accuracy but no monetary ROI. Today has no period switch; history offers week/month/all only.

When both arms exist in one snapshot, track the current steady research arm, keeping legacy formal publication evidence outside this model cohort. Never replace a frozen earlier-game record with a later revised selection.

Final today view: no cumulative-profit chart or period buttons; every game has always-visible legs with automatic team jerseys. History retains the cumulative-profit chart and week/month/all controls.
