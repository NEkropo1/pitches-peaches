# Measured run

What one complete pipeline run costs and produces. Every figure is either
measured from artifacts on disk or read off the provider's billing page —
nothing is estimated by token-counting the output.

**The run measured here:** 2026-08-12 · `openai` / `gpt-5.4-mini` (served as
`gpt-5.4-mini-2026-03-17`) · effort `medium` · **interactive** (six probe
answers typed by hand, gate confirmed) · **no audio** · JSON CV.

That configuration matters for every number below, so it is stated before them
rather than after. Audio in particular changes the request count by a third.

## Headline

| Metric | Result |
|---|---:|
| Model requests | **9** |
| Web-search tool calls | ~22 |
| Stages completed | 6 / 6 |
| Wall time, recon-complete → done | 19m 26s |
| Reader-facing dossier | 5 files, 8,022 words, 51,014 bytes |
| All artifacts | 16 files, 144,419 bytes |

## Requests per stage

| Stage | Requests | What they are |
|---|---:|---|
| recon | 3 | grounded research, structured extraction, the dossier |
| profile | 1 | CV extraction |
| match | 2 | initial score, then a re-score after the probe answers |
| gate | 1 | the recommendation |
| playbook | 1 | the whole playbook in one call |
| render | 1 | the diagrams |
| **Total** | **9** | |

Two things move this:

- **Audio** adds one narration call per document — **3 more**, so 12 in total.
  This run did not render audio (`run.json` records `render: {audio: false}`).
- **Skipping the probe loop** with `--non-interactive` removes the match
  re-score, so 8 instead of 9. The card is then marked provisional.

## Cost

The provider's billing page for 2026-08-12 UTC. That day covered **two** runs
on two machines — this one, and a second with audio enabled whose artifacts are
not in this repository.

| Row | Both runs |
|---|---:|
| `gpt-5.4-mini` input | $0.35 |
| `gpt-5.4-mini` output | $1.13 |
| `gpt-5.4-mini` cached input | <$0.01 |
| Web search tool calls | $0.44 |
| **Attributable total** | **$1.92** |

The day's grand total was $2.04; the remainder is unrelated `gpt-5.5` and
`gpt-5.4-nano` activity.

**That averages ~$0.96 per run, but the two runs were not alike.** This 9-request
run sits below the average and the 12-request audio run above it. A defensible
range for a single no-audio run is **roughly $0.80–$0.95**, and audio adds three
long-form generations on top.

It cannot be split more precisely, because nothing records per-run usage — see
below.

Roughly **59% output, 23% web search, 18% input**. Output dominates because it
includes reasoning tokens and the discarded first match draft: the pipeline
generates a full `Match`, takes the probe answers, and re-scores, by design.

At published `gpt-5.4-mini` rates ($0.75/M input, $4.50/M output, $0.01 per
search) the two runs together imply roughly **467k input and 251k output
tokens**.

### What this number is not

- **`run.json` records no usage.** These figures come from a billing page, not
  from the tool. That is the single biggest gap in the project.
- **Billing aggregates the day and rounds to cents.**
- **The web-search row is not attributed to a model,** so the ~22 calls per run
  assumes all of it came from these two runs.
- **One posting, one CV.** A denser posting or a longer CV moves this.

## What the run produced

Measured from `runs/acme/first_test_run/`.

| | |
|---|---:|
| Company / role | Semgrep / Senior Backend Software Engineer |
| Research sources captured | 17 |
| Recon claims | 9 |
| Role requirements | 6 |
| Match | 88 / 100 (strong) |
| Fit points / gaps / probes | 6 / 4 / 5 |
| Probe answers incorporated | 6 |
| Unsupported quotes dropped | 0 |
| Gate | `apply_with_caveats` → user chose proceed |
| Playbook branch | `founder_led` |
| Technologies / questions | 3 / 9 |
| Mermaid diagrams | 2 |

| File | Words | Bytes |
|---|---:|---:|
| `00-README.md` | 243 | 1,542 |
| `01-company.md` | 1,870 | 11,989 |
| `02-fit.md` | 888 | 6,048 |
| `03-playbook.md` | 4,707 | 28,727 |
| `04-diagrams.md` | 314 | 2,708 |

Word counts across all 16 artifacts are not additive as unique content: the
JSON, Markdown, HTML and Mermaid deliberately restate the same material in
different shapes.

## Timing

`run.json` records stage *completion* times, not API start and end. These
intervals include reading time, six typed probe answers, and the gate
confirmation — they are wall clock, not model latency.

| Interval | Elapsed |
|---|---:|
| profile | 0m 39s |
| match (includes typing six answers) | 13m 02s |
| gate (includes reading and deciding) | 2m 45s |
| playbook | 2m 50s |
| render | 0m 10s |
| recon complete → done | 19m 26s |

The recon stage's own duration is not recoverable: no start timestamp is
written.

## What measuring this exposed

Three real defects. Two are fixed:

- **`recon-notes.md` ended with "If you want, I can turn these notes into…"** —
  a chat habit in a file nobody can reply to. Now banned in the shared voice
  prompt *and* stripped deterministically on write.
- **The README's cost estimate was wrong by roughly 3×**, guessed from Opus 5
  list prices without anything having been run.
- **This document itself first claimed 12 requests while describing a no-audio
  run** — the request breakdown came from the *other* machine's run, mixed into
  figures measured from this one. A reader caught the contradiction against the
  README's "no audio" claim before it did any damage.

That third one has the same root cause as the other two: **nothing records
usage**, so every number here is assembled by hand from a billing page and a
memory of how a run was configured. The fix is to capture provider, model,
effort, stage, token counts, search calls and latency per response into
`run.json`, then print a receipt at the end of a run:

```
9 responses · 233k in · 126k out · 22 searches · ~$0.88
```

Until that exists, this file will keep going stale, and the way it goes stale
will keep being subtle.

## Reproducing

```bash
peaches run tests/fixtures/posting.txt --cv tests/fixtures/cv.json -C runs/probe
```

Answer the probes to reproduce this run; add `--non-interactive` for the
cheaper 8-request variant. Then read `runs/probe/run.json` for stage timings
and counts, and your provider's billing page for spend. Expect different
numbers — the model is non-deterministic, and what you type into the probe loop
changes what the match stage is given.
