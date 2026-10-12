# Lesson Studio — next ideas

A running list of pipeline ideas to discuss and build. Newest at the bottom; mark items **[done]** or **[dropped]** rather than deleting them.

---

## 1. Planner chooses the chapter form: slide, diagram or animation

*Raised 2026-10-08.*

**Problem.** Every chapter currently goes to a coded Manim scene. Many concepts don't need motion, and coded scenes are the expensive part of the pipeline. In one test, a single chapter took 6 attempts and about 9 minutes, and was kept only with review notes. Producing lessons this way at scale would make the cost per concept shoot up. Motion that carries no meaning also distracts the learner.

**Idea.** The planner explicitly gives each chapter a `form`, with a one-line reason.

| Form | Use for | How it's made |
|---|---|---|
| `slide` | definitions, classifications, recaps, worked-example setups, "why it matters" | fixed template filled from JSON; no coder |
| `diagram` | a still figure with labels and highlights | the existing diagram route |
| `animation` | motion, processes, a quantity changing, constructions where order matters | coded scene at a complexity tier |

**Rules.**
- The planner's test is: *"What changes over time that the learner must watch happen?"* If nothing does, the chapter is not an animation.
- The plan reviewer challenges every `animation` choice: would a slide with cued reveals teach it just as well?
- Soft budget: at most about 40% of chapters animated unless the reviewer accepts a stated reason. Tune this from data.
- The complexity rating (routine, involved or novel) applies only to `animation` chapters.

**Slides must still follow the narration** (this is what keeps them from feeling like a dead PPT):
- Each bullet or term appears on its cue phrase.
- The formula term being spoken is highlighted.
- A picture appears when it's mentioned.
- This uses the cue timing we already resolve after narration.

**Slide templates**, a fixed renderer in scene_kit:
- title banner
- key points
- definition or callout
- formula card (with highlighting of individual terms)
- two-column comparison
- picture with caption
- summary

The script model fills a small JSON: the layout, the items, and the cue for each item. Checks are automatic (text fits, nothing overlaps) instead of the vision-model review loop. The cost should be close to zero, with no runtime failures.

**Measurement.** The runs table shows cost and time per chapter form. This tells us the saving per lesson and lets us set the animation budget.

**Pictures: adopt the remotion infofilm image cards** *(decided 2026-10-08)*

The reference is the rainbow render: `~/remotion/output/rainbow-integration/`, with artifacts in `~/remotion/artifacts/rainbow-integration/`. Remotion is used as a library only and is never modified.

What it already does:
- **Image cards** (`kind: image`): a full-bleed generated picture with gentle camera motion (drift, push, pull or hold). On top sit the heading, a one-line summary, an amber banner, a counter (`04 / 10`) and source tags.
- **Graphic cards** (`flow`, `compare`, `cycle`): numbered boxes with a short title and detail line. Items reveal on cue; in the frame from the compare card, the second box is still fading in.
- **Image generation**:
  - Qwen Image 2.1 runs locally on :8075, with Flux.2 Dev as the fallback (`image-providers.json`, policy `standard_then_premium`).
  - The planner writes one shared style prompt for the whole lesson, then a prompt for each asset with a purpose, acceptance criteria and `fact_ids`.
  - A vision review checks every candidate against its acceptance criteria and records its limitations.
  - The pictures contain **no text and no diagrams**. All text is overlaid by the renderer, so it is always crisp and correct.

How this fits Lesson Studio:
- Picture chapters show context, real-world phenomena and setting ("where you see this", "why it matters"). They never carry diagrams where scientific accuracy matters. Those stay as Manim diagrams or animations.
- Reuse infofilm's image steps as a library: the style prompt, the asset prompts with acceptance criteria, the provider policy and the vision review. Add them as model-settings steps so presets can test them (e.g. `image_prompt`, `image_review`).
- Render slide chapters either:
  - **(a)** through the remotion renderer, one segment per chapter, then join them to the Manim chapters at assembly; or
  - **(b)** by porting the card layouts into scene_kit.

  **Decided: (a), see below.**
