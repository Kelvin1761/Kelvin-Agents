/**
 * 旺財街機 — 賽事突發事件系統
 * 模擬真實賽馬嘅隨機事件：
 * - 慢閘 (slow start)
 * - 阻擋 (interference)
 * - 拉馬 (pull up / easing)
 * - 爆發 (burst of speed)
 * - 失蹄 (stumble)
 * - 研訊 (stewards inquiry flag)
 */

const EVENT_TYPES = {
  SLOW_GATE:     'slow_gate',
  INTERFERENCE:  'interference',
  PULL_UP:       'pull_up',
  BURST:         'burst',
  STUMBLE:       'stumble',
  WIDE_RUN:      'wide_run',
};

// Event probability per second (adjusted by phase)
const EVENT_CHANCES = {
  [EVENT_TYPES.SLOW_GATE]:    { phases: [0],    chance: 0.08 },  // 8% per sec during gate
  [EVENT_TYPES.INTERFERENCE]: { phases: [1, 2], chance: 0.005 }, // 0.5% per sec
  [EVENT_TYPES.PULL_UP]:      { phases: [2, 3], chance: 0.002 }, // 0.2% per sec
  [EVENT_TYPES.BURST]:        { phases: [3],    chance: 0.015 }, // 1.5% per sec during sprint
  [EVENT_TYPES.STUMBLE]:      { phases: [1, 2], chance: 0.003 }, // 0.3% per sec
  [EVENT_TYPES.WIDE_RUN]:     { phases: [2],    chance: 0.01 },  // 1% per sec in bends
};

export class EventSystem {
  constructor(runners, rng) {
    this.rng = rng;
    this.events = [];      // All events that have occurred
    this.activeEffects = new Map(); // runner id → [{ type, remaining, modifier }]
    this.hasSlowGate = new Set();   // Track which runners had slow gate
    this.stewardsFlags = [];        // Interference events → potential inquiry

    for (const r of runners) {
      this.activeEffects.set(r.id, []);
    }
  }

  /**
   * Check and trigger events each physics tick
   * @param {Array} runners - all runners (sorted by position)
   * @param {number} dt - delta time
   * @param {number} phase - current phase (0-3)
   * @param {Map} trafficStates - from TrafficSystem
   * @returns {Map} runner id → { speedMod, laneShift, event }
   */
  update(runners, dt, phase, trafficStates) {
    const results = new Map();

    for (const r of runners) {
      if (r.finished) {
        results.set(r.id, { speedMod: 1.0, laneShift: 0, event: null });
        continue;
      }

      let speedMod = 1.0;
      let laneShift = 0;
      let triggeredEvent = null;

      // ── Check for new events ──
      for (const [type, config] of Object.entries(EVENT_CHANCES)) {
        if (!config.phases.includes(phase)) continue;

        // Adjust chance based on runner stats
        let adjustedChance = config.chance * dt;
        adjustedChance *= this._getEventProbModifier(r, type);

        if (this.rng() < adjustedChance) {
          triggeredEvent = this._triggerEvent(r, type, phase, trafficStates);
          if (triggeredEvent) break; // Only one event per tick per runner
        }
      }

      // ── Process active effects ──
      const effects = this.activeEffects.get(r.id) || [];
      const remaining = [];
      for (const eff of effects) {
        eff.remaining -= dt;
        if (eff.remaining > 0) {
          speedMod *= eff.speedMod || 1.0;
          laneShift += eff.laneShift || 0;
          remaining.push(eff);
        }
      }
      this.activeEffects.set(r.id, remaining);

      results.set(r.id, { speedMod, laneShift, event: triggeredEvent });
    }

    return results;
  }

  /**
   * Modify event probability based on runner's attributes
   */
  _getEventProbModifier(runner, eventType) {
    switch (eventType) {
      case EVENT_TYPES.SLOW_GATE:
        // Bad gate speed = more likely to have slow start
        return (1.2 - (runner.gateSpeed || 1.0)) * 2;
      case EVENT_TYPES.BURST:
        // High burst chance runners more likely
        return (runner.burstChance || 0.1) * 5;
      case EVENT_TYPES.STUMBLE:
        // Low consistency = more likely to stumble
        return (1 - (runner.consistency || 0.7)) * 2;
      case EVENT_TYPES.PULL_UP:
        // Low energy = more likely to pull up
        return runner.energy < 20 ? 3.0 : runner.energy < 40 ? 1.5 : 0.5;
      default:
        return 1.0;
    }
  }

  /**
   * Trigger a specific event
   */
  _triggerEvent(runner, type, phase, trafficStates) {
    // Prevent duplicate slow gate
    if (type === EVENT_TYPES.SLOW_GATE && this.hasSlowGate.has(runner.id)) return null;

    const event = {
      type,
      runnerId: runner.id,
      runnerName: runner.name,
      position: runner.position,
      time: 0, // Will be set by physics engine
      phase,
    };

    switch (type) {
      case EVENT_TYPES.SLOW_GATE:
        this.hasSlowGate.add(runner.id);
        this.activeEffects.get(runner.id).push({
          type, remaining: 1.5 + this.rng() * 1.0,
          speedMod: 0.6,
        });
        event.description = `${runner.name} 慢閘！起步大失位置`;
        break;

      case EVENT_TYPES.INTERFERENCE:
        this.activeEffects.get(runner.id).push({
          type, remaining: 0.8 + this.rng() * 0.5,
          speedMod: 0.85,
          laneShift: (this.rng() > 0.5 ? 1 : -1),
        });
        event.description = `${runner.name} 受到阻擋，被迫轉線！`;
        this.stewardsFlags.push(event);
        break;

      case EVENT_TYPES.PULL_UP:
        this.activeEffects.get(runner.id).push({
          type, remaining: 2.0 + this.rng() * 2.0,
          speedMod: 0.70,
        });
        event.description = `${runner.name} 被騎師拉停，似乎有問題！`;
        break;

      case EVENT_TYPES.BURST:
        this.activeEffects.get(runner.id).push({
          type, remaining: 1.0 + this.rng() * 0.5,
          speedMod: 1.15 + this.rng() * 0.10,
        });
        event.description = `${runner.name} 突然加速！末段猛衝！`;
        break;

      case EVENT_TYPES.STUMBLE:
        this.activeEffects.get(runner.id).push({
          type, remaining: 0.5 + this.rng() * 0.3,
          speedMod: 0.75,
        });
        event.description = `${runner.name} 失蹄一步，即時回復`;
        break;

      case EVENT_TYPES.WIDE_RUN:
        this.activeEffects.get(runner.id).push({
          type, remaining: 1.5 + this.rng() * 1.0,
          speedMod: 0.95,
          laneShift: 2,
        });
        event.description = `${runner.name} 被迫跑出外檔`;
        break;
    }

    this.events.push(event);
    return event;
  }

  /**
   * Get all events for race result / commentary
   */
  getEvents() { return this.events; }

  /**
   * Check if stewards inquiry should be called
   */
  shouldCallStewards() {
    return this.stewardsFlags.length >= 2;
  }

  /**
   * Get active effects for HUD display
   */
  getActiveEffectsForRunner(runnerId) {
    return (this.activeEffects.get(runnerId) || []).map(e => e.type);
  }
}
