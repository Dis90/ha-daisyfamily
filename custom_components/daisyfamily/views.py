"""HTTP view that streams message attachments from Daisy Family."""

from __future__ import annotations

import logging
import re
from urllib.parse import quote

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

try:  # Home Assistant 2024.x and later
    from homeassistant.components.http import KEY_HASS
except ImportError:  # pragma: no cover
    KEY_HASS = "hass"

from .api import DaisyFamilyError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_ID = re.compile(r"^[0-9A-Za-z\-]{8,64}$")


class DaisyAttachmentView(HomeAssistantView):
    """GET /api/daisyfamily/attachment/{attachment_id}?name=file.pdf&mime=application/pdf

    Requires a Home Assistant login. The dashboard card opens it with a signed
    path, so it also works as a plain link in a new browser tab.
    """

    url = "/api/daisyfamily/attachment/{attachment_id}"
    name = "api:daisyfamily:attachment"
    requires_auth = True

    async def get(self, request: web.Request, attachment_id: str) -> web.Response:
        if not _ID.match(attachment_id):
            return web.Response(status=400, text="Invalid attachment id")
        hass = request.app[KEY_HASS]
        last_error: Exception | None = None
        for entry in hass.config_entries.async_entries(DOMAIN):
            coordinator = getattr(entry, "runtime_data", None)
            if coordinator is None:
                continue
            try:
                body, content_type = await coordinator.client.async_get_attachment(
                    attachment_id,
                    request.query.get("mime", "application/octet-stream"),
                )
            except DaisyFamilyError as err:
                last_error = err
                continue
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("Attachment %s download failed", attachment_id)
                last_error = err
                continue
            name = re.sub(r'[\r\n"\\]', "", request.query.get("name", "liite"))
            ascii_name = name.encode("ascii", "replace").decode().replace("?", "_")
            return web.Response(
                body=body,
                content_type=content_type.split(";")[0],
                headers={
                    "Content-Disposition": (
                        f'inline; filename="{ascii_name}"; '
                        f"filename*=UTF-8''{quote(name)}"
                    ),
                    "X-Content-Type-Options": "nosniff",
                },
            )
        _LOGGER.warning(
            "Attachment %s (%s) could not be downloaded: %s",
            attachment_id,
            request.query.get("mime"),
            last_error,
        )
        return web.Response(
            status=502,
            text=f"Could not download the attachment from Daisy: {last_error or 'no connection'}",
        )
