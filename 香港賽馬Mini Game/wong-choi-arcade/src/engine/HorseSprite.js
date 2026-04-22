/**
 * 旺財街機 — 馬匹 Sprite 類 v2
 * 用 sprite sheet 做跑步動畫，配合綵衣顏色 tint
 */
import { Container, Graphics, Text, TextStyle, Sprite, Texture, Rectangle, Assets } from 'pixi.js';

const HORSE_WIDTH = 64;
const HORSE_HEIGHT = 64;
const SPRITE_COLS = 3;
const SPRITE_ROWS = 4;
const TOTAL_FRAMES = 12;
const GALLOP_SPEED = 0.15;

// Fallback gallop bounce when sprite sheet not available
const GALLOP_BOUNCE = [0, -2, -4, -3, -1, 1, 3, 2];

export class HorseSprite extends Container {
  constructor(runnerData, index) {
    super();
    this.runnerData = runnerData;
    this.horseIndex = index;
    this.animFrame = 0;
    this.animTimer = 0;
    this.spriteFrames = [];
    this.usingSpriteSheet = false;

    const silk = runnerData.horse.meta.silkColors || { primary: '#888', secondary: '#fff' };

    // Draw improved fallback body (used until sprite loads)
    this.body = new Container();
    this._drawImprovedBody(silk);
    this.addChild(this.body);

    // Animated sprite (loaded async)
    this.animatedSprite = null;
    this._loadSpriteSheet();

    // Barrier number
    this.label = new Text({
      text: `${runnerData.barrier}`,
      style: new TextStyle({ fontFamily: 'Press Start 2P, monospace', fontSize: 9, fill: '#ffffff', fontWeight: 'bold',
        dropShadow: true, dropShadowColor: '#000', dropShadowDistance: 1 }),
    });
    this.label.anchor = { x: 0.5, y: 1 };
    this.label.x = HORSE_WIDTH / 2;
    this.label.y = -2;
    this.addChild(this.label);

    // Name label
    this.nameLabel = new Text({
      text: runnerData.horse.name,
      style: new TextStyle({ fontFamily: 'monospace', fontSize: 9, fill: '#FFD700',
        dropShadow: true, dropShadowColor: '#000', dropShadowDistance: 1 }),
    });
    this.nameLabel.anchor = { x: 0.5, y: 0 };
    this.nameLabel.x = HORSE_WIDTH / 2;
    this.nameLabel.y = HORSE_HEIGHT + 2;
    this.nameLabel.visible = false;
    this.addChild(this.nameLabel);

    // Dust particles
    this.dustParticles = [];
    this._initDust();
  }

  _drawImprovedBody(silk) {
    const g = new Graphics();

    // Horse body — more detailed shape
    // Main torso
    g.roundRect(10, 18, 38, 20, 6);
    g.fill(0x8B6914);
    g.stroke({ color: 0x5C4510, width: 1 });

    // Neck
    g.roundRect(42, 10, 10, 18, 3);
    g.fill(0x7B5F1A);

    // Head
    g.roundRect(48, 6, 14, 12, 4);
    g.fill(0x9B7B2C);
    g.stroke({ color: 0x5C4510, width: 1 });

    // Eye
    g.circle(56, 10, 2);
    g.fill(0x000000);

    // Jockey (torso on horse)
    g.roundRect(20, 6, 18, 14, 3);
    g.fill(silk.primary);
    g.stroke({ color: silk.secondary, width: 1 });

    // Jockey head/helmet
    g.circle(29, 2, 5);
    g.fill(silk.secondary);
    g.stroke({ color: silk.primary, width: 1 });

    // Front legs
    g.rect(14, 38, 5, 16);
    g.fill(0x5C4510);
    g.rect(22, 38, 5, 16);
    g.fill(0x5C4510);

    // Back legs
    g.rect(35, 38, 5, 16);
    g.fill(0x5C4510);
    g.rect(43, 38, 5, 16);
    g.fill(0x5C4510);

    // Tail
    g.moveTo(10, 20);
    g.quadraticCurveTo(2, 16, 4, 24);
    g.stroke({ color: 0x3a2808, width: 3 });

    this.body.addChild(g);
  }

