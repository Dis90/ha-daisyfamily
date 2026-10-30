"""Base entities for Daisy Family."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import DaisyFamilyCoordinator


def as_local(value: datetime | None) -> datetime | None:
    """Attach the Home Assistant time zone to a naive local datetime."""
    if value is None:
        return None
    return value.replace(tzinfo=dt_util.get_default_time_zone())


def account_device(coordinator: DaisyFamilyCoordinator) -> DeviceInfo:
    entry = coordinator.config_entry
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"Daisy Family ({entry.data['host']})",
        manufacturer="Daisy Family",
    )


class DaisyAccountEntity(CoordinatorEntity[DaisyFamilyCoordinator]):
    """Entity for account-level data (messages, bulletins, notices)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DaisyFamilyCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_device_info = account_device(coordinator)

    @property
    def messages(self) -> dict[str, Any] | None:
        return (self.coordinator.data or {}).get("messages")

    @property
    def bulletins(self) -> dict[str, Any] | None:
        return (self.coordinator.data or {}).get("bulletins")

    @property
    def notices(self) -> dict[str, Any] | None:
        return (self.coordinator.data or {}).get("notices")

    @property
    def calendar(self) -> dict[str, Any] | None:
        return (self.coordinator.data or {}).get("calendar")


class DaisyChildEntity(CoordinatorEntity[DaisyFamilyCoordinator]):
    """Entity belonging to one child."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: DaisyFamilyCoordinator, child_id: str, key: str
    ) -> None:
        super().__init__(coordinator)
        self._child_id = child_id
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{child_id}_{key}"
        child = coordinator.data["children"][child_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, child_id)},
            name=child["name"],
            manufacturer="Daisy Family",
            model="Lapsi",
            via_device=(DOMAIN, coordinator.config_entry.entry_id),
        )

    @property
    def child(self) -> dict[str, Any] | None:
        return ((self.coordinator.data or {}).get("children") or {}).get(self._child_id)

    @property
    def available(self) -> bool:
        return super().available and self.child is not None


class DaisyDiagnosticEntity(DaisyAccountEntity):
    """Diagnostic entity: stays available while updates fail (that is the point)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        return True
