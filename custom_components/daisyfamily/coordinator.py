"""Data update coordinator for Daisy Family."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    DaisyFamilyAuthError,
    DaisyFamilyClient,
    DaisyFamilyConnectionError,
)
from .const import (
    CALENDAR_DAYS_AHEAD,
    CALENDAR_DAYS_BACK,
    CALENDAR_REFRESH_SECONDS,
    CENTRE_REFRESH_SECONDS,
    DOMAIN,
    PICTURE_REFRESH_SECONDS,
    UPDATE_INTERVAL,
    CONF_CARE_DAYS,
    CONF_CARE_DAYS_BACK,
    DEFAULT_CARE_DAYS_BACK,
    CONF_MAX_BULLETINS,
    CONF_MAX_MESSAGES,
    DEFAULT_MAX_BULLETINS,
    DEFAULT_CARE_DAYS,
    DEFAULT_MAX_MESSAGES,
)
from .parser import (
    parse_bulletins,
    parse_calendar,
    parse_centres,
    parse_children,
    parse_messages,
    parse_notices,
    parse_pictures,
)

_LOGGER = logging.getLogger(__name__)

type DaisyConfigEntry = ConfigEntry[DaisyFamilyCoordinator]


class DaisyFamilyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches children, care times and messages."""

    config_entry: DaisyConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: DaisyConfigEntry, client: DaisyFamilyClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        # Pictures change rarely: fetch them at most once per PICTURE_REFRESH_SECONDS.
        self._pictures: dict[str, dict[str, Any]] = {}
        self._pictures_checked: float | None = None
        # Holiday periods / public holidays: raw payload, refetched every few hours.
        self._calendar_payload: dict[str, Any] | None = None
        self._calendar_checked: float | None = None
        # Daycare centre details: parsed records, refetched about once a day.
        self._centres: list[dict[str, Any]] = []
        self._centres_checked: float | None = None
        # Full message threads by thread id: (newest-saved marker, thread payload).
        self._thread_cache: dict[str, tuple[str, dict[str, Any]]] = {}
        # Diagnostics (kept even when an update fails).
        self.diag_last_success: datetime | None = None
        self.diag_last_attempt: datetime | None = None
        self.diag_last_error: str | None = None
        self.diag_failures = 0
        self.diag_duration: float | None = None
        self.diag_failed_parts: list[str] = []

    async def _async_enrich_messages(
        self, messages: dict[str, Any], limit: int
    ) -> dict[str, Any]:
        """Add full texts of the newest `limit` threads to the MessageData payload.

        MessageData itself includes the full text of only the newest threads, so
        the rest are fetched one by one (and cached until the thread changes).
        """
        headers = (messages.get("ListMessage") or {}).get("listMessage") or []
        newest = sorted(headers, key=lambda t: t.get("NewestSaved") or "", reverse=True)[
            : max(0, limit)
        ]
        have = {
            (m.get("ThreadId"))
            for t in messages.get("MessageThreads") or []
            for m in (t.get("listMessageModels") or [])[:1]
        }
        wanted = [t for t in newest if t.get("ThreadId") not in have]
        keep = {t.get("ThreadId") for t in newest}
        self._thread_cache = {k: v for k, v in self._thread_cache.items() if k in keep}

        todo = [
            t
            for t in wanted
            if self._thread_cache.get(t.get("ThreadId"), ("", {}))[0]
            != (t.get("NewestSaved") or "")
        ]
        sem = asyncio.Semaphore(4)

        async def fetch(t: dict[str, Any]) -> None:
            async with sem:
                try:
                    thread = await self.client.async_get_message_thread(t["ThreadId"])
                except (DaisyFamilyAuthError, DaisyFamilyConnectionError) as err:
                    _LOGGER.debug("Could not fetch thread %s: %s", t.get("ThreadId"), err)
                    return
            if isinstance(thread, dict) and thread.get("listMessageModels"):
                self._thread_cache[t["ThreadId"]] = (t.get("NewestSaved") or "", thread)

        if todo:
            await asyncio.gather(*(fetch(t) for t in todo))
        extra = [
            self._thread_cache[t["ThreadId"]][1]
            for t in wanted
            if t.get("ThreadId") in self._thread_cache
        ]
        if not extra:
            return messages
        return {
            **messages,
            "MessageThreads": [*(messages.get("MessageThreads") or []), *extra],
        }

    async def _async_update_data(self) -> dict[str, Any]:
        """Run an update and record its outcome for the diagnostic entities."""
        started = time.monotonic()
        self.diag_last_attempt = dt_util.utcnow()
        self.diag_failed_parts = []
        try:
            data = await self._async_fetch()
        except (ConfigEntryAuthFailed, UpdateFailed) as err:
            self.diag_failures += 1
            self.diag_last_error = str(err)[:250] or type(err).__name__
            self.diag_duration = round(time.monotonic() - started, 2)
            raise
        except Exception as err:  # noqa: BLE001 - recorded, then re-raised
            self.diag_failures += 1
            self.diag_last_error = f"{type(err).__name__}: {err}"[:250]
            self.diag_duration = round(time.monotonic() - started, 2)
            raise
        self.diag_failures = 0
        self.diag_last_error = None
        self.diag_last_success = dt_util.utcnow()
        self.diag_duration = round(time.monotonic() - started, 2)
        return data

    async def _async_fetch(self) -> dict[str, Any]:
        now = dt_util.now().replace(tzinfo=None)  # API uses naive local time
        today = now.date()
        back = int(
            self.config_entry.options.get(CONF_CARE_DAYS_BACK, DEFAULT_CARE_DAYS_BACK)
        )
        # Always include the Monday of this week (weekly hours are summed from it).
        start = min(today - timedelta(days=back), today - timedelta(days=today.weekday()))
        end = today + timedelta(
            days=int(self.config_entry.options.get(CONF_CARE_DAYS, DEFAULT_CARE_DAYS))
        )

        try:
            children = await self.client.async_get_children()
            times = await self.client.async_get_nursing_times(start, end)
        except DaisyFamilyAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except DaisyFamilyConnectionError as err:
            raise UpdateFailed(str(err)) from err

        # Everything below is secondary: a failure must not hide the children,
        # so fall back to the previous values.
        previous = self.data or {}

        async def optional(key: str, call: Callable[[], Awaitable[Any]]) -> Any:
            try:
                return await call()
            except (DaisyFamilyAuthError, DaisyFamilyConnectionError) as err:
                _LOGGER.debug("Could not fetch %s: %s", key, err)
                self.diag_failed_parts.append(key)
                return None

        messages = await optional("messages", self.client.async_get_messages)
        max_messages = int(
            self.config_entry.options.get(CONF_MAX_MESSAGES, DEFAULT_MAX_MESSAGES)
        )
        if messages is not None:
            try:
                messages = await self._async_enrich_messages(messages, max_messages)
            except Exception:  # noqa: BLE001 - extra texts are optional
                _LOGGER.debug("Could not fetch full message texts", exc_info=True)
        bulletins = await optional("bulletins", self.client.async_get_bulletins)
        main_stats = await optional("main stats", self.client.async_get_main_stats)
        vacation = await optional("vacation status", self.client.async_get_vacation_status)

        if (
            self._pictures_checked is None
            or time.monotonic() - self._pictures_checked >= PICTURE_REFRESH_SECONDS
        ):
            pictures = await optional(
                "profile pictures", self.client.async_get_profile_pictures
            )
            if pictures is not None:
                self._pictures = parse_pictures(pictures)
                self._pictures_checked = time.monotonic()

        if (
            self._centres_checked is None
            or time.monotonic() - self._centres_checked >= CENTRE_REFRESH_SECONDS
        ):
            centres = await optional("centre info", self.client.async_get_centre_infos)
            if centres is not None:
                self._centres = parse_centres(centres)
                self._centres_checked = time.monotonic()

        if (
            self._calendar_checked is None
            or time.monotonic() - self._calendar_checked >= CALENDAR_REFRESH_SECONDS
        ):
            calendar = await optional(
                "calendar",
                lambda: self.client.async_get_calendar(
                    today - timedelta(days=CALENDAR_DAYS_BACK),
                    today + timedelta(days=CALENDAR_DAYS_AHEAD),
                ),
            )
            if calendar is not None:
                self._calendar_payload = calendar
                self._calendar_checked = time.monotonic()

        return {
            "children": parse_children(children, times, now, self._centres),
            "calendar": parse_calendar(self._calendar_payload, vacation, today),
            "pictures": self._pictures,
            "messages": parse_messages(messages, max_messages)
            if messages is not None
            else previous.get("messages"),
            "bulletins": parse_bulletins(
                bulletins,
                now,
                int(
                    self.config_entry.options.get(
                        CONF_MAX_BULLETINS, DEFAULT_MAX_BULLETINS
                    )
                ),
            )
            if bulletins is not None
            else previous.get("bulletins"),
            "notices": parse_notices(main_stats, vacation, times)
            if main_stats is not None or vacation is not None
            else previous.get("notices"),
            "user_name": self.client.user_name,
        }
