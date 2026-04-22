/**
 * 旺財街機 — 遊戲狀態機 (XState v5)
 * 狀態流程: MENU → RACE_SETUP → INTEL_REVIEW → BETTING → RACING → PHOTO_FINISH → STEWARDS → RESULT → NEXT_RACE → DAY_SUMMARY
 */
import { createMachine, assign } from 'xstate';

const INITIAL_BALANCE = 1000;
const TOTAL_RACES = 10;

export const gameMachine = createMachine({
  id: 'wongChoiArcade',
  initial: 'menu',
  context: {
    mode: 'solo',
    players: [],
    currentRace: 0,
    totalRaces: TOTAL_RACES,
    raceData: null,
    bets: [],
    raceResult: null,
    raceHistory: [],
    achievements: [],
    jackpot: 0,
    dongGoStreak: 0,
    loanCount: 0,
    seed: null,
  },

  states: {
    menu: {
      on: {
        START_SOLO: {
          target: 'raceSetup',
          actions: assign({
            mode: () => 'solo',
            players: () => [{ name: '玩家', balance: INITIAL_BALANCE, bets: [], results: [] }],
            currentRace: () => 0,
            raceHistory: () => [],
            loanCount: () => 0,
            jackpot: () => 0,
            seed: () => Date.now().toString(),
          }),
        },
        START_MULTI: {
          target: 'playerSetup',
          actions: assign({ mode: () => 'multiplayer' }),
        },
      },
    },

    playerSetup: {
      on: {
        CONFIRM_PLAYERS: {
          target: 'raceSetup',
          actions: assign({
            players: ({ event }) => event.players.map(p => ({
              name: p.name, balance: INITIAL_BALANCE, bets: [], results: [],
            })),
            currentRace: () => 0,
            raceHistory: () => [],
            loanCount: () => 0,
            jackpot: () => 0,
            seed: () => Date.now().toString(),
          }),
        },
        BACK: 'menu',
      },
    },

    raceSetup: {
      on: {
        RACE_GENERATED: {
          target: 'intelReview',
          actions: assign({ raceData: ({ event }) => event.raceData }),
        },
      },
    },

    intelReview: {
      on: { PROCEED_TO_BETTING: 'betting' },
    },

    betting: {
      on: {
        PLACE_BET: {
          actions: assign({ bets: ({ event }) => event.bets }),
        },
        CONFIRM_BETS: {
          target: 'racing',
          guard: ({ context }) => context.bets.length > 0,
        },
        TIMEOUT: 'racing',
      },
    },

    racing: {
      on: {
        RACE_FINISHED: {
          target: 'photoFinish',
          actions: assign({ raceResult: ({ event }) => event.result }),
        },
      },
    },

    photoFinish: {
      on: {
        PHOTO_DONE: [
          { target: 'stewards', guard: ({ context }) => context.raceResult?.stewardsInquiry },
          { target: 'result' },
        ],
      },
    },

    stewards: {
      on: {
        STEWARDS_RESOLVED: {
          target: 'result',
          actions: assign({ raceResult: ({ event }) => event.updatedResult }),
        },
      },
    },

    result: {
      on: {
        NEXT_RACE: [
          {
            target: 'bankruptcy',
            guard: ({ context }) => context.players.some(p => p.balance <= 0),
          },
          {
            target: 'daySummary',
            guard: ({ context }) => context.currentRace >= context.totalRaces - 1,
          },
          {
            target: 'raceSetup',
            actions: assign({
              currentRace: ({ context }) => context.currentRace + 1,
              raceHistory: ({ context }) => [...context.raceHistory, context.raceResult],
              raceData: () => null,
              bets: () => [],
              raceResult: () => null,
            }),
          },
        ],
      },
    },

    bankruptcy: {
      on: {
        ACCEPT_LOAN: {
          target: 'raceSetup',
          actions: assign({
            loanCount: ({ context }) => context.loanCount + 1,
            players: ({ context }) => context.players.map(p =>
              p.balance <= 0 ? { ...p, balance: 500 } : p
            ),
            currentRace: ({ context }) => context.currentRace + 1,
            raceHistory: ({ context }) => [...context.raceHistory, context.raceResult],
            raceData: () => null,
            bets: () => [],
            raceResult: () => null,
          }),
        },
        REJECT_LOAN: {
          target: 'daySummary',
          actions: assign({
            raceHistory: ({ context }) => [...context.raceHistory, context.raceResult],
          }),
        },
      },
    },

    daySummary: {
      on: { PLAY_AGAIN: 'menu' },
    },
  },
});
