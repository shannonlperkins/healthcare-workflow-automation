# Design Notes

## Objective

Reduce ambassador time spent manually scanning worklists by surfacing only the studies and capacity conditions most likely to require intervention.

## Principle

**Automate surveillance; preserve human judgment.**

The system should not attempt to replace radiologists, interpret images, or invent client rules. It should make approved operational rules easier to execute consistently at scale.

## Required production inputs

- Study ID / operational accession token
- Client or facility
- Priority class
- Modality or specialty
- Study received timestamp
- Contractual SLA
- Current queue age
- Radiologist active status
- Shift end time
- Client credentialing / privileges
- Modality / specialty eligibility
- Current workload or queue depth
- Estimated read capacity
- Known system outages or interface issues

## Useful model features later

Historical training data could add:

- hour of day
- day of week
- client-level arrival rate
- modality arrival rate
- rolling 15 / 30 / 60-minute volume
- active eligible reader count
- reader utilization
- predicted read time
- shift transitions
- recent SLA performance
- abnormal queue growth

## Guardrails

1. No diagnosis or clinical interpretation.
2. No free-text PHI sent to a general-purpose model.
3. Eligibility and client requirements remain rules, not model guesses.
4. Every recommendation should be explainable.
5. Human override is preserved and logged.
6. Stale or incomplete data should downgrade confidence rather than silently act.

## Phase 2 implemented design

### Demand estimation

`forecast_demand` learns an empirical count distribution for each client/modality/priority stream from completed historical hours matching the forecast weekday and hour (timestamps normalized to UTC). At least four matching observations are needed. Otherwise it falls back to the same hour across weekdays with at least seven observations, then the complete observed window with at least 24 hours. Every stream must explicitly include zero-volume hours and extend through the latest completed hour; gaps are rejected. The demo stores timestamps in UTC and displays forecasts in America/Chicago. Production ingestion must use one agreed time basis and account for local daylight-saving effects.

Forecast means and percentile ranges are descriptive estimates. No future/current incomplete bucket is used to train the forecast. The demo's repeated seasonal patterns are invented and must not be interpreted as actual site demand.

### Capacity and turnaround simulation

Bootstrap sampling draws a count from each forecast stream/hour's empirical distribution. Arrivals are uniform within each hour. Fixed synthetic read times are CT 7, MRI 12, XR 3 and US 8 minutes, adjusted by a reader speed factor. These values are illustrative operational assumptions, not clinical benchmarks. A stochastic rounding step preserves fractional expectations when applying volume scenario multipliers.

The simulator uses a single shared resource per radiologist. It enforces client credentialing and modality membership; a reader cannot read multiple jobs simultaneously. Dispatch is nonpreemptive, STAT before Urgent before Routine, then earliest deadline inside each priority. Among eligible free readers, the heuristic favors the least flexible reader to preserve broader eligibility. This is a heuristic, not globally optimal routing.

The authoritative capacity source is `shifts.csv`, not the Phase 1 snapshot's `active` flag or workload slot counts. Initial `busy_minutes` represent already-assigned work outside `studies.csv`, ensuring the displayed open queue is not counted twice. A read must finish within both the shift and the simulation horizon. Future jobs near the horizon whose deadline is later remain pending without being classified as overdue. Hypothetical full-window coverage overrides schedules only; it never creates new credentials.

Hourly capacity is counted once per reader in reference read minutes, adjusted for speed. Aggregate demand/capacity differences are diagnostic context; only the simulation's eligibility-aware completions reflect usable throughput across competing queues. No client-level capacity sum is presented as independent capacity for each client.

### Risk semantics and actions

Group breach frequency is the proportion of sampled scenarios with at least one due-within-window miss in that client/modality/priority group. High = at least 50%, Watch = at least 20%, Low = below 20%; these are demo display thresholds, not validated escalation policy. Expected misses and backlog accompany the frequency so a large queue's near-certain chance of at least one miss is not confused with every study being at risk.

Recommendations ask for coverage review or escalation of missing eligible coverage. No dispatch, credential change, client notification, or clinical decision is performed. Scenario results use a fixed random seed; staffing-only comparisons receive the same demand realizations. Demand-changing comparisons may consume different random draws and remain illustrative.

### Evaluation and limits

The rolling forecast backtest predicts one hour every four hours across seven holdout days, trains strictly before each prediction time, and reports cell-level MAE and WAPE. A flat recent-week per-stream count mean is the comparison baseline. This evaluates count predictions, not calibration of SLA-breach probabilities.

Production evaluation must cover correlated client surges, intra-hour arrival clustering, changing service times, stochastic reader availability, interruptions, different clinical priority policies, rare events and new-client cold starts. Licensing, privileges, specialty, reporting type, image readiness and critical-result communication are not enforced by this demo. Full integrations also need freshness checks, audit trails, access control, and approved operational policies. No real operational feed or sensitive information is included.
