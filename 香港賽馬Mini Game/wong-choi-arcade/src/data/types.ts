export type HorseRank = 'S' | 'A' | 'B' | 'C' | 'D';
export type RunningStyle = 'LEADER' | 'FRONT_RUNNER' | 'CHASER' | 'CLOSER';

export interface Horse {
  id: string;
  name: { zh: string; en: string };
  rank: HorseRank;
  runningStyle: RunningStyle;
  
  // Base Attributes (0-100)
  attributes: {
    baseSpeed: number;        // 基礎極速
    consistency: number;      // 均速穩定性
    burst: number;            // 爆發力
    handling: number;         // 檔位適應/過彎靈活
    stamina: number;          // 耐力 (特別重要於大慢步速或泥地)
  };

  // Hidden/Environmental Preferences (Multipliers, default 1.0)
  preferences: {
    dirtPreference: number;   // 泥地性能
    wetTrackPreference: number; // 爛地/黑雨性能 (>>1.0 means loves heavy track)
  };

  // Personality Tags (Optional constraints or bonuses)
  tags: string[]; 
}

export interface Jockey {
  id: string;
  name: { zh: string; en: string };
  weightAllowances: number; // 見習騎師減磅 (0, 3, 5, 7, 10)
  skill: number;            // 騎功 (影響意外避免與爆發判定)
  isLocal: boolean;         // 華將 (30% 配對偏好)
}

export interface Trainer {
  id: string;
  name: { zh: string; en: string };
  bonusType: 'CONDITION' | 'SPEED' | 'STAMINA' | 'NONE'; 
  bonusValue: number;
}
