/**
 * 旺財街機 — 主遊戲引擎 v2
 * AI 像素畫背景 + Sprite Sheet 馬匹 + 改良 HUD
 */
import { Application, Container, Graphics, Text, TextStyle, Sprite, Assets, TilingSprite, Texture } from 'pixi.js';
import { PhysicsEngine } from './PhysicsEngine.js';
import { CameraSystem } from './CameraSystem.js';
import { ParticleSystem } from './ParticleSystem.js';
import { soundManager } from './SoundManager.js';
import { HorseSprite, HORSE_WIDTH, HORSE_HEIGHT } from './HorseSprite.js';

const CANVAS_W = 960;
const CANVAS_H = 440;
const TRACK_Y = 140;       // Track top Y (pushed down for bigger sky area)
const LANE_HEIGHT = 24;    // Spacing between lanes
const WORLD_SCALE = 0.5;   // meters → pixels

export class RaceEngine {
  constructor() {
    this.app = null;
    this.physics = null;
    this.camera = null;
    this.horseSprites = [];
    this.worldContainer = null;
    this.hudContainer = null;
    this.bgLayers = [];
    this.onFinish = null;
    this.running = false;
  }

  async init(containerEl, raceData, onFinish) {
    this.onFinish = onFinish;

    this.app = new Application();
    await this.app.init({
      width: CANVAS_W,
      height: CANVAS_H,
      backgroundColor: 0x0b1628,
      antialias: false,
      resolution: window.devicePixelRatio || 1,
      autoDensity: true,
    });

    containerEl.innerHTML = '';
    containerEl.appendChild(this.app.canvas);
    this.app.canvas.style.width = '100%';
    this.app.canvas.style.maxWidth = CANVAS_W + 'px';
    this.app.canvas.style.imageRendering = 'pixelated';

    this.worldContainer = new Container();
    this.hudContainer = new Container();
    this.app.stage.addChild(this.worldContainer);
    this.app.stage.addChild(this.hudContainer);

    // Load and draw background
    await this._drawBackground(raceData.distance);

    // Draw track
    this._drawTrack(raceData.distance);

    // Init physics
    this.physics = new PhysicsEngine(raceData, raceData.seed);

    // Init camera
    this.camera = new CameraSystem(CANVAS_W, CANVAS_H, raceData.distance);

    // Create horse sprites
    this.horseSprites = raceData.runners.map((runner, i) => {
      const sprite = new HorseSprite(runner, i);
      sprite.x = 0;
      sprite.y = TRACK_Y + i * LANE_HEIGHT;
      this.worldContainer.addChild(sprite);
      return sprite;
    });

    // Init particle system
    this.particles = new ParticleSystem(this.worldContainer);
    this.particles.setTrackType(raceData.isDirt || false);
    this.finishConfettiFired = false;

    // Create HUD
    this._createHUD(raceData);
  }

