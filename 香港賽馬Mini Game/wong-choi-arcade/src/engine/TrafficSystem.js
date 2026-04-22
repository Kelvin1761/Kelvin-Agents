/**
 * 旺財街機 — 疊位系統 (Traffic System)
 * 管理馬匹之間嘅空間關係：
 * - 避免重疊 (collision avoidance)
 * - 被困 (boxed in)
 * - 搵位突圍 (finding gaps)
 * - 內外檔策略 (inside/outside bias)
 * - 氣流效應 (drafting/slipstream)
 */

const LANE_MIN = 1;
const LANE_MAX = 12;
const MERGE_THRESHOLD = 8;   // 位置差距少於 8m = 太近
const DRAFT_RANGE = 15;       // 氣流效應範圍 (m)
const DRAFT_BONUS = 0.03;     // 氣流速度加成 3%
const BOXED_SPEED_PENALTY = 0.92; // 被困速度懲罰
const LANE_CHANGE_COOLDOWN = 2.0; // 轉 lane 冷卻時間 (秒)

export class TrafficSystem {
  constructor(runners, rng) {
    this.rng = rng;
    this.states = new Map();

    for (const r of runners) {
      this.states.set(r.id, {
        lane: r.lane,
        targetLane: r.lane,
        laneChangeTimer: 0,
        isBoxedIn: false,
        isDrafting: false,
        draftFrom: null,
        wideRunning: false,
      });
    }
  }

  /**
   * Update traffic states — called each physics tick
   * @param {Array} runners - sorted by position (leader first)
   * @param {number} dt - delta time
   * @param {number} phase - current race phase (0-3)
   * @returns {Map} - runner id → { lane, speedModifier, isBoxedIn, isDrafting }
   */
  update(runners, dt, phase) {
    const results = new Map();

    // Build spatial grid: lane → [runners sorted by position]
    const laneGrid = new Map();
    for (const r of runners) {
      const st = this.states.get(r.id);
      if (!st) continue;
      const lane = st.lane;
      if (!laneGrid.has(lane)) laneGrid.set(lane, []);
      laneGrid.get(lane).push(r);
    }

    for (const r of runners) {
      const st = this.states.get(r.id);
      if (!st || r.finished) {
        results.set(r.id, { lane: r.lane, speedMod: 1.0, isBoxedIn: false, isDrafting: false });
        continue;
      }

      let speedMod = 1.0;
      st.laneChangeTimer = Math.max(0, st.laneChangeTimer - dt);

      // ── 1. Check boxed in ──
      st.isBoxedIn = this._checkBoxedIn(r, st.lane, runners, laneGrid);
      if (st.isBoxedIn) {
        speedMod *= BOXED_SPEED_PENALTY;
      }

      // ── 2. Check drafting (slipstream) ──
      const draftResult = this._checkDrafting(r, st.lane, runners);
      st.isDrafting = draftResult.drafting;
      st.draftFrom = draftResult.from;
      if (st.isDrafting) {
        speedMod *= (1 + DRAFT_BONUS);
      }

      // ── 3. Lane strategy (AI decision) ──
      if (st.laneChangeTimer <= 0 && phase >= 1) {
        const newLane = this._decideLaneChange(r, st, runners, laneGrid, phase);
        if (newLane !== st.lane) {
          st.targetLane = newLane;
          st.laneChangeTimer = LANE_CHANGE_COOLDOWN;
        }
      }

      // ── 4. Smooth lane transition ──
      if (st.lane !== st.targetLane) {
        const dir = st.targetLane > st.lane ? 1 : -1;
        st.lane += dir * dt * 2.0; // ~0.5s per lane change
        if (Math.abs(st.lane - st.targetLane) < 0.1) {
          st.lane = st.targetLane;
        }
      }

      // ── 5. Inside rail bonus (shorter distance) ──
      if (st.lane <= 3) {
        speedMod *= 1.005; // Very slight inner rail advantage
      } else if (st.lane >= 10) {
        // Wide running — can be beneficial if avoiding traffic
        st.wideRunning = true;
        if (!st.isBoxedIn) speedMod *= 1.002;
      }

      results.set(r.id, {
        lane: Math.round(st.lane * 10) / 10, // 1 decimal place
        speedMod,
        isBoxedIn: st.isBoxedIn,
        isDrafting: st.isDrafting,
      });
    }

    return results;
  }

