/**
 * 旺財街機 — 廣播級鏡頭系統
 * Phase 1: 側面追蹤 (直路)
 * Phase 2: pseudo-2.5D 入彎透視
 * Phase 3: 終點衝線 zoom
 */

const CAMERA_MODES = {
  SIDE:    'side',     // 標準側面追蹤
  TURN:    'turn',     // 入彎 pseudo-2.5D
  FINISH:  'finish',   // 衝線 zoom-in
};

export class CameraSystem {
  constructor(canvasWidth, canvasHeight, raceDistance) {
    this.canvasW = canvasWidth;
    this.canvasH = canvasHeight;
    this.raceDistance = raceDistance;
    this.mode = CAMERA_MODES.SIDE;

    // Camera position (world coordinates)
    this.x = 0;
    this.y = 0;
    this.zoom = 1.0;
    this.skew = 0;       // For pseudo-2.5D turn effect
    this.targetX = 0;
    this.targetZoom = 1.0;
    this.targetSkew = 0;

    // Turn zone (40-60% of race = bend)
    this.turnStart = raceDistance * 0.40;
    this.turnEnd = raceDistance * 0.60;
    this.turnPeak = raceDistance * 0.50;
  }

  /**
   * Update camera based on leader position
   * @param {number} leaderPos - leader's position in meters
   * @param {number} dt - delta time
   */
  update(leaderPos, dt) {
    const progress = leaderPos / this.raceDistance;

    // Determine mode
    if (leaderPos >= this.turnStart && leaderPos <= this.turnEnd) {
      this.mode = CAMERA_MODES.TURN;
    } else if (progress > 0.90) {
      this.mode = CAMERA_MODES.FINISH;
    } else {
      this.mode = CAMERA_MODES.SIDE;
    }

    // Calculate targets
    switch (this.mode) {
      case CAMERA_MODES.SIDE:
        this.targetX = leaderPos - this.canvasW * 0.3;
        this.targetZoom = 1.0;
        this.targetSkew = 0;
        break;

      case CAMERA_MODES.TURN: {
        this.targetX = leaderPos - this.canvasW * 0.5;
        // Skew ramps up to peak, then down
        const turnProgress = (leaderPos - this.turnStart) / (this.turnEnd - this.turnStart);
        const skewCurve = Math.sin(turnProgress * Math.PI); // 0 → 1 → 0
        this.targetSkew = skewCurve * 0.15; // max ~8.5 degrees
        this.targetZoom = 1.0 + skewCurve * 0.1; // slight zoom in turn
        break;
      }

      case CAMERA_MODES.FINISH:
        this.targetX = leaderPos - this.canvasW * 0.7;
        this.targetZoom = 1.3;
        this.targetSkew = 0;
        break;
    }

    // Smooth interpolation
    const lerp = Math.min(1, dt * 3);
    this.x += (this.targetX - this.x) * lerp;
    this.zoom += (this.targetZoom - this.zoom) * lerp;
    this.skew += (this.targetSkew - this.skew) * lerp;
  }

  /**
   * Convert world position to screen position
   */
  worldToScreen(worldX, worldY) {
    const screenX = (worldX - this.x) * this.zoom;
    const screenY = worldY + (worldX - this.x) * this.skew; // pseudo-2.5D skew
    return { x: screenX, y: screenY * this.zoom };
  }

  /**
   * Apply camera transform to a PixiJS Container
   */
  applyToContainer(container) {
    container.x = -this.x * this.zoom;
    container.y = 0;
    container.scale.set(this.zoom);
    container.skew.set(0, this.skew);
  }

  getMode() { return this.mode; }
  getProgress() { return this.x / this.raceDistance; }
}
