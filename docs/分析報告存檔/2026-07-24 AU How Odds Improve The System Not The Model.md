# Resolving the paradox: "how do you improve an odds-blind model by reading odds?" (2026-07-24)

Kelvin's sharp question. Honest, data-backed answer.

## Two different uses of odds — only one touches the model

1. **Odds as a runtime INPUT** (model reads odds → outputs ranking): makes the
   model accurate but turns it into an odds-reader. **We never do this.**
2. **Odds/results as an offline TEACHER** (show the model where it was wrong,
   then fix genuine data-based signals): the model gets smarter while staying
   odds-blind at runtime. **This is legitimate — but it has a hard ceiling.**

## The ceiling, measured

The 90 "blindspot winners" (market top-2, our model ranked ≥5, WON) profiled on
OUR OWN features — their median in-race percentile (0=worst, 1=best):

| feature | percentile |
|---|---:|
| trial / jockey / rating | ~0.50 |
| form / class | ~0.40 |
| consistency | 0.29 |
| sectional | 0.12 |
| **pace_figure** | **0.00 (worst in field)** |

On every signal we have, these winners look like **slow, below-average horses**
— so the model ranked them low *correctly, given our data*. There is **no
fixable pattern** to re-weight: they are not "horses with a signal we
underweighted," they are horses whose winning quality is **invisible in our
data**. The market's money reflected information we simply do not possess.

## Therefore

- **You can improve the model only where OUR data has a fixable gap.** That is
  real but nearly exhausted (21 candidates tested, 1 passed — facts-refresh).
- **The rest of the market's edge cannot be learned into the model**, because
  there is nothing in our data to learn it from. The only way to use it is the
  **market column at runtime** (rescue / blindspot zone). That is not
  "improving the model" — it is adding a second instrument.

## The symmetry (why you need both, and must not merge them)

- **Savagery Vibe:** the MODEL saw quality (consistency 100, pace_figure 75)
  the MARKET missed → the model's overlay bet.
- **The 90 blindspot winners:** the MARKET saw quality our DATA lacks → the
  market's rescue.

Each instrument catches exactly what the other is structurally blind to.
Blending them into one number destroys both edges. Keeping them as two
opinions captures both.

## One-line answer

Reading the odds improves your **SYSTEM** (model + market column), not your
**MODEL**. The model stays an independent instrument; the odds are a second
instrument; the value is in comparing them — never in fusing them.
