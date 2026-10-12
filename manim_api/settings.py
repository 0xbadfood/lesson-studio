from dataclasses import asdict, dataclass
import os
from pathlib import Path
import shlex

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Settings:
    data_root: str = str(ROOT / 'api-data')
    qwen_url: str = 'http://10.8.0.5:8001/v1'
    coding_provider: str = 'luna'
    luna_url: str = 'https://api.openai.com/v1'
    luna_model: str = 'gpt-6-luna'
    luna_reasoning_effort: str = 'high'
    luna_code_max_output_tokens: int = 24000
    luna_patch_max_output_tokens: int = 16000
    remotion_root: str = '/home/nitin/remotion'
    research_python: str = '/home/nitin/kbagent/env/bin/python'
    kbagent_root: str = '/home/nitin/kbagent'
    manim_python: str = '/home/nitin/remotion/.venv-manim-pilot/bin/python'
    python_base: str = '/home/nitin/.pyenv/versions/3.11.9'
    max_attempts: int = 5
    qwen_code_max_tokens: int = 10000
    # Per-role hosted models (OpenRouter ids; empty = the default Qwen/Luna behaviour). Key: OPENROUTER_API_KEY.
    openrouter_url: str = 'https://openrouter.ai/api/v1'
    planner_model: str = ''
    coder_routine_model: str = ''
    coder_hard_model: str = ''
    code_thinking: int = 3072
    content_thinking: int = 2048
    layout_thinking: int = 1024
    plan_thinking: int = 2048
    model_timeout: int = 480
    render_timeout: int = 600
    research_timeout: int = 1500
    job_timeout: int = 7200

    def __post_init__(self):
        if self.coding_provider not in ('qwen', 'luna'):
            raise ValueError('coding_provider must be qwen or luna')
        if self.luna_reasoning_effort not in ('none', 'low', 'medium', 'high', 'xhigh', 'max'):
            raise ValueError('Unsupported Luna reasoning effort')

    @classmethod
    def from_env(cls):
        result = cls()
        for field in asdict(result):
            value = os.environ.get('MANIM_' + field.upper())
            if value is not None:
                setattr(result, field, int(value) if isinstance(getattr(result, field), int) else value)
        result.qwen_url = os.environ.get('QWEN_BASE_URL', result.qwen_url).rstrip('/')
        result.luna_url = result.luna_url.rstrip('/')
        result.__post_init__()
        return result

    def public(self):
        return asdict(self)


def research_environment(settings):
    """Borrow the existing search credential, never source a shell env file."""
    env = dict(os.environ)
    if not env.get('TAVILY_API_KEY'):
        path = Path(settings.remotion_root) / '.service.env'
        if path.exists():
            for line in path.read_text().splitlines():
                if line.startswith('TAVILY_API_KEY='):
                    values = shlex.split(line.partition('=')[2])
                    if values:
                        env['TAVILY_API_KEY'] = values[0]
    return env
