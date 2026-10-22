# Production architecture: portal, content and provider nodes (plan, 2026-10-22)

**Starting point**
- madesimple.in (on toystech.in, `~/kriyaflow`) is only a shell: accounts, sessions and a credit ledger, with a
  front end that already expects curriculum, film and lesson endpoints.
- The real portal runs on larger, load-balanced servers.
- Media lives in an object store, not on any server.
- Provider nodes with their own capabilities join a network of workers (user's direction: Celery).

## 1. How big the content is (measured 2026-10-22)

| What | Size |
|---|---|
| One chapter digest (`digest.json`) | mean 214 KB, max 523 KB, ~51 KB gzipped |
| 159 digests built so far | 34 MB |
| All of NCERT in English (1,142 chapters, Class 1–12, every subject) | ~250 MB, ~60 MB compressed |
| Visual needs | ~15 KB a chapter, ~17 MB for everything |
| Page images used to build digests | 2.25 GB now, ~16 GB for everything (only a rebuild needs them: cold storage) |
| Hindi editions (later) | about twice the text |

**Conclusion:** the content is small enough to be resident on every worker. It needs no shared database on the hot
path.

## 2. Tiers

**Portal tier: stateless, load-balanced.**
- Auth, credits, projects, the curriculum API, job submission and status, and media links.
- Grows out of the kriyaflow API (Hono, Better Auth) that is already written.
- Several instances run behind a load balancer. None holds files.

**Shared state: managed PostgreSQL.**
- Holds users, sessions, the credit ledger, projects, films and their stage states, and which film exists for which
  concept.
- It is the system of record. Celery's messages are transport, not the truth.
- The kriyaflow API switches to it with one setting (`DATABASE_URL`).

**Object storage (S3-compatible) with a CDN in front.** It holds:
- videos, images, audio and figures;
- every pipeline stage's cached output, keyed by the stage identity hash as today (lets a film resume on any node);
- the content bundles;
- the cold page images.

Nodes get short-lived signed URLs, never storage credentials.

**Content bundles: immutable and versioned.**
- The content factory (today the Spark and the amdserver; later rented GPUs) builds digests, visual needs, the
  visual registry and the diagram library.
- Each release is published as one versioned bundle, e.g. `content-2026.10.24.tar.zst` (~60 MB), plus a manifest
  with hashes.
- Nodes sync to the current version on start and when a new version is announced. Rollback means pointing at the
  previous version.

## 3. Work: Celery with queues by capability

**Broker: RabbitMQ.**
- Durable queues and per-queue routing.
- Late acknowledgement with long consumer timeouts for GPU tasks.
- Priorities.
- TLS with a separate login for each node.

**Results:** written to Postgres and object storage by the tasks themselves. Large outputs never travel through
Celery's result backend.

**Each capability is a queue.** A node's worker subscribes to the queues it can serve, e.g.
`celery -A flow worker -Q llm.plan,tts.vibevoice`.

| Queue | Work | Typical node |
|---|---|---|
| `llm.plan` | research, evidence, idea plan, script, scene plan, questions (mostly waiting on LLM APIs) | small CPU servers, many tasks each |
| `llm.local` | in-house model calls (digest, visual needs, audits) | Lucebox/llama.cpp GPU nodes |
| `tts.<voice engine>` | narration takes, per point | GPU node with the voice model |
| `asr.audit` | Whisper cross-check of narration | GPU or strong CPU |
| `image.<model>` | stills, per scene (klein today, maybe GLM-Image later) | image-factory GPU nodes |
| `video.ltx` | motion clips | 24 GB+ GPU |
| `code.manim` | coded animations in the sandbox (bwrap/seccomp) | CPU nodes with the manim kit |
| `figure.code` | chemistry, biology and map figures (RDKit, cairosvg) | any CPU node |
| `render.remotion` | layout check and final render | CPU-heavy nodes |
| `content.build` | digest and visual-needs builds (not film work) | the content factory |

**A film is a Celery workflow (canvas).**
1. A planning chain runs first.
2. A group for the media fan-out follows:
   - TTS per point;
   - images per scene;
   - clips and animations per beat;
   - figures.
3. A chord collects that group into the render.

Each task is small and **idempotent**: it checks the stage cache in object storage first and does nothing if the
output exists. A retried or re-delivered task is therefore cheap and safe. The current pipeline already caches every
stage by identity hash, so this mostly means moving the cache from local disk to the object store.

**Long tasks:**
- Celery suits short tasks best, so the pipeline's per-scene and per-point parallelism becomes the task size.
  Nothing is a single hours-long task.
- Settings for GPU queues:
  - `acks_late` with `worker_prefetch_multiplier=1`, so a node takes one GPU task at a time;
  - generous broker timeouts.
- A task that dies is re-delivered to another node with the same capability.

## 4. Provider nodes joining the network

**Joining:**
1. Register the node and receive broker credentials, a node id and its allowed queues.
2. Run the node agent.
   - It reports capabilities: GPU model and VRAM, installed engines and models with versions, licences, CPU and RAM.
   - The portal checks the report against the queues the node asked for.
3. Start the workers on the approved queues.

**Trust:**
- **What a node sees:** content (public NCERT digests) and its task's inputs, through signed URLs.
- **What a node never gets:** user data, the database, or other tasks' outputs.
- **QA gates on every node's output:** the same checks already in the pipeline.
  - Image review for stills.
  - The three-Whisper audit for audio.
  - The layout check for renders.
  - Code checks for figures.

  A node whose outputs keep failing review loses its queues.

**Metering:** each task records its node, duration and outcome. That is the basis for paying providers and for
routing work to the faster or cheaper nodes.

**Model licences:** a node may only serve a queue whose model meets the licence policy (Apache/MIT/BSD). The agent
reports the model and its version, and the portal enforces the policy per queue.

## 5. What carries over, and the migration path

**Carries over unchanged:**
- the pipeline stages and their validators;
- stage caching by identity hash;
- the QA gates;
- the kits (chemistry, molecules, biology, maps);
- digests, the visual registry and the diagram library (as the content bundle);
- the kriyaflow API's auth and credit ledger.

**Steps:**
1. **Content bundle:** build and publish it.
2. **Stage cache to object storage:** behind the existing `Store` interface.
3. **Tasks:** wrap each stage, and the per-scene and per-point fan-outs, as Celery tasks.
4. **Workflow:** run one film as a canvas on the current machines, with the Spark and the amdserver each as nodes.
5. **Postgres:** film, job and credit state. The kriyaflow API takes over submission.
6. **Load-balanced portal:** stand up the portal servers and the CDN. Retire the per-subject studio portals as
   public front doors; they stay as internal tools.
7. **Node agent:** registration and onboarding for outside provider nodes.

## 6. On AWS (user, 2026-10-22: "AWS becomes the most obvious choice ... we will fulfil all requirements there")

Region **ap-south-1 (Mumbai)** for latency to Indian students and for data residency. CloudFront's Indian edges
serve the media.

| Piece | AWS service |
|---|---|
| Portal tier | Application Load Balancer + ECS on Fargate (or an EC2 Auto Scaling group) running the portal API; static front end on S3 + CloudFront |
| Shared state | RDS for PostgreSQL (Multi-AZ), or Aurora PostgreSQL when it grows |
| Broker | Amazon MQ for RabbitMQ (managed, TLS); outside provider nodes connect with their own logins |
| Object storage and delivery | S3 (media, stage caches, content bundles; Glacier for page images) + CloudFront with signed URLs |
| Planning workers (`llm.plan`, `figure.code`, `code.manim`, `render.remotion`) | ECS or EC2 CPU instances, scaled on queue depth |
| GPU workers (`tts`, `image`, `video.ltx`, `llm.local`) | EC2 GPU instances (g6/L4 or g6e/L40S class; check what Mumbai offers), mostly **Spot**: idempotent, cached tasks make an interruption cost only the task in flight |
| LLM APIs | Claude through the Anthropic API, or Amazon Bedrock if keeping traffic and billing inside AWS is preferred |
| Secrets and identity | Secrets Manager; IAM roles for AWS workers (no keys on nodes); outside nodes get broker credentials and presigned S3 URLs only |
| Observability | CloudWatch metrics and alarms (queue depth, task failures, QA-gate rejections per node) |

**GPU capacity in layers (user, 2026-10-22):**
- **Steady load:** a few always-on GPUs (e.g. RTX 5090s on RunPod, with a network volume for the models) keep their
  models loaded.
- **Overflow:** EC2 GPU instances.
- **Joining:** every provider joins the Celery broker with **its own login (a per-node secret)** over TLS, so one can
  be revoked or rotated alone and metering is per node.

**Starting EC2 media workers fast:**
- An **Auto Scaling warm pool** holds GPU instances that were set up once and then *stopped*, each keeping its EBS
  disk with the models. Scale-out starts one in about 1–2 minutes, and stopped instances cost only their disk.
  Capacity must be free at that moment, which is why the always-on layer comes first.
- Alternatives:
  - **a golden AMI** with the models baked in, plus **EBS Fast Snapshot Restore** in the AZs used (otherwise a disk
    made from a snapshot loads lazily and the first read of 20–40 GB is slow);
  - **local NVMe filled from S3 at boot** (parallel copy at about 1–2 GB/s, roughly 15–40 s for our models), for Spot
    instances that are never kept.
- An EBS volume attaches to one instance in its own Availability Zone (io2 multi-attach allows up to 16, fine for
  read-only weights).
- Loading weights into GPU memory still takes tens of seconds to a few minutes per model. Only always-on workers skip
  it.

**Our own machines stay in the network.** The Spark, the amdserver and the aiserver join as provider nodes over
TLS, with no AWS credentials, and serve the queues they are good at (`llm.local`, `content.build`, images).

## 7. The subject studios stay internal (user, 2026-10-22)

History, Chemistry, Biology and Lesson Studio stay as **internal tools**. They are "required for us to keep
refining our core work": pilots, reviews and fixes happen there first. madesimple.in is the only public front door.
The studios use the same pipeline and can submit to the same queues, but stay behind the VPN or the internal Caddy
routes, not on public marketing domains.

## Open questions

- **Credits:** what a film costs, and what a provider earns per task type.
- **GPU instances:** which types ap-south-1 offers at Spot prices that fit the ~$10-a-film budget. Bench a film on
  each class before choosing.
- **LLM traffic:** Bedrock or the direct Anthropic API.
