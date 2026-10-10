# NBA report input cache — 2026-10-10

A reproducible synthetic unit fixture showed that changing Sportsbet JSON from
1.74 to 1.85 reused an existing valid report without running the generator.
This fixture was never used as live odds or prediction evidence.

Report reuse now requires matching SHA-256 digests for the odds, extractor,
renderer, active model and feature names, execution mode, Git revision and report.
An absent or malformed cache forces regeneration. The existing output firewall
still runs. Inputs changing during generation prevent successful completion.
The sidecar is written atomically after generation and validation.

No scoring weights or trained model artifacts changed. This fixes source/report
consistency; it does not demonstrate better prediction performance. Live full-day
publication still requires complete official schedule and market coverage.

Validation: NBA daily test suite and repository quick/full gates are recorded in
the exact-scope release manifest. Separate tests cover changed inputs, tampered
reports, cache absence, reuse with firewall, regeneration and concurrent mutation.
