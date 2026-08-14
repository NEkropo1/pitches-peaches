# Semgrep — Senior Backend Software Engineer

> *Facts below are verified against public sources as of 2026-08-13: Semgrep’s about page, the 2020/2021/2023/2024/2025/2026 Semgrep blog posts, the Semgrep product and pricing pages, MIT News coverage of r2c, the founder keynote, the AI hackathon and AppSec builder posts, the internship posts, the Wellfound r2c people page, and the GitHub Advanced Security and Snyk Code docs. Where something is inference rather than fact, it is explicitly labelled. Anything labelled "unverified" you confirm on the call, not before.*

## What you are walking into.

You are walking into a founder-led security company that is already past the tiny-startup phase: Semgrep said it had 150+ full-time people in November 2024, it raised a $100M Series D in February 2025, and the role is posted as senior backend work with a $163,000 to $246,500 base salary range plus equity and variable compensation. This is not a “keep the lights on” backend seat. It is a seat where backend decisions are part of the product promise: fast scans, fewer false positives, cleaner triage, and integrations that do not break customer trust.

The company’s public story is unusually coherent for a scaleup. It started as r2c in 2017, reopened the open-source Semgrep project in 2020, and turned that into a broader AppSec platform. The people in the room are not career operators detached from the product. Drew Dennison, Isaac Evans, and Luke O’Malley are all founders, and the engineering leader you are likely to meet, Cathy Polinsky, is new enough that she is still defining what “excellent” looks like inside the org. That means you should expect a mix of technical depth and product judgment, not just “can you ship code.”

## The lineage.

In 2017, Semgrep was founded by Drew Dennison, Isaac Evans, and Luke O’Malley under the r2c name. The company’s own history says it later reignited the open-source Semgrep project in 2020 and used that as the base for the current platform.

Before Semgrep, the founders came out of different places, which matters because it explains why the company keeps sounding like a hybrid of research lab, developer tool company, and security product business. Isaac Evans was at MIT researching binary exploitation; the MIT News piece on r2c is from 2022, so the exact timing of that work is not fully pinned down in the materials I consulted. Luke O’Malley’s background includes product and engineering work at Palantir. Drew Dennison had been a Redpoint Ventures EIR. Those pre-Semgrep roles are part of why the company sounds technically opinionated but still commercially aware.

Then the company stages itself in public milestones rather than a single neat origin story. In 2021 it announced a Series B. In 2023 it announced a Series C. In 2024 it publicly described itself as having 150+ full-time Semgreppers and noted a downtown San Francisco HQ with a New York satellite office. In 2025 it announced the $100M Series D led by Menlo Ventures, with Felicis, Harpoon, Lightspeed, Redpoint, and Sequoia participating. The 2024 renaming work around “Semgrep OSS” is another clue that the company is still shaping how its open-source and commercial identities fit together.

Charitably, this looks like a founder-led company that kept following the same problem as it grew: code security needed a better developer experience, and they kept broadening the product until the market agreed. Uncharitably, it also looks like a company that has repeatedly found distribution around an idea that still has to prove how cleanly it becomes a durable platform. Both readings are true at once.

## What the product actually is.

Semgrep is an application security platform for code. That means it sits in the world where security and engineering meet at the source code level, not just at the perimeter. The product promise is that teams can catch, flag, and fix real issues before they ship. The practical enemy is the backlog of findings that security teams do not trust and developers do not want to touch.

If you need the vocabulary for the call, think in these terms. “Code security” here is mostly about static analysis over source code and related signals. “False positives” are findings that do not represent real risk; reducing them matters because security teams spend time triaging junk. “Reachable vulnerabilities” are issues that matter in practice because they can actually be hit in the running system. “AppSec” means application security, and in this company’s framing it is built for developers as much as for security teams.

Semgrep says its platform now includes Code, Supply Chain, Secrets, and Assistant, with a Pro Engine underneath. That means the buyer is not just buying a scanner; they are buying a system that handles multiple security surfaces and tries to turn results into something usable. The company’s public claim is that its AI learns context to cut false positives and prioritize reachable vulnerabilities, and that this has been validated by 95% of security reviewers across 6M+ findings. That is Semgrep’s claim, not independent validation in the material I used.

The money is public and useful. Semgrep’s Free Edition includes up to 10 repos, 10 contributors, and 60 AI credits. The paid Teams tier starts at $30 per month per contributor. The public pricing page does not spell out a full enterprise commercial structure, so that part is unverified — confirm on the call whether there is a separate enterprise motion, how it is sold, and where backend work touches that motion.

## The system described in the posting.

Taken seriously, the posting is asking for someone who can operate at the junction of product backend, platform backend, and infrastructure. The words “design, build and maintain a fast and reliable user experience for our customers” are doing real work here. They are not asking only for CRUD services. They are asking for the part of the stack that makes the product feel trustworthy under load.

The technical shape is clear: APIs, data models, services, databases, query optimization, and distributed systems. The stack listed in the posting is TypeScript and React on the frontend, Python with Flask and SQLAlchemy on the backend, Kubernetes for deployment, and AWS for hosting. That means you are likely stepping into a codebase with some older Python service patterns, a web product surface, and enough scale or complexity that database behavior and service boundaries matter. The requirement to be comfortable integrating third-party vendors into first-party code suggests you may also be dealing with payments, AI vendors, authentication, security tooling, or other external dependencies that have to look native to the product.

