# AU progressive publication

Goal: publish each complete evening meeting while extraction continues; keep one morning batch and isolate invalid meetings.

- [x] Add one shared publication transaction lock covering AU, HKJC, hooks and direct deploys.
- [x] Add closed-list snapshot merging and per-meeting quarantine without weakening field gates.
- [x] Add a subprocess publisher with immutable input copies, coalescing, durable results and bounded shutdown.
- [x] Wire evening completion callbacks and retain morning batch behavior; expose failures accurately.
- [x] Test overlap, coalescing, restart, failure isolation, immutable inputs and foreign-region preservation.
- [x] Run an offline replay benchmark recording copy time, foreground delay and publication count.
- [ ] Run quick/full checks, exact-scope release, production verification and clean up the worktree.

No extra Sportsbet fetches or scoring changes. Disable with WC_AU_PROGRESSIVE_PUBLISH=0.
