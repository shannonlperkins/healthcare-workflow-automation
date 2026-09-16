# Automation Rules

## Purpose

These rules define how the fictional future-state work queue classifies, prioritizes, assigns, reminds, and escalates administrative healthcare tasks.

AI-assisted classification is used only to interpret administrative intent and suggest a category. Final workflow rules remain deterministic and high-risk exceptions require human review.

## Intake Rules

Every incoming request receives:

- unique request ID;
- received timestamp;
- request category;
- priority level;
- assigned owner or queue;
- due date;
- current status;
- escalation flag;
- completion timestamp when closed.

Requests missing required information are routed to `Needs Clarification` rather than silently assigned.

## Classification Rules

| Request Type | Default Queue | Default Priority | Target Completion |
| --- | --- | --- | --- |
| Referral | Referral Team | Standard | 2 business days |
| Prior Authorization | Authorization Team | High | 1 business day |
| Scheduling Follow-up | Scheduling | Standard | 1 business day |
| Records Request | Records | Standard | 3 business days |
| Billing Question | Billing Support | Standard | 2 business days |
| Documentation Follow-up | Clinical Support | Standard | 2 business days |
| Administrative Patient Message | Patient Support | Standard | 1 business day |
| Medication Workflow — Administrative | Clinical Support | High | Same business day |

## Priority Rules

### Urgent
Use only when a request contains a predefined safety or time-sensitive trigger. The automation does not resolve the request; it immediately routes it to human review.

### High
Used for time-sensitive administrative work such as prior authorizations, same-day medication workflow tasks, and items already approaching an external deadline.

### Standard
Used for routine work that can be completed within the normal service-level target.

### Low
Used for non-time-sensitive internal follow-up, reporting cleanup, or informational tasks.

## Ownership Rules

1. Assign by request type first.
2. If the designated owner is unavailable, route to the backup queue.
3. Never leave a task unassigned.
4. If confidence in classification is below the defined threshold, route to `Needs Human Review`.
5. Clinical interpretation is never assigned to an automated agent.

## Reminder Rules

- 50% of SLA elapsed: passive queue reminder.
- 75% of SLA elapsed: owner reminder.
- 100% of SLA elapsed: mark overdue and alert queue lead.
- 125% of SLA elapsed: escalate to operational leader.

## Escalation Rules

A task escalates immediately when:

- patient-safety language is detected;
- the request requires clinical judgment;
- the request category is ambiguous;
- required information is missing after one clarification attempt;
- an external deadline will be missed;
- the task is overdue beyond the secondary threshold;
- ownership cannot be resolved automatically.

## Closure Rules

A task cannot be marked complete unless:

- disposition is documented;
- completion timestamp is recorded;
- required follow-up is either completed or converted into a new linked task;
- exception/escalation status is resolved.

## Auditability

The model assumes each automated action is logged with:

- original classification;
- final classification;
- owner assignment;
- due-date calculation;
- reminders sent;
- escalation events;
- completion status.

This creates an operational audit trail while preserving human control over exceptions and clinical judgment.
