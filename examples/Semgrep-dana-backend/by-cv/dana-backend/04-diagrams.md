# Diagrams

## Semgrep's likely product and backend architecture, with tenant and metering boundaries

```mermaid
flowchart TD
CUST["Customer org<br/>Security team / developers"]
WEB["Semgrep web app<br/>TypeScript + React"]
API["Backend API<br/>Python + Flask + SQLAlchemy"]
AUTH["AuthN/AuthZ<br/>(inferred) tenant + role checks"]
TEN[("Tenant data store<br/>orgs, repos, users, findings")]
SCAN["Scan / analysis service<br/>Pro Engine + rules processing"]
JOBQ["Async jobs / queue<br/>(inferred) scan throughput"]
INT["Third-party integrations<br/>GitHub/GitLab, CI, cloud, vendors (inferred)"]
AI["Assistant / AI credits<br/>(inferred) external model vendor"]
SUB["Billing + plans<br/>Free / Teams / enterprise"]
MTR[("Usage meter<br/>scans, repos, contributors, AI credits")]
OBS["Logs / metrics / alerts<br/>(inferred) reliability"]
AWS["AWS + Kubernetes hosting"]

CUST -->|"uses product"| WEB
WEB -->|"API calls"| API
API -->|"authenticate and authorize"| AUTH
AUTH -->|"read/write tenant scope"| TEN
API -->|"create scans and fetch findings"| SCAN
SCAN -->|"enqueue heavy work"| JOBQ
JOBQ -->|"run analysis at scale"| SCAN
SCAN -->|"store results per tenant"| TEN
API -->|"sync repos, PRs, tickets, vendor data"| INT
API -->|"request AI help / credits"| AI
API -->|"check entitlement and plan"| SUB
SUB -->|"bill by usage and seat count"| MTR
SCAN -->|"increment usage"| MTR
API -->|"emit health signals"| OBS
SCAN -->|"emit traces and errors"| OBS
WEB -->|"served from"| AWS
API -->|"deployed on"| AWS
SCAN -->|"deployed on"| AWS
JOBQ -->|"hosted on"| AWS
```

*Also written to `diagrams/architecture.mermaid`.*

## Predicted Semgrep interview process from recruiter screen to offer

```mermaid
flowchart TD
A["Recruiter screen"] -->|"fit for hybrid role, motivation, comp, location"| B{"Location and level fit?"}
B -->|"yes"| C["Hiring manager call"]
B -->|"no"| X["No hire / hold"]
C -->|"scope, ownership, backend judgment, product motivation"| D{"Signals enough backend depth and ownership?"}
D -->|"yes"| E["Technical screen or live coding"]
D -->|"no"| X
E -->|"correctness, edge cases, production-shaped code"| F{"Pass coding bar?"}
F -->|"yes"| G["System design interview"]
F -->|"no"| X
G -->|"scaling, data model, reliability, tenant isolation"| H{"Good architecture tradeoffs?"}
H -->|"yes"| I["Final loop / panel"]
H -->|"no"| X
I -->|"founders and leaders assess product judgment, speed, collaboration"| J{"Strong culture and role fit?"}
J -->|"yes"| K["Offer"]
J -->|"no"| X
```

*Also written to `diagrams/process.mermaid`.*
