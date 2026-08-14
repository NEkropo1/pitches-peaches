# A complete run, exactly as it came out

This is real output, not a mock-up. One `peaches run` against the checked-in
fixture posting and CV on 2026-08-13, `openai` / `gpt-5.4-mini` at effort
`medium`, inside a workspace. Nothing here was written by hand except this file.

It exists so you can read what the tool produces without installing anything,
setting a key, or spending the ~$0.90 a run costs.

```bash
peaches run tests/fixtures/posting.txt --cv tests/fixtures/cv.json --audio
```

**Dana Whitfield is invented.** The CV is `tests/fixtures/cv.json`, written as a
realistic test fixture with one deliberate internal inconsistency so the
proofreading has something to find — which it did. The posting is Semgrep's
real one, saved to a file.

## What to look at

Start with [`by-cv/dana-backend/00-README.md`](by-cv/dana-backend/00-README.md),
which is what the tool tells you to read and in what order. Then
[`fit.html`](by-cv/dana-backend/fit.html) in a browser for the card.

## Why the layout looks like this

`01-company.md`, `recon.json` and `recon-notes.md` sit at the top of this
directory rather than beside the dossier, because they depend on the **posting**
and not on your CV. Researching a company is three model requests and around
twenty web searches — the most expensive stage in the pipeline — so trying a
second CV against the same posting reads them instead of paying again. Anything
that depends on both lives under `by-cv/<name>/`.

## The audio

Only [`scripts/02-fit.wav`](by-cv/dana-backend/scripts/02-fit.wav) is here — 6.6
minutes, kokoro, `af_heart` at 160 wpm. **The other two were too large for
GitHub**: the company narration is 42 MB and the playbook narration is 108 MB,
past GitHub's 100 MB per-file limit. One is enough to hear the voice, and the
scripts are all in `scripts/*.txt`. Pass `--audio` to synthesize them yourself.

**This run narrated the fit card; the tool no longer does.** Listening to it is
why — a scored table becomes "technical, ninety. ownership, ninety-three", and
the thing that makes the card useful, seeing four scores at once, is exactly
what a voice cannot do. `--audio` now narrates the company research and the
playbook only, which is one less model call and six fewer minutes of audio.
The sample is left here because it is the only one small enough to ship, and
because hearing why it was dropped is more use than being told.

## One honest caveat about the fit points

The five probe answers in this run were supplied by a test harness rather than
typed by a person, and four of the five came back as a generic fallback because
of a bug in that harness — not in the tool.

You can see the consequence in the fifth fit point, and it is worth seeing:

> **You already said you have production experience integrating third-party
> vendors** — *"Yes, I have production experience with this — it came up in the
> multi-tenant CI analytics platform work described in my CV."*

The quote is verbatim from what the harness typed, so quote verification
correctly let it through. It has nothing to verify against except the answer it
was given. A vague answer produces a vague fit point; the other five, which come
from the CV itself, are what the tool does with real material.

That paragraph is left in rather than edited out, because a run published as a
real run should be one.
