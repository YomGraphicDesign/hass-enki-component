"""Fan platform for Enki integration."""

from math import ceil
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EnkiConfigEntry
from .base import EnkiBaseEntity
from .const import DOMAIN
from .coordinator import EnkiCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: EnkiConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up fans."""
    coordinator: EnkiCoordinator = config_entry.runtime_data.coordinator

    fans = [
        EnkiCeilingFan(coordinator, device)
        for device in coordinator.data
        if device.get("deviceType") == "ceiling_fans"
    ]

    async_add_entities(fans)


class EnkiCeilingFan(EnkiBaseEntity, FanEntity):
    """Enki ceiling fan."""

    _attr_speed_count = 6

    def __init__(self, coordinator: EnkiCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator, device, "fan")
        self._device = device
        self._attr_supported_features = self._get_supported_features()

    def _get_supported_features(self) -> FanEntityFeature:
        return (
            FanEntityFeature.SET_SPEED
            | FanEntityFeature.TURN_ON
            | FanEntityFeature.TURN_OFF
        )

    @property
    def supported_features(self) -> FanEntityFeature:
        return self._get_supported_features()

    @property
    def name(self) -> str:
        return None

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}-{self._device['nodeId']}-fan"

    @property
    def is_on(self) -> bool | None:
        device = self.coordinator.get_node(self._device["nodeId"])
        if device is None:
            return None
        fan_speed = device.get("fanSpeedValue")
        if fan_speed is not None:
            return fan_speed > 0
        fan_power = device.get("fanPowerValue")
        if fan_power in ("ON", "OFF"):
            return fan_power == "ON"
        return None

    @property
    def percentage(self) -> int | None:
        device = self.coordinator.get_node(self._device["nodeId"])
        if device is None or device.get("fanSpeedValue") is None:
            return None
        return round(device["fanSpeedValue"] * 100 / self._attr_speed_count)

    @property
    def percentage_step(self) -> float:
        return 100 / self._attr_speed_count

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        if percentage is not None:
            await self.async_set_percentage(percentage)
            return
        await self.coordinator.api.change_power_state(
            self._device["homeId"], self._device["nodeId"], True, endpoint=2
        )
        self.coordinator.update_data(self._device["nodeId"], None, "fanPowerValue", "ON")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.async_set_percentage(0)

    async def async_set_percentage(self, percentage: int) -> None:
        fan_speed = self._percentage_to_speed(percentage)
        await self.coordinator.api.change_fan_speed(
            self._device["homeId"], self._device["nodeId"], fan_speed
        )
        fan_power = "ON" if fan_speed > 0 else "OFF"
        self.coordinator.update_data(self._device["nodeId"], None, "fanSpeedValue", fan_speed)
        self.coordinator.update_data(self._device["nodeId"], None, "fanPowerValue", fan_power)

    def _percentage_to_speed(self, percentage: int) -> int:
        if percentage <= 0:
            return 0
        return min(self._attr_speed_count, ceil(percentage * self._attr_speed_count / 100))