  async _drawBackground(distance) {
    const trackW = distance * WORLD_SCALE + 400;

    try {
      // Load track background image
      const bgTex = await Assets.load('/assets/track_bg.png');

      if (bgTex) {
        // Use the top half for sky + grandstand (parallax slow)
        const skyBg = new TilingSprite({
          texture: bgTex,
          width: trackW + CANVAS_W,
          height: TRACK_Y,
        });
        skyBg.tileScale.set(TRACK_Y / bgTex.height * 2.2);
        this.worldContainer.addChildAt(skyBg, 0);
        this.bgLayers.push({ sprite: skyBg, speed: 0.15 });

        // Add atmosphere overlay for depth
        const atmosphere = new Graphics();
        atmosphere.rect(0, 0, trackW + CANVAS_W, TRACK_Y);
        atmosphere.fill({ color: 0x0b1628, alpha: 0.3 });
        this.worldContainer.addChild(atmosphere);
        this.bgLayers.push({ sprite: atmosphere, speed: 0.15 });

        return; // success — skip fallback
      }
    } catch (e) {
      console.warn('Track BG not loaded, using fallback:', e.message);
    }

    // === Fallback: improved procedural background ===
    // Night sky gradient
    const sky = new Graphics();
    sky.rect(0, 0, trackW + CANVAS_W, TRACK_Y);
    sky.fill(0x0b1628);
    this.worldContainer.addChild(sky);

    // Stars
    const stars = new Graphics();
    for (let i = 0; i < 60; i++) {
      const sx = Math.random() * (trackW + CANVAS_W);
      const sy = Math.random() * (TRACK_Y * 0.6);
      const brightness = 0.3 + Math.random() * 0.7;
      stars.circle(sx, sy, 1);
      stars.fill({ color: 0xffffff, alpha: brightness });
    }
    this.worldContainer.addChild(stars);
    this.bgLayers.push({ sprite: stars, speed: 0.05 });

    // City skyline silhouette
    const skyline = new Graphics();
    for (let x = 0; x < trackW; x += 30) {
      const h = 15 + Math.random() * 40;
      const w = 15 + Math.random() * 20;
      skyline.rect(x, TRACK_Y - h, w, h);
      skyline.fill({ color: 0x1a2a4a, alpha: 0.8 });
      // Windows
      for (let wy = TRACK_Y - h + 4; wy < TRACK_Y - 2; wy += 6) {
        for (let wx = x + 3; wx < x + w - 3; wx += 5) {
          if (Math.random() > 0.4) {
            skyline.rect(wx, wy, 2, 3);
            skyline.fill({ color: 0xffdd88, alpha: 0.6 });
          }
        }
      }
    }
    this.worldContainer.addChild(skyline);
    this.bgLayers.push({ sprite: skyline, speed: 0.2 });

    // Stadium lights
    for (let x = 200; x < trackW; x += 400) {
      const light = new Graphics();
      // Pole
      light.rect(x, TRACK_Y - 55, 3, 55);
      light.fill(0x888888);
      // Light fixture
      light.rect(x - 8, TRACK_Y - 60, 20, 8);
      light.fill(0xcccccc);
      // Glow
      light.circle(x + 2, TRACK_Y - 56, 15);
      light.fill({ color: 0xffffaa, alpha: 0.15 });
      this.worldContainer.addChild(light);
      this.bgLayers.push({ sprite: light, speed: 0.3 });
    }

    // Grandstand
    const stand = new Graphics();
    for (let x = 0; x < trackW; x += 300) {
      // Structure
      stand.rect(x + 50, TRACK_Y - 30, 200, 30);
      stand.fill(0x2a2a3a);
      stand.stroke({ color: 0x444466, width: 1 });
      // Spectator dots
      for (let sy = TRACK_Y - 28; sy < TRACK_Y - 4; sy += 6) {
        for (let sx = x + 54; sx < x + 246; sx += 4) {
          const c = [0xff6666, 0x66aaff, 0xffff66, 0xff88cc, 0x88ff88][Math.floor(Math.random() * 5)];
          stand.circle(sx, sy, 1.5);
          stand.fill({ color: c, alpha: 0.5 + Math.random() * 0.3 });
        }
      }
    }
    this.worldContainer.addChild(stand);
    this.bgLayers.push({ sprite: stand, speed: 0.4 });
  }

