# PitchesPeaches

[![CI](https://github.com/NEkropo1/pitches-peaches/actions/workflows/ci.yml/badge.svg)](https://github.com/NEkropo1/pitches-peaches/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Give it a job posting and your CV, and it writes you a prep dossier: markdown
files with mermaid diagrams, a fit card you open in a browser, and optionally
audio you can listen to on a walk. It never applies to anything. It does not
open a browser, does not touch a job board account, does not contact anyone,
and has no way to submit a form. It produces files on disk and stops. That
constraint is the product.

```bash
uv tool install pitches-peaches
export ANTHROPIC_API_KEY=...     # or OPENAI_API_KEY, or GEMINI_API_KEY

peaches init                     # a workspace here
peaches cv add ~/cv.pdf          # free; parsing happens on first use
peaches run https://the-job-posting
```

It is provider-agnostic: set whichever key you have and it uses that one.
It needs **Python 3.14+** — `uv tool install` fetches a suitable interpreter
for you, so this matters only if you install it some other way.

> ### ⚠️ v0.1.2: what has actually been run
>
> Verified end to end on **OpenAI only**, with **`gpt-5.4-mini`** — both
> non-interactive and with the probe loop and gate answered by hand, using a
> JSON CV, inside a workspace, with the CV parsed into the shared cache, and
> with narration synthesized to `.wav` by kokoro.
>
> Everything else is covered by the offline test suite but has **never made a
> live API call**:
>
> - the **Anthropic and Gemini providers**
> - any model other than `gpt-5.4-mini`
> - **PDF CVs** (every live run so far used a JSON CV)
> - the **macOS `say` backend**
> - **a second CV reusing a shared recon** — the layout is right and the saving
>   is offline-tested, but no live run has taken it
>
> **Audio needs one more install than the extra can express**, and the run
> offers to do it for you rather than leaving it to this paragraph. Kokoro
> fetches a pronunciation model on first use with a downloader that shells out
> to `pip`, which a uv-created virtualenv does not have — so
> `uv tool install "pitches-peaches[audio]"` is not enough on its own. When you
> ask for audio and only that model is missing, you are asked once:
>
> ```
> Kokoro needs the en_core_web_sm pronunciation model, which its own
> installer cannot fetch inside a uv environment. It is a ~12 MB download:
>   uv pip install --python … en_core_web_sm-3.8.0-py3-none-any.whl
> Install en_core_web_sm now? [Y/n]:
> ```
>
> Say no, or run non-interactively, and nothing is installed: `peaches` reports
> kokoro unavailable, falls back to macOS voices where it can, and leaves the
> narration scripts on disk either way. A backend that fails cannot end a run.
>
> Treat the rest as unproven rather than broken — the code may well work, it
> just has not been watched working. The CLI says so at runtime when you are on
> an unverified combination, and `peaches version` prints both lists.
> [DEBRIEF.md](DEBRIEF.md) has the precise state of each, and
> [METRICS.md](METRICS.md) has what a verified run actually cost and produced.

No uv? `curl -LsSf https://raw.githubusercontent.com/NEkropo1/pitches-peaches/main/install.sh | sh`
(or `install.ps1` on Windows) installs uv and then the tool.

## What comes out

**[A complete run is checked in.](examples/Semgrep-dana-backend/)** Real output
against the fixture posting and CV — the dossier, the card, the diagrams, and
one narration `.wav`. Read that before installing anything.

A directory of files. `00-README.md` indexes them, `fit.html` is the card, and
the numbered documents are the dossier:

```
runs/acme/
├── 00-README.md        what to read, and what to confirm on the call
├── 01-company.md       the company, the product, the people
├── 02-fit.md           how this role fits what you have already done
├── 03-playbook.md      what they will ask, answered at depth
├── 04-diagrams.md      the system and the process
├── fit.html            the card, self-contained, opens offline
├── diagrams/*.mermaid  the diagrams on their own
├── scripts/*.txt       narration scripts (with --audio)
├── recon.json          every claim, labelled and sourced
├── profile.json        your CV, structured
├── match.json          the card data
├── gate.json           the recommendation and why
├── playbook.json       questions and reference answers
└── run.json            which stages ran, and what you decided
```

The card, as `peaches match` prints it — this is genuine output from the run
in [METRICS.md](METRICS.md), against the checked-in fixture posting and CV,
trimmed for length:

```
Senior Backend Software Engineer — Semgrep

AI recommendation — you decide next. PitchesPeaches does not apply to anything, contact
anyone, or send anything anywhere. Everything below is built from what you provided about
yourself.

  OVERALL   88/100   STRONG FIT
           ████████████████████████████████████████░░░░░░

  TECHNICAL         90  █████████████████████████████░░░
                        You already run Python, Flask, SQLAlchemy, PostgreSQL, Redis,
                        Kubernetes, and AWS in production, and you have explicit database
                        and distributed-systems work behind them.

  OWNERSHIP         93  ██████████████████████████████░░
                        You led the move from a single-tenant monolith to a multi-tenant
                        service, made storage and tracing decisions, ran on-call, and owned
                        the platform end to end.

  DELIVERY          91  █████████████████████████████░░░
                        You have concrete production numbers: around 400 customer
                        organisations, p99 query latency from 4.2 seconds to 380
                        milliseconds, and a 38% infra cut.

  BUSINESS CONTEXT  84  ███████████████████████████░░░░░
                        You are adjacent rather than native: static analysis, linting, pre-
                        commit tooling, and multi-tenant developer infrastructure are close
                        to Semgrep, but you have not spent your career in AppSec as the
                        product itself.

WHY YOU FIT — WITH EVIDENCE

  Semgrep's core product shape is close to the static-analysis tooling you built and kept
  adopted.
      "Built and maintained internal linting and pre-commit tooling across the company's
      repositories, authored custom AST-based Python rules to catch unsafe database access
      patterns, instrumented rule hit rates, and drove the false-positive rate down so the
      tooling stayed adopted."
      claim: Static analysis tooling

  Your event-driven backend work fits the workflow and reliability side of Semgrep's
  roadmap.
      "Rebuilt the nightly reconciliation job as an event-driven service, added idempotency
      keys after a retry storm caused duplicate charges, and built the replay tooling and
      guardrails that followed."
      claim: Idempotent workflows

  [... four more, each with the line from the CV it came from ...]

GAPS

  You are remote in Lisbon.
      The role expects 3+ days per week in an office in San Francisco, New York, Boston, or
      Denver unless they make a remote exception, so you need that conversation early.

  You have not shipped an AppSec product.
      You have strong developer-tooling and static-analysis experience, but your record does
      not show a security scanning product or code-risk workflow as the main business.

  [... two more ...]

WHAT TO PREPARE

  - Lead with the CI analytics migration story: monolith to multi-tenant Kubernetes,
  ClickHouse plus PostgreSQL, p99 from 4.2 seconds to 380 milliseconds, and the 38% infra
  spend reduction.
  - Decide now what you will say about the hybrid requirement. If you cannot do 3+ days in
  an office, say that cleanly before the loop goes deep.
  [... three more ...]
```

Every quote is verbatim from the CV. Any the model could not find there was
dropped before the card was rendered.

## Several applications, several CVs

A job search is not one run. `peaches init` makes a workspace, and everything
after that is organised for you:

```
├── cvs/
│   ├── backend-senior.pdf          yours, never touched
│   ├── platform-lead.md
│   └── .parsed/                    derived; delete it and it rebuilds
└── applications/
    ├── 01-semgrep/
    │   ├── recon.json              shared by every CV below
    │   ├── 01-company.md
    │   └── by-cv/
    │       ├── backend-senior/     the dossier, as shown above
    │       └── platform-lead/
    └── 02-acme/
```

```bash
peaches ls                          # the board: what exists and how far it got
peaches resume 1                    # continue where you left off
peaches run <posting> --cv platform-lead    # a second CV, same posting
```

**Recon sits above the CV split, and that is the point.** Researching the
company is three model requests and around twenty web searches — roughly 40% of
a run — and it does not depend on your CV at all. Trying a second CV against a
posting you have already researched reuses it and costs nothing extra.

**Your CV is parsed once.** The cache stores the SHA-256 of the file it read,
so an edited CV is noticed rather than silently scored against a version you
have since rewritten. Nothing is parsed without asking first, because that is a
model call and it is your money — and a run that finds a changed CV with nobody
there to ask refuses and names the command rather than guessing.

**What you type into the probe loop can be kept.** Those answers are CV
material you never wrote down. Say yes when asked and they follow that CV into
every future application, so each one asks fewer questions and produces a card
with more evidence behind it.

Handles like `01-semgrep` are computed from the URL by string work alone — no
model call, and no waiting for one. The company and role shown by `peaches ls`
are read back out of `recon.json` once it exists. Ids are never reused: delete
`02` and the next application is `03`, so a path you saved somewhere never
quietly comes to mean a different job.

`-C <dir>` is unchanged and bypasses all of this, putting one run in one
directory exactly as before.

## How it works

Six stages. Each one is independently runnable and resumable, writes a typed
artifact into one run directory, and refuses to start if what it depends on is
missing — naming the command that produces it.

| Stage | What it does |
|---|---|
| `recon` | Researches the company with web search, then writes a typed record and `01-company.md`. |
| `profile` | Parses your CV — `.json`, `.md`, `.txt`, or `.pdf` — into structured form. |
| `match` | Works out what your CV leaves open, asks you, then scores the role against you on four dimensions with your answers already in hand. |
| `gate` | Recommends apply, apply-with-caveats, or don't. You decide. |
| `playbook` | Predicts what they will ask and answers it at depth. |
| `render` | Diagrams, the index, `fit.html`, and optionally narration audio. |

**On the scores, straight:** the model produces them. There is no weighting
table, because calibrating one honestly needs ground-truth match
data this project does not have, and a hand-picked weight table is fake
precision dressed up as objectivity. What makes the numbers worth reading is
the structure around them — four fixed dimensions that are always all present,
and every positive point carrying the actual line from your CV it came from. If
a quote turns out not to be in your CV, the point is dropped before you see it,
because the failure that actually costs you the job is walking in repeating a
sentence you never wrote.

**Two different postures, on purpose.** Every claim the tool makes about the
*company* is labelled `verified`, `inferred`, or `unverified`, with a source —
enforced by a schema validator, not asked for politely in a prompt, because you
are going to repeat those facts to someone who knows whether they are true.
Everything you say about *yourself* is taken as true. No confidence ratings on
your background, no "self-reported", no hedging. You supply the truth about
your own career and you are responsible for it; the tool's job is to be useful
with it, not to audit it.

The one exception is proofreading. If two lines of your CV disagree — "5+
years" in one place and a timeline that adds to thirteen in another — it says
so, phrased as a choice to make before the call, never as a doubt about which
is true.

**It does not grade you.** The playbook supplies questions and reference
answers. There is no scoring, no mock interview, no "you got that wrong". You
read the answers and decide what you know.

## Better voiceovers

`peaches run` asks at the end, once the dossier exists and you can see whether
it is worth listening to:

```
Narration is written for the ear and synthesized with kokoro. It costs one more
model call per document and a few minutes.
Render narration audio? [y/N]:
```

Enter means no. Pass `--audio` or `--no-audio` to decide up front and skip the
question, which is also what a `--non-interactive` run does. Either way it
writes TTS-safe narration scripts to `scripts/*.txt`; if no backend is
available it writes the scripts anyway and tells you exactly what to install.

There is a quality ladder, and it is worth knowing where you are on it:

1. **kokoro** — the default. Free, offline, Apache-2.0, 82M parameters, runs
   on every platform. `uv tool install "pitches-peaches[audio]"`. Best
   quality-per-install of the offline options.
2. **macOS system voices** — zero install, auto-selected on a Mac when kokoro
   is absent. The default voices (Samantha, Daniel) are clear but plainly
   synthetic. The **Enhanced** and **Premium** voices are a large step up and
   free: System Settings → Accessibility → Spoken Content → System Voice →
   Manage Voices. Then `--voice Ava`.
3. **A paid TTS API** — noticeably better than either. We do not ship one,
   because it would mean a second credential, and the whole point is that
   `{LLM_PROVIDER}_API_KEY` is the only thing you have to supply.

That third rung is a fifteen-line file. The backend contract is:

```python
class TTSBackend(Protocol):
    name: str
    def available(self) -> bool: ...
    def synthesize(self, text: str, out: Path, voice: str, rate: int) -> Result: ...
```

A working ElevenLabs backend, in full:

```python
import os, requests
from pathlib import Path
from pitches_peaches.tts.base import Result
from pitches_peaches.tts.normalize import normalize_for_speech, strip_pause_markers

class ElevenLabs:
    name = "elevenlabs"

    def available(self) -> bool:
        return bool(os.environ.get("ELEVENLABS_API_KEY"))

    def synthesize(self, text: str, out: Path, voice: str, rate: int) -> Result:
        spoken = normalize_for_speech(text, pauses="strip")
        response = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
            headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
            json={"text": spoken, "model_id": "eleven_multilingual_v2"},
            timeout=300,
        )
        response.raise_for_status()
        out.write_bytes(response.content)
        words = len(strip_pause_markers(spoken).split())
        return Result(out, words / rate * 60, words, self.name, voice, rate)
```

Register it in `pitches_peaches/tts/__init__.py` under `_BACKENDS` and select
it with `--tts-backend elevenlabs`. The same shape works for OpenAI TTS — swap
the URL, the header, and the JSON body.

## Configuration

Precedence is **flag > environment variable > `peaches.toml` > default**.
`peaches init` writes a `peaches.toml` with every knob and a comment on each.

| Key | Env | Default | What it does |
|---|---|---|---|
| `provider` | `PEACHES_PROVIDER` | `auto` | `auto` uses whichever key you have set. |
| `model` | `PEACHES_MODEL` | `auto` | `auto` means the provider's default. |
| `effort` | `PEACHES_EFFORT` | `high` | `low`–`max`, for recon and playbook. |
| `parse_effort` | `PEACHES_PARSE_EFFORT` | `medium` | Effort for the parsing stages. |
| `max_technologies` | `PEACHES_MAX_TECHNOLOGIES` | `3` | Cap on playbook technology blocks. |
| `max_questions_per_tech` | `PEACHES_MAX_QUESTIONS_PER_TECH` | `3` | Cap on questions in each. |
| `audio` | `PEACHES_AUDIO` | `false` | Synthesize narration on `render`. |
| `tts_backend` | `PEACHES_TTS_BACKEND` | `auto` | `auto`, `kokoro`, `say`, `none`. |
| `voice` | `PEACHES_VOICE` | `af_heart` | Kokoro voice id, or a macOS `say` voice. |
| `rate` | `PEACHES_RATE` | `178` | Words per minute. ~150 slow, ~180 brisk. |

One provider key is the only credential, and the only value never written to a
config file. Put it in your environment or in `.env` in the run directory;
`peaches init` adds `.env` to the generated `.gitignore`. Copy
[`.env.sample`](.env.sample) to get started.

The prompts live in `pitches_peaches/prompts/*.md` and are loaded at runtime,
so you can tune the voice of your own dossiers without touching Python.

## Providers

There is no default provider. `provider` defaults to `auto`, which uses
whichever key you have set — so setting `OPENAI_API_KEY` and running is enough,
with no flags and no config.

```bash
uv tool install "pitches-peaches[all-providers]"

export OPENAI_API_KEY=...
peaches run <posting> --cv ~/cv.pdf          # uses openai, and says so
```

Pin one explicitly when you have several keys:

```bash
peaches run <posting> --cv ~/cv.pdf --provider anthropic
```

`--model` also defaults to `auto`, resolving to that provider's own default
(`claude-opus-5`, `gpt-5.4-mini`, `gemini-3-pro`), so switching provider never
also requires switching model. Set one explicitly and it is never overridden.

Getting it wrong is meant to be self-correcting. Asking for a provider whose
key you have not set tells you which key you *do* have and the three ways to
use it; having no key at all lists every option with the full path of the
`.env` it would read.

`--effort` means the same thing on Anthropic and OpenAI — both take
`low` through `max`. Gemini's thinking ladder stops at `high`, so `xhigh` and
`max` step down to it rather than erroring; the same command works everywhere.

All three ground stage 1 with their own server-side web search — Anthropic's
`web_search_20260209`, OpenAI's `web_search` tool on the Responses API, and
Gemini's Google Search grounding. That is the one call shape where the three
genuinely differ, so it is the first thing to check when adding a fourth. Only
the OpenAI one has been confirmed working against the live API.

Adding a provider is [one file](src/pitches_peaches/providers/), the same shape
as the TTS backends: `parse`, `write`, `research`, plus `available()`. The e2e
suite doubles as the conformance test — it asserts only on structure, so
`pytest --e2e --provider yours` passing means your backend is wired correctly.

## Privacy

Your CV never leaves your machine except to your chosen provider's API, under
your own key. There is no server, no telemetry, no account, and no phoning home. Output
is local files in a directory you chose. The web searches during recon are
about the company, not about you — your CV is not in that request.

## Cost

Measured, not guessed: **roughly $0.80–$0.95 for one complete run** on
`openai/gpt-5.4-mini` at `medium` effort — 9 model requests and about 22 web
searches. Output is ~59% of the bill, web search ~23%.

[METRICS.md](METRICS.md) has the breakdown, the billing evidence, and an honest
account of what that number is not.

Two things move it:

- **Audio** adds one narration call per document — 12 requests instead of 9.
- **Model.** The figure above is a mini-tier model. An Opus- or GPT-5-tier
  model is several times more per token.

`--effort medium` is a reasonable dial to reach for before changing model,
because the playbook's depth is the part worth paying for. Re-running a single
stage only re-spends that stage.

> Nothing records token usage yet, so this comes from a provider billing page
> rather than from the tool itself. Fixing that is the top item in
> [DEBRIEF.md](DEBRIEF.md).

## Development

```bash
uv venv && uv pip install -e ".[dev]"
pytest
```

The tests cover the deterministic parts — schema validators, the state machine,
quote verification, score banding, config precedence, `.env` parsing, TTS
normalization, provider resolution, and card rendering. None of them need
network or an API key, and there are no mock-the-LLM tests asserting on model
output, because those test the mock.

The live tests are opt-in, because they cost money:

```bash
pytest --e2e -k smoke                  # one cheap call
pytest --e2e                           # the full pipeline
pytest --e2e --provider anthropic      # prove a provider this release has not
```

They assert on structure only, so the same suite is the conformance test for a
provider: `--provider X` passing means that backend is wired correctly. That is
how the box at the top of this README gets shorter.

## Licence

MIT.

---

*The name is a pun on the pitch you make. And on Peaches.*
