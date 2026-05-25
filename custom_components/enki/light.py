"""Light setup for our Integration."""

from typing import Optional
from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.components.light.const import DEFAULT_MIN_KELVIN, DEFAULT_MAX_KELVIN 
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EnkiConfigEntry
from .base import EnkiBaseEntity
from .coordinator import EnkiCoordinator
from .const import LOGGER

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: EnkiConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up the Binary Sensors."""
    # This gets the data update coordinator from the config entry runtime data as specified in your __init__.py
    coordinator: EnkiCoordinator = config_entry.runtime_data.coordinator

    # ----------------------------------------------------------------------------
    # Here we are going to add some lights entities for the lights in our mock data.
    # We have an on/off light and a dimmable light in our mock data, so add each
    # specific class based on the light type.
    # ----------------------------------------------------------------------------
    lights = []

    lights.extend(
        [
            EnkiLight(coordinator, device, "state")
            for device in coordinator.data
            if device.get("type") == "lights" or device.get("deviceType") == "ceiling_fans"
        ]
    )

    # Create the lights.
    async_add_entities(lights)

class EnkiLight(EnkiBaseEntity, LightEntity):
    """Implementation of an light depending on its capabilities."""
    _attr_supported_color_modes = set()
    _attr_color_mode = None
    _attr_min_color_temp_kelvin = None
    _attr_max_color_temp_kelvin = None
    BRIGHTNESS_SCALE = (1,255)

    def __init__(
        self, coordinator: EnkiCoordinator, device: dict[str, Any], parameter: str
    ) -> None:
        """Initialise entity."""
        super().__init__(coordinator, device, parameter)
        self._device = device
        self._capabilities = self._get_capabilities(device)
        self._color_temp_values = None
        if "possibleValues" in device and "change_brightness" in device["possibleValues"]:
            min = device["possibleValues"]["change_brightness"]["range"]["min"]
            max = device["possibleValues"]["change_brightness"]["range"]["max"]
            LOGGER.debug("brightness min : " + str(min))
            LOGGER.debug("brightness max : " + str(max))
            self.BRIGHTNESS_SCALE = (min, max)

        if "change_color_temperature" in self._capabilities:
            self._attr_supported_color_modes.add(ColorMode.COLOR_TEMP)
            self._attr_color_mode = ColorMode.COLOR_TEMP
            if "possibleValues" in device and "change_color_temperature" in device["possibleValues"]:
                values = device["possibleValues"]["change_color_temperature"]["values"]
                min = int(values[0][1:-1])
                max = int(values[-1][1:-1])
                self._attr_min_color_temp_kelvin=min
                self._attr_max_color_temp_kelvin=max
                self._color_temp_values = []
                for val in values:
                    self._color_temp_values.append(int(val[1:-1]))
            else:
                if device.get("deviceType") == "ceiling_fans":
                    self._attr_min_color_temp_kelvin=2748
                    self._attr_max_color_temp_kelvin=6500
                else:
                    self._attr_min_color_temp_kelvin=DEFAULT_MIN_KELVIN
                    self._attr_max_color_temp_kelvin=DEFAULT_MAX_KELVIN

        if "change_hue" in self._capabilities and "change_saturation" in self._capabilities:
            self._attr_supported_color_modes.add(ColorMode.HS)
            self._attr_color_mode = ColorMode.HS

        if "change_brightness" in self._capabilities:
            if len(self._attr_supported_color_modes) == 0:
                self._attr_supported_color_modes.add(ColorMode.BRIGHTNESS)
            if self._attr_color_mode is None:
                self._attr_color_mode = ColorMode.BRIGHTNESS

        if "switch_electrical_power" in  self._capabilities:
            if len(self._attr_supported_color_modes) == 0:
                self._attr_supported_color_modes.add(ColorMode.ONOFF)
                self._attr_color_mode = ColorMode.ONOFF

        if len(self._attr_supported_color_modes) > 1:
            self._attr_color_mode = None  # will be resolved dynamically

    def _get_capabilities(self, device):
        if device.get("capabilities"):
            return device["capabilities"]
        if device.get("deviceType") == "ceiling_fans":
            return [
                "switch_electrical_power",
                "change_brightness",
                "change_color_temperature",
            ]
        return []

    @property
    def color_mode(self) -> ColorMode | None:
        if self._attr_color_mode is not None:
            return self._attr_color_mode
        last = self.coordinator.get_device_parameter(self.node_id, "lastReportedValue")
        if last and ("hue" in last or "saturation" in last):
            return ColorMode.HS
        return ColorMode.COLOR_TEMP

    @property
    def is_on(self) -> bool | None:
        """Return if the binary sensor is on."""
        # This needs to enumerate to true or false
        last_reported_values = self.coordinator.get_device_parameter(self.node_id, "lastReportedValue")
        if not last_reported_values:
            return None
        return last_reported_values.get("power") == "ON"

    def closest_temp_value(self, target_value):
        if self._color_temp_values is None:
            return max(self._attr_min_color_temp_kelvin, min(self._attr_max_color_temp_kelvin, target_value))
        return min(self._color_temp_values, key=lambda x: abs(x - target_value)) 

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        last = self.coordinator.get_device_parameter(self.node_id, "lastReportedValue")
        state = dict(last) if last else None

        if state is not None:
            state["power"] = "ON"
            if "brightness" in kwargs:
                ha_value = kwargs["brightness"]
                state["brightness"] = round(ha_value / 255, 2)
                LOGGER.debug(f"setting brightness to {ha_value} => {state['brightness']}")
            if "hs_color" in kwargs:
                hue, sat = kwargs["hs_color"]
                state["hue"] = round(hue / 360, 4)
                state["saturation"] = round(sat / 100, 4)
                state["colorMode"] = "hs"
                LOGGER.debug(f"setting hs_color to {hue},{sat} => {state['hue']},{state['saturation']}")
            if "color_temp_kelvin" in kwargs:
                ha_value = kwargs["color_temp_kelvin"]
                value = self.closest_temp_value(ha_value)
                state["colorTemperature"] = "T" + str(value) + "K"
                state["colorMode"] = "ct"
                LOGGER.debug(f"setting color temp to {ha_value} => {value}")

        await self.coordinator.api.change_light_state(
            self._device["homeId"], self._device["nodeId"], "power", "ON", current_state=state
        )
        self.coordinator.update_data(self.node_id, "lastReportedValue", "power", "ON")
        if state is not None and "brightness" in kwargs:
            self.coordinator.update_data(self.node_id, "lastReportedValue", "brightness", state["brightness"])
        if state is not None and "hs_color" in kwargs:
            self.coordinator.update_data(self.node_id, "lastReportedValue", "hue", state["hue"])
            self.coordinator.update_data(self.node_id, "lastReportedValue", "saturation", state["saturation"])
        if state is not None and "color_temp_kelvin" in kwargs:
            self.coordinator.update_data(self.node_id, "lastReportedValue", "colorTemperature", state["colorTemperature"])

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        await self.coordinator.api.change_light_state(
            self._device["homeId"], self._device["nodeId"], "power", "OFF"
        )
        self.coordinator.update_data(self.node_id, "lastReportedValue", "power", "OFF")

    @property
    def hs_color(self) -> tuple[float, float] | None:
        """Return the hue and saturation color value."""
        last = self.coordinator.get_device_parameter(self.node_id, "lastReportedValue")
        if not last:
            return None
        hue = last.get("hue")
        sat = last.get("saturation")
        if hue is None or sat is None:
            return None
        return (round(hue * 360, 1), round(sat * 100, 1))

    @property
    def brightness(self) -> Optional[int]:
        """Return the current brightness."""
        last_reported_values = self.coordinator.get_device_parameter(self.node_id, "lastReportedValue")
        if not last_reported_values or "brightness" not in last_reported_values:
            return None
        return round(last_reported_values["brightness"] * 255)
    
    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the color temperature in Kelvin."""
        last_reported_values = self.coordinator.get_device_parameter(self.node_id, "lastReportedValue")
        return int(last_reported_values["colorTemperature"][1:-1])
