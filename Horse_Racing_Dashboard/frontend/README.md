# frontend/ — React implementation (NOT the deployed dashboard)

Read this before changing anything in here. There are **two** dashboard
implementations in this directory tree, and this is not the one that ships.

## What actually gets deployed

`./deploy.sh` builds and publishes **`../static_template.html`** — a single
self-contained HTML file with inline CSS and vanilla JS, no build step. That is
what lives at <https://wongchoi-dashboard.pages.dev> and what installs as the
iPhone app. `deploy.sh` never reads this folder.

## What this folder is

A parallel React + Vite implementation of the same dashboard (~5,900 lines across
`src/pages/` and `src/components/`). It is maintained, not abandoned — but it is
not deployed by any script in this repo.

## The one file shared by both

**`src/index.css` is consumed by the deployed dashboard.**
[`generate_static.py`](../generate_static.py) reads it and inlines it into
`static_template.html` at build time:

```python
css_path = Path(__file__).resolve().parent / "frontend" / "src" / "index.css"
```

So editing `src/index.css` changes the live dashboard, even though it sits inside
the React app. Design tokens, `.app-header`, `.app-main`, `.race-pills`,
`.horse-card` and friends all come from here.

Two of those rules are load-bearing in a non-obvious way and carry comments
saying so — `.app-main { overflow-x: clip }` and `html, body { overflow-y: visible }`.
Both were scroll containers once, and a scroll-container ancestor silently
disables `position: sticky` on the mobile race switcher with no error anywhere.

## Consistency tests

`../tests/test_static_template.mjs` reads files from **both** implementations and
asserts they agree on specific points, so a change here can fail the dashboard
test suite:

- `src/pages/RaceDetailPage.jsx` — no duplicate Top Picks panels
- `src/components/HorseCard.jsx`
- `src/index.css`

Run them from `Horse_Racing_Dashboard/`:

```bash
node --test tests/test_static_template.mjs
```

## Running this app locally

Standard Vite. Note that what you see will **not** match production, because
production is the static template, not this.

```bash
npm install && npm run dev
```
