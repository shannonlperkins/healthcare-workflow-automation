# Radiology SLA & Capacity Risk Monitor

A synthetic-data MVP for a teleradiology operations team.

The monitor continuously ranks open studies by **operational risk** so ambassadors can spend less time manually watching queues and more time helping radiologists, clients, and true exceptions.

> **Important:** This project uses synthetic operational data only. It does not interpret medical images, determine clinical urgency, or make diagnostic decisions.

## Business problem

At scale, an operations team may have to track:

- client-specific turnaround-time requirements
- STAT / urgent / routine queues
- radiologist credentials by client
- modality eligibility
- active versus offline radiologists
- current reader workload
- approaching SLA breaches
- exceptions that require a person

Manual surveillance does not scale well. The goal is to convert that work into **exception-based operations**.

## MVP

The application:

1. Loads synthetic client SLA rules, radiologist eligibility, workload, and open studies.
2. Determines which active radiologists are eligible for each study.
3. Calculates an explainable 0–100 operational risk score.
4. Classifies each study as GREEN, YELLOW, or RED.
5. Produces a prioritized queue and a human-readable next action.
6. Separately displays radiologist capacity and utilization.

## Risk logic

The MVP score combines:

- **55% SLA pressure** — how much of the allowed turnaround time has elapsed
- **20% capacity pressure** — workload of eligible radiologists
- **15% eligibility pressure** — scarcity of eligible readers
- **10% priority pressure** — STAT / urgent / routine
- an additional penalty for an existing SLA breach

A study with **no active eligible reader** is automatically RED.

The weighting is intentionally transparent for a proof of concept. In production, contractual rules should remain deterministic while a calibrated predictive model can estimate future breach probability from historical operational data.

## Architecture

~~~text
Client SLA Rules ───────┐
Credentialing Rules ────┤
Open Study Queue ───────┼──> Risk Engine ──> Prioritized Queue
Radiologist Capacity ───┤                     ├─> Ambassador Actions
Shift / Availability ───┘                     └─> Capacity Alerts
~~~

## Run locally

~~~bash
cd radiology-sla-capacity-monitor
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
~~~

## Run tests

~~~bash
pytest -q
~~~

## Suggested production roadmap

### Phase 1 — Rules + live monitoring
Connect operational feeds for study status, SLA rules, radiologist eligibility, shift status, and queue workload.

### Phase 2 — Forecasting
Predict demand by hour, client, modality, urgency, and day-of-week. Compare projected demand with scheduled reading capacity.

### Phase 3 — Breach prediction
Train and calibrate a model using de-identified historical operational data to estimate the probability of an SLA miss before it occurs.

### Phase 4 — Next-best-action engine
Recommend queue redistribution, coverage escalation, or ambassador intervention while preserving deterministic credentialing and client rules.

### Phase 5 — Operations copilot
Allow authorized staff to ask questions such as:

- Which clients are at highest SLA risk in the next 30 minutes?
- Where do we have a CT capacity gap tonight?
- Which client requirements are driving the most manual interventions?
- What changed in the last hour?

## Safety / governance

A production version should:

- avoid PHI wherever operational identifiers are sufficient
- maintain role-based access
- log recommendations and human overrides
- keep credentialing, licensing, and contractual rules deterministic
- validate data freshness before acting
- require human review for material operational escalations
- never use this system for diagnosis or image interpretation

## Portfolio framing

This project demonstrates how healthcare operations can use AI and automation to shift staff from **manual surveillance** to **exception management**, increasing scalability while protecting radiologist focus and client service.
