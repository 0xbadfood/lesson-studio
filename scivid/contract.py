"""The lesson request contract shared by the portal, the API and the pipeline."""
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LessonRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    topic: str = Field(min_length=3, max_length=600, description='What to teach, or the question to solve')
    chapter: Optional[str] = Field(default=None, pattern=r'^[a-z]{4}[0-9]:[0-9]{2}$',
                                   description='NCERT chapter id, e.g. iesc1:06')
    web_research: bool = Field(default=False, description='Search the web for evidence')
    class_level: Optional[Union[Literal['open'], int]] = Field(
        default=None, description="Class 6-12, or 'open' for no level limit (full depth, up to undergraduate). "
                                  'Required when no chapter is given; with a chapter it overrides the chapter\'s class.')
    mode: Literal['explainer', 'solver'] = 'explainer'
    duration_seconds: int = Field(default=120, ge=45, le=360, description='Advisory length')
    voice: Literal['default', 'kane'] = 'default'
    notes: str = Field(default='', max_length=1500, description='Teacher notes for emphasis or examples')
    include_history: bool = Field(default=False, description='Add historical context where the planner finds it '
                                                             'fits (always shown as slides)')

    @field_validator('topic', 'notes', mode='before')
    @classmethod
    def strip(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode='after')
    def grounded(self):
        # School-level lessons must be grounded; with no level limit a frontier planner may teach from its own
        # knowledge (standard concepts need no research at that depth).
        if not self.chapter and not self.web_research and self.class_level != 'open':
            raise ValueError('Choose a textbook chapter, turn on web research, or both: every school-level lesson '
                             "needs a source. Lessons with no level limit may skip sources.")
        if isinstance(self.class_level, int) and not 6 <= self.class_level <= 12:
            raise ValueError("Class level must be 6 to 12, or 'open' for no level limit.")
        if not self.chapter and self.class_level is None:
            raise ValueError("Without a chapter, give the class level (6-12, or 'open' for no limit) so the lesson is pitched correctly.")
        return self


STAGES = ['scope', 'evidence', 'plan', 'script', 'narration', 'visuals', 'render', 'assemble', 'done']
STAGE_LABELS = {'scope': 'Understanding the request', 'evidence': 'Gathering sources', 'plan': 'Planning the lesson',
                'script': 'Writing the narration', 'narration': 'Recording the voice', 'visuals': 'Creating visuals',
                'render': 'Animating chapters', 'assemble': 'Assembling the video', 'done': 'Ready'}
