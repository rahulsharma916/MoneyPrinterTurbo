## Phase 6 Step 12 — Automated Production Optimization & Continuous Improvement

Builds a channel-separated, evidence-backed optimization backlog from the existing
Phase 6 Step 6 performance intelligence and Step 11 production intelligence reports.

### Run

```bash
python automation/build_youtube_production_optimization.py \
  --performance storage/reports/performance_intelligence.json \
  --production storage/reports/production_intelligence.json \
  --output-json storage/reports/optimization_plan.json \
  --output-md storage/reports/optimization_plan.md \
  --output-csv storage/reports/optimization_actions.csv
```

The tool produces:
- JSON decision-support plan with per-channel baseline and recommendations.
- Markdown review report.
- CSV action backlog suitable for manual prioritization.

### Decision logic

- Uses only supplied Analytics metrics, technical quality outcomes, workflow checkpoint
  status and explicitly recorded actual cost ledger entries.
- Flags weak average view percentage, engagement and subscriber conversion for controlled
  creative tests; strong view percentage for structured replication tests.
- Uses an existing directional format comparison only as a test-priority signal.
- Flags failed technical checks, stale evidence and blocked/failed workflow stages.
- Calculates reported cost per 1,000 views only when actual cost records and Analytics
  views exist; currencies remain separate. This is not revenue, ROI or profitability.
- Missing analytics or cost data is explicitly treated as missing/unknown, never zero.

### Safety and limitations

This is deterministic decision support, not autonomous optimization. It does not alter
content calendars, prompts, scripts, budgets, assets, channel settings or credentials. It
does not call providers, render videos, upload, schedule or retry jobs. Every action is
marked for human approval. Compare equivalent reporting windows and use YouTube Studio
for CTR, retention curves, revenue and official YPP eligibility.

Run tests with:

```bash
python -m unittest automation.tests.test_build_youtube_production_optimization
```

Tests are added with this change; they must be run in the project environment before
release.
