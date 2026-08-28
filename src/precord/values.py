"""Routines for generating values."""

from __future__ import annotations

import logging
import secrets
import string
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

logger = logging.getLogger(__name__)

STATE_TOKEN_CHARACTERS = string.ascii_letters + string.digits + ".,-:"

ROLE_IDS = {
    "volunteer": 1534168020786614374,
    "core": 1534168020786614375,
    "av": 1534168020786614373,
    "specialist": 1534168020786614372,
    "education": 1534168020778352824,
    "dataai": 1535535424229875844,
    "platformeng": 1535535634750640199,
    "cybersecurity": 1535535725163061348,
    "devrel": 1535535987718099005,
    "rse": 1535536080617472010,
    "speaker": 1534168020778352830,
    "sprints": 1534168020778352823,
    "sponsor": 1534168020778352829,
}
ITEM_IDS = {
    "team_member": {1122991},
    "speaker": {826206},
    "sprints": {826222, 826210},
    "sponsor": {1102464, 826208},
}
TEAM_ROLES = {
    "Volunteer": [ROLE_IDS["volunteer"]],
    "Organiser": [ROLE_IDS["core"]],
    "AV Team": [ROLE_IDS["av"]],
    "Track Organiser": [ROLE_IDS["specialist"]],
    "Education": [ROLE_IDS["specialist"], ROLE_IDS["education"]],
    "Data & AI": [ROLE_IDS["specialist"], ROLE_IDS["dataai"]],
    "Platform Engineering": [ROLE_IDS["specialist"], ROLE_IDS["platformeng"]],
    "Cybersecurity": [ROLE_IDS["specialist"], ROLE_IDS["cybersecurity"]],
    "Developer Relations": [ROLE_IDS["specialist"], ROLE_IDS["devrel"]],
    "Research Software Engineering": [ROLE_IDS["specialist"], ROLE_IDS["rse"]],
}


def generate_state_token() -> str:
    """Generate a random token we use to match up requests."""
    return "".join(secrets.choice(STATE_TOKEN_CHARACTERS) for _ in range(23))


def generate_nickname(answers: dict[str, Any]) -> str | None:
    """Generate the nickname to use on the server based on answers in the order."""
    if "primary_name" not in answers:
        return None
    if answers.get("east_asian_name_order") == "True":
        return f"{answers.get('additional_names', '')} {answers['primary_name']}"
    return f"{answers['primary_name']} {answers.get('additional_names', '')}"


def generate_role_list(items: set[int], answers: dict[str, Any]) -> list[int]:
    """Generate the initial role list based on answers in the order."""
    roles: set[int] = set()

    for item in items:
        if item in ITEM_IDS["team_member"]:
            team = answers.get("team")
            if team in TEAM_ROLES:
                roles.update(TEAM_ROLES[team])
            else:
                logger.warning("Item %s has no roles for team answer %r", item, team)
        if item in ITEM_IDS["speaker"]:
            roles.add(ROLE_IDS["speaker"])
        if item in ITEM_IDS["sprints"]:
            roles.add(ROLE_IDS["sprints"])
        if item in ITEM_IDS["sponsor"]:
            roles.add(ROLE_IDS["sponsor"])

    return list(roles)
