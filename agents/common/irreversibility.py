"""Statement the mission director must type, and how a second operator confirms."""

from __future__ import annotations

import re

_DASHES = str.maketrans({"—": "-", "–": "-", "−": "-"})
_VERSION = re.compile(r"\bv(\d+)\b", re.IGNORECASE)
_OPTION = re.compile(r"option\s+([abc])\b", re.IGNORECASE)


def normalise(text: str) -> str:
    collapsed = " ".join(text.translate(_DASHES).split())
    return collapsed.casefold()


def command_statement(option_key: str, pass_number: int) -> str:
    return (
        f"Authorized — Option {option_key}, firing on pass {pass_number}, "
        "I am taking command responsibility"
    )


def statement_matches(text: str, option_key: str, pass_number: int) -> bool:
    return normalise(text) == normalise(command_statement(option_key, pass_number))


def mentions_option(text: str, option_key: str) -> bool:
    found = _OPTION.search(text)
    return found is not None and found.group(1).upper() == option_key.upper()


def stated_version(text: str) -> int | None:
    found = _VERSION.search(text)
    if found is None:
        return None
    return int(found.group(1))


def is_confirmation(text: str, option_key: str) -> bool:
    folded = text.casefold()
    if "confirm" not in folded:
        return False
    return mentions_option(text, option_key)


def is_approval_attempt(text: str) -> bool:
    folded = text.casefold()
    tokens = (
        "authoriz",
        "authoris",
        "confirm",
        "taking command",
        "approve",
        "approved",
    )
    return any(token in folded for token in tokens)
