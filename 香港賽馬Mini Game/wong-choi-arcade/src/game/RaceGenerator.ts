import { horses } from '../data/horses';
import { jockeys } from '../data/jockeys';
import { trainers } from '../data/trainers';
import type { Horse, Jockey, Trainer } from '../data/types';
import { shuffle, randomFloat } from '../utils/rng';

export interface Competitor {
  id: number; // Draw number 1-12
  horse: Horse;
  jockey: Jockey;
  trainer: Trainer;
  odds: number;
}

export class RaceGenerator {
  
  static generateRace(_seed?: string): Competitor[] {
    // We already set the seed before calling this via rng.ts or we rely on the caller to do it.
    // Assuming the seed is already set.
    
    // Pick 12 unique horses
    const shuffledHorses = shuffle(horses).slice(0, 12);
    
    // Pick 12 unique jockeys
    const shuffledJockeys = shuffle(jockeys).slice(0, 12);

    // Pick 12 unique trainers
    const shuffledTrainers = shuffle(trainers).slice(0, 12);

    const competitors: Competitor[] = [];

    // Combine them and generate odds
    for (let i = 0; i < 12; i++) {
        const horse = shuffledHorses[i];
        const jockey = shuffledJockeys[i];
        const trainer = shuffledTrainers[i];

        // Base rating from attributes (Max ~ 100)
        const horseRating = 
           horse.attributes.baseSpeed * 0.4 +
           horse.attributes.consistency * 0.2 +
           horse.attributes.burst * 0.2 +
           horse.attributes.stamina * 0.1 +
           horse.attributes.handling * 0.1;
        
        // Adjust rating based on jockey
        const totalRating = horseRating + (jockey.skill * 0.1) - (jockey.weightAllowances * 0.5);

        // Simple odds generator logic (higher rating = lower odds)
        // This will be refined to ensure the book runs to ~110% overround.
        // For now, simple scaling: 
        const rawOdds = Math.max(1.5, 99.0 - (totalRating - 80) * 3 + (randomFloat() * 10 - 5));

        competitors.push({
            id: i + 1, // Draw number 1-12
            horse,
            jockey,
            trainer,
            odds: parseFloat(rawOdds.toFixed(1))
        });
    }

    // Sort by draw number just in case
    return competitors.sort((a,b) => a.id - b.id);
  }
}