  async _loadSpriteSheet() {
    try {
      const tex = await Assets.load('/assets/horse_sprite.png');
      if (!tex) return;

      const frameW = tex.width / SPRITE_COLS;
      const frameH = tex.height / SPRITE_ROWS;

      this.spriteFrames = [];
      for (let row = 0; row < SPRITE_ROWS; row++) {
        for (let col = 0; col < SPRITE_COLS; col++) {
          const frame = new Texture({
            source: tex.source,
            frame: new Rectangle(col * frameW, row * frameH, frameW, frameH),
          });
          this.spriteFrames.push(frame);
        }
      }

      if (this.spriteFrames.length > 0) {
        this.animatedSprite = new Sprite(this.spriteFrames[0]);
        this.animatedSprite.width = HORSE_WIDTH;
        this.animatedSprite.height = HORSE_HEIGHT;

        // Tint with silk color
        const silk = this.runnerData.horse.meta.silkColors?.primary || '#888';
        // Light tint to preserve details
        this.animatedSprite.alpha = 0.95;

        this.body.visible = false;
        this.addChildAt(this.animatedSprite, 0);
        this.usingSpriteSheet = true;
      }
    } catch (e) {
      // Fallback to graphics body
      console.warn('Sprite sheet not loaded, using fallback:', e.message);
    }
  }

  _initDust() {
    for (let i = 0; i < 4; i++) {
      const dust = new Graphics();
      dust.circle(0, 0, 2);
      dust.fill({ color: 0x8B7355, alpha: 0.4 });
      dust.visible = false;
      dust.vx = 0;
      dust.vy = 0;
      dust.life = 0;
      this.addChild(dust);
      this.dustParticles.push(dust);
    }
  }

  /**
   * Update animation
   */
  updateAnimation(dt, speed, isLeading) {
    if (speed > 0.5) {
      this.animTimer += dt * 1000 * speed * 0.3;
      const frameIdx = Math.floor(this.animTimer * GALLOP_SPEED) % (this.usingSpriteSheet ? TOTAL_FRAMES : GALLOP_BOUNCE.length);

      if (frameIdx !== this.animFrame) {
        this.animFrame = frameIdx;

        if (this.usingSpriteSheet && this.animatedSprite && this.spriteFrames[frameIdx]) {
          this.animatedSprite.texture = this.spriteFrames[frameIdx];
        } else {
          this.body.y = GALLOP_BOUNCE[frameIdx % GALLOP_BOUNCE.length];
        }
      }

      // Emit dust particles at speed
      if (speed > 2 && Math.random() < 0.3) {
        this._emitDust();
      }
    }

    // Update dust
    for (const d of this.dustParticles) {
      if (d.life > 0) {
        d.life -= dt;
        d.x += d.vx * dt;
        d.y += d.vy * dt;
        d.alpha = d.life * 0.5;
        if (d.life <= 0) d.visible = false;
      }
    }

    // Show name for leading horse
    this.nameLabel.visible = isLeading;

    // Leading horse glow effect
    if (isLeading) {
      this.alpha = 1.0;
    } else {
      this.alpha = 0.85;
    }
  }

  _emitDust() {
    const d = this.dustParticles.find(p => p.life <= 0);
    if (!d) return;
    d.visible = true;
    d.x = 4 + Math.random() * 8;
    d.y = HORSE_HEIGHT - 8 + Math.random() * 4;
    d.vx = -(20 + Math.random() * 20);
    d.vy = -(5 + Math.random() * 10);
    d.life = 0.4 + Math.random() * 0.3;
    d.alpha = 0.5;
  }
}

export { HORSE_WIDTH, HORSE_HEIGHT };
