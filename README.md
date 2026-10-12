# Lesson Studio: narrated science and maths lessons

The current system is `scivid/` with its portal, **Lesson Studio**. Start it with
`./run_studio.sh start` (port 18610; `stop`, `restart`, `status`). The access key is in
`scivid-data/api-token`. A lesson needs a topic plus a grounding source: an NCERT chapter
(Classes 6–10, read from `~/story_generator/ncert_downloader`), web research, or both.
Narration uses the frozen `~/remotion` infofilm audio stack as a library.

The older `manim_api/` service and its page are retired; the notes below describe the
original centripetal/centrifugal pilot.

# Centripetal and centrifugal force — Qwen + Manim

The generic web API is documented in [API.md](API.md). It accepts a topic,
uses Qwen for research/planning/review and Luna for coding/repairs, and returns
a silent MP4 with detailed model token reports. Start
with `bash run_api.sh 18610`; it binds to `0.0.0.0:18610`.

A silent, animated explainer of circular motion, tangent release,
the force law, rotating frames, and a turning car. Two implementations are
kept separately: the original Codex-written animation with Qwen planning and
review, and a new animation whose scaffold and all seven scenes were written
by Qwen. Manim renders the MP4s. No Claude API is used.

The configured local model is `Qwen3.8-27B-Q4_K_M.gguf` at
`http://10.8.0.5:8001/v1`. Planning and review are separate requests to the
same model. They are not independent models.
Set `QWEN_BASE_URL` to use another OpenAI-compatible endpoint.

## Files

- `centripetal_centrifugal_qwen_coded.mp4`: Qwen-written video, 1080p, 30 fps.
- `qwen_generated_forces.py`: assembled Qwen-authored animation source.
- `qwen_scene_codegen.py`: generates one scaffold and one scene per Qwen call;
  passes feedback back to Qwen and assembles the returned methods.
- `qwen_codegen.py`: source validation, scoped code/frame reviews, and an
  experimental whole-script generator.
- `build_qwen_coded.py`: Qwen coding → render → review → bounded repair workflow.
- `test_qwen_physics.py`: eight checks against Qwen's actual physics helpers
  and exact correspondence between the source and saved Qwen responses.
- `audit_qwen_coded_review.py`: source/numerical audit of disputed motion review findings.
- `artifacts/qwen-scenes/`: individual generated methods and repair feedback history.
- `artifacts/qwen-code-author.json`: coding model, response paths and source hash.
- `artifacts/qwen-coded-build.json`: new video provenance and validation results.
- `centripetal_centrifugal_qwen.mp4`: finished video, 1080p, 30 fps.
- `centripetal_centrifugal.py`: original Codex-written Manim implementation.
- `storyboard.json`: Qwen's accepted scene plan and captions.
- `qwen_workflow.py`: bounded storyboard planning/review and multimodal frame review.
- `build_video.py`: repeatable planning → physics checks → render → frame review workflow.
- `check_render.py`: MP4 validation and four checkpoints per scene.
- `test_physics.py`: seven numerical checks, including release velocity,
  rotating-frame acceleration, and actual force-arrow directions.
- `audit_qwen_review.py`: the follow-up mathematical audit of disputed review findings.
- `artifacts/qwen/`: complete Qwen requests, responses and review reports.
- `artifacts/final/`: 28 rendered checkpoints, contact sheet and MP4 metadata.
- `artifacts/final-build.json`: final provenance, validation and review outcomes.

## Render the saved plan

The existing Remotion environment already has Manim 0.21 installed:

```bash
/home/nitin/remotion/.venv-manim-pilot/bin/python -m manim \
  -qh --fps 30 qwen_generated_forces.py QwenForces
```

This renders Qwen's saved source directly, without another API call, to
`media/videos/qwen_generated_forces/1080p30/QwenForces.mp4`.
To render the original implementation:

```bash
/home/nitin/remotion/.venv-manim-pilot/bin/python -m manim \
  -qh --fps 30 centripetal_centrifugal.py CentripetalCentrifugal
```

