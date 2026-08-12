# PitchesPeaches

Give it a job posting and your CV, and it writes you a prep dossier: markdown
files with mermaid diagrams, a fit card you open in a browser, and optionally
audio you can listen to on a walk. It never applies to anything. It does not
open a browser, does not touch a job board account, does not contact anyone,
and has no way to submit a form. It produces files on disk and stops. That
constraint is the product, not a limitation of it.

```bash
uv tool install pitches-peaches
export ANTHROPIC_API_KEY=sk-ant-...
peaches run https://the-job-posting --cv ~/cv.pdf -C runs/acme
```

No uv? `curl -LsSf https://raw.githubusercontent.com/nekropol/pitches-peaches/main/install.sh | sh`
(or `install.ps1` on Windows) installs uv and then the tool. Nothing else.

## What comes out

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

The card, as `peaches match` prints it:

```
Senior Backend Software Engineer — Semgrep

AI recommendation — you decide next. PitchesPeaches does not apply to anything, contact
anyone, or send anything anywhere. Everything below is built from what you provided about
yourself.

  OVERALL   74/100   POSSIBLE FIT
           ██████████████████████████████████░░░░░░░░░░░░

  TECHNICAL         82  ██████████████████████████░░░░░░
                        Your Python, Postgres and Kubernetes work lines up with the stack
                        they describe, and you chose Postgres over faster stores on purpose.

  OWNERSHIP         78  █████████████████████████░░░░░░░
                        You inherited an MVP and decided what to rebuild, which is the scope
                        they are hiring for.

  DELIVERY          85  ███████████████████████████░░░░░
                        Three minutes to three seconds against a one-minute SLA is the kind
                        of number that ends this conversation early.

  BUSINESS CONTEXT  45  ██████████████░░░░░░░░░░░░░░░░░░
                        Application security is not a domain you have worked in, and their
                        buyer's constraints will be unfamiliar.

WHY YOU FIT — WITH EVIDENCE

  You have already run the migration they are most likely to attempt next.
      "moved to self-managed Kubernetes"
      claim: Kubernetes platform ownership

  You can name the latency numbers, which is what a reliability-focused team probes for.
      "end-to-end processing from about three minutes to about three seconds"
      claim: Latency work with figures

GAPS

  No application security background.
      Their product is a static analysis tool for security teams, and the vocabulary of that
      buyer is not in your record.

  No OCaml.
      The analysis core is OCaml. The posting treats it as learnable, and the rest of the
      stack is Python, so this matters less than it looks.

WHAT TO PREPARE

  - Have one incident story ready with the invariant you added afterwards.
  - Learn what a false positive costs an AppSec team, in hours per week.
```

> That card is real output from the renderer, but its *contents* come from
> `tests/fixtures/match.json` rather than from a live run — see
> [DEBRIEF.md](DEBRIEF.md) for exactly what has and has not been executed
> against the API. Once you have run `pytest --e2e`, replace this with the
> genuine article.


## How it works

Six stages. Each one is independently runnable and resumable, writes a typed
artifact into one run directory, and refuses to start if what it depends on is
missing — naming the command that produces it.

| Stage | What it does |
|---|---|
| `recon` | Researches the company with web search, then writes a typed record and `01-company.md`. |
| `profile` | Parses your CV — `.json`, `.md`, `.txt`, or `.pdf` — into structured form. |
| `match` | Scores the role against you on four dimensions, then asks you follow-up questions and re-scores. |
| `gate` | Recommends apply, apply-with-caveats, or don't. You decide; the decision is recorded. |
| `playbook` | Predicts what they will ask and answers it at depth. |
| `render` | Diagrams, the index, `fit.html`, and optionally narration audio. |

**On the scores, straight:** the model produces them. There is no weighting
table in the Python, because calibrating one honestly needs ground-truth match
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

The one exception is proofreading. If two lines of your CV disagree — "8+
years" in one place and a timeline that adds to thirteen in another — it says
so, phrased as a choice to make before the call, never as a doubt about which
is true.

**It does not grade you.** The playbook supplies questions and reference
answers. There is no scoring, no mock interview, no "you got that wrong". You
read the answers and decide what you know.

## Better voiceovers

`--audio` writes TTS-safe narration scripts to `scripts/*.txt` and then
synthesizes them. If no backend is available it writes the scripts anyway and
tells you exactly what to install.

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
   `ANTHROPIC_API_KEY` is the only thing you have to supply.

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
| `provider` | `PEACHES_PROVIDER` | `anthropic` | `anthropic`, `openai`, `gemini`, or `auto`. |
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

Anthropic by default; OpenAI and Gemini are one flag away.

```bash
uv tool install "pitches-peaches[all-providers]"

peaches run <posting> --cv ~/cv.pdf --provider openai
peaches run <posting> --cv ~/cv.pdf --provider gemini
peaches run <posting> --cv ~/cv.pdf --provider auto     # whichever key is set
```

You do not also have to change `--model`: it defaults to `auto`, which resolves
to that provider's default (`claude-opus-5`, `gpt-5.4-mini`, `gemini-3-pro`).
Set one explicitly and it is never overridden.

`--effort` means the same thing on Anthropic and OpenAI — both take
`low` through `max`. Gemini's thinking ladder stops at `high`, so `xhigh` and
`max` step down to it rather than erroring; the same command works everywhere.

All three ground stage 1 with their own server-side web search — Anthropic's
`web_search_20260209`, OpenAI's `web_search` tool on the Responses API, and
Gemini's Google Search grounding. That is the one call shape where the three
genuinely differ, so it is the first thing to check when adding a fourth.

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

A full run is roughly **300k–500k input tokens and 40k–70k output**, most of it
the recon research and the playbook's long answers. At Opus 5 pricing ($5/$25
per million) that is **about $2.50–$4.50 per application**.

Cheaper, in the order I would reach for them: `--effort medium`, then a smaller
model (`--model claude-sonnet-5`), then a cheaper provider. Effort first,
because the depth of the playbook answers is the part worth paying for.

These are estimates, not measurements — nothing records token usage yet. See
[DEBRIEF.md](DEBRIEF.md).

Re-running a single stage only re-spends that stage.

## Development

```bash
uv venv && uv pip install -e ".[dev]"
pytest
```

The tests cover the deterministic parts — schema validators, the state machine,
quote verification, score banding, config precedence, TTS normalization, and
card rendering. None of them need network or an API key, and there are no
mock-the-LLM tests asserting on model output, because those test the mock.

## Licence

MIT.

---

*The name is a pun on the pitch you make. And on Peaches.*
