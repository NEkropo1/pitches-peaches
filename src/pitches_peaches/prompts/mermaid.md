Draw the diagrams for this dossier.

Produce two, unless the material genuinely does not support one:

1. **`architecture`** — the company's product and system as you understand it
   from the recon and the posting. What talks to what, where the tenant or
   customer boundary is, where the money is metered, where the data lives.
   Mark anything you inferred rather than read, in the node label.
2. **`process`** — the predicted interview process as a flow, from first
   contact to offer, with the decision points and what each stage assesses on
   the edge labels.

# Mermaid rules

`flowchart TD`. Label the edges — an unlabelled arrow carries no information.

Node text uses `<br/>` for line breaks. Wrap every label in double quotes so
punctuation and slashes do not break the parser:

```
A["FastAPI Gateway<br/>Anthropic/OpenAI-compatible API"] -->|"validate token"| B
```

Node ids are short and alphanumeric. Use `[( )]` for datastores and `[ ]` for
services. Keep each diagram under about eighteen nodes — past that it stops
being readable and starts being wallpaper.

Do not include the ```` ```mermaid ```` fence in the `mermaid` field. Just the
diagram source, starting with `flowchart TD`.

`title` is a human sentence, not a filename.

---

# The role and company

{{recon}}

# The predicted process

{{process}}
