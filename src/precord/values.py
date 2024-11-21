"""Routines for generating values."""

from __future__ import annotations

import secrets
import string
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

STATE_TOKEN_CHARACTERS = string.ascii_letters + string.digits + ".,-:"

ROLE_IDS = {
    "volunteer": 1307641013493305379,
    "core": 1307641013493305380,
    "av": 1307641013493305378,
    "specialist": 1307641013258420242,
    "education": 1307641013258420238,
    "scientific": 1307641013258420241,
    "devoops": 1307641013258420240,
    "speaker": 1307641013493305377,
    "sprints": 1307641013258420237,
    "sponsor": 1307641013493305376,
}
ITEM_IDS = {
    "team_member": {569202, 637767},
    "speaker": {569203, 637766},
    "sprints": {569209, 569215, 569216},
}
TEAM_ROLES = {
    "Volunteer Team": [ROLE_IDS["volunteer"]],
    "Core Team": [ROLE_IDS["core"]],
    "AV Team": [ROLE_IDS["av"]],
    "Education": [ROLE_IDS["specialist"], ROLE_IDS["education"]],
    "Scientific Python": [ROLE_IDS["specialist"], ROLE_IDS["scientific"]],
    "All Things Data": [ROLE_IDS["specialist"], ROLE_IDS["scientific"]],
    "DevOops": [ROLE_IDS["specialist"], ROLE_IDS["devoops"]],
}


def generate_state_token() -> str:
    """Generate a random token we use to match up requests."""
    return "".join(secrets.choice(STATE_TOKEN_CHARACTERS) for _ in range(23))


def generate_nickname(answers: dict[str, Any]) -> str | None:
    """Generate the nickname to use on the server based on answers in the order."""
    if "primary_name" not in answers:
        return None
    if answers["east_asian_name_order"] == "True":
        return f"{answers.get('additional_names', '')} {answers['primary_name']}"
    return f"{answers['primary_name']} {answers.get('additional_names', '')}"


def generate_role_list(items: set[int], answers: dict[str, Any]) -> list[int]:
    """Generate the initial role list based on answers in the order."""
    roles: set[int] = set()

    for item in items:
        if item in ITEM_IDS["team_member"]:
            roles.update(TEAM_ROLES[answers["team"]])
        if item in ITEM_IDS["speaker"]:
            roles.add(ROLE_IDS["speaker"])
        if item in ITEM_IDS["sprints"]:
            roles.add(ROLE_IDS["sprints"])

    if answers.get("sponsor", "") == "True":
        roles.add(ROLE_IDS["sponsor"])

    return list(roles)
