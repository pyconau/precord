"""Web handling bits."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING, NewType
from urllib.parse import quote_plus

import httpx
import jwt
import svcs
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, PackageLoader, Template, select_autoescape
from pydantic import SerializationInfo, ValidationInfo, field_serializer, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from svcs.fastapi import DepContainer  # noqa: TCH002

from . import database, values

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from typing import Any


class Settings(BaseSettings):
    """Settings that will come from the environment."""

    model_config = SettingsConfigDict(env_prefix="precord_")

    discord_client_id: str
    discord_client_secret: str
    discord_bot_token: str
    discord_guild_id: str
    discord_welcome_channel_id: str
    discord_redirect_uri: str

    pretix_api_token: str
    pretix_jwt_public_key: str

    state_token_lifetime: timedelta = timedelta(minutes=1800)

    @field_serializer("state_token_lifetime")
    def serialize_state_token_lifetime(
        self,
        state_token_lifetime: timedelta,
        _info: SerializationInfo,
    ) -> int:
        """Serialise the state token lifetime as an integer value representing seconds."""
        return int(state_token_lifetime.total_seconds())

    @field_validator("state_token_lifetime")
    @classmethod
    def validate_state_token_lifetime(cls, value: Any, _info: ValidationInfo) -> timedelta:
        """Parse the input value as an integer and convert that to a timedelta."""
        if isinstance(value, timedelta):
            return value
        return timedelta(seconds=int(value))


STATE_TOKEN_LIFETIME = timedelta(minutes=30)
DISCORD_AUTHORIZE_FORMAT = "https://discord.com/oauth2/authorize?client_id={client_id}&state={state_token}&redirect_uri={redirect_uri}&response_type=code&scope=identify+guilds.join"
DISCORD_API_BASE_URI = "https://discord.com/api/v10"
DISCORD_TOKEN_URI = f"{DISCORD_API_BASE_URI}/oauth2/token"
DISCORD_CURRENT_USER_URI = f"{DISCORD_API_BASE_URI}/users/@me"

ErrorTemplate = NewType("ErrorTemplate", Template)


@svcs.fastapi.lifespan
async def lifespan(
    _app: FastAPI,
    registry: svcs.Registry,
) -> AsyncGenerator[dict[str, Any], None]:
    """Set up all our services for later use."""
    registry.register_factory(Settings, lambda: Settings())  # type: ignore[call-arg]
    registry.register_factory(httpx.AsyncClient, lambda: httpx.AsyncClient())

    await database.database_setup(registry)

    registry.register_factory(
        Environment,
        lambda: Environment(loader=PackageLoader("precord"), autoescape=select_autoescape()),
    )

    def get_error_template(container: svcs.Container) -> Template:
        env = container.get(Environment)
        return env.get_template("error.html")

    registry.register_factory(ErrorTemplate, get_error_template)

    yield {"registry": registry}


app = FastAPI(lifespan=lifespan)
logger = logging.getLogger(__name__)


@app.exception_handler(404)
async def custom_404_handler(request: Request, _exc: HTTPException) -> HTMLResponse:
    """Handle 404 (Not Found) errors."""
    with svcs.Container(request.state.registry) as services:
        error_template = await services.aget(ErrorTemplate)
        return HTMLResponse(
            error_template.render(),
            status_code=HTTPStatus.NOT_FOUND,
        )


@app.exception_handler(500)
async def custom_500_handler(request: Request, _exc: HTTPException) -> HTMLResponse:
    """Handle 500 (Internal Server Error) errors."""
    with svcs.Container(request.state.registry) as services:
        error_template = await services.aget(ErrorTemplate)
        return HTMLResponse(
            error_template.render(message="An internal error occurred"),
            status_code=HTTPStatus.BAD_REQUEST,
        )


@app.get("/join", response_model=None)
async def join(
    services: DepContainer,
    token: str | None = None,
) -> RedirectResponse | HTMLResponse:
    """Handle an initial request using the URI provided by Pretix.

    Pretix gives us a JWT. We verify that this JWT was signed by the private key
    we gave Pretix. If it is, we get the order code out of it and ensure that both
    it and the "position" that Pretix generated the code for are valid.

    Once we've finished validating the request we use the Pretix item code along with
    answers given to a bunch of questions asked during the order process to determine
    a server nickname and an initial role set. These are stored, along with a generated
    state token, in the database. The user is then redirected into Discord's OAuth2
    flow.
    """
    settings, client, error_template, select_active, insert_pending = await services.aget(
        Settings,
        httpx.AsyncClient,
        ErrorTemplate,
        database.SelectActive,
        database.InsertPending,
    )

    if not token:
        return HTMLResponse(
            error_template.render(message="Missing ticket information"),
            status_code=HTTPStatus.BAD_REQUEST,
        )

    try:
        payload = jwt.decode(token, settings.pretix_jwt_public_key, algorithms=["RS256"])
    except jwt.exceptions.DecodeError:
        return HTMLResponse(
            error_template.render(message="Invalid ticket information"),
            status_code=HTTPStatus.BAD_REQUEST,
        )

    response = await client.get(
        f"https://pretix.eu/api/v1/organizers/pyconau/events/2024/orders/{payload['order']}/",
        params={"include_canceled_positions": "true"},
        headers={"authorization": f"Token {settings.pretix_api_token}"},
    )
    if response.status_code != HTTPStatus.OK:
        return HTMLResponse(
            error_template.render(message="Failed to retrieve ticket information"),
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        )

    order = response.json()
    position = next(
        pos for pos in order["positions"] if pos["positionid"] == int(payload["position"])
    )
    if order["status"] != "p" or position["canceled"]:
        return HTMLResponse(
            error_template.render(message="Ticket is not valid"),
            status_code=HTTPStatus.UNAUTHORIZED,
        )

    row = await select_active.fetchrow(payload["order"], int(payload["position"]))
    if row is not None:
        return RedirectResponse(
            f"https://discord.com/channels/{settings.discord_guild_id}/{settings.discord_welcome_channel_id}",
            status_code=HTTPStatus.FOUND,
        )

    items = {position["item"] for position in order["positions"] if not position["canceled"]}
    answers = {a["question_identifier"]: a["answer"] for a in position["answers"]}
    nickname = values.generate_nickname(answers)
    roles = values.generate_role_list(items, answers)

    state_token = values.generate_state_token()
    await insert_pending.executemany(
        [
            (
                payload["order"],
                int(payload["position"]),
                state_token,
                datetime.now(tz=UTC),
                nickname,
                roles,
            ),
        ],
    )

    return RedirectResponse(
        DISCORD_AUTHORIZE_FORMAT.format(
            client_id=settings.discord_client_id,
            state_token=state_token,
            redirect_uri=quote_plus(settings.discord_redirect_uri),
        ),
        status_code=HTTPStatus.FOUND,
    )


@app.get("/redirect", response_model=None)
async def redirect(
    services: DepContainer,
    code: str,
    state: str,
) -> RedirectResponse | HTMLResponse:
    """Handle the request as it returns from the Discord OAuth2 flow.

    We first check the state token to make sure we have information for it and that
    that information isn't unacceptably old. If the state is acceptable we delete the
    database record so it can't be reused.

    We then use the token given to us by Discord to get an access token for the user.
    We use this token to get the Discord user record for this user and thus their
    Discord user ID. This then allows us to add the user to our Discord server ("guild")
    with the nickname and roles we worked out earlier.

    Lastly the user is redirected to the Discord web app and the #welcome channel in
    our server.
    """
    settings, client, select_pending, delete_pending, insert_active, error_template = (
        await services.aget(
            Settings,
            httpx.AsyncClient,
            database.SelectPendingByStateToken,
            database.DeletePending,
            database.InsertActive,
            ErrorTemplate,
        )
    )

    row = await select_pending.fetchrow(state)
    if row is None:
        return HTMLResponse(
            error_template.render(message="Registration is in invalid state"),
            status_code=HTTPStatus.BAD_REQUEST,
        )

    await delete_pending.executemany([(row["order_code"], row["position"])])

    if datetime.now(tz=UTC) - row["created"] > STATE_TOKEN_LIFETIME:
        return HTMLResponse(
            error_template.render(message="Registration has expired"),
            status_code=HTTPStatus.BAD_REQUEST,
        )

    response = await client.post(
        DISCORD_TOKEN_URI,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.discord_redirect_uri,
        },
        headers={"content-type": "application/x-www-form-urlencoded"},
        auth=(settings.discord_client_id, settings.discord_client_secret),
    )
    response.raise_for_status()
    token = response.json()

    response = await client.get(
        DISCORD_CURRENT_USER_URI,
        headers={"authorization": f"{token['token_type']} {token['access_token']}"},
    )
    response.raise_for_status()
    user = response.json()

    await insert_active.executemany(
        [
            (
                row["order_code"],
                row["position"],
                str(user["id"]),
                row["created"],
                row["nickname"],
                row["roles"],
            ),
        ],
    )

    parameters = {
        "access_token": token["access_token"],
    }
    if row["nickname"] is not None:
        parameters["nick"] = row["nickname"]
    if row["roles"]:
        parameters["roles"] = row["roles"]

    response = await client.put(
        f"{DISCORD_API_BASE_URI}/guilds/{settings.discord_guild_id}/members/{user['id']}",
        headers={"authorization": f"Bot {settings.discord_bot_token}"},
        json=parameters,
    )
    if response.status_code not in (
        HTTPStatus.OK,
        HTTPStatus.CREATED,
        HTTPStatus.NO_CONTENT,
    ):
        return HTMLResponse(
            error_template.render(message="Discord registration request failed"),
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        )

    return RedirectResponse(
        f"https://discord.com/channels/{settings.discord_guild_id}/{settings.discord_welcome_channel_id}",
        status_code=HTTPStatus.FOUND,
    )
