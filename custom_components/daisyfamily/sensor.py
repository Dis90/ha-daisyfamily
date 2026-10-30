"""Sensors for Daisy Family."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DaisyConfigEntry
from .entity import DaisyAccountEntity, DaisyChildEntity, DaisyDiagnosticEntity, as_local


@dataclass(frozen=True, kw_only=True)
class DaisyChildSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _next_care_attrs(child: dict[str, Any]) -> dict[str, Any]:
    nxt = child["next_reservation"]
    return {
        "end": _iso(as_local(nxt["end"])) if nxt else None,
        "upcoming": [
            {"start": _iso(r["start"]), "end": _iso(r["end"])}
            for r in child["upcoming_reservations"]
        ],
    }


WEEKDAYS = ("ma", "ti", "ke", "to", "pe", "la", "su")


def _reservation_attrs(child: dict[str, Any]) -> dict[str, Any]:
    """All upcoming reservations in the polled window."""
    rows = []
    for r in child["upcoming_all"]:
        start, end = r["start"], r["end"]
        rows.append(
            {
                "date": start.date().isoformat(),
                "weekday": WEEKDAYS[start.weekday()],
                "start": start.strftime("%H:%M"),
                "end": end.strftime("%H:%M"),
                "hours": round((end - start).total_seconds() / 3600, 2),
                "locked": r.get("locked"),
                "text": (
                    f"{WEEKDAYS[start.weekday()]} {start.day}.{start.month}. "
                    f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')}"
                ),
            }
        )
    return {
        "reservations": rows,
        "absences": [d.isoformat() for d in child["upcoming_absences"]],
        "history": [
            {
                "date": h["date"].isoformat(),
                "weekday": WEEKDAYS[h["date"].weekday()],
                "start": h["start"].strftime("%H:%M") if h["start"] else None,
                "end": h["end"].strftime("%H:%M") if h["end"] else None,
                "arrived": h["arrived"].strftime("%H:%M") if h["arrived"] else None,
                "departed": h["departed"].strftime("%H:%M") if h["departed"] else None,
                "absent": h["absent"],
            }
            for h in child["history"]
        ],
        "centre": child.get("centre"),
        "group": (child.get("group") or "").strip() or None,
    }


def _centre_attrs(child: dict[str, Any]) -> dict[str, Any]:
    info = child.get("centre_info") or {}
    return {
        "address": info.get("address"),
        "phone": info.get("phone"),
        "manager": info.get("manager"),
        "manager_phone": info.get("manager_phone"),
        "open_type": info.get("open_type"),
        "open_times": info.get("open_times"),
        "group": (child.get("group") or "").strip() or info.get("group"),
        "group_phone": info.get("group_phone"),
        "group_open_times": info.get("group_open_times"),
        "placement_start": info.get("placement_start") or _iso(child["placement_start"]),
        "placement_end": info.get("placement_end") or _iso(child["placement_end"]),
    }


CHILD_SENSORS: tuple[DaisyChildSensorDescription, ...] = (
    DaisyChildSensorDescription(
        key="centre",
        translation_key="centre",
        value_fn=lambda c: (c.get("centre_info") or {}).get("centre") or c["centre"],
        attrs_fn=_centre_attrs,
    ),
    DaisyChildSensorDescription(
        key="group",
        translation_key="group",
        value_fn=lambda c: c["group"],
        attrs_fn=lambda c: {
            "centre": c["centre"],
            "placement_start": _iso(c["placement_start"]),
            "placement_end": _iso(c["placement_end"]),
        },
    ),
    DaisyChildSensorDescription(
        key="care_start_today",
        translation_key="care_start_today",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda c: as_local(
            c["today_reservation"]["start"] if c["today_reservation"] else None
        ),
    ),
    DaisyChildSensorDescription(
        key="care_end_today",
        translation_key="care_end_today",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda c: as_local(
            c["today_reservation"]["end"] if c["today_reservation"] else None
        ),
    ),
    DaisyChildSensorDescription(
        key="next_care_start",
        translation_key="next_care_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda c: as_local(
            c["next_reservation"]["start"] if c["next_reservation"] else None
        ),
        attrs_fn=_next_care_attrs,
    ),
    DaisyChildSensorDescription(
        key="arrived_today",
        translation_key="arrived_today",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda c: as_local(c["arrived"]),
    ),
    DaisyChildSensorDescription(
        key="departed_today",
        translation_key="departed_today",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda c: as_local(c["departed"]),
    ),
    DaisyChildSensorDescription(
        key="next_absence",
        translation_key="next_absence",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda c: c["next_absence"],
        attrs_fn=lambda c: {
            "upcoming": [d.isoformat() for d in c["upcoming_absences"]],
        },
    ),
    DaisyChildSensorDescription(
        key="reserved_hours_week",
        translation_key="reserved_hours_week",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=2,
        value_fn=lambda c: c["reserved_hours_week"],
    ),
    DaisyChildSensorDescription(
        key="reservations",
        translation_key="reservations",
        value_fn=lambda c: len(c["upcoming_all"]),
        attrs_fn=_reservation_attrs,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DaisyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            DaisyUnreadMessagesSensor(coordinator),
            DaisyLatestMessageSensor(coordinator),
            DaisyAllMessagesSensor(coordinator),
            DaisyBulletinCountSensor(coordinator),
            DaisyLatestBulletinSensor(coordinator),
            DaisyNextVacationSensor(coordinator),
            DaisyNextHolidaySensor(coordinator),
            DaisyLastSuccessSensor(coordinator),
            DaisyUpdateDurationSensor(coordinator),
        ]
    )

    known: set[str] = set()

    def _add_new_children() -> None:
        new = [cid for cid in coordinator.data["children"] if cid not in known]
        if not new:
            return
        known.update(new)
        async_add_entities(
            DaisyChildSensor(coordinator, cid, description)
            for cid in new
            for description in CHILD_SENSORS
        )

    _add_new_children()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_children))


class DaisyChildSensor(DaisyChildEntity, SensorEntity):
    entity_description: DaisyChildSensorDescription
    _unrecorded_attributes = frozenset(
        {"reservations", "absences", "upcoming", "history"}
    )

    def __init__(self, coordinator, child_id: str, description: DaisyChildSensorDescription) -> None:
        super().__init__(coordinator, child_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        child = self.child
        return self.entity_description.value_fn(child) if child else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        child = self.child
        fn = self.entity_description.attrs_fn
        return fn(child) if child and fn else None


class DaisyUnreadMessagesSensor(DaisyAccountEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "viestiketjua"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "unread_messages")

    @property
    def native_value(self) -> int | None:
        msgs = self.messages
        return msgs["unread_threads"] if msgs else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        msgs = self.messages
        if not msgs:
            return None
        return {
            "total_threads": msgs["total_threads"],
            "recent_unread": msgs["recent_unread"],
        }


class DaisyAllMessagesSensor(DaisyAccountEntity, SensorEntity):
    """All message threads (newest first) in the `messages` attribute."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "viestiketjua"
    _unrecorded_attributes = frozenset({"messages"})

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "all_messages")

    @property
    def native_value(self) -> int | None:
        msgs = self.messages
        return msgs["total_threads"] if msgs else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        msgs = self.messages
        if not msgs:
            return None
        return {
            "messages": [
                {
                    **m,
                    "sent": _iso(m["sent"]),
                    "parts": [{**x, "sent": _iso(x["sent"])} for x in m["parts"]],
                }
                for m in msgs["all"]
            ]
        }


