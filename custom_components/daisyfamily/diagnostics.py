"""Diagnostics download for Daisy Family (credentials and personal data redacted)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .coordinator import DaisyConfigEntry

TO_REDACT = {"username", "password", "token", "host", "user_name"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: DaisyConfigEntry
) -> dict[str, Any]:
    c = entry.runtime_data
    data = c.data or {}
    children = data.get("children") or {}
    messages = data.get("messages") or {}
    bulletins = data.get("bulletins") or {}
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "update": {
            "interval": str(c.update_interval),
            "last_update_success": c.last_update_success,
            "last_success": c.diag_last_success,
            "last_attempt": c.diag_last_attempt,
            "last_error": c.diag_last_error,
            "consecutive_failures": c.diag_failures,
            "duration_s": c.diag_duration,
            "failed_parts": c.diag_failed_parts,
            "logins": c.client.login_count,
        },
        "counts": {
            "children": len(children),
            "message_threads": len(messages.get("all") or []),
            "bulletins": len(bulletins.get("posts") or []),
            "reservation_days": {
                cid: len(ch.get("reservations") or []) for cid, ch in children.items()
            },
        },
    }
