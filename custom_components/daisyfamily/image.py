"""Profile pictures of the children."""

from __future__ import annotations

from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import DaisyConfigEntry, DaisyFamilyCoordinator
from .entity import DaisyChildEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DaisyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    known: set[str] = set()

    def _add_new_children() -> None:
        # Only children that have a picture get an entity; a child whose
        # picture is added later gets one on the next update.
        pictures = (coordinator.data or {}).get("pictures") or {}
        new = [
            cid
            for cid in coordinator.data["children"]
            if cid in pictures and cid not in known
        ]
        if not new:
            return
        known.update(new)
        async_add_entities(DaisyChildImage(hass, coordinator, cid) for cid in new)

    _add_new_children()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_children))


class DaisyChildImage(DaisyChildEntity, ImageEntity):
    """The child's profile picture, served through Home Assistant."""

    def __init__(
        self, hass: HomeAssistant, coordinator: DaisyFamilyCoordinator, child_id: str
    ) -> None:
        DaisyChildEntity.__init__(self, coordinator, child_id, "picture")
        ImageEntity.__init__(self, hass)
        self._digest: str | None = None
        self._sync_picture()

    @property
    def _picture(self) -> dict[str, Any] | None:
        return ((self.coordinator.data or {}).get("pictures") or {}).get(self._child_id)

    def _sync_picture(self) -> None:
        """Update content type and timestamp when the picture has changed."""
        picture = self._picture
        digest = picture["digest"] if picture else None
        if digest == self._digest:
            return
        self._digest = digest
        if picture:
            self._attr_content_type = picture["content_type"]
            self._attr_image_last_updated = dt_util.utcnow()
        else:
            self._attr_image_last_updated = None

    @property
    def available(self) -> bool:
        return super().available and self._picture is not None

    @callback
    def _handle_coordinator_update(self) -> None:
        self._sync_picture()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        picture = self._picture
        return picture["bytes"] if picture else None
