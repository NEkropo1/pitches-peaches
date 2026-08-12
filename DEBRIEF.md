# Debrief

Updated after the multi-provider work. The headline is unchanged: **no stage
has ever run against a live API — on any provider.** No usable credential was
available, so every model-facing code path in this repo is unexecuted. The
deterministic half is tested properly; the half that talks to a model is
written against SDK surfaces verified by introspecting the installed packages,
and nothing more.

Read this as the to-do list for the first session that has a key.

---

## 1. What is actually verified

147 offline tests pass. They cover, genuinely:

| Area | File | What is pinned |
|---|---|---|
| Schema validators | `test_schemas.py` | verified-needs-a-source; all four dimensions; duplicate/missing dimensions; score bounds; both readings non-empty |
| Quote verification | `test_quotes.py` | normalization (whitespace, case, smart punctuation), invented quotes dropped, probe answers count as source |
| Score banding | `test_quotes.py` | every threshold boundary, including off-by-one either side |
| State machine | `test_state.py` | resume, missing-dependency messages naming the producing command, gate blocking, `--force` |
| Config precedence | `test_state.py` | flag > env > file > default, bool/int coercion, unknown keys ignored |
| Prompt loading | `test_prompts.py` | every placeholder resolves; `{{pause:N}}` is not mistaken for one; the voice fragment reaches each prompt |
| TTS normalization | `test_tts.py` | acronyms, lexicon, symbols, pause markers, `[[...]]` injection neutralized, duration estimates |
| Card rendering | `test_cards.py` | three surfaces agree on the numbers; HTML self-contained and escaped; fixed-width terminal output |
| CLI | `test_cli.py` | init idempotent and complete; out-of-order stages name the right fix; dependency errors precede the key error |
| Providers | `test_providers.py` | registry and `auto` selection; per-provider model defaulting; effort clamping; content-part conversion for all three; the three grounding result walkers; schema portability against the real OpenAI and Gemini SDKs |

Two real bugs were caught by writing those tests, not by reading the code: the
`{{pause:900}}` / `{{placeholder}}` delimiter collision, and unwrapped terminal
output that ran to 187 columns.

## 2. What is completely unexecuted

Everything below has never made or handled a real API response.

- **`llm.py` in its entirety.** All three call shapes. In particular:
  - `research()`'s `pause_turn` resume loop. I have never seen a `pause_turn`
    from this code. The resume appends `final.content` and re-sends; if the
    server rejects that shape the whole recon stage fails.
  - `_sources_in` / `_searches_in` block walking. The attribute names
    (`server_tool_use`, `web_search_tool_result`, `.url`) come from the SDK
    docs, not from an observed response object.
  - `parse()` passing `output_config={"effort": ...}` *alongside*
    `output_format=Schema`. I verified in the installed SDK source that these
    are merged rather than one clobbering the other, so this should hold — but
    "should" is doing work.
  - PDF document blocks. Never sent one.
- **Every stage module.** `recon`, `profile`, `match`, `gate`, `playbook`,
  `render` — the orchestration is exercised only by the e2e test, which is
  skipped.
- **Every prompt.** Not one has been through a model. This is the biggest
  unknown in the project by a wide margin; see §4.
- **The OpenAI and Gemini providers, entirely.** Their SDK surfaces were
  introspected against the installed packages (`openai` 3.0.0, `google-genai`
  2.17.0) rather than written from memory — signatures, parameter names, tool
  types, and effort enums are all confirmed to exist. What is *not* confirmed is
  runtime behaviour: whether the streaming event names fire as expected, whether
  the grounding result walkers read the right fields on a real response, and
  whether `gpt-5.4-mini` / `gemini-3-pro` are correct model ids for your
  accounts. Both walkers are unit-tested against hand-built response objects, so
  the logic is right *if* the shapes are.
- **Both TTS backends.** `kokoro` is not installed here and `say` was never
  invoked. The kokoro segment/silence concatenation is the least certain part —
  I am not confident `KPipeline(...)` yields `(gs, ps, audio)` triples in the
  installed version, and the `lang_code=voice[:1]` inference is a guess from
  the voice-id convention (`af_heart` → `a`).

## 3. Run this first

```bash
cp .env.sample runs/probe/.env    # fill in one provider key
cd runs/probe && peaches init

# cheapest possible proof of life — one small parse call
pytest --e2e -k smoke                       # anthropic
pytest --e2e -k smoke --provider openai     # openai
pytest --e2e -k smoke --provider gemini     # gemini

# then the whole thing, ~$2-5
pytest --e2e --provider openai
```

The smoke test is the one to run first against each provider: it is the
cheapest thing that fails when a credential, a model id, or a structured-output
binding is wrong. If `--e2e --provider X` passes in full, that backend is
correctly wired — the suite asserts only on structure, so it doubles as the
provider conformance test.

The e2e test asserts on structure and invariants only — artifacts exist, schemas
survive a real round trip, verified claims carry sources, surviving quotes are
really in the source, the band matches the score, `fit.html` has no external
references. It deliberately never asserts on the model's wording, because that
tests the model rather than this code and fails forever for the wrong reasons.

Point it at a real CV with `PEACHES_E2E_CV=/path/to/cv.pdf` — the checked-in
fixture is an invented person, since this repo is public.

