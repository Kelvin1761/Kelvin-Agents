import seedrandom from 'seedrandom';

let rng = seedrandom('wong-choi-initial-seed');

export const setSeed = (seed: string) => {
  rng = seedrandom(seed);
};

// Returns a float between 0 (inclusive) and 1 (exclusive)
export const randomFloat = () => rng();

// Returns an integer between min (inclusive) and max (inclusive)
export const randomInt = (min: number, max: number) => {
  return Math.floor(rng() * (max - min + 1)) + min;
};

// Shuffle array using Fisher-Yates and the seeded RNG
export function shuffle<T>(array: T[]): T[] {
  const newArray = [...array];
  for (let i = newArray.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [newArray[i], newArray[j]] = [newArray[j], newArray[i]];
  }
  return newArray;
}
