# Workflow Design

## Current State

```mermaid
flowchart TD
    A[Request received from phone, portal, fax, email, or internal message] --> B[Shared inbox or individual queue]
    B --> C[Staff manually reads request]
    C --> D[Staff decides category and priority]
    D --> E[Email / Teams / spreadsheet / memory]
    E --> F{Clear owner?}
    F -- Yes --> G[Owner works request]
    F -- No --> H[Manual follow-up to find owner]
    H --> G
    G --> I{Needs follow-up?}
    I -- Yes --> J[Individual reminder or manual tracking]
    J --> G
    I -- No --> K[Complete]
    K --> L[Limited aggregate reporting]
```

### Current-State Failure Points

- inconsistent intake;
- manual classification;
- unclear ownership;
- multiple tracking locations;
- reminders depend on individual behavior;
- overdue work is difficult to identify;
- backlog is not visible in real time;
- exception handling is inconsistent.

---

## Future State

```mermaid
flowchart TD
    A[Request received] --> B[Standardized intake]
    B --> C[AI-assisted administrative classification]
    C --> D{Classification confidence acceptable?}
    D -- No --> E[Human review]
    D -- Yes --> F[Rules assign priority]
    E --> F
    F --> G[Owner / queue assigned]
    G --> H[Due date calculated]
    H --> I[Central work queue]
    I --> J{Clinical / safety / policy exception?}
    J -- Yes --> K[Human exception pathway]
    J -- No --> L[Owner works task]
    K --> L
    L --> M{SLA threshold reached?}
    M -- 50% --> N[Queue reminder]
    M -- 75% --> O[Owner alert]
    M -- 100% --> P[Overdue + lead escalation]
    N --> L
    O --> L
    P --> L
    L --> Q[Disposition documented]
    Q --> R[Complete]
    R --> S[KPI dashboard + audit trail]
```

## Control Points

The future-state workflow deliberately preserves human control at high-risk points:

1. low-confidence classification;
2. clinical interpretation;
3. patient-safety concerns;
4. policy exceptions;
5. missing information;
6. unresolved ownership;
7. extended overdue work.

## Operating Model

The workflow is designed around five principles:

**One intake structure** — every request enters with the same required metadata.

**One accountable owner** — no task remains unassigned.

**One service-level clock** — deadlines are based on request type and priority.

**One exception pathway** — automation stops when human judgment is required.

**One performance view** — backlog, overdue work, handling time, and exceptions are visible to leaders.
