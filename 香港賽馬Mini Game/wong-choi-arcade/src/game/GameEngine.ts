import type { Competitor } from './RaceGenerator';
import { randomFloat } from '../utils/rng';

export type RacePhase = 'GATE' | 'MID' | 'TURN' | 'FINAL_SPRINT' | 'FINISH';

export interface RunnerState {
  competitor: Competitor;
  position: { x: number, y: number }; // x=distance, y=lane(1-12)
  currentSpeed: number;
  currentStamina: number;
  isTrapped: boolean; // 三四疊塞車
  trappedTimer: number;
  placement: number; // 即時排名
  isStumbling?: boolean;
  stumbleTimer?: number;
}

export class GameEngine {
  private runners: RunnerState[] = [];
  private phase: RacePhase = 'GATE';
  private totalDistance = 2000; // default 2000m
  private elapsedTime = 0;
  
  // Track parameters
  private isDirt = false;
  private isWet = false;

  private isPaused = false;
  private lastTime = 0;
  private animationFrameId: number | null = null;
  
  // Callbacks for React or Pixi Hooking
  public onTick?: (runners: RunnerState[], phase: RacePhase) => void;
  public onFinish?: (results: RunnerState[]) => void;

  constructor(competitors: Competitor[], distance: number = 2000) {
    this.totalDistance = distance;
    this.runners = competitors.map((c, idx) => ({
      competitor: c,
      position: { x: 0, y: idx + 1 }, // Start at gate 1-12
      currentSpeed: 0,
      currentStamina: c.horse.attributes.stamina, // base stamina points
      isTrapped: false,
      trappedTimer: 0,
      placement: 1
    }));
  }

  public setTrackConditions(dirt: boolean, wet: boolean) {
    this.isDirt = dirt;
    this.isWet = wet;
  }

  public start() {
    console.log("🏇 Race Started! Distance:", this.totalDistance);
    this.isPaused = false;
    this.phase = 'GATE';
    this.lastTime = performance.now();
    this.loop(this.lastTime);
  }