  _drawTrack(distance) {
    const trackW = distance * WORLD_SCALE + 200;
    const numLanes = 12;
    const trackH = numLanes * LANE_HEIGHT + 8;

    // Grass area
    const grass = new Graphics();
    grass.rect(-100, TRACK_Y + trackH, trackW + 200, 150);
    grass.fill(0x1e6b1e);
    this.worldContainer.addChild(grass);

    // Track surface
    const track = new Graphics();
    track.roundRect(-10, TRACK_Y - 6, trackW + 20, trackH + 12, 4);
    track.fill(0x2a5a28);
    track.stroke({ color: 0xffffff, width: 2 });
    this.worldContainer.addChild(track);

    // Inner track surface (slightly different shade)
    const inner = new Graphics();
    inner.rect(0, TRACK_Y, trackW, trackH);
    inner.fill(0x336633);
    this.worldContainer.addChild(inner);

    // Rail (top white fence)
    const railTop = new Graphics();
    for (let x = 0; x < trackW; x += 30) {
      railTop.rect(x, TRACK_Y - 8, 2, 10);
      railTop.fill(0xcccccc);
    }
    railTop.moveTo(0, TRACK_Y - 6);
    railTop.lineTo(trackW, TRACK_Y - 6);
    railTop.stroke({ color: 0xdddddd, width: 2 });
    this.worldContainer.addChild(railTop);

    // Rail (bottom fence)
    const railBot = new Graphics();
    for (let x = 0; x < trackW; x += 30) {
      railBot.rect(x, TRACK_Y + trackH, 2, 10);
      railBot.fill(0xcccccc);
    }
    railBot.moveTo(0, TRACK_Y + trackH + 2);
    railBot.lineTo(trackW, TRACK_Y + trackH + 2);
    railBot.stroke({ color: 0xdddddd, width: 2 });
    this.worldContainer.addChild(railBot);

    // Lane dividers (subtle)
    for (let i = 1; i < numLanes; i++) {
      const lane = new Graphics();
      for (let x = 0; x < trackW; x += 20) {
        lane.rect(x, TRACK_Y + i * LANE_HEIGHT, 10, 1);
        lane.fill({ color: 0xffffff, alpha: 0.08 });
      }
      this.worldContainer.addChild(lane);
    }

    // Distance markers
    const markerStyle = new TextStyle({
      fontSize: 9, fill: '#aaa', fontFamily: 'Press Start 2P, monospace',
      dropShadow: true, dropShadowColor: '#000', dropShadowDistance: 1,
    });
    for (let m = 200; m <= distance; m += 200) {
      const x = m * WORLD_SCALE;

      const pole = new Graphics();
      pole.rect(x - 1, TRACK_Y - 20, 3, 22);
      pole.fill(0xffffff);
      this.worldContainer.addChild(pole);

      const txt = new Text({ text: `${m}m`, style: markerStyle });
      txt.x = x - 12;
      txt.y = TRACK_Y - 30;
      this.worldContainer.addChild(txt);
    }

    // Finish line (checkered pattern)
    const finishX = distance * WORLD_SCALE;
    const finish = new Graphics();
    for (let row = 0; row < trackH + 16; row += 4) {
      for (let col = 0; col < 8; col += 4) {
        const isWhite = (Math.floor(row / 4) + Math.floor(col / 4)) % 2 === 0;
        finish.rect(finishX + col, TRACK_Y - 8 + row, 4, 4);
        finish.fill(isWhite ? 0xffffff : 0x000000);
      }
    }
    this.worldContainer.addChild(finish);

    // Finish post
    const post = new Graphics();
    post.rect(finishX, TRACK_Y - 40, 4, 44);
    post.fill(0xff0000);
    post.rect(finishX - 10, TRACK_Y - 44, 24, 8);
    post.fill(0xff0000);
    this.worldContainer.addChild(post);

    const finishLabel = new Text({
      text: '🏁 FINISH',
      style: new TextStyle({ fontSize: 10, fill: '#ff4444', fontFamily: 'Press Start 2P, monospace',
        dropShadow: true, dropShadowColor: '#000', dropShadowDistance: 1 }),
    });
    finishLabel.x = finishX - 20;
    finishLabel.y = TRACK_Y - 56;
    this.worldContainer.addChild(finishLabel);
  }

  _createHUD(raceData) {
    // Background panel for HUD
    const hudBg = new Graphics();
    hudBg.roundRect(4, 2, CANVAS_W - 8, 22, 3);
    hudBg.fill({ color: 0x000000, alpha: 0.7 });
    this.hudContainer.addChild(hudBg);

    // Race info
    const infoStyle = new TextStyle({
      fontSize: 10, fill: '#00ffff', fontFamily: 'Press Start 2P, monospace',
      dropShadow: true, dropShadowColor: '#000', dropShadowDistance: 1,
    });
    this.raceInfoText = new Text({
      text: `R${raceData.raceNumber} | ${raceData.venue} | ${raceData.raceClass} | ${raceData.distance}m`,
      style: infoStyle,
    });
    this.raceInfoText.x = 12;
    this.raceInfoText.y = 6;
    this.hudContainer.addChild(this.raceInfoText);

    // Timer
    this.timerText = new Text({
      text: '0.0s',
      style: new TextStyle({ fontSize: 12, fill: '#FFD700', fontFamily: 'Press Start 2P, monospace',
        dropShadow: true, dropShadowColor: '#000', dropShadowDistance: 1 }),
    });
    this.timerText.x = CANVAS_W - 90;
    this.timerText.y = 5;
    this.hudContainer.addChild(this.timerText);

    // Live rankings panel
    const rankBg = new Graphics();
    rankBg.roundRect(CANVAS_W - 130, 28, 126, Math.min(5, raceData.runners.length) * 16 + 8, 3);
    rankBg.fill({ color: 0x000000, alpha: 0.65 });
    this.hudContainer.addChild(rankBg);

    const rankTitle = new Text({
      text: '📊 排名',
      style: new TextStyle({ fontSize: 8, fill: '#888', fontFamily: 'monospace' }),
    });
    rankTitle.x = CANVAS_W - 125;
    rankTitle.y = 30;
    this.hudContainer.addChild(rankTitle);

    this.rankTexts = [];
    for (let i = 0; i < Math.min(5, raceData.runners.length); i++) {
      const rt = new Text({
        text: '',
        style: new TextStyle({
          fontSize: 8,
          fill: i === 0 ? '#FFD700' : i === 1 ? '#C0C0C0' : i === 2 ? '#CD7F32' : '#888',
          fontFamily: 'monospace',
        }),
      });
      rt.x = CANVAS_W - 125;
      rt.y = 42 + i * 16;
      this.hudContainer.addChild(rt);
      this.rankTexts.push(rt);
    }

    // Event ticker (bottom left)
    const eventBg = new Graphics();
    eventBg.roundRect(4, CANVAS_H - 30, 350, 26, 3);
    eventBg.fill({ color: 0x000000, alpha: 0.65 });
    this.hudContainer.addChild(eventBg);

    this.eventText = new Text({
      text: '',
      style: new TextStyle({ fontSize: 8, fill: '#ff8800', fontFamily: 'monospace' }),
    });
    this.eventText.x = 10;
    this.eventText.y = CANVAS_H - 26;
    this.hudContainer.addChild(this.eventText);
  }

