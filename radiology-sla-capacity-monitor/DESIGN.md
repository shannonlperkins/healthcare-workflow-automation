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
