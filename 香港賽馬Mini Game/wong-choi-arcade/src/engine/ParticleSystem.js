/**
 * 旺財街機 — 粒子特效系統
 * - 泥濺 (mud splash) — 泥地賽
 * - 草碎 (turf spray) — 草地賽
 * - 衝線紙碎 (confetti) — 終點
 * - 蹄塵 (hoof dust) — 通用
 */
import { Container, Graphics } from 'pixi.js';

const MAX_PARTICLES = 200;

const PARTICLE_PRESETS = {
  hoof_dust: {
    color: 0x8B7355, alpha: 0.4, size: 2, life: 0.4,
    vx: [-30, -10], vy: [-15, -5], gravity: 20,
  },
  turf_spray: {
    color: 0x22aa22, alpha: 0.5, size: 2.5, life: 0.5,
    vx: [-40, -15], vy: [-25, -8], gravity: 35,
  },
  mud_splash: {
    color: 0x5C3D1A, alpha: 0.6, size: 3, life: 0.6,
    vx: [-50, -10], vy: [-30, -5], gravity: 40,
  },
  confetti: {
    color: null, alpha: 0.9, size: 4, life: 2.5,
    vx: [-60, 60], vy: [-80, -20], gravity: 25,
  },
};

const CONFETTI_COLORS = [0xff4444, 0xffdd44, 0x44aaff, 0xff44aa, 0x44ff88, 0xffffff];

export class ParticleSystem {
  constructor(worldContainer) {
    this.container = new Container();
    worldContainer.addChild(this.container);
    this.particles = [];
    this.isDirt = false;
  }

  setTrackType(isDirt) {
    this.isDirt = isDirt;
  }

  /**
   * Emit particles at a position
   * @param {string} type - preset name
   * @param {number} x - world x
   * @param {number} y - world y
   * @param {number} count - number of particles
   */
  emit(type, x, y, count = 1) {
    const preset = PARTICLE_PRESETS[type];
    if (!preset) return;

    for (let i = 0; i < count && this.particles.length < MAX_PARTICLES; i++) {
      const p = this._getOrCreateParticle();
      const color = type === 'confetti'
        ? CONFETTI_COLORS[Math.floor(Math.random() * CONFETTI_COLORS.length)]
        : preset.color;

      p.gfx.clear();
      if (type === 'confetti') {
        // Confetti: small rectangles
        p.gfx.rect(-preset.size / 2, -preset.size / 2, preset.size, preset.size * 0.6);
      } else {
        // Round particles
        p.gfx.circle(0, 0, preset.size * (0.5 + Math.random() * 0.5));
      }
      p.gfx.fill({ color, alpha: preset.alpha });

      p.gfx.x = x + (Math.random() - 0.5) * 6;
      p.gfx.y = y + (Math.random() - 0.5) * 4;
      p.gfx.visible = true;
      p.gfx.alpha = preset.alpha;

      p.vx = preset.vx[0] + Math.random() * (preset.vx[1] - preset.vx[0]);
      p.vy = preset.vy[0] + Math.random() * (preset.vy[1] - preset.vy[0]);
      p.gravity = preset.gravity;
      p.life = preset.life * (0.8 + Math.random() * 0.4);
      p.maxLife = p.life;
      p.active = true;

      // Confetti spin
      if (type === 'confetti') {
        p.spin = (Math.random() - 0.5) * 8;
      } else {
        p.spin = 0;
      }
    }
  }

  /**
   * Emit particles for a running horse
   */
  emitForHorse(x, y, speed, isLeader) {
    if (speed < 1.5) return;

    const chance = Math.min(0.4, speed * 0.08);
    if (Math.random() > chance) return;

    const type = this.isDirt ? 'mud_splash' : (speed > 2.5 ? 'turf_spray' : 'hoof_dust');
    const count = isLeader ? 2 : 1;
    this.emit(type, x + 4, y + 50, count); // Emit from hooves
  }

  /**
   * Burst confetti at finish line
   */
  emitFinishConfetti(x, y) {
    this.emit('confetti', x, y - 40, 30);
    this.emit('confetti', x, y, 20);
    this.emit('confetti', x, y + 40, 30);
  }

  /**
   * Update all particles
   */
  update(dt) {
    for (const p of this.particles) {
      if (!p.active) continue;

      p.life -= dt;
      if (p.life <= 0) {
        p.active = false;
        p.gfx.visible = false;
        continue;
      }

      // Physics
      p.vx *= 0.98; // air friction
      p.vy += p.gravity * dt;
      p.gfx.x += p.vx * dt;
      p.gfx.y += p.vy * dt;

      // Fade out
      const lifeRatio = p.life / p.maxLife;
      p.gfx.alpha = lifeRatio * 0.6;

      // Confetti spin
      if (p.spin) {
        p.gfx.rotation += p.spin * dt;
      }
    }
  }

  _getOrCreateParticle() {
    // Reuse inactive particle
    for (const p of this.particles) {
      if (!p.active) return p;
    }
    // Create new
    const gfx = new Graphics();
    this.container.addChild(gfx);
    const p = { gfx, vx: 0, vy: 0, gravity: 0, life: 0, maxLife: 0, active: false, spin: 0 };
    this.particles.push(p);
    return p;
  }

  destroy() {
    this.container.destroy({ children: true });
    this.particles = [];
  }
}
