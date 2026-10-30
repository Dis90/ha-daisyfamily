"""Config flow for Daisy Family."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import (
    DaisyFamilyAuthError,
    DaisyFamilyClient,
    DaisyFamilyConnectionError,
)
from .const import (
    CONF_CARE_DAYS_BACK,
    DEFAULT_CARE_DAYS_BACK,
    MAX_CARE_DAYS_BACK,
    CONF_MAX_BULLETINS,
    DEFAULT_MAX_BULLETINS,
    MAX_BULLETINS_LIMIT,
    CONF_CARE_DAYS,
    DEFAULT_CARE_DAYS,
    MAX_CARE_DAYS,
    MIN_CARE_DAYS,
    CONF_MAX_MESSAGES,
    DEFAULT_HOST,
    DEFAULT_MAX_MESSAGES,
    DOMAIN,
    MAX_MESSAGES_LIMIT,
)

_LOGGER = logging.getLogger(__name__)


def normalize_host(value: str) -> str:
    """'https://Janakkala.daisyfamily.fi/login' or 'janakkala' -> host name."""
    host = re.sub(r"^https?://", "", value.strip().lower()).split("/")[0]
    if host and "." not in host:
        host = f"{host}.daisyfamily.fi"
    return host


class DaisyFamilyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return DaisyOptionsFlow()

    async def _async_try_login(self, host: str, username: str, password: str) -> str | None:
        """Return an error key, or None when the login works."""
        client = DaisyFamilyClient(
            async_create_clientsession(self.hass), host, username, password
        )
        try:
            await client.async_login()
        except DaisyFamilyAuthError:
            return "invalid_auth"
        except DaisyFamilyConnectionError:
            return "cannot_connect"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error during login")
            return "unknown"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = normalize_host(user_input[CONF_HOST])
            username = user_input[CONF_USERNAME].strip()
            error = await self._async_try_login(host, username, user_input[CONF_PASSWORD])
            if error is None:
                await self.async_set_unique_id(f"{host}_{username.lower()}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Daisy Family ({host})",
                    data={
                        CONF_HOST: host,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )
            errors["base"] = error

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST,
                    default=(user_input or {}).get(CONF_HOST, DEFAULT_HOST),
                ): str,
                vol.Required(
                    CONF_USERNAME, default=(user_input or {}).get(CONF_USERNAME, "")
                ): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self._async_try_login(
                entry.data[CONF_HOST], entry.data[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            if error is None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"username": entry.data[CONF_USERNAME]},
            errors=errors,
        )


def _box(minimum: int, maximum: int) -> NumberSelector:
    """A plain number input (not a slider)."""
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum, max=maximum, step=1, mode=NumberSelectorMode.BOX
        )
    )


class DaisyOptionsFlow(OptionsFlow):
    """Integration options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={key: int(value) for key, value in user_input.items()}
            )
        current = self.config_entry.options.get(CONF_MAX_MESSAGES, DEFAULT_MAX_MESSAGES)
        current_back = self.config_entry.options.get(
            CONF_CARE_DAYS_BACK, DEFAULT_CARE_DAYS_BACK
        )
        current_days = self.config_entry.options.get(CONF_CARE_DAYS, DEFAULT_CARE_DAYS)
        current_bulletins = self.config_entry.options.get(
            CONF_MAX_BULLETINS, DEFAULT_MAX_BULLETINS
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_CARE_DAYS_BACK, default=current_back): _box(
                    0, MAX_CARE_DAYS_BACK
                ),
                vol.Required(CONF_CARE_DAYS, default=current_days): _box(MIN_CARE_DAYS, MAX_CARE_DAYS),
                vol.Required(CONF_MAX_MESSAGES, default=current): _box(1, MAX_MESSAGES_LIMIT),
                vol.Required(CONF_MAX_BULLETINS, default=current_bulletins): _box(1, MAX_BULLETINS_LIMIT)
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
