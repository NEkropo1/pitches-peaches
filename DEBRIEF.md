# Debrief

**The full pipeline has now run end to end against live OpenAI** —
`gpt-5.4-mini`, all six stages, 5m16s, every assertion in
`test_full_pipeline` green. That is the first real execution this project has
had, and it replaces the previous headline ("nothing has ever run").

Still unexecuted: **Anthropic and Gemini**. Their provider code is written
against SDK surfaces verified by introspection, and the shared pipeline above
them is now proven, but neither has made a real call. Run
`pytest --e2e --provider anthropic` and `--provider gemini` to close that.

Read this as the to-do list for the next session.

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

## 2. What the live OpenAI runs proved

The full-pipeline test asserts on structure only, so passing it means all of
this actually works, not just that it did not crash:

- All six stages run in order, each writing the artifact the next one requires.
- Every artifact survives a real round trip and re-validates against its schema.
- **Grounding works**: recon's web search ran and citations were extracted
  (`state.stages["recon"]["sources"]` was non-empty, which was the assertion
  most likely to catch a wrong field name).
- **Quote verification survived contact with a real model**: fit points came
  back with quotes that are genuinely in the source. It did not drop everything,
  which was failure mode #3 below.
- **The Playbook schema held together** — the single biggest predicted risk.
  Answers came back over the 600-character depth floor rather than collapsing
  into stubs, so the "split it into one call per technology" refactor is *not*
  needed on this model. Re-check on Anthropic and Gemini before concluding it
  never is.
- Render wrote `00-README.md`, `02-fit.md`, `03-playbook.md`, a self-contained
  `fit.html` with no external references, and standalone `.mermaid` files.
- The gate recorded its decision and the state machine survived the whole run.
- **The interactive paths work.** A second run drove the probe loop with six
  typed answers and confirmed at the gate, then re-scored — so the probe loop,
  the re-score, and the gate prompt are all exercised. `METRICS.md` measures
  that run.

## 3. What is still unexecuted

Everything below has never made or handled a real API response.

- **`llm.py` against Anthropic and Gemini.** All three call shapes are proven
  on OpenAI. Against the other two, in particular:
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
  - PDF document blocks. Never sent one on any provider — the live run used the
    JSON fixture CV, so the `.pdf` path is still untested everywhere.
- **Both TTS paths at the pipeline level.** Every live run so far passed
  `audio=False`, so narration generation and synthesis are still unexecuted.
  This is also the one that bit the docs: METRICS.md initially quoted a
  12-request breakdown (which includes three narration calls) while describing
  a no-audio run, and a reader caught the contradiction against the README.
  The measured no-audio run makes **9** requests.
- **The Anthropic and Gemini providers.** OpenAI is now proven; these two are
  not. Their SDK surfaces were introspected against the installed packages
  (`anthropic` 0.121.0, `google-genai` 2.17.0), so signatures and tool types are
  confirmed to exist, but no call has been made. Specifically unverified:
  Anthropic's `pause_turn` resume loop and `web_search_tool_result` walking, and
  whether Gemini's grounding metadata arrives on streamed events or only on the
  final aggregated response. `gemini-3-pro` is also an unconfirmed model id.
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

0. ~~**`Playbook` is a big schema to fill in one structured call.**~~ Survived
   the live OpenAI run with answers above the depth floor. Left below because it
   is still unproven on Anthropic and Gemini.
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

### The schema lesson, learned the expensive way

`Profile.contact` was `dict[str, str]`. OpenAI's `to_strict_json_schema`
converted it without complaint, my offline portability test passed, and the API
then returned a 400: a free-form object cannot satisfy strict mode's rule that
`required` list every key in `properties`. **Local schema conversion succeeding
does not mean the API will accept the result.**

It is now a typed `list[ContactDetail]`, and there is an offline guard
(`test_no_schema_contains_a_free_form_object`) that walks every schema and
rejects `additionalProperties` that is not `false`, plus any object where
`required` and `properties` disagree. Verified to fail on the old model. Add no
free-form `dict` fields to `models.py`.

### Two things I got wrong when scoping this, corrected after checking:

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

### e2e tests rot silently

They are skipped by default, so the DI refactor broke the `llm` fixture
(`LLM(config)` lost its two positional args) and nothing noticed until a live
run. Any change to `LLM`, `Config`, or a stage signature needs
`pytest --e2e -k smoke` afterwards, or at minimum a read of `test_e2e.py`.

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
