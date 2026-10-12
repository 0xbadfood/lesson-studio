# Manim API: Qwen + Luna

Submit a topic and receive a source-grounded, silent Manim MP4. Qwen at
`http://10.8.0.5:8001/v1` performs research synthesis, planning and review.
OpenAI `gpt-6-luna` authors scene code and repairs via the Responses API, using
`OPENAI_API_KEY` or `OPENAI_TOKEN` inherited from the service environment.
Tavily supplies web search; fetched pages supply evidence. The existing
Remotion research worker is reused read-only. No Claude model API is called.

The service supplies layout helpers, source/reference validation, numerical
arithmetic checks, a persistent queue, isolated rendering and media checks.
The configured coding model authors each scene module and exact replacement text for repairs. The API
applies replacements only when the original text matches uniquely, preserving
unrelated code. The source bundle contains the resulting modules; the original
model responses, base source and edits remain archived. The API's layout/runtime
helpers are separate supporting code.

## Start and open

```bash
cd /home/nitin/manim
bash run_api.sh 18610
```

The configured binding is `0.0.0.0:18610`. Open `http://localhost:18610` on this
host, or `http://10.8.0.2:18610` over the VPN. The OpenAPI interface is `/docs`.
The browser interface accepts a topic, audience, approximate length, output
quality and optional teaching instructions, and shows progress and downloads.

For a background process with durable server logs:

```bash
python3 scripts/start_api.py --port 18610
python3 scripts/stop_api.py
```

The background launcher saves the server PID in `api-data/server.json` and
logs in `api-data/server.log`. Stopping the API leaves active video workers
running so the next API instance can reattach.

The API token is generated once at `api-data/api-token`, with mode 0600.
Enter its contents on the sign-in page or use an Authorization bearer header.
`MANIM_API_KEY` overrides the generated token. Credentials are not saved in job
configuration snapshots or passed into generated animation processes.

The installed Python environment already includes the web dependencies;
`requirements-api.txt` pins them for another installation. The renderer uses
the existing Manim 0.21 environment, FFmpeg, and Linux Bubblewrap.

## Python client

The local client reads the token file without printing the token:

```bash
python3 api_client.py health
python3 api_client.py create \
  --topic "Explain centripetal and centrifugal forces" \
  --duration 90 --quality hd --wait --output lesson.mp4
python3 api_client.py list
python3 api_client.py get JOB_ID
python3 api_client.py download JOB_ID --kind code --output source.zip
```

For a remote client, set `MANIM_API_KEY` and pass
`--url http://10.8.0.2:18610` before the command name.

## HTTP contract

Every API and download route requires `Authorization: Bearer YOUR_TOKEN`
or the browser's authenticated cookie. Browser login is `POST /api/session`
with `{"token":"YOUR_TOKEN"}`. Cross-origin writes are rejected.

`POST /api/jobs` returns **202 Accepted** immediately:

```json
{
  "topic": "Why a released whirling stone follows a tangent",
  "audience": "High-school students",
  "duration_seconds": 90,
  "quality": "hd",
  "instructions": "Use a horizontal top view and ignore gravity and air resistance."
}
```

Topic: 3–1,000 characters; duration: 20–180 seconds; quality: `hd` (1920×1080,
30 fps) or `preview` (854×480, 15 fps). Instructions are optional. Output has
no narration or audio. Unknown request fields are rejected. Duration guides
the storyboard; small differences from animation frame rounding are expected.

An optional `Idempotency-Key` header prevents duplicate submissions. Reusing
that key with different input returns 409.

| Endpoint | Result |
|---|---|
| `GET /api/health` | Model/runtime/research readiness |
| `POST /api/jobs` | Submit topic; returns job ID and queued status |
| `GET /api/jobs` | Recent jobs |
| `GET /api/jobs/{id}` | Status, current stage, error and available downloads |
| `POST /api/jobs/{id}/cancel` | Cancel a queued/running job |
| `POST /api/jobs/{id}/resume` | Resume a failed, interrupted or cancelled job |
| `GET /api/jobs/{id}/files/video` | Validated MP4, available after success |
| `GET /api/jobs/{id}/files/code` | Model-authored scene modules and layout helper ZIP |
| `GET /api/jobs/{id}/files/storyboard` | Accepted storyboard JSON |
| `GET /api/jobs/{id}/files/research` | Source URLs, claims and passage references |
| `GET /api/jobs/{id}/files/report` | Reviews, checks, provenance and MP4 metadata |
| `GET /api/jobs/{id}/files/log` | Worker progress/error log |
| `GET /api/jobs/{id}/files/token_usage` | Usage JSON per call, model, role and scene |
| `GET /api/jobs/{id}/files/token_csv` | Per-call token usage and latency CSV |

Statuses are `queued`, `running`, `succeeded`, `failed`, `interrupted` and
`cancelled`. Stages include research, planning, coding, preview, review,
audit, repair, rendering, validating and done. A failed job includes its actual error
and retains its artifacts. No failed/unvalidated video is exposed as a result.

