# Phase 2 demonstration

## Explain the idea in 30 seconds

“I built a synthetic prototype that learns hourly study demand and compares it with scheduled, eligible reading capacity. It models readers as shared resources, so it doesn't count the same physician's time separately for every client. An ambassador gets client and modality exceptions rather than manually scanning everything. Leadership can also test a volume increase or coverage change before deciding how to respond.”

## Two-minute walkthrough

1. Open the current queue to show the original SLA-age and eligibility monitor.
2. Select **Forecast & what-if planning** to show expected six-hour arrivals, completions, misses and backlog.
3. Point to the hourly view: throughput drops as shifts end while new work continues arriving.
4. Review the client/modality/priority table. Explain that simulated breach frequency means at least one miss in that group, not a validated probability for an individual study.
5. Activate full-window coverage for Dr. Brooks and click **Compare coverage scenarios**. Completions rise and modeled misses fall, but unsupported client/modality queues remain visible.
6. Test a volume increase to connect the tool to growth decisions.
7. Open **Forecast evidence and assumptions** to show how the historical estimator was evaluated and which assumptions need validation.

## Connect it to the ambassador's role

“The goal is to remove surveillance work and give the ambassador earlier, more specific coverage signals. That preserves time for supporting radiologists and resolving exceptions that need human judgment. Before live deployment, I'd validate the data, the eligible coverage rules and the forecast against the organization's actual outcomes.”

## What is implemented

Historical demand estimation, repeatable scenario simulation, explicit shift/eligibility constraints, client-level exceptions, staffing/volume comparisons, exports, rolling count-forecast evaluation and automated tests.

## What still requires production work

Live feeds; complete licensing, privileges, specialty and contractual rules; calibrated breach prediction; real service-time/arrival distributions; validated escalation thresholds; access controls; audit logs and workflow integration. This prototype demonstrates operational reasoning, not an installed product or verified business result.