Your angle is to treat this as a product-system role, not a pure platform role. The open questions in the record are the ones that matter most: how much of the job is customer-facing product work versus infrastructure, what is new build versus legacy Flask/SQLAlchemy, and where the current bottleneck actually sits. If the answer is scan latency, query latency, triage pipelines, auth/tenant isolation, or vendor integrations, the right conversation is about reducing customer-visible friction without creating a new maintenance tax.

## The market claim.

Semgrep’s public positioning is that it is the leader in code security for builders, with trust from Vanta, Lyft, and Dropbox, Gartner recognition in application security testing, and a product that reduces false positives and triage burden. The cleanest way to test that claim is to compare it with the rest of the category.

The asterisk is that Semgrep is not alone. GitHub Advanced Security has code scanning and autofix material in its docs, and Snyk Code also advertises automatic fixing paths. So the defensible version of Semgrep’s claim is not “we are the only platform that can do this.” It is: Semgrep is a developer-first AppSec platform with open-source roots, broad language coverage, a high release cadence, and a stronger public story around reducing false positives and making security work feel less like a separate workflow.

The company’s own numbers support that framing. It says it covers 40+ languages, runs 75M+ scans per year, has 3000+ community rules, and ships 100+ releases. Those numbers imply breadth and activity, not a narrow point solution. If you want the strongest honest version of the market claim, it is that Semgrep has built real distribution in a crowded AppSec market by making the product feel closer to how builders work than how legacy security tools work.

## The people.

### Cathy Polinsky — co-CTO and VP of Engineering

Verified: she is co-CTO and VP of Engineering, and the materials describe her as recently joined. The public writing attached to her name centers on hackathons, product-centric thinking, and shipping demos.

Inferred: she is likely to care about speed that does not turn into a maintenance disaster. She probably wants to see whether you can move quickly, make tradeoffs explicit, and still leave the codebase healthier than you found it.

What tends to land well is concrete evidence that you know how to ship under constraints: a before/after latency win, a migration that cut support load, a database change that improved reliability, or a story about using a small implementation to validate a bigger product bet. What tends to land badly is architecture talk that sounds clean but ignores delivery pressure. Hypothesis: she will probe for whether your instincts are product-minded or merely technically elegant.

### Drew Dennison — CTO and co-founder

Verified: he is CTO and co-founder, and the materials cast him as the public technical face of the company. His pre-Semgrep background includes Redpoint Ventures EIR.

Inferred: he will likely push on system design, performance, and whether your solutions create product bloat. He is probably looking for someone who can reason at the level of databases, service boundaries, and throughput, not just endpoints.

What tends to land well is specificity: query plans, bottleneck analysis, scaling tradeoffs, failure modes, and why one data model is better than another. What tends to land badly is generic “best practices” language without numbers or an explanation of the operational cost. Hypothesis: he will ask whether you can make hard tradeoffs without hiding complexity somewhere else in the stack.

### Isaac Evans — CEO and co-founder

Verified: he is CEO and co-founder, and before Semgrep he was at MIT researching binary exploitation. The public writing tied to him is about product and strategy.

Inferred: he is likely to care about how backend choices affect the product architecture, the business, and the AppSec buyer problem. He will probably care less about abstract elegance than about whether the system helps Semgrep win trust and adoption.

What tends to land well is showing that you understand the buyer’s pain: security teams drowning in findings, developers ignoring tools that interrupt flow, and the need to make security feel actionable. What tends to land badly is treating the work as only an internal engineering problem. Hypothesis: he will probe whether you can connect technical decisions to conversion, retention, and workflow adoption.

### Luke O’Malley — CPO and co-founder

Verified: he is CPO and co-founder, and the materials frame him around developer-first AppSec; his pre-Semgrep background includes product and engineering work at Palantir.

Inferred: he is probably the person most focused on whether your backend choices make the user experience simpler or more brittle. Expect him to care about the friction visible to developers and security reviewers, not just the shape of the service layer.

What tends to land well is product judgment expressed through backend decisions: making a page load faster because the workflow matters, reducing ambiguity in a triage queue, or removing a vendor boundary the user should never feel. What tends to land badly is engineering that is technically neat but makes the product feel heavier. Hypothesis: he will ask whether your designs help the user move faster without adding hidden complexity.

## The process.

The full-time backend interview loop is not confirmed in the materials I consulted. Public Semgrep internship posts described recruiter screens, take-home coding projects, live technical challenges, a hiring manager screen, and informal calls with the CTO and other team members, but that is not the same thing as the loop for this role. Unverified — confirm on the call.

The useful questions are direct: how many rounds are there, is there a take-home, is there a system design round, who is in the loop, and what “exceptional candidates” means for remote consideration. Also ask whether the role is mostly product backend, infrastructure, or a mix, because that changes what the interview will reward.

## Close.

You are walking into a founder-led, well-funded AppSec scaleup with real usage, real customers, and a backend surface that sits close to product value. The interview is likely to test whether you can keep the system fast and reliable while making the product feel simpler, reducing false positives and friction, and handling the legacy-plus-new-build reality of a Python/Kubernetes/AWS stack.

Be concrete about tradeoffs, tie every backend choice to customer impact, and show that you can improve the system without pretending complexity does not exist.