  public pause() {
    this.isPaused = true;
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
    }
  }

  private loop = (currentTime: number) => {
    if (this.isPaused) return;

    // Calculate delta time in seconds, capped at 0.1s to prevent huge jumps if tab is inactive
    let dt = (currentTime - this.lastTime) / 1000;
    if (dt > 0.1) dt = 0.1;
    this.lastTime = currentTime;

    this.updateLogics(dt);
    
    // Sort by placement for Live Ranking 
    this.runners.sort((a,b) => b.position.x - a.position.x);
    this.runners.forEach((r, idx) => r.placement = idx + 1);

    if (this.onTick) this.onTick(this.runners, this.phase);

    if (this.phase === 'FINISH') {
      console.log("🏁 Race Finished!");
      if (this.onFinish) this.onFinish(this.runners);
      return; // Stop loop
    }

    this.animationFrameId = requestAnimationFrame(this.loop);
  }

  private updateLogics(dt: number) {
    this.elapsedTime += dt;
    const leaderX = Math.max(...this.runners.map(r => r.position.x));

    // Phase Transitions
    // Increase mid and turn distance slightly to let pack dynamics play out
    if (this.phase === 'GATE' && leaderX > 150) {
      this.phase = 'MID';
    } else if (this.phase === 'MID' && leaderX > (this.totalDistance - 650)) {
      this.phase = 'TURN';
    } else if (this.phase === 'TURN' && leaderX > (this.totalDistance - 350)) {
      this.phase = 'FINAL_SPRINT';
    } else if (this.phase === 'FINAL_SPRINT' && leaderX >= this.totalDistance) {
      if (this.runners.every(r => r.position.x >= this.totalDistance)) {
        this.phase = 'FINISH';
      }
    }

    // Update each runner
    this.runners.forEach(r => {
      // If crossed finish line, stop moving relative to distance (just keep it at final time or something)
      // For simplicity, stop at totalDistance + some overrun
      if (r.position.x >= this.totalDistance + 50) return;

      const attrs = r.competitor.horse.attributes;
      const pref = r.competitor.horse.preferences;
      
      let speedMulti = 1.0;

      // Bad weather penalty 
      if (this.isWet) speedMulti *= pref.wetTrackPreference;
      if (this.isDirt) speedMulti *= pref.dirtPreference;

      let targetSpeed = 0;
      const distToLeader = leaderX - r.position.x;

      switch(this.phase) {
        case 'GATE':
           // Output speed depends on baseSpeed + Burst + RNG
           targetSpeed = (attrs.baseSpeed * 0.5 + attrs.burst * 0.5) * speedMulti;
           if (r.competitor.horse.runningStyle === 'LEADER') targetSpeed *= 1.15;
           if (r.competitor.horse.runningStyle === 'FRONT_RUNNER') targetSpeed *= 1.08;
           if (r.competitor.horse.runningStyle === 'CLOSER') targetSpeed *= 0.82; // Drop back specifically to save gas
           break;
        case 'MID':
           targetSpeed = (attrs.baseSpeed * 0.6 + attrs.consistency * 0.4) * speedMulti;
           
           // Pack dynamics: Drafting (找遮擋) and pacing
           if (distToLeader > 15 && distToLeader < 60) {
              targetSpeed *= 1.05; // Drafting bonus (catch up slightly for free)
           } else if (distToLeader <= 5) {
              targetSpeed *= 0.98; // Leader wind resistance
              r.currentStamina -= 2 * dt; // Leader burns extra stamina
           }

           // Running style logic
           if (r.competitor.horse.runningStyle === 'CLOSER' && distToLeader < 80) {
              targetSpeed *= 0.85; // Closer intentionally drops back to save gas
           } else if (r.competitor.horse.runningStyle === 'LEADER' && distToLeader === 0) {
              targetSpeed *= 1.02; // Leader tries to push the pace
           }

           r.currentStamina -= (targetSpeed * 0.045 * dt); // drain stamina

           // Random Stumble Event
           if (!r.isStumbling && r.position.x > 200 && r.position.x < (this.totalDistance - 400) && randomFloat() < 0.002) {
             r.isStumbling = true;
             r.stumbleTimer = 1.0;
           }
           break;
        case 'TURN':
           targetSpeed = (attrs.baseSpeed * 0.6 + attrs.handling * 0.4) * speedMulti;
           
           // 三疊/四疊 (3/4 wide) 蝕位 penalty
           let turnStaminaDrain = 0.05;
           if (r.position.y > 6) {
              targetSpeed *= 0.98; 
              turnStaminaDrain = 0.07; // 40% more stamina drain (3 wide)
           }
           if (r.position.y > 9) {
              targetSpeed *= 0.95;
              turnStaminaDrain = 0.09; // 80% more stamina drain (4 wide)
           }
           
           // Bunching up before the straight! Make it dense and dramatic.
           if (distToLeader > 20 && distToLeader < 120) targetSpeed *= 1.12; 
           
           r.currentStamina -= (targetSpeed * turnStaminaDrain * dt);

           // Random Stumble Event
           if (!r.isStumbling && randomFloat() < 0.002) {
             r.isStumbling = true;
             r.stumbleTimer = 1.0;
           }
           break;
        case 'FINAL_SPRINT':
        case 'FINISH': // remaining ones running
           // depend heavily on remaining stamina and burst
           const staminaFactor = Math.max(0, r.currentStamina) / 100;
           
           if (staminaFactor <= 0.05) {
              // Bonk! 跑乾
              targetSpeed = attrs.baseSpeed * 0.5 * speedMulti; 
           } else {
              targetSpeed = (attrs.burst * 0.6 + attrs.baseSpeed * 0.4) * (0.7 + staminaFactor * 0.5) * speedMulti;
              
              if (r.competitor.horse.runningStyle === 'CLOSER') {
                 // Massive late charge if they saved gas
                 targetSpeed *= (1.1 + staminaFactor * 0.35); 
              } else if (r.competitor.horse.runningStyle === 'CHASER') {
                 targetSpeed *= (1.05 + staminaFactor * 0.25);
              }
           }
           break;
      }

      // Stumble Penalty
      if (r.isStumbling && r.stumbleTimer && r.stumbleTimer > 0) {
          r.stumbleTimer -= dt;
          targetSpeed *= 0.4; // Massive speed drop when stumbling!
          if (r.stumbleTimer <= 0) r.isStumbling = false;
      }

      // Add a wilder flutter to speed so horses swap places naturally
      const flutter = 0.85 + randomFloat() * 0.3; // 0.85 to 1.15
      targetSpeed *= flutter;

      // Acceleration (slower in MID/TURN to make it look heavier, faster in sprint)
      const accelRate = this.phase === 'FINAL_SPRINT' ? 1.5 : 0.8;
      r.currentSpeed += (targetSpeed - r.currentSpeed) * dt * accelRate;
      
      // Move forward
      r.position.x += r.currentSpeed * dt;
    });
  }
}
