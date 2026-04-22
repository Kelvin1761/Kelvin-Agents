/**
 * 旺財街機 — 物理引擎 v2
 * 4 階段賽事物理 + TrafficSystem + EventSystem
 * 基於 deltaTime，確保跨設備一致性
 */
import seedrandom from 'seedrandom';
import { TrafficSystem } from './TrafficSystem.js';
import { EventSystem } from './EventSystem.js';

const PHASES = {
  GATE:    0,  // 起步 (0-100m)
  EARLY:   1,  // 前段 (100-400m)  
  MID:     2,  // 中段/入彎 (400m - 距離*0.75)
  SPRINT:  3,  // 末段衝刺 (距離*0.75 - finish)
};

const STYLE_MODIFIERS = {
  '領放': { [PHASES.GATE]: 1.15, [PHASES.EARLY]: 1.12, [PHASES.MID]: 1.0,  [PHASES.SPRINT]: 0.92 },
  '居前': { [PHASES.GATE]: 1.05, [PHASES.EARLY]: 1.08, [PHASES.MID]: 1.02, [PHASES.SPRINT]: 0.98 },
  '居中': { [PHASES.GATE]: 0.95, [PHASES.EARLY]: 0.98, [PHASES.MID]: 1.05, [PHASES.SPRINT]: 1.05 },
  '後上': { [PHASES.GATE]: 0.85, [PHASES.EARLY]: 0.90, [PHASES.MID]: 1.02, [PHASES.SPRINT]: 1.18 },
};

export class PhysicsEngine {
  constructor(raceData, seed) {
    this.rng = seedrandom(seed + '_physics');
    this.distance = raceData.distance;
    this.runners = raceData.runners.map(r => this._initRunner(r));
    this.elapsed = 0;
    this.finished = false;
    this.finishOrder = [];
    this.incidents = [];

    // Phase boundaries (meters)
    this.phaseBounds = {
      gate: 100,
      early: 400,
      mid: this.distance * 0.75,
      finish: this.distance,
    };

    // Sub-systems
    this.traffic = new TrafficSystem(this.runners, this.rng);
    this.events = new EventSystem(this.runners, this.rng);
    
    // Event log for HUD display
    this.recentEvents = [];
  }

  _initRunner(runner) {
    const s = runner.horse.stats;
    const jockey = runner.jockey;
    return {
      id: runner.horse.id,
      name: runner.horse.name,
      runner,
      position: 0,           // meters traveled
      speed: 0,              // current speed (m/s)
      lane: runner.barrier,  // 1-12
      energy: s.energyLevel,
      stamina: s.stamina,
      baseSpeed: s.baseSpeed,
      burstChance: s.burstChance,
      burstPower: s.burstPower,
      finalSprint: s.finalSprint,
      consistency: s.consistency,
      gateSpeed: s.gateSpeed,
      runningStyle: s.runningStyle,
      jockeyRating: jockey.rating,
      jockeySkill: jockey.skill,
      pullUp: false,
      finished: false,
      finishTime: null,
      // v2 additions
      isBoxedIn: false,
      isDrafting: false,
      activeEvent: null,
    };
  }

  getPhase(pos) {
    if (pos < this.phaseBounds.gate) return PHASES.GATE;
    if (pos < this.phaseBounds.early) return PHASES.EARLY;
    if (pos < this.phaseBounds.mid) return PHASES.MID;
    return PHASES.SPRINT;
  }

  /**
   * Main update loop
   */
  update(dt) {
    if (this.finished) return this.getState();
    this.elapsed += dt;

    // Determine leader phase for global events
    const sorted = [...this.runners].sort((a, b) => b.position - a.position);
    const leaderPhase = this.getPhase(sorted[0]?.position || 0);

    // ── Run Traffic System ──
    const trafficResults = this.traffic.update(sorted, dt, leaderPhase);

    // ── Run Event System ──
    const eventResults = this.events.update(this.runners, dt, leaderPhase, trafficResults);

    // ── Update each runner ──
    for (const r of this.runners) {
      if (r.finished) continue;

      const phase = this.getPhase(r.position);
      const styleMod = STYLE_MODIFIERS[r.runningStyle]?.[phase] || 1.0;

      // Base speed calculation
      let targetSpeed = r.baseSpeed * styleMod;

      // Phase-specific adjustments
      switch (phase) {
        case PHASES.GATE:
          targetSpeed *= r.gateSpeed * (0.9 + this.rng() * 0.2);
          break;
        case PHASES.EARLY:
          targetSpeed *= 1.0 + (r.jockeyRating / 1000);
          break;
        case PHASES.MID:
          r.energy -= dt * (2.0 + (1.0 - r.stamina / 100) * 3.0);
          if (r.energy < 30) targetSpeed *= 0.85;
          if (r.jockeySkill.phase === 2) targetSpeed *= (1 + r.jockeySkill.bonus);
          break;
        case PHASES.SPRINT:
          targetSpeed *= r.finalSprint;
          if (this.rng() < r.burstChance * dt) {
            targetSpeed *= r.burstPower;
          }
          if (r.energy < 20) targetSpeed *= 0.75;
          if (r.jockeySkill.phase === 4) targetSpeed *= (1 + r.jockeySkill.bonus);
          break;
      }

      // Consistency jitter
      const jitter = 1.0 + (this.rng() - 0.5) * 2 * (1 - r.consistency) * 0.1;
      targetSpeed *= jitter;

      // ── Apply Traffic modifiers ──
      const tState = trafficResults.get(r.id);
      if (tState) {
        targetSpeed *= tState.speedMod;
        r.lane = tState.lane;
        r.isBoxedIn = tState.isBoxedIn;
        r.isDrafting = tState.isDrafting;
      }

      // ── Apply Event modifiers ──
      const eState = eventResults.get(r.id);
      if (eState) {
        targetSpeed *= eState.speedMod;
        if (eState.laneShift) {
          r.lane = Math.max(1, Math.min(12, r.lane + eState.laneShift * dt));
        }
        if (eState.event) {
          r.activeEvent = eState.event;
          this.recentEvents.push(eState.event);
          // Keep only last 5 events for HUD
          if (this.recentEvents.length > 5) this.recentEvents.shift();
        }
      }

      // Smooth speed transition
      r.speed += (targetSpeed - r.speed) * Math.min(1, dt * 3);

      // Update position
      r.position += r.speed * dt * 50;

      // Check finish
      if (r.position >= this.distance) {
        r.finished = true;
        r.finishTime = this.elapsed;
        r.position = this.distance;
        this.finishOrder.push(r);
      }
    }

    // Check if all finished
    if (this.finishOrder.length >= this.runners.length) {
      this.finished = true;
    }

    return this.getState();
  }

  getState() {
    const sorted = [...this.runners].sort((a, b) => b.position - a.position);
    return {
      runners: sorted,
      finished: this.finished,
      finishOrder: this.finishOrder,
      elapsed: this.elapsed,
      distance: this.distance,
      progress: Math.min(1, (sorted[0]?.position || 0) / this.distance),
      recentEvents: this.recentEvents,
    };
  }

  getResult() {
    return {
      positions: this.finishOrder.map((r, i) => ({
        ...r.runner,
        position: i + 1,
        finishTime: r.finishTime,
      })),
      stewardsInquiry: this.events.shouldCallStewards() || this.rng() < 0.05,
      incidents: this.events.getEvents(),
    };
  }
}
