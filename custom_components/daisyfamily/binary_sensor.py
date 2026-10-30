"""Binary sensors for Daisy Family."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DaisyConfigEntry
from .entity import DaisyAccountEntity, DaisyChildEntity, DaisyDiagnosticEntity
from .parser import MISSING_RESERVATIONS_TEXT

DESCRIPTIONS = (
    BinarySensorEntityDescription(
        key="absent_today",
        translation_key="absent_today",
    ),
    # No device class on purpose: "presence" would show the states as Home/Away.
    BinarySensorEntityDescription(
        key="at_daycare",
        translation_key="at_daycare",
    ),
)


NOTICE_DESCRIPTIONS = (
    BinarySensorEntityDescription(
        key="reservations_missing",
        translation_key="reservations_missing",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    BinarySensorEntityDescription(
        key="vacation_reservations_missing",
        translation_key="vacation_reservations_missing",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DaisyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        DaisyNoticeBinarySensor(coordinator, description)
        for description in NOTICE_DESCRIPTIONS
    )
    async_add_entities([DaisyConnectionProblemSensor(coordinator)])
    known: set[str] = set()

    def _add_new_children() -> None:
        new = [cid for cid in coordinator.data["children"] if cid not in known]
        if not new:
            return
        known.update(new)
        async_add_entities(
            DaisyChildBinarySensor(coordinator, cid, description)
            for cid in new
            for description in DESCRIPTIONS
        )

    _add_new_children()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_children))


class DaisyChildBinarySensor(DaisyChildEntity, BinarySensorEntity):
    def __init__(self, coordinator, child_id: str, description: BinarySensorEntityDescription) -> None:
        super().__init__(coordinator, child_id, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        child = self.child
        if not child:
            return None
        value = child[self.entity_description.key]
        return None if value is None else bool(value)


class DaisyNoticeBinarySensor(DaisyAccountEntity, BinarySensorEntity):
    """Care time notices from the Daisy start page."""

    def __init__(self, coordinator, description: BinarySensorEntityDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        notices = self.notices
        if notices is None:
            return None
        if self.entity_description.key == "reservations_missing":
            return notices["reservations_missing"]
        return notices["vacation_missing"]

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        notices = self.notices
        if notices is None:
            return None
        if self.entity_description.key == "reservations_missing":
            return {
                "message": MISSING_RESERVATIONS_TEXT if notices["reservations_missing"] else None,
                "lock_time": notices["lock_time"],
                "days_to_select": notices["days_to_select"],
                "locked_days_to_select": notices["locked_days_to_select"],
                "children": notices["reservations_missing_children"],
            }
        return {
            "message": " ".join(notices["vacation_rows"]) or None,
            "rows": notices["vacation_rows"],
        }


class DaisyConnectionProblemSensor(DaisyDiagnosticEntity, BinarySensorEntity):
    """On when the latest update failed or some part of it could not be fetched."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "connection_problem")

    @property
    def is_on(self) -> bool:
        c = self.coordinator
        return c.diag_failures > 0 or bool(c.diag_failed_parts)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        c = self.coordinator
        return {
            "last_error": c.diag_last_error,
            "consecutive_failures": c.diag_failures,
            "failed_parts": c.diag_failed_parts,
        }
