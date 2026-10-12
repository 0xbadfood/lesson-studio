from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class VideoRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    topic: str = Field(min_length=3, max_length=1000)
    audience: str = Field(default='High-school students', min_length=3, max_length=200)
    duration_seconds: int = Field(default=90, ge=20, le=180)
    quality: Literal['preview', 'hd'] = 'hd'
    instructions: str = Field(default='', max_length=1500)

    @field_validator('topic', 'audience', 'instructions', mode='before')
    @classmethod
    def clean(cls, value):
        return value.strip() if isinstance(value, str) else value


class Calculation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    label: str
    expression: str = Field(max_length=300)
    expected: float = Field(allow_inf_nan=False)
    tolerance: float = Field(default=0.000001, ge=0, le=1, allow_inf_nan=False)
    source_ids: list[str] = Field(min_length=1)


class SceneSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^s[0-9]{2}$')
    title: str = Field(min_length=1, max_length=90)
    goal: str = Field(min_length=10, max_length=600)
    visual: str = Field(min_length=10, max_length=1600)
    motion: list[str] = Field(min_length=1, max_length=8)
    caption: str = Field(min_length=1, max_length=160)
    duration_seconds: float = Field(ge=6, le=40)
    source_ids: list[str] = Field(min_length=1)
    calculations: list[Calculation] = Field(default_factory=list, max_length=8)
    complexity: Optional[Literal['routine', 'involved', 'novel']] = None   # set by a tiering planner


class Storyboard(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str
    assumptions: list[str]
    scenes: list[SceneSpec] = Field(min_length=2, max_length=7)
