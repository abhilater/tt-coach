"""Versioned prompt templates."""

from app.llm.schemas import PROMPT_VERSION


def system_analyst() -> str:
    return (
        "You are an expert table tennis coach assistant. "
        "Given video metadata and transcript snippets, extract structured coaching insights. "
        "Respond ONLY with valid JSON matching the requested schema. No markdown."
    )


def user_analyst(title: str, description: str, transcript_excerpt: str) -> str:
    return (
        f"Video title: {title}\n\nDescription snippet:\n{description[:2000]}\n\n"
        f"Transcript excerpt:\n{transcript_excerpt[:12000]}\n\n"
        "Produce JSON fields: summary, drills (array of {name, steps, reps_or_duration}), "
        "coaching_tips (array of strings), try_next_session (string), "
        "key_mistakes_addressed (array), skill_tags (array), chapters (array of {title, start_hint}), "
        "quality_score (0-1 float)."
    )


def prompt_meta() -> str:
    return PROMPT_VERSION