- **Style mismatch to resolve.** The infofilm cards use an editorial teal look with a serif heading. Our Manim chapters are dark navy (#0B1220) with DejaVu Sans. One lesson should look like one product, so pick a single palette and type scale for both.
- **GPU.** Image generation needs the lab GPU. Daytime POCs run on the local 3090 (`scripts/gpu_mode.sh media`); full runs go in the evening. Generated images are cached by prompt hash, as in infofilm, so a redo doesn't pay twice.

**Decisions** *(2026-10-08)*
- **Render and join.** Slide chapters are rendered by the remotion renderer, one segment per chapter. The segments are joined with the Manim chapters at assembly.
- **Consistent look through a planned background.** The planner sets one lesson-wide `theme`. Both renderers use it, so every chapter shares the same backdrop:
  - background: a gradient (colours plus direction), or one generated low-detail backdrop plate for the lesson, made once and reused for every chapter
  - accent colours and text colours, the heading and body fonts, and the banner style
  - the theme is fixed with the plan, so a redo keeps it
- **Manim side.** `scene_kit.begin()` draws the theme background, a colour gradient or the plate as an image. This is trusted kit code, so coded scenes still can't load images themselves. The kit palette constants (WHITE, CYAN …) come from the theme instead of being fixed.
- **Remotion side.** Pass the theme as timeline data: background, accent and fonts. If the renderer doesn't accept a custom background, use its existing props and adjust our theme to match, because remotion is not modified.
- Check before building: does a generated image card sit well on the shared backdrop? Possibly the image fills the card while the frame, the header strip and the subtitle band use the theme.

Earlier lesson (from the image-first trials): generated images work for atmosphere and context, not for labelled scientific figures.

**Status:** built 2026-10-08, first version.
- The planner gives each chapter route `coded` or `slide`, with no % budget; the plan reviewer challenges animation where a slide would do.
- The lesson `theme` colours both the remotion cards and the Manim background.
- The script writes one card per narration point; cards change on each point's first word.
- `scivid/slides.py` builds the pictures (Qwen Image under the GPU lease, checked by the frame-review model) and renders through a private copy of the remotion renderer.
- Not yet: cue-timed reveals inside a card (flow items reveal evenly across the card), and per-form cost columns in the runs table.

---

## 2. Narration never pauses during animated chapters (issue; needs planning)

*Raised 2026-10-08.*

**Problem.** In animated chapters the narration is one fixed, continuous recording. The animation is fitted to it afterwards (cues → seconds). The narrator talks without a break, so the learner gets no time to watch the motion and let the idea sink in. It feels unnatural: the voice is always ahead of, or on top of, what is happening on screen.

**Direction (to plan in detail).** Animated chapters need a different treatment from slide chapters:
- Allow narration to follow the animation, not only the other way round.
- Or plan **slots** for each beat, where the narration comes *before* the animation (set up what to watch), *during* it (talk over it) or *after* it (name what was just seen). Silent "watch" gaps are allowed.

**Open questions:**
- Who decides the slots: the planner (per chapter beat), the script writer, or the coder after it knows how long an animation takes?
- How to build the audio: separate narration clips per beat with silence inserted between them, instead of one continuous take, while keeping MFA alignment and the Whisper audit per clip.
- How long the pauses are: a fixed minimum "watch" gap, or set by the motion's own duration.
- Subtitles and the cue timing must use the new clip offsets.
- Slide chapters can probably keep continuous narration.

**Proposed approach** *(2026-10-08, under discussion)*: the clock is built from sentences plus inserted silences.
1. **Sentence clips.** Prefer cutting the existing point takes at sentence ends, using the MFA word times and the natural gap between sentences. Fall back to synthesizing each sentence separately. One take per point keeps natural intonation and a steady voice; sentences synthesized one by one can sound flat, and the voice drifts between takes.
2. **The coder declares motion lengths.** For each cue, the coder states how long its motion runs and whether the learner should watch it in silence. These go in a small manifest beside the code, before the final render.
3. **The sync planner places pauses**, at sentence ends (or at a comma at most):
   - pause = the motion running past the next sentence start, plus any "watch" time asked for
   - mostly deterministic; the script writer can add pedagogical hints such as "pause after this", and an LLM only resolves the rest
   - capped at about 0.6–2.5 s per pause
4. **The clock is rebuilt.** Word times = MFA time + the silence inserted before that word. Cues, subtitles and `at()` all use the new clock, and the scene is rendered once against it.
5. **Silence is room tone, not digital zero.** Use low-level noise taken from the take itself, with short crossfades, so a pause doesn't sound like a dropout.
6. The per-point Whisper audit stays as it is. The whole-recording audit runs on the spliced file. Slide chapters keep continuous narration.

**Status:** approach proposed, not built.

---

## 3. More polish on the animation canvas (tentative)

*Raised 2026-10-08.*

**Observation.** Coded Manim chapters look bare next to the infofilm cards: a plain dark canvas with a heading. They need more framing and finish.

**Possible additions (not decided):**
- **Cards:** panels that group related objects, for example a formula card beside the motion, or a "given / find" card.
- **Banners:** a short tag for the key idea or result, as on the image cards.
- **A consistent frame:** a header strip, the chapter counter, and a source tag in the footer. This ties in with the lesson theme from idea 1.

All of these would be kit helpers in scene_kit, so coders call them instead of drawing their own.

**Pending evidence.** We have no maths production yet. Make one maths lesson first and see what the canvas actually lacks before deciding what to add. Physics lessons may need different things from maths.

**Status:** observation only; wait for a maths production.

---

## 4. Review and retry loop: stop wasted attempts

*Raised 2026-10-08 from the coastline-paradox run (lesson 2ffcf663, haiku-only preset).*

**Evidence.** The lesson came out well and cost $0.42 of Haiku, but scene coding took 2 h 48 min of a 3 h 17 min run:
- 45 attempts across 8 chapters
- only 2 chapters passed both reviews; 6 used all their attempts and kept a render with notes
- Qwen reviews took about 97 minutes (72 calls), Haiku coding about 59 minutes, so the reviews are the bottleneck
- real catches: a mismatch between the ε label and the ruler, the circle radius against the perimeter formula, the wrong Koch apex construction, a counter disagreeing with the chart
- wasted retries:
  - c8, five times: insisted the drawing match the cue's wording ("stage-one coastline")
  - c2: the reviewer contradicted its own earlier finding
  - c4 and c3: pedantic demands ("each equation transforms into the next", "the segment runs from x=0 to x=1")
  - c1: a false "length went down" alarm, caused by a mid-walk frame in the contact sheet

**Decisions** *(2026-10-08)*
1. **The reviewer gets the review log, not just the last attempt.** Pass all earlier findings and the coder's replies into each review. The reviewer must not contradict an earlier finding the coder already fixed, and it must say whether each earlier issue is now fixed.
2. **No tier escalation onto the same model.** If the next tier maps to the same model and connection, don't move up. Spend the attempt as a normal repair, or stop. When every tier is the same model, escalation is off.
3. **The reviewer must not match wording.** Its job is to check that the science and maths are correct, the visual is legible, and the scene teaches what the narration says. It does not check that the drawing literally matches the cue or plan text. Wording mismatches are at most notes, never a reason to retry.

**Related, to consider:**
- Let the coder dispute a finding, for example "the cue wording is wrong, keeping depth 3 because …". A dispute the reviewer accepts goes into the notes instead of forcing another retry.
- Ask for a retry only on major problems with correctness or legibility.
- Contact-sheet frames taken mid-animation can mislead: a counter that resets at the start of each walk read as a drop. Sample at the end of a cue's motion, or tell the reviewer the frame time is inside a running animation.
- Track the share of findings that turned out pedantic or false, per reviewer model, in the runs table.

**Status:** built 2026-10-08 (`scivid/coded.py`):
- decisions 1–3 are in;
- coder disputes are in, and a reply that only disputes is reviewed again without re-rendering;
- the reviewers are told that a counter partway through a run or reset for a new run is not wrong;
- the offline test is `test_review_loop_keeps_log_and_skips_same_model_escalation`.

Still open: per-reviewer tracking of false findings, and sampling frames at the end of a cue's motion.

---

## 5. Optional historical context, always on slides

*Raised 2026-10-08.*

**Idea.** Most concepts have a history: who found it, the problem they were trying to solve, and how the idea changed. That story makes a lesson more interesting. The teacher can choose to add **historical context** when submitting a lesson.

**How it works:**
- **Request form:** a "Historical context" option, off by default.
- **Planner:** when the option is on, the planner adds history chapters to the plan. They are not added when it's off.
- **Form:** history chapters are always `slide` (see idea 1), never animated. That keeps them cheap, and an image card suits a period setting, a portrait-style scene or the original problem.
- **Facts:** names, dates and claims must come from the evidence, like any other fact, and the reviewers check them. The spoken-form normalizer reads years as years ("sixteen eighty-seven").
- **Pictures:** generated scenes for atmosphere only. Never present a generated image as a real portrait or document of a real person.

**To decide:**
- Placement: one opening "story" chapter, short notes placed where each idea first appears, or both, chosen by the planner.
- A length budget, for example at most about 15% of the lesson, so history doesn't crowd out the concept.
- Whether research should look for history sources specifically when the option is on.

**Status:** built 2026-10-08. There is an "Historical context" switch on the form (`include_history`). The planner places history freely, in slide chapters marked `history: true`; there's no length budget, by decision, and it's to be reviewed after a few renders.

---

## 6. Reviewers score fixed criteria; code decides pass or fail

*Raised 2026-10-08.*

**Problem.** Today the reviewer model returns `pass` and labels its own issues "major" or "minor", so the model decides the outcome. That is why its strictness drifts: it raised wording matches as major, contradicted itself between rounds, and failed whole attempts on nitpicks.

**Idea.** We define the criteria. The reviewer only scores each one, with a reason, and code turns the scores into pass or fail.

**Proposed rubric** (each criterion scored 0–3: 0 = wrong or missing, 1 = serious problem, 2 = small flaw, 3 = right; a reason is required below 3):
- **Content review (code and timeline):**
  - `science`: facts, units, physics and maths are correct
  - `numbers`: numbers on screen are computed correctly and match the narration
  - `sync`: at each cue the screen shows what is being said
  - `demonstrations`: the planned demonstrations are actually shown
- **Frame review (contact sheet):**
  - `legibility`: no text overlaps, nothing cut off
  - `clarity`: the frame is uncluttered and the eye knows where to look
  - `visual_correctness`: what is drawn fits the values and labels
  - `teaches`: the picture makes the idea clear

**Code-owned decision (thresholds are settings, tuned by experiment):**
- Correctness gates: `science` and `numbers` must be 3, because any error fails.
- Everything else must be at least 2.
- A score of 2 is a note for the teacher, not a retry.
- The feedback to the coder is the reasons for the criteria that failed.
- If no attempt passes, keep the **highest-scoring** attempt, not the last one.

**Later:** the same pattern for plan review, script review and the picture check. The runs table shows average scores per reviewer model, to calibrate reviewers against each other.

**Status:** built 2026-10-08 (`scivid/review.py`).
- One method for every review: plan, script, scene content, scene frames, diagram frames and slide pictures. The model only scores; `review.decide()` decides.
- The minimums are global settings, edited in Settings → Review rules. They are frozen into each lesson, and saved configurations carry their own.
- A score below its minimum fails the review and its reason goes back for a fix; a score below 3 that meets the minimum becomes a note.
- The best-scored attempt, plan or script is kept when none passes.

Decision: frame `visual_correctness` defaults to a minimum of 2, not 3, because frame readers misjudge mid-animation states; correctness is gated at 3 in the content review instead.

---

## 7. NEXT THEME: minimise false positives, repair in place

*Set by the user on 2026-10-09 as the theme of the next round of work.*

**Goal.** Every retry must fix a real problem, and each fix touches only what is wrong.

**Done so far:**
- Scored reviews with pass/fail decided in code (idea 6).
- Review logs passed to the reviewers.
- No matching on wording.
- Frames taken after animations finish.
- Negated mentions ignored by the picture check.
- **Targeted repairs for the plan and script** (`scivid/patch.py`):
  - a failed review gets a patch of operations on stable ids (chapters `cN`, demos `dN`, points `cNpM`, cues `kN`, slides by point id), not a rewrite;
  - code applies the patch and reruns the normal checks, and the reviewer re-scores the whole document;
  - wrong calculations from the code-run numbers check are also fixed by a patch;
  - patch calls use medium effort;
  - a full rewrite happens only on a structural failure (plan `order` or `coverage`) or after two patch rounds that don't pass.
  - Evidence for the change: a full plan revision took 52–74 s and in one run introduced a new error (a reversed Lenz direction) while fixing another.

**Built 2026-10-09:**
- **Reviewer accuracy** (`scivid/findings.py`, Settings → Reviewer accuracy):
  - every failed criterion in the run history is a finding (195 so far);
  - people mark findings right or wrong, or the Review auditor step (Opus) judges the backlog, at about $0.017 per finding;
  - a person's verdict overrides the auditor's;
  - the false-positive rate is shown per reviewer model, review and criterion.
- **Scene repairs are edit-first:** exact-text edits (up to 16); a full module only with a `rewrite_reason`. Edits are checked inside the model call, and repairs use medium effort.
- **Slide cards reveal each box on its exact phrase:** the script gives `reveal` phrases; MFA times become frames. The renderer component is our copy at `scivid/cards/Video.tsx`; ~/remotion is untouched.

**Still open:**
- Re-check only what a patch could affect, when that is provably safe. Today the whole document is re-scored.
- Use the measured false-positive rates to tune the review rules, or to change reviewer models per criterion.

---

**Review rule change** *(2026-10-09, after the Lenz run; the user agreed)*:
- Correctness criteria (science, numbers, plan and script accuracy, diagram correctness, picture "not misleading") now need **2**, not 3.
- The scale tells every reviewer that any actual error of fact, number, science, maths or history scores at most 1, so real errors still fail, and a 2 ("correct but simplified") is a note.
- Why: in the Lenz run, c5 failed all 6 attempts on "science 2" while the reviewer wrote that the physics was correct.
- No-text in pictures stays at 3.
- **Dispute arbitration:** when the coder disputed findings in the previous round and the reviewer still fails the attempt, the Review auditor rules on each failed criterion. Code turns criteria ruled "wrong" into notes.
- Frame reviews judge each frame against its own cue only.
