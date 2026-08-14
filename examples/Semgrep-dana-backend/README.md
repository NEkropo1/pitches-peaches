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

Both narrations are here, kokoro at `af_heart`, 160 wpm:

| | | |
|---|---:|---:|
| [`01-company.mp3`](by-cv/dana-backend/scripts/01-company.mp3) | 14.9 min | 7.1 MB |
| [`03-playbook.mp3`](by-cv/dana-backend/scripts/03-playbook.mp3) | 39.3 min | 18.9 MB |

They ship as MP3 because they could not ship at all otherwise: the same audio
is 42 MB and 108 MB as WAV, and the second is past GitHub's 100 MB per-file
limit. Narration is now compressed with whatever the machine has — `lame` for
MP3, otherwise `afconvert` for M4A, which comes with macOS.

**The fit card is not narrated, and this example used to show why.** An earlier
version of this run included it: 6.6 minutes of a scored table read aloud as
"technical, ninety. ownership, ninety-three". What makes the card useful is
seeing four scores at once, which is the one thing a voice cannot do, so
`--audio` now covers the company research and the playbook only. `fit.html` is
where the card belongs.

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
