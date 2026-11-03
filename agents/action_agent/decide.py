"""Action-agent decisions that do not touch the database."""

from __future__ import annotations


def conflicting_keys(
    lines: list[dict[str, object]], queued_keys: set[str], *, persistence: bool
) -> list[str]:
    """With room memory off, a second proposal queues two unauthorised sequences."""
    if persistence:
        return []
    posts = [
        str(line.get("text", ""))
        for line in lines
        if str(line.get("text", "")).startswith("OPTIONS")
    ]
    if len(posts) < 2:
        return []
    return [key for key in ("B", "C") if key not in queued_keys]