class DaisyLatestMessageSensor(DaisyAccountEntity, SensorEntity):
    _unrecorded_attributes = frozenset({"content", "preview"})

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "latest_message")

    @property
    def native_value(self) -> str | None:
        msgs = self.messages
        latest = msgs["latest"] if msgs else None
        title = latest["title"] if latest else None
        return title[:255] if title else None  # state is limited to 255 chars

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        msgs = self.messages
        latest = msgs["latest"] if msgs else None
        if not latest:
            return None
        return {
            "sender": latest["sender"],
            "sent": _iso(latest["sent"]),
            "preview": latest["preview"],
            "content": latest["content"],
            "unread": latest["unread"],
        }


def _bulletin_dict(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": item["title"],
        "content": item["content"],
        "date": _iso(item["date"]),
        "valid_until": _iso(item["end"]),
        "recipient": item["recipient"],
        "attachments": item["attachments"],
        "files": item["files"],
    }


class DaisyBulletinCountSensor(DaisyAccountEntity, SensorEntity):
    """Number of active bulletin board posts; the posts are in attributes."""

    _unrecorded_attributes = frozenset({"posts"})

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "bulletins")

    @property
    def native_value(self) -> int | None:
        data = self.bulletins
        return data["count"] if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.bulletins
        if not data:
            return None
        return {"posts": [_bulletin_dict(i) for i in data["items"]]}


