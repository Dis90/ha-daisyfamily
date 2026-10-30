"""Small async client for the Daisy Family parent web API.

The endpoints were taken from a browser session (HAR) against the Daisy
Family web app. The API is not publicly documented and may change.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from datetime import date
from typing import Any

import aiohttp

from .const import TOKEN_MAX_AGE_SECONDS

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class DaisyFamilyError(Exception):
    """Base error."""


class DaisyFamilyConnectionError(DaisyFamilyError):
    """The service could not be reached or returned an unexpected response."""


class DaisyFamilyAuthError(DaisyFamilyError):
    """Username or password was rejected."""


class DaisyFamilyClient:
    """Client for a single Daisy Family municipality site."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        username: str,
        password: str,
    ) -> None:
        self._session = session
        self._base = f"https://{host}"
        self._username = username
        self._password = password
        self._token: str | None = None
        self._token_time = 0.0
        self.login_count = 0
        self.person_id: str | None = None
        self.user_name: str | None = None

    # ------------------------------------------------------------------ auth
    async def async_login(self) -> None:
        """Log in and store the bearer token."""
        try:
            async with self._session.post(
                f"{self._base}/api/auth/login",
                json={"Username": self._username, "Password": self._password},
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status in (401, 403):
                    raise DaisyFamilyAuthError("Login rejected")
                if resp.status != 200:
                    raise DaisyFamilyConnectionError(
                        f"Login returned HTTP {resp.status}"
                    )
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise DaisyFamilyConnectionError(str(err)) from err

        if not isinstance(data, dict) or not data.get("Success") or not data.get(
            "Token"
        ):
            raise DaisyFamilyAuthError(
                f"Login failed (code {data.get('ErrorCode') if isinstance(data, dict) else '?'})"
            )
        self._token = data["Token"]
        self._token_time = time.monotonic()
        self.login_count += 1
        self.person_id = data.get("PersonID")
        self.user_name = data.get("UserName")

    async def _ensure_token(self) -> None:
        if (
            self._token is None
            or time.monotonic() - self._token_time > TOKEN_MAX_AGE_SECONDS
        ):
            await self.async_login()

    async def _request(
        self, method: str, path: str, *, json_body: Any | None = None
    ) -> Any:
        """Send an authenticated request, logging in again once on 401."""
        for attempt in (1, 2):
            await self._ensure_token()
            try:
                async with self._session.request(
                    method,
                    f"{self._base}{path}",
                    json=json_body,
                    headers={"Authorization": f"Bearer {self._token}"},
                    timeout=REQUEST_TIMEOUT,
                ) as resp:
                    if resp.status in (401, 403) and attempt == 1:
                        self._token = None
                        continue
                    if resp.status in (401, 403):
                        raise DaisyFamilyAuthError("Request not authorised")
                    if resp.status != 200:
                        raise DaisyFamilyConnectionError(
                            f"{path} returned HTTP {resp.status}"
                        )
                    return await resp.json(content_type=None)
            except (aiohttp.ClientError, TimeoutError) as err:
                raise DaisyFamilyConnectionError(f"{path}: {err}") from err
        raise DaisyFamilyConnectionError(f"{path}: no response")  # pragma: no cover

    # ------------------------------------------------------------------ data
    async def async_get_children(self) -> dict[str, Any]:
        return await self._request("GET", "/api/persons/getchildren/")

    async def async_get_nursing_times(self, start: date, end: date) -> dict[str, Any]:
        """Reservations (NursingTimes) and actual events (Statuses) per day."""
        path = (
            f"/api/nursingtimes/getnursingtimes/{date.today().month:02d}/"
            f"{start.isoformat()}/{end.isoformat()}"
        )
        return await self._request("GET", path)

    async def async_get_messages(self) -> dict[str, Any]:
        return await self._request("POST", "/api/Messages/MessageData/", json_body={})

    async def async_get_bulletins(self) -> list[dict[str, Any]]:
        """Bulletin board (ilmoitustaulu) posts for the parent."""
        return await self._request("GET", "/api/bulletinboards?type=parent")

    async def async_get_main_stats(self) -> dict[str, Any]:
        """Start page status: unread counts, missing care time notices."""
        return await self._request(
            "POST", "/api/persons/getmainstats2", json_body={"PersonID": self.person_id}
        )

    async def async_get_vacation_status(self) -> dict[str, Any]:
        """Notice about missing reservations for holiday periods."""
        return await self._request("GET", "/api/nursingtimes/vacationstatus")

    async def async_get_profile_pictures(self) -> list[dict[str, Any]]:
        """Profile pictures of the children (base64), `ImageBase64` is null if none."""
        return await self._request("GET", "/api/image/getprofilepictures/")

    async def async_get_centre_infos(self) -> list[dict[str, Any]]:
        """Daycare centres of the children: contact details, opening hours, groups."""
        return await self._request("GET", "/api/centre/getcentreinfos")

    async def async_get_calendar(self, start: date, end: date) -> dict[str, Any]:
        """Holiday periods (`VacationPeriodList`) and public holidays (`HolidayList`)."""
        return await self._request(
            "GET",
            f"/api/nursingtimes/getnursingtimesquick/{start.isoformat()}/{end.isoformat()}",
        )

    async def async_get_attachment(
        self, attachment_id: str, mime_type: str
    ) -> tuple[bytes, str]:
        """Download a message attachment; returns (content, content type).

        The service answers `POST /api/files/previewFile` with a data URI
        ("data:<mime>;base64,<data>"), normally as a JSON string. The response
        is read as text so that a plain data URI or a raw base64 body also work.
        """
        path = "/api/files/previewFile"
        body = {
            "FileId": attachment_id,
            "FileType": "ATTACHMENT",
            "FileMimeType": mime_type,
        }
        text = ""
        ctype = ""
        for attempt in (1, 2):
            await self._ensure_token()
            try:
                async with self._session.post(
                    f"{self._base}{path}",
                    json=body,
                    headers={"Authorization": f"Bearer {self._token}"},
                    timeout=REQUEST_TIMEOUT,
                ) as resp:
                    if resp.status in (401, 403) and attempt == 1:
                        self._token = None
                        continue
                    if resp.status != 200:
                        raise DaisyFamilyConnectionError(
                            f"{path} returned HTTP {resp.status}"
                        )
                    ctype = resp.headers.get("Content-Type", "")
                    text = (await resp.text()).strip()
                    break
            except (aiohttp.ClientError, TimeoutError) as err:
                raise DaisyFamilyConnectionError(f"{path}: {err}") from err

        if text.startswith('"'):
            try:
                text = json.loads(text)
            except ValueError as err:
                raise DaisyFamilyConnectionError(
                    f"{path}: invalid JSON string ({err})"
                ) from err
        if not isinstance(text, str) or not text:
            raise DaisyFamilyConnectionError(f"{path}: empty response ({ctype})")

        if text.startswith("data:") and "," in text:
            head, encoded = text.split(",", 1)
            content_type = head.removeprefix("data:").split(";")[0] or mime_type
        else:
            head, encoded, content_type = "", text, mime_type
        try:
            return base64.b64decode(encoded, validate=True), content_type
        except ValueError as err:
            # Not base64: report what came back (start only, no secrets expected).
            snippet = text[:60].replace("\n", " ")
            raise DaisyFamilyConnectionError(
                f"{path}: unexpected response ({ctype}, starts with {snippet!r})"
            ) from err

    async def async_set_thread_read(self, thread_id: str) -> None:
        """Mark a message thread as read (`POST /api/messages/setthreadread/`)."""
        path = "/api/messages/setthreadread/"
        for attempt in (1, 2):
            await self._ensure_token()
            try:
                async with self._session.post(
                    f"{self._base}{path}",
                    json={"Data": thread_id},
                    headers={"Authorization": f"Bearer {self._token}"},
                    timeout=REQUEST_TIMEOUT,
                ) as resp:
                    if resp.status in (401, 403) and attempt == 1:
                        self._token = None
                        continue
                    if resp.status != 200:
                        raise DaisyFamilyConnectionError(
                            f"{path} returned HTTP {resp.status}"
                        )
                    return  # response body is not needed
            except (aiohttp.ClientError, TimeoutError) as err:
                raise DaisyFamilyConnectionError(f"{path}: {err}") from err

    async def async_get_message_thread(self, thread_id: str) -> dict[str, Any]:
        """Full thread incl. message texts (`POST /api/Messages/GetMessageThread2`)."""
        return await self._request(
            "POST",
            "/api/Messages/GetMessageThread2",
            json_body={"ThreadId": thread_id, "MessageId": "", "HideRecipients": True},
        )