  /**
   * Check if a runner is boxed in (front + both sides blocked)
   */
  _checkBoxedIn(runner, lane, allRunners, laneGrid) {
    const myPos = runner.position;
    const intLane = Math.round(lane);

    // Front blocked in same lane?
    const sameLane = laneGrid.get(intLane) || [];
    const frontBlocked = sameLane.some(r => 
      r.id !== runner.id && 
      r.position > myPos && 
      r.position - myPos < MERGE_THRESHOLD
    );
    if (!frontBlocked) return false;

    // Check left lane
    const leftLane = intLane - 1;
    const leftBlocked = leftLane < LANE_MIN || (laneGrid.get(leftLane) || []).some(r =>
      Math.abs(r.position - myPos) < MERGE_THRESHOLD
    );

    // Check right lane
    const rightLane = intLane + 1;
    const rightBlocked = rightLane > LANE_MAX || (laneGrid.get(rightLane) || []).some(r =>
      Math.abs(r.position - myPos) < MERGE_THRESHOLD
    );

    return leftBlocked && rightBlocked;
  }

  /**
   * Check if runner can draft behind another
   */
  _checkDrafting(runner, lane, allRunners) {
    const intLane = Math.round(lane);
    for (const other of allRunners) {
      if (other.id === runner.id) continue;
      const otherSt = this.states.get(other.id);
      if (!otherSt) continue;
      
      if (Math.round(otherSt.lane) === intLane &&
          other.position > runner.position &&
          other.position - runner.position < DRAFT_RANGE &&
          other.position - runner.position > 2) {
        return { drafting: true, from: other.name };
      }
    }
    return { drafting: false, from: null };
  }

  /**
   * AI lane change decision
   */
  _decideLaneChange(runner, state, allRunners, laneGrid, phase) {
    const currentLane = Math.round(state.lane);
    const myPos = runner.position;

    // If boxed in → try to escape
    if (state.isBoxedIn) {
      const options = [];
      for (const delta of [-1, 1, -2, 2]) {
        const testLane = currentLane + delta;
        if (testLane < LANE_MIN || testLane > LANE_MAX) continue;
        const occupied = (laneGrid.get(testLane) || []).filter(r =>
          Math.abs(r.position - myPos) < MERGE_THRESHOLD
        );
        if (occupied.length === 0) {
          options.push(testLane);
        }
      }
      if (options.length > 0) {
        // Prefer inner rail
        options.sort((a, b) => a - b);
        return options[0];
      }
    }

    // Sprint phase → move to inner if clear
    if (phase >= 3 && currentLane > 3) {
      const innerLane = currentLane - 1;
      const innerOccupied = (laneGrid.get(innerLane) || []).filter(r =>
        Math.abs(r.position - myPos) < MERGE_THRESHOLD * 1.5
      );
      if (innerOccupied.length === 0) {
        return innerLane;
      }
    }

    // Avoid collision with horse directly ahead
    const sameLane = laneGrid.get(currentLane) || [];
    const ahead = sameLane.find(r =>
      r.id !== runner.id &&
      r.position > myPos &&
      r.position - myPos < MERGE_THRESHOLD
    );
    if (ahead) {
      // Move to less crowded adjacent lane
      const leftCount = (laneGrid.get(currentLane - 1) || []).length;
      const rightCount = (laneGrid.get(currentLane + 1) || []).length;
      if (currentLane > LANE_MIN && leftCount <= rightCount) return currentLane - 1;
      if (currentLane < LANE_MAX) return currentLane + 1;
    }

    return currentLane; // No change
  }
}
