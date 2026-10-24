"""Administrator settings for the science-video engine. Environment overrides use SCIVID_<NAME>."""
from dataclasses import asdict, dataclass, fields
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Settings:
    data_root: str = str(ROOT / 'scivid-data')
    # Models
    planner_url: str = 'http://10.8.0.8:8001/v1'      # Qwen 27B FP8 on amdserver (vision): planning, scripts, cues, grounding
    reviewer_url: str = 'http://10.8.0.8:8001/v1'     # review; same host today, a separate node later
    math_url: str = 'http://10.8.0.4:18080/v1'        # GLM on Spark: candidate solver, benchmark pending
    luna_url: str = 'https://api.openai.com/v1'       # paid; only after local coding attempts fail
    luna_model: str = 'gpt-6-luna'
    # Media services
    image_url: str = 'http://127.0.0.1:8075'          # Qwen Image 2.1 (local 3090)
    spark_voice_url: str = 'http://10.8.0.4:8092'     # resident VibeVoice on Spark (same checkpoint and LoRA)
    tts_engine: str = 'luxtts'                        # luxtts (CPU, speed 0.75) | vibevoice (GPU) (user, 2026-10-24)
    remote_voice_lock: str = '/tmp/scivid-remote-voice.lock'   # serialises our narrations on the remote server
    gpu_lock: str = '/tmp/infofilm-rtx3090.lock'      # shared with infofilm
    remotion_root: str = '/home/nitin/remotion'       # frozen; used as a library
    research_python: str = '/home/nitin/kbagent/env/bin/python'
    kbagent_root: str = '/home/nitin/kbagent'
    manim_python: str = '/home/nitin/remotion/.venv-manim-pilot/bin/python'
    segment_python: str = '/home/nitin/remotion/artifacts/experiments/circular-image-mggen-manim/.venv/bin/python'
    sam_weights: str = '/home/nitin/remotion/artifacts/experiments/circular-image-mggen-manim/vendor/MG-GEN/weights/sam2_b.pt'
    python_base: str = '/home/nitin/.pyenv/versions/3.11.9'
    ncert_root: str = '/home/nitin/story_generator/ncert_downloader/ncert_official_books/English'
    # Budgets
    image_attempts: int = 3
    code_attempts: int = 4
    luna_after_attempts: int = 2   # local coding attempts before the paid model is allowed
    model_timeout: int = 600
    render_timeout: int = 900
    job_timeout: int = 4 * 3600
    width: int = 1280
    height: int = 720
    fps: int = 30

    @classmethod
    def from_env(cls):
        value = cls()
        for f in fields(value):
            raw = os.environ.get('SCIVID_' + f.name.upper())
            if raw is not None:
                setattr(value, f.name, type(getattr(value, f.name))(raw))
        return value

    def public(self):
        return asdict(self)
