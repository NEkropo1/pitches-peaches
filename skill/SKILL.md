---
name: interview-prep
description: >-
  Research a company and build an interview prep dossier from a job posting and
  the user's CV. Use when the user is preparing for an interview, wants a
  company researched before they apply, asks whether they should apply to a
  job, wants to know what a company will ask them, or shares a job posting URL
  alongside their CV. Produces local markdown, diagrams and an HTML fit card.
  It never submits an application.
---

# Interview prep

Shell out to the `peaches` CLI. It does the work; this file only drives it.

Check it is installed with `peaches version`, which also prints what has been
tested; if not, `uv tool install pitches-peaches`.

**v0.1.0 is verified only on `openai` with `gpt-5.4-mini`.** The Anthropic and
Gemini providers, PDF CVs, and audio are written but have never made a live
call. If the user is relying on one of those, say so — do not present them as
proven.

One provider key (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY` or `GEMINI_API_KEY`)
must be in the environment; the provider is picked from whichever is set. Never
ask the user to paste a key into the chat — tell them to export it, or put it
in `.env` in the run directory.

## Run it

You need the job posting (a URL or a saved file) and the user's CV (`.json`,
`.md`, `.txt` or `.pdf`). Ask for whichever is missing; do not proceed without
both. Use one run directory per application:

```
peaches run <url-or-file> --cv <cv-path> -C runs/<company>
```

The run is interactive: it asks the user about their own background, then
whether to proceed. Let those prompts reach the user, do not answer on their
behalf. `--non-interactive` skips them and marks the card provisional.

## If a stage fails

Each stage is resumable and re-runnable alone, in this order:

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

Point the user at `<dir>/00-README.md`, which indexes everything, and
`<dir>/fit.html` for the score card.

If the gate recommended not applying, the run stops there by design. Report that
plainly with the "build first" list; do not re-run with `--force` unless asked.
Two things to state accurately: the tool never applies to anything or contacts
anyone, and it takes what the user says about themselves as true.
