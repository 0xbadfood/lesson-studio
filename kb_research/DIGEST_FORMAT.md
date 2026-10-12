# Textbook digest format (draft v1)

One digest per NCERT chapter (English, Classes 6–12, Science and Maths).
It is the single input for lessons: a teacher, parent or student picks a
chapter, picks a concept, and everything they need comes from the digest
(plus links into other chapters' digests).

The digest is **audience-neutral**. It records what the book teaches, what
is missing, and checked additions. Who the lesson is for (teacher, parent,
student; age) changes how a lesson is made from it, not the digest.

## What the purpose needs, and what v0 (the keph1-05 run) lacks

| Need | v0 | v1 |
|---|---|---|
| Teach a concept "in detail" | 25 one-paragraph summaries for the whole chapter; derivation steps, worked solutions and figures not captured | Faithful **blocks**: every definition, equation, derivation step, worked example (problem, steps, answer), figure, activity, box, exercise |
| Choose a concept | Flat items, examples mixed with ideas; 4 coarse objectives | **Concepts** grouped under the book's own **sections**, each pointing at its blocks |
| Practice | End-of-chapter exercises ignored | Exercises are blocks, mapped to concepts |
| Know it's complete | Model decides what matters | Code inventories numbered things in the text (sections, Eq., Example, Fig., Activity, exercises) and requires each one as a block |
| Correct equations | pdftotext garbles maths (see 5.6 derivation) | Blocks are read from page images + text, equations stored as LaTeX |
| Prerequisites | Not recorded | Per concept; resolved to concepts in earlier chapters/classes after the corpus is built |
| Trust in additions | G5 had an arithmetic error; a blog was used as a source | Additions carry checkable calculations (code evaluates them) and a source tier |
| Search (RAG) | One document per chapter | Every block, concept, gap and addition is a record with a global id and metadata |

## Layout

```
digest.json
  schema: "textbook_digest_v1"
  source      chapter identity + provenance
  outline     the book's sections
  blocks      what the textbook contains (faithful, complete)
  concepts    what the textbook teaches (built from blocks)
  gaps        what is missing, per concept
  additions   checked knowledge that fills each gap
```

Global ids are `<chapter-id>:<local id>`, e.g. `keph1-05:B14`, `keph1-05:C4`.
Every record that quotes the book carries `pages` (PDF page numbers of the
chapter file) and a `quote` anchor that code checks against the page text.

### source
```json
{"id": "keph1-05", "class": 11, "subject": "physics", "book": "keph1",
 "chapter": 5, "title": "Work, Energy and Power", "pdf": ".../keph105.pdf",
 "pages": 21, "page_text_sha": "…", "model": "qwen3.8-27b",
 "built_at": "2026-10-09T…", "builder_version": "1"}
```

### outline
The book's numbered sections, found by code from headings and confirmed by
the model. Section ids are the book's own numbers.
```json
[{"id": "5.5", "title": "Work done by a variable force", "pages": [5, 6]},
 {"id": "5.6", "title": "The work-energy theorem for a variable force", "pages": [6, 7]},
 {"id": "5.11.2", "title": "Collisions in one dimension", "parent": "5.11", "pages": [16, 17]},
 {"id": "end", "title": "Summary, points to ponder, exercises", "pages": [18, 21]}]
```

### blocks — what the textbook contains
One block per teachable unit, in book order. Common fields: `id`, `type`,
`section`, `title`, `text` (faithful, in the book's words where possible),
`pages`, `quote`, `ref` (the book's number: "Eq. 5.8a", "Example 5.6", "Fig. 5.3").

| type | extra fields |
|---|---|
| definition, law, principle, fact | `latex` (if any) |
| equation | `latex`, `symbols` [{symbol, meaning, unit}] |
| derivation, proof | `from` (block ids / assumptions), `steps` [{latex, reason}], `result` (block id) |
| worked_example | `problem`, `given`, `find`, `steps` [{latex, reason}], `answer` {value, unit} |
| figure, table | `caption`, `shows` (what it depicts — enough to redraw it) |
| activity, experiment | `aim`, `materials`, `procedure`, `observation` |
| box | `kind` (history, application, note) |
| summary_point, ponder_point | — |
| exercise | `kind` (numerical, conceptual, proof, diagram), `answer` if the book gives one |

Lists in biology/chemistry (organelles, properties, classifications) are
`fact` blocks with a `items` list.

### concepts — what the textbook teaches
Built after the blocks. This is the list a user chooses from.
```json
{"id": "C4", "name": "Work-energy theorem for a variable force",
 "aliases": ["WE theorem", "work energy theorem", "integral form of Newton's second law"],
 "sections": ["5.6"],
 "summary": "The change in kinetic energy equals the work done by the net force, even when the force varies with position.",
 "depth": "derived",
 "blocks": {"core": ["B21", "B22"], "examples": ["B23"], "figures": [], "exercises": ["B88", "B91"]},
 "objectives": ["Derive K_f − K_i = ∫F dx from Newton's second law",
                "Use it to find speed after a position-dependent force"],
 "prerequisites": [{"name": "Work done by a variable force (area under F–x)", "ref": "keph1-05:C3"},
                   {"name": "Integration of 1/x", "ref": null}],
 "difficulty": "core"}
```
- `depth`: mentioned | stated | derived | applied (how far the book goes).
- `difficulty`: foundation | core | advanced (for audience adaptation).
- Every block belongs to at least one concept (code check).
- `prerequisites[].ref` is null until the cross-corpus linking pass.

### gaps
As in v0, but attached to concepts:
`{id, concept, blocks, type, missing, why_it_matters, priority, resolve, research_question}`
with type ∈ intuition, skipped_step, prerequisite, misconception, context,
visual, oversimplification, history.

### additions
One per gap:
```json
{"id": "A5", "gap": "G5", "title": "…", "content": "…",
 "level": "within | extension",
 "provenance": "standard_knowledge | web",
 "sources": [{"url": "…", "tier": "official | academic | reference | other"}],
 "calculations": [{"expr": "2*(0.5+1.5+2.5)", "value": 9, "unit": "J"}],
 "checks": {"numbers": "ok | failed | none", "sources": "ok | weak"},
 "status": "accepted | needs_review",
 "textbook_note": "how it fits the book's notation"}
```
Code evaluates each `expr` and compares with `value`; a failure sends it
back to the model, then marks `needs_review`. Web additions must cite
fetched URLs; `other` tier alone means `checks.sources = weak`.

## Example (real content, keph1-05 §5.6)

```json
{"id": "B21", "type": "derivation", "section": "5.6",
 "title": "Work-energy theorem for a variable force (one dimension)",
 "from": ["B8", "Newton's second law F = m dv/dt"],
 "steps": [
   {"latex": "\\frac{dK}{dt} = \\frac{d}{dt}\\left(\\tfrac12 m v^2\\right) = m\\frac{dv}{dt}\\,v", "reason": "differentiate K"},
   {"latex": "= F\\,v = F\\frac{dx}{dt}", "reason": "Newton's second law; v = dx/dt"},
   {"latex": "dK = F\\,dx", "reason": "multiply by dt"},
   {"latex": "\\int_{K_i}^{K_f} dK = \\int_{x_i}^{x_f} F\\,dx", "reason": "integrate between positions"},
   {"latex": "K_f - K_i = \\int_{x_i}^{x_f} F\\,dx \\quad (5.8a)", "reason": ""},
   {"latex": "K_f - K_i = W \\quad (5.8b)", "reason": "Eq. 5.7: the integral is the work"}],
 "result": "B22", "pages": [6, 7], "ref": "Eq. 5.8a, 5.8b",
 "quote": "We are now familiar with the concepts of work and kinetic energy to prove the work-energy theorem"}

{"id": "B23", "type": "worked_example", "section": "5.6", "ref": "Example 5.6",
 "problem": "A 1 kg block moving at 2 m/s enters a rough patch from x = 0.10 m to 2.01 m where the retarding force is F_r = −k/x, k = 0.5 J. Find the final kinetic energy and speed.",
 "given": ["m = 1 kg", "v_i = 2 m/s", "F_r = −k/x for 0.1 < x < 2.01 m", "k = 0.5 J"],
 "find": ["K_f", "v_f"],
 "steps": [{"latex": "K_f = K_i + \\int_{0.1}^{2.01} \\frac{-k}{x}dx = \\tfrac12 m v_i^2 - k\\ln\\frac{2.01}{0.1}", "reason": "Eq. 5.8a"},
           {"latex": "= 2 - 0.5\\ln 20.1 = 2 - 1.5 = 0.5\\ \\text{J}", "reason": ""},
           {"latex": "v_f = \\sqrt{2K_f/m} = 1\\ \\text{m/s}", "reason": ""}],
 "answer": {"value": "0.5 J; 1 m/s"}, "pages": [7, 8]}
```

Note how the page text shows this derivation scrambled (two columns, the
integral signs split from their limits). This is why blocks are read from
page images as well as text.

## How a request uses it

1. User picks chapter → the UI lists `concepts` grouped by `outline` sections.
2. User picks one or more concepts (or types a topic; it is matched against
   names and aliases).
3. Code assembles the packet: the concepts, their blocks, gaps, accepted
   additions, prerequisite concepts from other digests, and exercises.
4. The planner gets the packet, plus search over all digests for anything else.

## Build order per chapter (as built: `kb_research/digest.py`)

| Step | Model | What code checks |
|---|---|---|
| 1. pages: one vision call per page (image + PDF text) | Qwen 27B, 3090, no thinking | quotes or 8-word runs of the block found in the page text (`quote_found`; a page fails only if most miss), LaTeX braces, section ids, numbered examples/equations/activities/theorems present; figures and exercise numbering checked over the chapter, missing ones re-read |
| 2. concepts | Qwen, no thinking | every block in a concept (a few stragglers placed by a small follow-up call), sections from the outline |
| 3. gaps, per group of concepts | Qwen, thinking | at most 3 per concept; context and history gaps go to research (at most 2 per group) |
| 4. research | search agent on Qwen (Tavily + Obscura) | answers must cite fetched pages; the agent is sent back to search if it answers without sources |
| 5. additions, 4 gaps per call | Qwen, no thinking | every computed number listed as plain arithmetic and re-evaluated (trig in degrees); web sources must be fetched pages, with a tier |
| 6. audit, per group | Claude Haiku (Lesson Studio's connection) | contradicts book, factual error, wrong number, unsupported, not a gap, misleading |
| 7. repair | Qwen, thinking | additions with audit errors rewritten once, checked by code, re-audited; what is still wrong stays `needs_review` |

Audit findings are kept in `digest.audit` and on each addition (`audit`, `repaired`). Corrected concept
summaries replace the wrong ones; gaps the book already covers are dropped.

## Pilot (2026-10-09)

| Chapter | Blocks | Concepts | Gaps | Web | Needs review | Time |
|---|---|---|---|---|---|---|
| keph1:05 Work, Energy and Power | 162 | 13 | 30 | 5 | 1 | ~36 min |
| kemh1:03 Trigonometric Functions | 190 | 7 | 21 | 2 | 0 | ~34 min |
| kebo1:08 Cell: The Unit of Life | 96 | 17 | 46 | 5 | 1 | ~38 min |

The audit caught a wrong concept summary (C6 in keph1-05), four wrong maths additions (all repaired), and an
inconsistency in the book itself (Example 5.8 prints k = 5.25×10³ N/m but its answer, 2.00 m, needs 6.25×10³).

Run the whole corpus (230 chapters, Classes 11-12 first): `kb_research/env/bin/python kb_research/digest.py --lanes 3`.
