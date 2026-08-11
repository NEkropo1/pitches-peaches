Rewrite this document as a narration script, to be read aloud by a synthesizer
into someone's headphones while they walk.

{{voice}}

# Hard rules for the ear

**No markdown.** No `#` headings, no `**bold**`, no bullet characters, no
tables, no links, no code fences, no backticks. A heading becomes a spoken
sentence that does the same job: "Part three. The market claim, and the
asterisk it needs."

**Spell out numbers and symbols.** "two point two million dollars", not
"$2.2M". "ninety percent", not "90%". "roughly three seconds", not "~3s".
"version zero", not "v0". Dates spoken as dates: "August third".

**Acronyms: say what a person would say.** Ones pronounced as words stay as
words — NIST, OWASP, RAG, SOC, SAML, SCIM, JSON, REST, CRUD. Everything else
gets spelled with spaces so the synthesizer does not guess: "P I I", "M L",
"S L A". Product names get the same treatment where the spelling misleads:
"Fast A P I", "Postgres", "Engine X", "Open A I", "Chat G P T", "Kubernetes"
for k8s.

**Pauses are the pacing.** Use `{{pause:900}}` between major sections and
`{{pause:400}}` where a beat helps a hard idea land. Milliseconds. Nothing else
in double braces.

**Sentences, spoken length.** A sentence you cannot say in one breath is too
long. A listener cannot re-read, so signpost before you explain — "Three things
matter here, and the third is the one they will push on" — and repeat any
number that carries weight.

# Structure

Open by saying which text this is and what it will do, in two sentences. Then
work through the document's substance in the same order. Close by compressing
it to the few things worth remembering, then say what the next text covers.

Do not add facts. This is the same content, re-cut for the ear. Where the
document had a list, turn it into prose with ordinals — "First… Second… And
third…" — because a spoken bullet list is unfollowable.

---

# The document

{{document}}
