"""Keyword / topic hints for rule-based tagging."""

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "serve": ["serve", "service", "toss", "pendulum"],
    "receive": ["receive", "return of serve", "short receive"],
    "footwork": ["footwork", "movement", "sidestep", "recovery"],
    "forehand_loop": ["forehand loop", "fh loop", "topspin forehand"],
    "backhand": ["backhand", "bh loop", "backhand topspin"],
    "blocking": ["block", "blocking"],
    "short_game": ["short game", "touch", "drop shot"],
    "strategy": ["strategy", "tactics", "placement"],
}


def infer_topics_from_text(text: str) -> list[str]:
    low = text.lower()
    found: list[str] = []
    for topic, kws in TOPIC_KEYWORDS.items():
        if any(k in low for k in kws):
            found.append(topic)
    return found
