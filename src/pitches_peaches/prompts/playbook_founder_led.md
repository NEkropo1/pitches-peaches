This is a small company, so there is no process to predict — there is a person
to understand. The interview will be shaped by whoever runs it far more than by
any rubric.

Fill `interviewer_profiles` from the recon's interviewers plus whatever public
trace they leave: prior companies, prior *titles* in order, talks, blog posts,
open-source work, the voice of the job ad itself.

Read the sequence of roles, not just the current one. A CTO who was a product
officer before they were a CTO evaluates architecture through "what does the
customer see and pay for", not through elegance — so a forty-minute purity
argument loses and a sentence about what the buyer experiences wins. Someone
who has only ever been an infrastructure engineer inverts that. Say which one
this is, label it as inference, and say what it predicts they will probe.

The job ad itself is evidence. If the founder wrote it, the vocabulary,
the length, and what it is anxious about all tell you how they think. A
requirements list is a list of ways the founder is afraid the hire could fail —
read it that way and say what each fear is.

`pitch_adaptation` is the payload: how the reader should shape their own story
for this specific person. Which project to lead with, which framing to use for
it, what to compress, what to cut entirely. Be concrete — name the project from
their background and the sentence that opens it.

Also cover what tends to land badly with this person, as testable hypotheses:
enterprise ceremony, hedged non-answers, asking them to define requirements
they do not have yet, or an unprompted architecture lecture.

Set `branch` to `founder_led`. Fill `rounds` only with what the posting or the
recon actually states about the process — do not invent a five-stage loop for a
three-person company. If the process is unknown, leave `rounds` empty and put
"what does your process look like" in `closing_questions`.
