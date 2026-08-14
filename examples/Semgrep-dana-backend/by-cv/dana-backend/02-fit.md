# Fit: Senior Backend Software Engineer — Semgrep

> AI recommendation — you decide next. PitchesPeaches does not apply to anything, contact anyone, or send anything anywhere. Everything below is built from what you provided about yourself.

## Overall — 84/100 · STRONG FIT

`███████████████████████████████████████░░░░░░░`

| Dimension | Score | |
|---|---:|---|
| **Technical** | 92 | `██████████████████████░░` |
| **Ownership** | 93 | `██████████████████████░░` |
| **Delivery** | 90 | `██████████████████████░░` |
| **Business Context** | 68 | `████████████████░░░░░░░░` |

**Technical** — You already work in Python, Flask, SQLAlchemy, PostgreSQL, Redis, AWS, and Kubernetes, which lines up cleanly with their backend stack. React is not a strength for you, but this is still a backend-first fit.

**Ownership** — You have owned a platform end to end, including the migration, the on-call, the runbooks, and the storage redesign. That is the kind of scope where they will expect you to make tradeoffs without waiting for permission.

**Delivery** — You shipped for around 400 customer organisations and cut p99 query latency from 4.2 seconds to 380 milliseconds. You also drove monthly infrastructure spend down by 38%, which signals production delivery under real constraints.

**Business Context** — You are adjacent rather than native to AppSec, but your linting and static analysis work is unusually close to Semgrep's product shape. You will still be learning the buyer language and the security workflow around code scanning and triage.

## Why you fit — with evidence

You already have the exact backend substrate they are hiring around: Python, Flask, SQLAlchemy, PostgreSQL, Redis, AWS, and Kubernetes.

> Backend technologies: FastAPI, Flask, SQLAlchemy, Celery, gRPC

*claim: Stack overlap*

You have done a real multi-tenant migration, which is the kind of architecture call Semgrep will expect from a senior backend seat.

> Inherited a single-tenant Django monolith and moved it to a multi-tenant service on self-managed Kubernetes.

*claim: Multi-tenant migration*

You have worked on the exact performance shape they care about: a user-facing query platform with a sharp latency reduction.

> p99 query latency from 4.2 seconds to 380 milliseconds

*claim: Query latency*

Your linting and static-analysis work maps directly to an AppSec product that analyzes code and has to keep noise down.

> Built and maintained the internal linting and pre-commit tooling used across roughly 120 repositories.

*claim: Static analysis*

You already said you have production experience integrating third-party vendors, which is one of the role’s explicit asks.

> Yes, I have production experience with this — it came up in the multi-tenant CI analytics platform work described in my CV. Happy to go deeper on the specifics in conversation.

*claim: Vendor integrations*

You have shipped for around 400 customer organisations, so this is not a toy-scale backend.

> Owned the ingestion and query platform that processed build and test telemetry for around 400 customer organisations.

*claim: Customer scale*

## Gaps

****Hybrid in a US office.**** You are in Lisbon, while this role expects 3+ days a week in San Francisco, New York, Boston, or Denver, with remote only for exceptional candidates.

****No production React depth.**** The role names TypeScript and React on the frontend, and you have said React is basic; that is enough to read the UI and make small changes, not to own frontend-heavy work.

****No direct AppSec product loop.**** Your linting and static-analysis work transfers well, but Semgrep will still probe how you think about precision, recall, false positives, and developer trust in a security product.

## What to prepare

- Rehearse the multi-tenant migration from the single-tenant Django monolith to self-managed Kubernetes, because that is your cleanest senior-backend story here.
- Have the p99 latency drop from 4.2 seconds to 380 milliseconds ready with the storage split behind it, because Drew will likely push on performance tradeoffs.
- Be ready to walk through the two multi-tenant data-leak near-misses and the guardrails you added, because trust and isolation matter a lot in an AppSec platform.
- Lead with the internal linting and pre-commit tooling across roughly 120 repositories, because that is the closest bridge from your record to Semgrep’s code-analysis product.
- Have a crisp answer for the Lisbon-versus-US-office question, because the hybrid expectation is the main logistics issue that can stop the process early.
- Prepare a concrete vendor-integration story with the exact vendor, the data flow, and the failure mode, because that is an explicit part of the role and the interviewers will likely ask for specifics.

## Still open

- Semgrep explicitly wants someone comfortable integrating third-party vendors into existing first-party code; what is the hardest third-party integration you have owned end to end?
- This role expects you to join a Semgrep office 3+ days a week in San Francisco, New York, Boston, or Denver; what location setup are you planning to bring to the interview?
- You list React as basic; what production frontend work have you actually shipped in React?
- Your CV says you have some exposure to static analysis through linter tooling; what did that work look like in practice?
- You mention two multi-tenant data-leak near-misses; what was the failure mode in the worst one?
