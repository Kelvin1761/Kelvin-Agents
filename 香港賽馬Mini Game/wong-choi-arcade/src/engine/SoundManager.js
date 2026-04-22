/**
 * 旺財街機 — 音效管理器
 * Howler.js wrapper，管理所有遊戲音效
 * 
 * 音效分類：
 * - UI: 按鈕/選擇/確認
 * - Race: 蹄聲/人群/開閘/衝線
 * - Ambient: 場地氣氛
 * 
 * 全部用 Web Audio API 合成，唔需要外部音效檔案
 */

// Audio context for generating sounds programmatically
let audioCtx = null;

function getAudioCtx() {
  if (!audioCtx) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  return audioCtx;
}

/**
 * Generate a simple synthesized sound buffer
 */
function createSynthSound(type, duration = 0.3, frequency = 440, volume = 0.3) {
  const ctx = getAudioCtx();
  const sampleRate = ctx.sampleRate;
  const length = sampleRate * duration;
  const buffer = ctx.createBuffer(1, length, sampleRate);
  const data = buffer.getChannelData(0);

  switch (type) {
    case 'click': {
      for (let i = 0; i < length; i++) {
        const t = i / sampleRate;
        const env = Math.exp(-t * 30);
        data[i] = env * Math.sin(2 * Math.PI * frequency * t) * volume;
      }
      break;
    }
    case 'confirm': {
      for (let i = 0; i < length; i++) {
        const t = i / sampleRate;
        const env = Math.exp(-t * 10);
        const freq = frequency + t * 500;
        data[i] = env * Math.sin(2 * Math.PI * freq * t) * volume;
      }
      break;
    }
    case 'bet': {
      for (let i = 0; i < length; i++) {
        const t = i / sampleRate;
        const env = Math.exp(-t * 15);
        data[i] = env * (Math.sin(2 * Math.PI * 800 * t) + Math.sin(2 * Math.PI * 1200 * t) * 0.5) * volume * 0.5;
      }
      break;
    }
    case 'gate': {
      // Gate opening — metallic clang
      for (let i = 0; i < length; i++) {
        const t = i / sampleRate;
        const env = Math.exp(-t * 5);
        data[i] = env * (
          Math.sin(2 * Math.PI * 200 * t) * 0.5 +
          Math.sin(2 * Math.PI * 350 * t) * 0.3 +
          Math.sin(2 * Math.PI * 800 * t) * 0.2 +
          (Math.random() - 0.5) * 0.3 * Math.exp(-t * 8)
        ) * volume;
      }
      break;
    }
    case 'hooves': {
      // Rhythmic hoof beats
      for (let i = 0; i < length; i++) {
        const t = i / sampleRate;
        const beatFreq = 8; // beats per second
        const beat = Math.pow(Math.sin(2 * Math.PI * beatFreq * t), 20);
        data[i] = beat * (Math.random() - 0.5) * volume * 1.5;
      }
      break;
    }
    case 'crowd': {
      // Crowd ambient — filtered noise
      for (let i = 0; i < length; i++) {
        const t = i / sampleRate;
        const noise = (Math.random() - 0.5);
        // Slow modulation for "wave" effect
        const mod = 0.5 + 0.5 * Math.sin(2 * Math.PI * 0.3 * t);
        data[i] = noise * volume * 0.3 * mod;
      }
      break;
    }
    case 'fanfare': {
      // Win fanfare — ascending notes
      const notes = [523, 659, 784, 1047]; // C5, E5, G5, C6
      for (let i = 0; i < length; i++) {
        const t = i / sampleRate;
        const noteIdx = Math.min(Math.floor(t / (duration / notes.length)), notes.length - 1);
        const noteT = t - noteIdx * (duration / notes.length);
        const env = Math.exp(-noteT * 4);
        data[i] = env * Math.sin(2 * Math.PI * notes[noteIdx] * t) * volume;
      }
      break;
    }
    case 'error': {
      for (let i = 0; i < length; i++) {
        const t = i / sampleRate;
        const env = Math.exp(-t * 12);
        data[i] = env * Math.sin(2 * Math.PI * 200 * t) * volume;
      }
      break;
    }
    default: {
      // Simple beep
      for (let i = 0; i < length; i++) {
        const t = i / sampleRate;
        data[i] = Math.exp(-t * 20) * Math.sin(2 * Math.PI * frequency * t) * volume;
      }
    }
  }

  return buffer;
}

class SoundManager {
  constructor() {
    this.enabled = true;
    this.masterVolume = 0.5;
    this.sounds = {};
    this.activeSources = new Map();
    this.initialized = false;
  }

  /**
   * Init audio context (must be called after user interaction)
   */
  init() {
    if (this.initialized) return;
    
    try {
      const ctx = getAudioCtx();
      
      // Pre-generate all sounds
      this.sounds = {
        // UI sounds
        click:    createSynthSound('click', 0.1, 600, 0.2),
        confirm:  createSynthSound('confirm', 0.25, 400, 0.25),
        bet:      createSynthSound('bet', 0.15, 800, 0.2),
        error:    createSynthSound('error', 0.3, 200, 0.2),
        
        // Race sounds
        gate:     createSynthSound('gate', 0.8, 200, 0.4),
        hooves:   createSynthSound('hooves', 2.0, 100, 0.3),
        crowd:    createSynthSound('crowd', 4.0, 100, 0.2),
        fanfare:  createSynthSound('fanfare', 1.2, 523, 0.35),
      };

      this.initialized = true;
    } catch (e) {
      console.warn('Audio init failed:', e.message);
      this.enabled = false;
    }
  }

  /**
   * Play a sound effect
   * @param {string} name - sound name
   * @param {object} options - { loop, volume }
   */
  play(name, options = {}) {
    if (!this.enabled || !this.initialized) return null;

    const buffer = this.sounds[name];
    if (!buffer) return null;

    try {
      const ctx = getAudioCtx();
      if (ctx.state === 'suspended') ctx.resume();

      const source = ctx.createBufferSource();
      source.buffer = buffer;

      const gainNode = ctx.createGain();
      gainNode.gain.value = (options.volume || 1.0) * this.masterVolume;

      source.connect(gainNode);
      gainNode.connect(ctx.destination);

      source.loop = options.loop || false;
      source.start(0);

      // Track for stopping later
      const id = `${name}_${Date.now()}`;
      this.activeSources.set(id, { source, gainNode });
      source.onended = () => this.activeSources.delete(id);

      return id;
    } catch (e) {
      return null;
    }
  }

  /**
   * Stop a specific sound
   */
  stop(id) {
    const s = this.activeSources.get(id);
    if (s) {
      try {
        s.source.stop();
      } catch (e) { /* already stopped */ }
      this.activeSources.delete(id);
    }
  }

  /**
   * Stop all sounds
   */
  stopAll() {
    for (const [id, s] of this.activeSources) {
      try { s.source.stop(); } catch (e) {}
    }
    this.activeSources.clear();
  }

  /**
   * Set master volume (0-1)
   */
  setVolume(vol) {
    this.masterVolume = Math.max(0, Math.min(1, vol));
    for (const [, s] of this.activeSources) {
      s.gainNode.gain.value = this.masterVolume;
    }
  }

  toggle() {
    this.enabled = !this.enabled;
    if (!this.enabled) this.stopAll();
    return this.enabled;
  }
}

// Singleton
export const soundManager = new SoundManager();
