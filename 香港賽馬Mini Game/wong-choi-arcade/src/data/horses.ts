import type { Horse } from './types';

export const horses: Horse[] = [
  // --- RANK S (Superstars) ---
  {
    id: 'H_S_001', name: { zh: '金鎗六十', en: 'Golden Sixty' },
    rank: 'S', runningStyle: 'CLOSER',
    attributes: { baseSpeed: 95, consistency: 98, burst: 100, handling: 90, stamina: 85 },
    preferences: { dirtPreference: 0.8, wetTrackPreference: 0.9 }, tags: []
  },
  {
    id: 'H_S_002', name: { zh: '浪漫勇士', en: 'Romantic Warrior' },
    rank: 'S', runningStyle: 'FRONT_RUNNER',
    attributes: { baseSpeed: 98, consistency: 95, burst: 94, handling: 92, stamina: 96 },
    preferences: { dirtPreference: 0.85, wetTrackPreference: 1.0 }, tags: []
  },
  // --- RANK A ---
  {
    id: 'H_A_001', name: { zh: '加州星球', en: 'California Spangle' },
    rank: 'A', runningStyle: 'LEADER',
    attributes: { baseSpeed: 97, consistency: 90, burst: 85, handling: 88, stamina: 90 },
    preferences: { dirtPreference: 0.9, wetTrackPreference: 0.95 }, tags: []
  },
  {
    id: 'H_A_002', name: { zh: '福逸', en: 'Wellington' },
    rank: 'A', runningStyle: 'CHASER',
    attributes: { baseSpeed: 93, consistency: 92, burst: 95, handling: 90, stamina: 82 },
    preferences: { dirtPreference: 0.8, wetTrackPreference: 0.8 }, tags: []
  },
  // --- RANK B ---
  {
    id: 'H_B_001', name: { zh: '永遠美麗', en: 'Beauty Eternal' },
    rank: 'B', runningStyle: 'FRONT_RUNNER',
    attributes: { baseSpeed: 88, consistency: 89, burst: 86, handling: 85, stamina: 88 },
    preferences: { dirtPreference: 0.9, wetTrackPreference: 1.0 }, tags: []
  },
  {
    id: 'H_B_002', name: { zh: '多巴先生', en: 'Senor Toba' },
    rank: 'B', runningStyle: 'CLOSER',
    attributes: { baseSpeed: 82, consistency: 85, burst: 88, handling: 80, stamina: 98 },
    preferences: { dirtPreference: 1.0, wetTrackPreference: 1.1 }, tags: ['stayer']
  },
  {
    id: 'H_B_003', name: { zh: '龍鼓飛揚', en: 'Glorious Dragon' },
    rank: 'B', runningStyle: 'CHASER',
    attributes: { baseSpeed: 85, consistency: 84, burst: 87, handling: 82, stamina: 85 },
    preferences: { dirtPreference: 0.9, wetTrackPreference: 1.0 }, tags: []
  },
  // --- RANK C ---
  {
    id: 'H_C_001', name: { zh: '中華盛景', en: 'The Golden Scenery' },
    rank: 'C', runningStyle: 'CHASER',
    attributes: { baseSpeed: 80, consistency: 82, burst: 84, handling: 78, stamina: 80 },
    preferences: { dirtPreference: 0.85, wetTrackPreference: 1.0 }, tags: []
  },
  {
    id: 'H_C_002', name: { zh: '神駒', en: 'Super Steed' },
    rank: 'C', runningStyle: 'CHASER',
    attributes: { baseSpeed: 81, consistency: 78, burst: 85, handling: 75, stamina: 78 },
    preferences: { dirtPreference: 1.0, wetTrackPreference: 1.1 }, tags: []
  },
  {
    id: 'H_C_003', name: { zh: '駿馬風采', en: 'Grand Fortune' },
    rank: 'C', runningStyle: 'LEADER',
    attributes: { baseSpeed: 85, consistency: 75, burst: 78, handling: 76, stamina: 75 },
    preferences: { dirtPreference: 0.9, wetTrackPreference: 0.8 }, tags: []
  },
  // --- RANK D (Longshots, heavy track specialists) ---
  {
    id: 'H_D_001', name: { zh: '泥地霸王', en: 'Mud Monster' },
    rank: 'D', runningStyle: 'FRONT_RUNNER',
    attributes: { baseSpeed: 70, consistency: 70, burst: 72, handling: 65, stamina: 85 },
    preferences: { dirtPreference: 1.5, wetTrackPreference: 1.4 }, tags: ['mudder']
  },
  {
    id: 'H_D_002', name: { zh: '旺財寶貝', en: 'Wong Choi Baby' },
    rank: 'D', runningStyle: 'CLOSER',
    attributes: { baseSpeed: 68, consistency: 70, burst: 80, handling: 68, stamina: 75 },
    preferences: { dirtPreference: 0.9, wetTrackPreference: 1.3 }, tags: ['heavy_tracker']
  },
  {
    id: 'H_D_003', name: { zh: '無名英雄', en: 'Nameless Hero' },
    rank: 'D', runningStyle: 'LEADER',
    attributes: { baseSpeed: 75, consistency: 65, burst: 68, handling: 60, stamina: 70 },
    preferences: { dirtPreference: 0.8, wetTrackPreference: 0.9 }, tags: []
  }
];
