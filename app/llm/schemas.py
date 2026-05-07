from pydantic import BaseModel, Field

PROMPT_VERSION = "v2"


class DrillItem(BaseModel):
    name: str = Field(description="Short drill name")
    steps: list[str] = Field(description="Ordered steps")
    reps_or_duration: str | None = Field(None, description="Suggested reps or duration")


class ChapterItem(BaseModel):
    title: str
    start_hint: str | None = Field(None, description="Approximate start phrase or topic")


class VideoInsights(BaseModel):
    summary: str = Field(description="Concise coaching summary")
    drills: list[DrillItem] = Field(default_factory=list)
    coaching_tips: list[str] = Field(default_factory=list)
    try_next_session: str = Field(description="One actionable practice focus")
    key_mistakes_addressed: list[str] = Field(default_factory=list)
    skill_tags: list[str] = Field(default_factory=list)
    chapters: list[ChapterItem] = Field(default_factory=list)
    quality_score: float = Field(ge=0.0, le=1.0, description="Estimated instructional quality")
