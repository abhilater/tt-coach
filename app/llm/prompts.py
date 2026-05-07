"""Versioned prompt templates."""

from __future__ import annotations

from app.llm.schemas import PROMPT_VERSION
from app.models import UserProfile


def system_analyst() -> str:
    return (
        "You are an expert table tennis coach assistant. "
        "Given video metadata and transcript snippets, extract structured coaching insights. "
        "Respond ONLY with valid JSON matching the requested schema. No markdown."
    )


def _join_or_dash(items: list | None) -> str:
    if not items:
        return "-"
    return ", ".join(str(x).strip() for x in items if str(x).strip()) or "-"


def format_player_profile(profile: UserProfile | None) -> str:
    """Render a compact player-profile block for the analyst prompt.

    Returns an empty string if no profile is available so the prompt collapses
    cleanly. The block is used solely to *frame* and *prioritize* insights;
    it is never used to filter videos or to influence ranking weights.
    """
    if profile is None:
        return ""
    level = (profile.level or "").strip() or "-"
    play_style = (profile.play_style or "").strip() or "-"
    goals = _join_or_dash(profile.goals)
    weaknesses = _join_or_dash(profile.weaknesses)
    if level == "-" and play_style == "-" and goals == "-" and weaknesses == "-":
        return ""
    return (
        "Player profile:\n"
        f"- Skill level: {level}\n"
        f"- Play style: {play_style}\n"
        f"- Goals: {goals}\n"
        f"- Weaknesses to address: {weaknesses}"
    )


def user_analyst(
    title: str,
    description: str,
    transcript_excerpt: str,
    player_profile_block: str = "",
) -> str:
    profile_section = ""
    if player_profile_block:
        profile_section = (
            f"\n\n{player_profile_block}\n\n"
            "Use the player profile only to (a) emphasize coaching tips and "
            "key_mistakes_addressed most relevant to their weaknesses, and "
            "(b) frame `summary` and `try_next_session` toward their stated goals "
            "and skill level. Do NOT invent content not supported by the transcript "
            "or description."
        )
    return (
        f"Video title: {title}\n\nDescription snippet:\n{description[:2000]}\n\n"
        f"Transcript excerpt:\n{transcript_excerpt[:12000]}"
        f"{profile_section}\n\n"
        "Produce JSON fields: summary, drills (array of {name, steps, reps_or_duration}), "
        "coaching_tips (array of strings), try_next_session (string), "
        "key_mistakes_addressed (array), skill_tags (array), chapters (array of {title, start_hint}), "
        "quality_score (0-1 float)."
    )


def prompt_meta() -> str:
    return PROMPT_VERSION
