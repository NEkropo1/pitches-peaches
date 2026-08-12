# Measured run

What one complete pipeline run actually costs and produces. Every figure here
is either measured from artifacts still on disk or read off the provider's own
billing page — nothing is estimated from token-counting the output.

**Snapshot:** 2026-08-12 · `openai` / `gpt-5.4-mini` (served as
`gpt-5.4-mini-2026-03-17`) · effort `medium` · non-interactive off (the probe
loop and gate were answered by hand) · no audio.

## Headline

| Metric | Result |
|---|---:|
| Estimated spend, one run | **~$0.96** |
| Model requests | 12 |
| Web-search tool calls | ~22 |
| Stages completed | 6 / 6 |
| Wall time, recon-complete → done | 19m 26s |
| Reader-facing dossier | 5 files, 8,022 words, 51,014 bytes |
| All artifacts | 16 files, 144,419 bytes |
| Offline tests at this commit | 202 passed, 3 skipped |

## Cost

The provider's billing page for 2026-08-12 UTC, which covers **two**
near-identical runs that day:

| Row | Two runs | Per run |
|---|---:|---:|
| `gpt-5.4-mini` input | $0.35 | $0.175 |
| `gpt-5.4-mini` output | $1.13 | $0.565 |
| `gpt-5.4-mini` cached input | <$0.01 | <$0.005 |
| Web search tool calls | $0.44 | $0.22 |
| **Attributable total** | **$1.92** | **~$0.96** |

The day's grand total was $2.04; the difference is unrelated `gpt-5.5` and
`gpt-5.4-nano` activity, excluded here.

Roughly **59% output, 23% web search, 18% input**. Output dominates because it
includes reasoning tokens and the discarded first match draft — the pipeline
re-scores after the probe answers, so one full `Match` is generated and thrown
away by design.

At the published `gpt-5.4-mini` rates ($0.75/M input, $4.50/M output, $0.01 per
search) that implies roughly **233k input and 126k output tokens per run**.

### What this number is not

Treat it as a good estimate, not a measurement:

- **`run.json` records no usage.** The tool cannot answer this question about
  itself yet; the figures come from the billing page, not from the run.
- **Billing aggregates the day and rounds to cents.** Per-run figures assume
  the two runs were comparable and divide by two.
- **The web-search row is not attributed to a model** by the billing page. The
  ~22 calls/run assumes all of it came from these runs.
- **One run, one posting, one CV.** A denser posting or a longer CV moves this.

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

Document sizes:

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

## Requests per stage

12 model requests, plus the web searches that happen inside the recon research
request:

| Stage | Requests | What they are |
|---|---:|---|
| recon | 3 | grounded research, structured extraction, the dossier |
| profile | 1 | CV extraction |
| match | 2 | initial score, then a re-score after the probe answers |
| gate | 1 | the recommendation |
| playbook | 1 | the whole structured playbook in one call |
| render | 4 | diagrams, plus narration for three documents |

Note that `render` made 4 calls in this run because narration was requested.
Without audio it makes 1, so a no-audio run is **9 requests**.

## Timing

`run.json` records stage *completion* times, not API start and end. These
intervals therefore include reading time, six typed probe answers, and the
gate confirmation — they are wall clock, not model latency.

| Interval | Elapsed |
|---|---:|
| profile | 0m 39s |
| match (includes typing six answers) | 13m 02s |
| gate (includes reading and deciding) | 2m 45s |
| playbook | 2m 50s |
| render | 0m 10s |
| recon complete → done | 19m 26s |

The recon stage's own duration is not recoverable, because no start timestamp
is written.

## What this measurement exposed

Two real defects, both since fixed:

- **`recon-notes.md` ended with "If you want, I can turn these notes into…"** —
  a chat habit in a file nobody can reply to. Now banned in the shared voice
  prompt *and* stripped deterministically on write, since a prompt is a
  request and an artifact is a deliverable.
- **The README's cost estimate was wrong by roughly 3×** in the direction that
  flatters nobody: it guessed $2.50–$4.50 from Opus 5 list prices without ever
  having run anything.

And one gap that is not yet fixed: **nothing records usage.** The highest-value
next change is capturing provider, model, effort, stage, token counts, search
calls and latency per response into `run.json`, then printing a receipt at the
end of a run — `12 responses · 233k in · 126k out · 22 searches · ~$0.96`. Until
that exists, this file has to be maintained by hand from a billing page, which
is exactly why it will go stale.

## Reproducing

```bash
peaches run tests/fixtures/posting.txt --cv tests/fixtures/cv.json -C runs/probe
```

Then read `runs/probe/run.json` for stage timings and counts, and your
provider's billing page for spend. Expect different numbers: the model is
non-deterministic, and the probe loop changes what the match stage is given.
