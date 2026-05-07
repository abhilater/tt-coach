"""Player profile is folded into the analyst prompt; ranking is unchanged."""

from __future__ import annotations

from app.llm.prompts import format_player_profile, user_analyst
from app.llm.schemas import PROMPT_VERSION
from app.models import UserProfile


def test_prompt_version_bumped_to_v2() -> None:
    assert PROMPT_VERSION == "v2"


def test_format_player_profile_renders_all_fields() -> None:
    p = UserProfile(
        id=1,
        level="intermediate",
        play_style="attacking looper",
        goals=["consistent forehand loop", "win local league"],
        weaknesses=["short backhand serves", "footwork to wide forehand"],
        preferred_languages=["en"],
        preferred_coaches=[],
    )
    block = format_player_profile(p)
    assert "Skill level: intermediate" in block
    assert "Play style: attacking looper" in block
    assert "consistent forehand loop, win local league" in block
    assert "short backhand serves, footwork to wide forehand" in block


def test_format_player_profile_handles_none_and_empty() -> None:
    assert format_player_profile(None) == ""
    empty = UserProfile(
        id=1,
        level=None,
        play_style=None,
        goals=[],
        weaknesses=[],
        preferred_languages=[],
        preferred_coaches=[],
    )
    assert format_player_profile(empty) == ""


def test_user_analyst_omits_profile_section_when_block_empty() -> None:
    out = user_analyst("Title", "desc", "transcript")
    assert "Player profile" not in out
    assert "Use the player profile" not in out


def test_user_analyst_includes_profile_section_when_block_present() -> None:
    block = format_player_profile(
        UserProfile(
            id=1,
            level="advanced",
            play_style="all-round",
            goals=["serve variation"],
            weaknesses=["backhand block"],
            preferred_languages=["en"],
            preferred_coaches=[],
        )
    )
    out = user_analyst("Title", "desc", "transcript", block)
    assert "Skill level: advanced" in out
    assert "Use the player profile" in out
    assert "key_mistakes_addressed" in out