## 4. Where I expect it to break, in order of likelihood

1. **`Playbook` is a big schema to fill in one structured call.** Three
   technologies × three questions × a long answer × deep dives, all inside one
   `messages.parse`. Two failure modes: it hits `max_tokens` at 64k and returns
   nothing parseable, or the model trades depth for schema-completion and the
   answers come back thin. The e2e test asserts `len(answer) > 600` as an early
   warning. **If this is the one that breaks, split it** — one call per
   technology, assembled in Python. That is the refactor I would bet on needing.
2. **`pause_turn` in recon.** See above. Watch for the resume limit error.
3. **Quote verification dropping too much.** If the model paraphrases rather
   than copying, `fit_points` could come back nearly empty and the card would
   look broken. The prompt says "copy it exactly — do not tidy, trim, or
   re-punctuate", but if the drop rate is high in practice the fix is probably
   to relax the check to a fuzzy match over a token window rather than to
   loosen the prompt. Every drop is logged as a `note:` line — watch that count.
4. **Recon on a thin posting.** The Semgrep fixture is a rich 5.3k-char posting
   from a well-documented company. A three-line posting from a company with no
   web presence is the real stress case, and `Recon` requires both readings and
   at least a company name. Worth a second e2e fixture.
5. **Provider-specific unknowns.** For OpenAI: whether
   `response.output_text.delta` is the right event name for visible text on
   your SDK version (if it is not, `write()` falls back to `output_text` on the
   final response, so it degrades to non-streaming rather than failing), and
   whether `web_search_call.action.query` is populated. For Gemini: whether
   grounding metadata arrives on streamed events or only on the final one — if
   sources come back empty but the prose is grounded, that is the cause, and
   the fix is to read `grounding_metadata` off the final aggregated response
   instead. The e2e test asserts `state.stages["recon"]["sources"]` is
   non-empty precisely to catch this.
6. **PDF CVs.** `cv-source.txt` is written empty for a PDF, so quote
   verification falls back to matching against `profile.json`. That means a
   quote is checked against the model's own extraction rather than the source
   document — weaker than for text CVs, and worth knowing before trusting it.

## 5. Multi-provider notes

Two things I got wrong when scoping this, corrected after checking:

- I expected the Pydantic schemas to need per-provider transformation, because
  of `Field(ge=0, le=100)` and 19 optional fields. They do not. The OpenAI SDK's
  `to_strict_json_schema` preserves `minimum`/`maximum` and rewrites optionals
  as nullable-required; `google-genai` accepts the model class directly as
  `response_schema`. All six schemas convert cleanly for both — there is a test
  for it (`test_providers.py`), which is cheap and will catch it if a future
  schema change breaks portability.
- The effort ladders line up better than expected. OpenAI accepts the same
  `low`/`medium`/`high`/`xhigh`/`max` as Anthropic. Only Gemini needs mapping,
  and `clamp_effort` steps down rather than erroring so the same command works
  on all three.

The genuinely provider-specific part is grounding, as expected: three different
tool declarations, three different result shapes, three different citation
fields. That is why `research()` is the one call shape with a real per-provider
implementation, and why the e2e test checks that sources came back at all.

## 6. Refactors I would consider, once it runs

None of these are worth doing before you have seen real output.

- **Split the playbook call** (see §4.1). Most likely genuinely necessary.
- **`llm.write()` buffers the whole document in memory** and only the CLI's
  `on_text` hook can stream it to the user; nothing currently passes one, so a
  60-second document generation looks like a hang. Wiring `on_text` through to
  a Rich live view is a small, high-value UX change.
- **`recon.py` does three model calls in one function.** Fine now; if a fourth
  appears, it wants decomposing.
- **`state.require_gate_passed` lives on `RunState`** but encodes a policy
  decision. If more policy accumulates it belongs in its own module.
- **`cards.py` imports `_bar` and `_ordered` into `gate.py` across a private
  boundary.** Make them public or move the gate summary into `cards.py`.
- **No retry/backoff beyond the SDK's default two.** A long playbook call that
  429s late is an expensive failure. Consider a resume that reuses the already
  written artifacts — the state machine supports it, nothing uses it.
- **`Config` coerces types by inspecting dataclass defaults** (`_coerce`).
  Works, slightly clever. Pydantic would be plainer given it is already a
  dependency.

## 7. Known gaps against the brief

- **The full pipeline has not been run end to end, and no output is attached.**
  This is the brief's explicit final requirement and it is not met.
- **The README's example card is real renderer output from a fixture**, not
  from a live run. It is labelled as such in place. Replace it after §3.
- **The Nemesis CSS was written from scratch** rather than reused, per your
  answer. If you want the real card's visual language, the CSS is isolated in
  one constant (`cards.CSS`) and nothing else needs to change.
- **Cost estimates in the README are inferred**, not measured. Measure them on
  the first real run — `run.json` does not record token usage today, and
  probably should.

## 8. Environment note

`uv` is installed via mise on this machine but has no global version pinned, so
bare `uv` fails. Either `mise use -g uv@0.10.11`, or keep prefixing with
`mise exec uv@0.10.11 -- uv`. The `.venv` here was created that way.