No `-p` flag is used: this exports an MP4 without opening a player.
Manim writes to `media/videos/centripetal_centrifugal/1080p30/`.

For another machine, install FFmpeg, Cairo and Pango development dependencies,
create a Python 3.11+ virtual environment, and install `requirements.txt`.
No LaTeX is required.

## Repeat planning and review

From this folder, with network access to your Qwen server:

```bash
python3 build_qwen_coded.py --reuse-plan --reuse-code
```

This validates/reviews the saved Qwen source and asks Qwen to repair any
failures before the final render. Drop `--reuse-code` to assemble the saved
Qwen scene fragments and generate any missing fragments. The default is one
scene per call; `--whole-script` is experimental. The tested quantized model
needed specific repair feedback and worked better scene by scene. Generated
animation source is never hand-patched: repairs come from Qwen responses;
assembly normalizes indentation and trailing newlines only.

Reasoning-enabled coding and review requests use the llama.cpp top-level
`thinking_budget_tokens=1024` field. Unlimited reasoning exhausted a 7,000
token response without producing code. The observed server has one inference
slot, so simultaneous requests queue and do not accelerate generation.

For the original implementation's planning/review workflow:

```bash
python3 build_video.py --reuse-plan
```

Drop `--reuse-plan` to run Qwen's planning/review stage; identical requests reuse
the recorded plan. Use `--preview` for 480p at 15 fps. Set `MANIM_PYTHON` to a
different interpreter if needed. The render command above is also available
when you only need an MP4 and do not need new network reviews.

Changed review images or code get a new review name based on the video and input hashes.
Changed planning prompts require archiving the old planning artifacts first;
the client rejects incompatible caches instead of silently reusing them.
The `--external-transport` option of `qwen_workflow.py` supports environments
where network requests must be issued separately: it writes a temporary
`*.transport.json`; send it to `/chat/completions`, save the response as
`*.incoming.json`, then repeat the same command. The temporary image payload
is removed after the response is consumed.

## Physics and review scope

The ball/string diagrams show ideal horizontal motion, ignoring other forces.
Centripetal means the inward net force supplied by real interactions.
Centrifugal is the outward pseudo-force used in a rotating frame.
After release, the rotating path is computed by rotating the inertial straight
trajectory; both centrifugal and Coriolis effects enter its description.
The original car example treats initial free motion followed by simplified
door contact. The Qwen-coded car scene compares an unconstrained passenger
with a passenger held in the turning car by contact. Neither is a detailed
collision or vehicle dynamics simulation.

Qwen reviews selected frames and the source code, not full playback. Numerical
checks supplement its judgments. Initial reviews and rejected suggestions stay
in the artifact history; the first visual review caught three layout problems,
while another incorrectly proposed reversing two already-inward force arrows.
Those arrows were checked mathematically and retained.

For the original implementation, the final examples review passed with optional presentation suggestions. The
final motion review initially confused release positions with later positions
and misread the velocity subtraction diagram. A separate Qwen audit using
computed coordinates retracted those factual findings and passed. Its audit
was a code/math review, not a new video playback review. Both the rejected
report and the audit remain available; model approval alone is not the
validation criterion.

The Qwen-coded version passed all eight physics/provenance tests, rendered at
1920×1080 and 30 fps, and passed a complete FFmpeg decode. Its duration is
116.03 seconds, with no audio. Both 28-frame contact sheets are available in
`artifacts/qwen-coded-preview/` and `artifacts/qwen-coded-final/`.
Qwen's examples review passed with minor suggestions. Its motion review
transposed the components of two correctly computed tangent vectors and
incorrectly called the leftward Δv arrow upward. The evaluated difference is
`[-0.692046,0,0]`; a subsequent Qwen numerical audit retracted both major
findings and passed. The raw review and audit are preserved separately, and
the repeat workflow audits major motion findings before attempting repairs.
Minor suggestions remain, including hiding the old force legend after the
opening release and labeling the car inset's forces more explicitly.
