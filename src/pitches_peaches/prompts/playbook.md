Build the technical playbook for this interview.

{{voice}}

# What this is and is not

You supply questions and reference answers. You do not grade, score, or judge
anything the reader says. There is no mock interview here, no "you got that
wrong", no readiness percentage. They read the answers; they decide what they
know.

# Branch: {{branch}}

{{branch_instructions}}

# The technical core

Pick at most {{max_technologies}} technologies from the role's requirements,
weighted by `must_have` and by what the reader will actually be tested on.
Fewer is fine. Three shallow ones is worse than two deep ones.

For each, at most {{max_questions_per_tech}} questions.

## Choose the third-most-likely question, not the first

Explicitly forbidden, by name, because they teach nothing to someone at this
level:

- "What is a Python decorator?" / "Explain list vs tuple" / "What is the GIL?"
  asked as a definition
- "What is a database index?" / "Explain normalization" / "SQL vs NoSQL"
- "What is Docker?" / "What is the difference between a container and a VM?"
- "Explain REST" / "What are HTTP verbs?" / "What is idempotency?" as a
  definition question
- "What is eventual consistency?" / "Explain CAP theorem"
- "What is a closure?" / "What is `this` in JavaScript?"
- Anything answerable from the first paragraph of the official docs.

Ask what a strong senior would find interesting: the question where the obvious
answer is right but incomplete, and the follow-up is where the engineering
lives. `why_this_one` says what separates a good answer from a complete one.

## Depth target

Answer as if explaining to a staff engineer who will ask a follow-up, and then
answer the follow-up before they ask it. Go down to mechanism. The reader
should finish the answer knowing not just what happens but why it was built
that way and what breaks when it is not.

Calibration, from three different stacks:

- **Python.** Not "what is name mangling" — why `__x` mangles at all, what
  problem in subclassing it solves, and where it fails. And: the full path from
  `python run.py` to a syscall — tokenizer, AST, compiler, bytecode, the CPython
  eval loop, frame objects, reference counting and the cycle collector, the GIL
  and what actually holds it, down to where the interpreter finally calls
  `write`.
- **Kafka.** Not "what is a partition" — three topics, three consumers, the
  leader for one partition dies and the quorum cannot elect. Walk the ISR, the
  controller, what `min.insync.replicas` does to the producer, unclean leader
  election and the data loss it trades for availability, and what the consumer
  group actually observes while this is happening.
- **FastAPI.** Not "how do I add a dependency" — what dependency injection is
  *for*, why it is a request-scoped resolution graph rather than a decorator
  convenience, how the cache and yield-teardown behave, and how server-sent
  events are actually wired in current versions, including where the connection
  dies and who notices.

## Deep dives

One or two per technology, on the parts where a single walkthrough is worth
more than another question. A deep dive is a mechanism narrated end to end —
the failure, what the system does, what the operator sees, what the fix is.

## Seniority scales the depth

This role is **{{seniority}}**.

- staff, principal, lead: the mechanism-level answers above, plus the trade
  they encode and when you would take the other side of it.
- senior: the mechanism-level answers above.
- mid: the same questions, less internals, more practical framing — what you do
  when this happens in production, what you check first, what the runbook says.
- junior or unknown: the same questions, answered from the outside in — what
  the thing does, when it bites, one level of mechanism.

# closing_questions

Four to six questions the reader asks *them*. Due diligence runs both ways, and
at a small company being evaluated back is usually a signal the founder is
filtering for. Make them specific to what the recon actually found — the open
questions, the unverified claims, the thing the market story does not explain.
Generic questions about culture are wasted turns.

---

# The role

{{recon}}

# Their background

{{profile}}

# Where they are strong and weak against this role

{{match}}
