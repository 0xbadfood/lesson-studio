# Solutions: solved questions and solution videos (planned, 2026-10-22)

**When:** last, after the explainers (chapter → concept → key idea films, notes, Test yourself). The user calls it "the
most iconic section of the whole project".

**Reference paper:** [JEE Advanced 2026, Paper 2 (English)](https://jeeadv.ac.in/documents/p2_english.pdf). It has 29
pages and three subjects (Mathematics, Physics, Chemistry) of 18 questions each, in four sections:

| Section | Question type | Marks |
|---|---|---|
| 1 | Single correct option | 12 |
| 2 | One or more correct options, with partial marking (e.g. +2 for two of three right, −1 for any wrong pick) | 20 |
| 3 | Integer or numerical answer | 20 |
| 4 | Paragraph-based sets of two or three questions | 8 |

Text extracts cleanly with `pdftotext -layout`, Unicode maths included. Some questions depend on a figure (circuits,
ray diagrams, structures, graphs).

**Licence (open, user is researching):** IIT owns the question papers. Whether a question can be shown directly in
a video, and on what terms, is the user's open research item. Internal testing is fine meanwhile.

## 1. Reading a paper

Split the PDF into structured questions with the vision model, as the textbook digest reads pages:
- subject and section;
- type (single, multiple, numerical, paragraph);
- stem and options;
- the paragraph a question belongs to;
- figures, cropped from the page;
- the marking scheme.

## 2. Solving (must be right)

The checks follow the chemistry approach: code confirms the result.

- **Two independent solutions** from strong models. When they disagree, a third settles it or the question is flagged
  for review.
- **Code checks the working, not only the answer:**
  - maths: sympy (integrals, limits, differential equations, matrices, conics, probability by enumeration);
  - physics: units and numbers;
  - chemistry: RDKit and the figure_library checks (structures, balanced reactions, mechanisms).
- **The official answer key** (published by IIT for each paper) is the final check. A mismatch means the solution is
  wrong, whatever the models agree on.
- **Multiple-correct questions:** each option is judged on its own, true or false with a reason, because the
  partial marking punishes one wrong pick.

## 3. Linking to concepts

Tag every question with the NCERT concepts and key ideas it uses:
- a solution can send the student to the concept film or key-idea film;
- across papers, the tags show which concepts the exam leans on.

## 4. Solution videos: a new film kind, "worked solution"

- One question per video, or one paragraph with its questions; about 2–5 minutes.
- **Narration by step:** understand the question, choose the idea, work it, check it. Then name the trap each wrong
  option sets.
- **On screen:**
  - the working written out step by step (equations as code-drawn figures);
  - coded animations where the picture is the solution, using the manim kits:
    - the conic and its tangents;
    - the region whose area is asked;
    - a ray through the prism;
    - a reaction mechanism.
- **Reused from the explainers:** narration and voices, audio audit, scene planning, figures, animations, render.

## Gaps to close first

- **Physics figures:** circuits, optics, mechanics diagrams and apparatus need exact, code-drawn figures, as
  chemistry and biology have.
- **Question figures** may need redrawing by code rather than cropping, depending on the licence finding.

## First experiment (when this starts)

Solve this paper's 18 maths questions:
- two models, plus sympy checks;
- score against the official answer key.

That shows early how reliable the solving step is, before any video work.