## Execution and saved work

Jobs run sequentially because the observed Qwen server has one inference slot.
SQLite stores the queue in `api-data/jobs.sqlite3`. Each job has a separate
`api-data/runs/JOB_ID/` directory, frozen settings, requests/responses, research
pages, source modules, preview/final frames and reviews. Active pipeline
processes survive an API restart; the new worker reattaches using PID identity.
An interrupted process can resume its saved research, plan and accepted scenes.

Research uses the Remotion harness's bounded search/fetch budget and fetched
source digests. Planning has three attempts; coding/repair has five attempts per
scene per run. Luna uses `high` reasoning, with a 24,000-token output cap for
new modules and 16,000 for source patches, including reasoning tokens. These
are caps, not a target or measured consumption. Legacy Qwen coding uses
3,072 reasoning tokens. Qwen budgets are 2,048 for planning/content checks
and 1,024 for the smaller visual layout check. They are
administrator settings (`MANIM_CODE_THINKING`, `MANIM_CONTENT_THINKING`,
`MANIM_PLAN_THINKING`, `MANIM_LAYOUT_THINKING`). Code and reviews are generated
one scene at a time. A resumed, valid unaccepted source is checked with the new
reviews before making further repairs.

Generated scenes render with Bubblewrap: only runtime dependencies and that
scene's working directory are mounted; credential files are not mounted, the
environment is cleared, socket syscalls are denied and process/file/memory/time
limits apply. The API never executes arbitrary test scripts generated by a model.

Preview geometry is monitored during animation for offscreen objects. Content
review receives code, relevant original source claims/passages and compact
geometry. A separate layout review receives two of the four saved preview
stills and measured text boxes. Major findings receive a focused audit before
repair. Topic conventions are included only for applicable lessons. HD
scenes receive their own geometry checks and checkpoint extraction. FFmpeg
joins accepted clips, verifies silent H.264 output and decodes the whole MP4.
Body text is also measured throughout the scene. Persistent overlaps return
the conflicting label names and timing to the coding model; brief transition overlaps are allowed.
Static checks also identify undefined names, unavailable Manim APIs and
incorrect redraw callback signatures before animation runs. Reviews receive
the API's helper contract, measured arrow lengths and text boxes.
A persistent "equal magnitude" label on opposing red/amber force arrows is
also checked against their measured lengths; mismatches are returned for repair.

These checks catch technical and many explanation errors. Arithmetic checks
do not establish every physical model or source claim; the same Qwen model's
review is not an independent factual guarantee. Full playback is not watched
by the automated workflow. Raw rejected candidates/reviews remain archived.

The live centripetal/centrifugal pilot required a manual content correction
and review arbitration: Qwen's longer review contradicted its own computed
matrix endpoints. A fresh, isolated Qwen arithmetic check confirmed the
correct axes label. Its scene code was preserved unchanged from Qwen's
response. The report records the manual intervention and both model answers;
this pilot does not establish that future videos need no content review.

## Configuration

Set `QWEN_BASE_URL` for another compatible Qwen endpoint. Other settings use
`MANIM_` plus the uppercase field name, for example `MANIM_DATA_ROOT`,
`MANIM_MANIM_PYTHON`, `MANIM_RESEARCH_PYTHON`, `MANIM_REMOTION_ROOT`,
`MANIM_MAX_ATTEMPTS`, `MANIM_RENDER_TIMEOUT` and `MANIM_JOB_TIMEOUT`.
These are administrator settings, not client-controlled paths or URLs.

New jobs default to `MANIM_CODING_PROVIDER=luna`. Use `qwen` to restore Qwen
coding. Luna settings are `MANIM_LUNA_MODEL`, `MANIM_LUNA_URL`,
`MANIM_LUNA_REASONING_EFFORT`, `MANIM_LUNA_CODE_MAX_OUTPUT_TOKENS` and
`MANIM_LUNA_PATCH_MAX_OUTPUT_TOKENS`. Older frozen jobs without a coding-provider
field retain Qwen when resumed. Model credentials never enter saved settings,
request artifacts or generated-code sandboxes.

Usage reports preserve the provider's original usage fields. Cached input is
a subset of input tokens; reasoning is a subset of output tokens. They must
not be added to those totals again. The report also gives uncached input and
non-reasoning output where both required counts are reported. Missing fields
are `null`, not estimates. Incomplete responses count toward usage. Reusing an
archived result locally adds no API call; reused inputs from a previous job
are recorded separately and excluded from the new job's call totals. This
report measures tokens and latency, not an estimated monetary charge.

Tavily credentials are read from `TAVILY_API_KEY`, or only that variable is
borrowed from Remotion's existing `.service.env`. Nothing is written into the
Remotion checkout. With a fresh installation, configure the research runtime,
Obscura fetcher, Tavily key, Manim environment, Python base path and Bubblewrap.

`run_api.sh` runs in the foreground; the detached launcher is also available.
This delivery does not install or
change a systemd unit, reverse proxy or firewall.
