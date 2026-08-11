---
name: interview-prep
description: >-
  Research a company and build an interview prep dossier from a job posting and
  the user's CV. Use when the user says they are preparing for an interview,
  wants a company researched before they apply, asks whether they should apply
  to a job, wants to know what a company will ask them, or shares a job posting
  URL alongside their CV. Produces local markdown, diagrams and an HTML fit
  card. It never submits an application.
---

# Interview prep

Shell out to the `peaches` CLI. It does the work; this file only drives it.

## Setup

Check it is installed: `peaches version`. If not:

```
uv tool install pitches-peaches
```

`ANTHROPIC_API_KEY` must be in the environment. Do not ask the user to paste it
into the chat — tell them to export it, or to put it in `.env` in the run
directory.

## What you need before running

1. The job posting — a URL, or a file the user saved it to.
2. The user's CV — `.json`, `.md`, `.txt`, or `.pdf`.

Ask for whichever is missing. Do not proceed without both.

## Run it

Pick a run directory per application, so dossiers do not overwrite each other:

```
peaches run <url-or-file> --cv <cv-path> -C runs/<company>
```

The run is interactive: it asks the user follow-up questions about their own
background, then asks whether to proceed. Let those prompts reach the user —
do not answer on their behalf. If the user wants it unattended, add
`--non-interactive`; the fit card is then marked provisional.

Add `--audio` for narration scripts and synthesized audio.

## Stages, if something fails partway

Each stage is resumable and can be re-run alone, in this order:

```
peaches recon <url-or-file> -C <dir>
peaches profile <cv-path> -C <dir>
peaches match -C <dir>
peaches gate -C <dir>
peaches playbook -C <dir>
peaches render -C <dir>
```

Errors name the command that fixes them. Follow that, do not improvise.

## Afterwards

Point the user at `<dir>/00-README.md`, which indexes everything, and at
`<dir>/fit.html` for the score card.

If the gate recommended not applying, the run stops there by design. Report
that outcome plainly and show the "build first" list — do not re-run with
`--force` unless the user asks.

Two things to state accurately if the user asks: the tool never applies to
anything or contacts anyone, and it takes what the user says about themselves
as true rather than verifying it.