class DaisyLatestBulletinSensor(DaisyAccountEntity, SensorEntity):
    """Title of the newest bulletin board post."""

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "latest_bulletin")

    @property
    def native_value(self) -> str | None:
        data = self.bulletins
        latest = data["latest"] if data else None
        title = latest["title"] if latest else None
        return title[:255] if title else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.bulletins
        latest = data["latest"] if data else None
        return _bulletin_dict(latest) if latest else None


def _vacation_dict(period: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": period["name"],
        "start": _iso(period["start"]),
        "end": _iso(period["end"]),
        "days": period["days"],
        "ongoing": period["ongoing"],
        "days_until_start": period["days_until_start"],
        "reservation_deadline": _iso(period["reservation_deadline"]),
    }


class DaisyNextVacationSensor(DaisyAccountEntity, SensorEntity):
    """Start date of the ongoing or next holiday period."""

    _attr_device_class = SensorDeviceClass.DATE
    _unrecorded_attributes = frozenset({"upcoming", "periods"})

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "next_vacation")

    @property
    def native_value(self):
        calendar = self.calendar
        period = calendar["next_vacation"] if calendar else None
        return period["start"] if period else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        calendar = self.calendar
        if not calendar:
            return None
        attrs: dict[str, Any] = {
            "upcoming": [_vacation_dict(p) for p in calendar["vacations"][:5]],
            "periods": [_vacation_dict(p) for p in calendar["vacations"]],
        }
        if calendar["next_vacation"]:
            attrs.update(_vacation_dict(calendar["next_vacation"]))
        return attrs


class DaisyNextHolidaySensor(DaisyAccountEntity, SensorEntity):
    """Date of the next public holiday (today counts)."""

    _attr_device_class = SensorDeviceClass.DATE
    _unrecorded_attributes = frozenset({"upcoming", "holidays"})

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "next_holiday")

    @property
    def native_value(self):
        calendar = self.calendar
        holiday = calendar["next_holiday"] if calendar else None
        return holiday["date"] if holiday else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        calendar = self.calendar
        if not calendar:
            return None
        attrs: dict[str, Any] = {
            "upcoming": [
                {"date": _iso(h["date"]), "name": h["name"]}
                for h in calendar["holidays"][:5]
            ],
            "holidays": [
                {"date": _iso(h["date"]), "name": h["name"]}
                for h in calendar["holidays"]
            ],
        }
        holiday = calendar["next_holiday"]
        if holiday:
            attrs.update(
                name=holiday["name"],
                days_until=holiday["days_until"],
                eve_compensation=holiday["eve_compensation"],
            )
        return attrs


class DaisyLastSuccessSensor(DaisyDiagnosticEntity, SensorEntity):
    """When the data was last fetched successfully."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "last_success")

    @property
    def native_value(self):
        return self.coordinator.diag_last_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        client = self.coordinator.client
        return {
            "last_attempt": self.coordinator.diag_last_attempt,
            "logins": client.login_count,
        }


class DaisyUpdateDurationSensor(DaisyDiagnosticEntity, SensorEntity):
    """How long the latest update took."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "update_duration")

    @property
    def native_value(self):
        return self.coordinator.diag_duration
