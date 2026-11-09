"""The Daisy Family integration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

import re

import voluptuous as vol
from homeassistant.core import ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .api import DaisyFamilyClient, DaisyFamilyError
from .views import DaisyAttachmentView
from .const import DOMAIN
from .coordinator import DaisyConfigEntry, DaisyFamilyCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.IMAGE]

CARD_FILES = (
    "daisyfamily-calendar-card.js",
    "daisyfamily-messages-card.js",
    "daisyfamily-bulletins-card.js",
)
CARD_VERSION = "1.0.1"
CARD_FLAG = "daisyfamily_card_registered"
SERVICE_MARK_READ = "mark_thread_read"
_THREAD_ID = re.compile(r"^[0-9A-Za-z\-]{8,64}$")


async def _async_mark_thread_read(hass: HomeAssistant, call: ServiceCall) -> None:
    """Mark a message thread as read in Daisy and refresh the data."""
    thread_id = call.data["thread_id"]
    done = False
    last_error: Exception | None = None
    for entry in hass.config_entries.async_entries(DOMAIN):
        coordinator = getattr(entry, "runtime_data", None)
        if coordinator is None:
            continue
        try:
            await coordinator.client.async_set_thread_read(thread_id)
        except DaisyFamilyError as err:
            last_error = err
            continue
        done = True
        await coordinator.async_request_refresh()
    if not done:
        raise HomeAssistantError(f"Could not mark the thread as read: {last_error}")



async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the dashboard cards and load them in every dashboard (once)."""
    if hass.data.get(CARD_FLAG):
        return
    hass.data[CARD_FLAG] = True
    configs = []
    for name in CARD_FILES:
        path = Path(__file__).parent / "www" / name
        configs.append(
            StaticPathConfig(f"/daisyfamily_static/{name}", str(path), False)
        )
    await hass.http.async_register_static_paths(configs)
    hass.http.register_view(DaisyAttachmentView())
    for name in CARD_FILES:
        add_extra_js_url(hass, f"/daisyfamily_static/{name}?v={CARD_VERSION}")


async def async_setup_entry(hass: HomeAssistant, entry: DaisyConfigEntry) -> bool:
    """Set up Daisy Family from a config entry."""
    # Own session so that the login cookies stay private to this entry.
    session = async_create_clientsession(hass)
    client = DaisyFamilyClient(
        session,
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    coordinator = DaisyFamilyCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    if not hass.services.has_service(DOMAIN, SERVICE_MARK_READ):

        async def _handle_mark_read(call: ServiceCall) -> None:
            await _async_mark_thread_read(hass, call)

        hass.services.async_register(
            DOMAIN,
            SERVICE_MARK_READ,
            _handle_mark_read,
            schema=vol.Schema({vol.Required("thread_id"): vol.All(str, vol.Match(_THREAD_ID))}),
        )
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await _async_register_card(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DaisyConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(hass: HomeAssistant, entry: DaisyConfigEntry) -> None:
    """Reload so that changed options take effect."""
    await hass.config_entries.async_reload(entry.entry_id)