  start() {
    this.running = true;
    soundManager.play('gate');
    this.crowdSoundId = soundManager.play('crowd', { loop: true, volume: 0.3 });
    this.hoovesSoundId = soundManager.play('hooves', { loop: true, volume: 0.4 });
    this.app.ticker.add(this._gameLoop, this);
  }

  _gameLoop(ticker) {
    if (!this.running) return;
    const dt = ticker.deltaMS / 1000;

    const state = this.physics.update(dt);

    const leader = state.runners[0];
    const leaderPos = leader?.position || 0;

    this.camera.update(leaderPos * WORLD_SCALE, dt);
    this.camera.applyToContainer(this.worldContainer);

    // Parallax
    for (const layer of this.bgLayers) {
      layer.sprite.x = -this.camera.x * layer.speed;
    }

    // Horse sprites + particles
    for (let i = 0; i < this.horseSprites.length; i++) {
      const physRunner = state.runners.find(
        r => r.id === this.horseSprites[i].runnerData.horse.id
      );
      if (physRunner) {
        const px = physRunner.position * WORLD_SCALE;
        const py = TRACK_Y + (physRunner.lane - 1) * LANE_HEIGHT;
        this.horseSprites[i].x = px;
        this.horseSprites[i].y = py;
        this.horseSprites[i].updateAnimation(dt, physRunner.speed, physRunner === leader);

        // Emit particles from hooves
        this.particles.emitForHorse(px, py, physRunner.speed, physRunner === leader);
      }
    }

    // Update particles
    this.particles.update(dt);

    // Finish confetti
    if (state.finished && !this.finishConfettiFired) {
      this.finishConfettiFired = true;
      const finishX = this.physics.distance * WORLD_SCALE;
      this.particles.emitFinishConfetti(finishX, TRACK_Y + 6 * LANE_HEIGHT);
    }

    // HUD - Rankings
    this.timerText.text = `${state.elapsed.toFixed(1)}s`;
    for (let i = 0; i < this.rankTexts.length && i < state.runners.length; i++) {
      const r = state.runners[i];
      const posLabel = i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : `${i + 1}.`;
      let status = '';
      if (r.isBoxedIn) status = ' ⛔';
      else if (r.isDrafting) status = ' 💨';
      this.rankTexts[i].text = `${posLabel} ${r.name}${status}`;
    }

    // HUD - Event ticker
    if (state.recentEvents && state.recentEvents.length > 0) {
      const latest = state.recentEvents[state.recentEvents.length - 1];
      this.eventText.text = `📢 ${latest.description}`;
    }

    // Finish check
    if (state.finished && this.running) {
      this.running = false;
      this.app.ticker.remove(this._gameLoop, this);
      soundManager.stop(this.hoovesSoundId);
      soundManager.play('fanfare');
      const result = this.physics.getResult();
      setTimeout(() => this.onFinish?.(result), 1500);
    }
  }

  destroy() {
    this.running = false;
    soundManager.stopAll();
    if (this.app) {
      this.app.ticker.remove(this._gameLoop, this);
      this.app.destroy(true, { children: true });
      this.app = null;
    }
    this.horseSprites = [];
    this.physics = null;
    this.camera = null;
  }
}
