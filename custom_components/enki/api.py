"""Enki API."""

import aiohttp
from dataclasses import dataclass
from typing import Any
import time
import uuid

from .const import (
    LOGGER,
    ENKI_OIDC_URL,
    ENKI_URL,
    ENKI_HOME_API_KEY,
    ENKI_BFF_API_KEY,
    ENKI_NODE_API_KEY,
    ENKI_REFERENTIEL_API_KEY,
    ENKI_LIGHTS_API_KEY,
    ENKI_TEMP_HUMIDITY_API_KEY,
    ENKI_PRESENCE_API_KEY,
    ENKI_BATTERY_API_KEY,
    ENKI_LUMINOSITY_API_KEY,
    ENKI_POWER_API_KEY,
    ENKI_AIRFLOW_API_KEY)

proxy = None
ENKI_USER_AGENT = "Enki/389 CFNetwork/3860.500.112 Darwin/25.4.0"

def _session():
    return aiohttp.ClientSession(
        headers={
            "User-Agent": ENKI_USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": "fr-FR,fr;q=0.9",
            "X-Correlation-Id": f"iOS_{str(uuid.uuid4()).upper()}",
        },
        skip_auto_headers={"User-Agent"},
    )

@dataclass
class Device:
    """API device."""
    home_id: str
    device_id: str
    node_id: str
    device_name: str

class API:
    """Class for Enki API."""

    def __init__(self, user: str, pwd: str) -> None:
        """Initialise."""
        self.user = user
        self.pwd = pwd

    @property
    def controller_name(self) -> str:
        """Return the name of the controller."""
        return self.user

    async def check_connected(self) -> bool:
        """Tell if token is still valid"""
        if not hasattr(self, '_access_token') or time.time() > self._tokenExpiresTime:
            await self.connect()
        return True

    async def connect(self) -> bool:
        """Connect to the Enki API."""
        try:
            async with _session() as session, session.request(
                method="POST",
                url=ENKI_OIDC_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
                         "X-Correlation-Id": f"iOS_{str(uuid.uuid4()).upper()}"},
                data={"grant_type": "password",
                      "client_id": "enki-front",
                      "username": self.user,
                      "password": self.pwd},
                proxy=proxy,) as resp:

                    response = await resp.json()
                    if resp.status == 200:
                        LOGGER.debug("connect succeeded, token expires in %s seconds", response["expires_in"])
                        self._access_token = response["access_token"]
                        self._refresh_token = response["refresh_token"]
                        self._token_type = response["token_type"]
                        self._tokenExpiresTime = time.time() + response["expires_in"]
                        return True
                    else:
                        LOGGER.error("Error connecting to api. status %s, response %s", resp.status, str(response))
                        raise APIAuthError("Error connecting to api. Invalid username or password.")
        except APIAuthError:
            raise
        except Exception as e:
            raise APIConnectionError("Error connecting to api : " + repr(e))

# *******************************************************
    async def get_homes(self):
        """Get list of homes."""
        await self.check_connected()
        homes = []
        async with _session() as session, session.request(
             method="GET",
             url=f"{ENKI_URL}/api-enki-home-prod/v1/homes",
             headers={"Authorization": f"{self._token_type} {self._access_token}",
                      "X-Gateway-APIKey": ENKI_HOME_API_KEY},
             proxy=proxy,) as resp:

                response = await resp.json()
                if resp.status == 200:
                    LOGGER.debug("get_homes : " + str(response))
                    for home in response["items"]:
                        homes.append(home["id"])
                    return homes
                else:
                    LOGGER.error("Error on get_homes. status %s, response %s", resp.status, str(response))
                    raise ValueError("bad credentials")

    def merge_properties(self, device, properties):
        for prop in properties:
            if prop != "id":
                device[prop] = properties[prop]

    async def get_items_in_section_for_home(self, home_id) -> list[dict[str, Any]]:
        """Get sections in home."""
        await self.check_connected()
        async with _session() as session, session.request(
             method="GET",
             url=f"{ENKI_URL}/api-enki-mobile-bff-prod/v1/dashboard/homes/{home_id}?hasGroups=true",
             headers={"Authorization": f"{self._token_type} {self._access_token}",
                      "X-Gateway-APIKey": ENKI_BFF_API_KEY},
             proxy=proxy,) as resp:
            devices = []
            response = await resp.json()
            if resp.status == 200:
                LOGGER.debug("get_items_in_section_for_home : " + str(response))
                for section in response["sections"]:
                    for item in section["items"]:
                        if 'deviceId' not in item["metadata"].keys():
                            continue
                        device = {
                            "homeId": home_id,
                            "deviceId": item["metadata"]["deviceId"],
                            "nodeId": item["metadata"]["nodeId"],
                            "deviceName": item["title"]["label"],
                            "state": item["state"],
                            "isEnabled": item["isEnabled"],
                            "metadata": item["metadata"],
                            "deviceType": item["metadata"].get("deviceType")
                        }
                        devices.append(device)

                        node_info = await self.get_node(home_id, device.get("nodeId"))
                        self.merge_properties(device, node_info)

                        device_info = await self.get_device(device.get("deviceId"))
                        self.merge_properties(device, device_info)

                        await self.refresh_device(device)

                        LOGGER.debug("device : " + repr(device))
                return devices
            else:
                LOGGER.error("Error on get_items_in_section_for_home. status %s, response %s", resp.status, str(response))
                raise ValueError("bad credentials")

    async def refresh_device(self, device, full=False):
        """Update device details"""
        device_info = await self.get_device(device.get("deviceId"))
        self.merge_properties(device, device_info)
        if not full:
            return device
        if device["type"] == "lights" and device["isEnabled"]:
            light_details = await self.get_light_details(device.get("homeId"), device.get("nodeId"))
            self.merge_properties(device, light_details)
        elif device["type"] == "sensors" and device["isEnabled"]:
            sensor_details = await self.get_sensor_details(device.get("homeId"), device.get("nodeId"), device.get("capabilities", []))
            self.merge_properties(device, sensor_details)
        elif device["type"] == "outlets" and device["isEnabled"]:
            power_details = await self.get_power_details(device.get("homeId"), device.get("nodeId"))
            self.merge_properties(device, power_details)
        elif device.get("deviceType") == "ceiling_fans" and device["isEnabled"]:
            light_details = await self.get_light_details(device.get("homeId"), device.get("nodeId"))
            fan_details = await self.get_fan_details(device.get("homeId"), device.get("nodeId"))
            self.merge_properties(device, light_details)
            self.merge_properties(device, fan_details)
        return device

    async def get_node(self, home_id, node_id):
        """Get details on a node."""
        await self.check_connected()
        async with _session() as session, session.request(
            method="GET",
            url=f"{ENKI_URL}/api-enki-node-agg-prod/v1/nodes/{node_id}",
            headers={"Authorization": f"{self._token_type} {self._access_token}",
                    "X-Gateway-APIKey": ENKI_NODE_API_KEY,
                    "homeId": f"{home_id}"},
            proxy=proxy,) as resp:

                response = await resp.json()
                if resp.status == 200:
                    LOGGER.debug("get_node : " + str(response))
                    return response
                else:
                    LOGGER.error("Error on get_node. status %s, response %s", resp.status, str(response))
                    raise ValueError("bad credentials")

    async def get_device(self, id):
        """Get details on a device."""
        await self.check_connected()
        async with _session() as session, session.request(
            method="GET",
            url=f"{ENKI_URL}/api-enki-referentiel-agg-prod/v1/devices/{id}?version=2.15.0",
            headers={"Authorization": f"{self._token_type} {self._access_token}",
                    "X-Gateway-APIKey": ENKI_REFERENTIEL_API_KEY},
            proxy=proxy,) as resp:

                response = await resp.json()
                if resp.status == 200:
                    LOGGER.debug("get_device : " + str(response))
                    return response
                elif resp.status == 404:
                    LOGGER.warning("get_device skipped for device %s: status %s, response %s", id, resp.status, str(response))
                    return {}
                else:
                    LOGGER.error("Error on get_device. status %s, response %s", resp.status, str(response))
                    raise ValueError("get_device failed")

    async def get_light_details(self, home_id, node_id):
        """Get light state"""
        await self.check_connected()
        async with _session() as session, session.request(
             method="GET",
             url=f"{ENKI_URL}/api-enki-lighting-prod/v1/lighting/{node_id}/check-light-state",
             headers={"Authorization": f"{self._token_type} {self._access_token}",
                      "homeId": home_id,
                      "X-Gateway-APIKey": ENKI_LIGHTS_API_KEY},
             proxy=proxy,) as resp:

                response = await resp.json()
                if resp.status == 200:
                    LOGGER.debug("get_light_details : " + str(response))
                    return response
                elif resp.status in (400, 404):
                    LOGGER.warning("get_light_details skipped for node %s: status %s", node_id, resp.status)
                    return {}
                else:
                    LOGGER.error("Error on get_light_details. status %s, response %s", resp.status, str(response))
                    raise ValueError("bad credentials")

    async def change_light_state(self, home_id, node_id, parameter, value, current_state=None):
        await self.check_connected()

        if current_state is not None:
            data = dict(current_state)
        else:
            details = await self.get_light_details(home_id, node_id)
            data = details.get("lastReportedValue") or {}
            data[parameter] = value

        for attempt in range(2):
            async with _session() as session, session.request(
                method="POST",
                url=f"{ENKI_URL}/api-enki-lighting-prod/v1/lighting/{node_id}/change-light-state",
                headers={"Authorization": f"{self._token_type} {self._access_token}",
                        "homeId": home_id,
                        "X-Gateway-APIKey": ENKI_LIGHTS_API_KEY},
                proxy=proxy,
                json=data) as resp:

                    if resp.status == 202:
                        return
                    if resp.status == 401 and attempt == 0:
                        LOGGER.warning("change_light_state: token expired, reconnecting")
                        await self.connect()
                        continue
                    response = await resp.json()
                    LOGGER.error("Error on change_light_state. status %s, response %s", resp.status, str(response))
                    raise ValueError("change_light_state failed")

    async def get_sensor_details(self, home_id, node_id, capabilities):
        """Get multi-sensor state (temperature, humidity, presence, luminosity, battery)."""
        await self.check_connected()
        result = {}

        async def _get(path, api_key):
            async with _session() as session, session.request(
                method="GET",
                url=f"{ENKI_URL}{path}",
                headers={"Authorization": f"{self._token_type} {self._access_token}",
                         "homeId": home_id,
                         "X-Gateway-APIKey": api_key},
                proxy=proxy,) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        LOGGER.warning("get_sensor_details %s skipped: status %s", path, resp.status)
                        return {}

        if "check_current_humidity" in capabilities:
            data = await _get(f"/api-enki-temperature-humidity-sensor-prod/v1/sensors/{node_id}/check-current-humidity", ENKI_TEMP_HUMIDITY_API_KEY)
            result["humidityValue"] = data.get("lastReportedValue")

        if "check_current_temperature" in capabilities:
            data = await _get(f"/api-enki-temperature-humidity-sensor-prod/v1/sensors/{node_id}/check-current-temperature", ENKI_TEMP_HUMIDITY_API_KEY)
            result["temperatureValue"] = data.get("lastReportedValue")

        if "check_motion_detection" in capabilities:
            data = await _get(f"/api-enki-presence-detector-prod/v1/sensors/{node_id}/check-motion-detection", ENKI_PRESENCE_API_KEY)
            result["presenceValue"] = data.get("lastReportedValue")

        if "check_illuminance_level" in capabilities:
            data = await _get(f"/api-enki-luminosity-sensor-prod/v1/sensors/{node_id}/check-illuminance-level", ENKI_LUMINOSITY_API_KEY)
            result["illuminanceValue"] = data.get("lastReportedValue")

        if "check_battery_health" in capabilities:
            data = await _get(f"/api-enki-battery-health-prod/v1/sensors/{node_id}/check-battery-health", ENKI_BATTERY_API_KEY)
            result["batteryValue"] = data.get("lastReportedValue")

        LOGGER.debug("get_sensor_details %s: %s", node_id, result)
        return result

    async def get_power_details(self, home_id, node_id, endpoint=None):
        """Get power outlet state."""
        await self.check_connected()
        endpoint_query = f"?endpoints={endpoint}" if endpoint is not None else ""
        async with _session() as session, session.request(
            method="GET",
            url=f"{ENKI_URL}/api-enki-power-prod/v1/power/{node_id}/check-electrical-power{endpoint_query}",
            headers={"Authorization": f"{self._token_type} {self._access_token}",
                     "homeId": home_id,
                     "X-Gateway-APIKey": ENKI_POWER_API_KEY},
            proxy=proxy,) as resp:
                if resp.status == 200:
                    response = await resp.json()
                    LOGGER.debug("get_power_details : %s", response)
                    return response
                else:
                    LOGGER.warning("get_power_details skipped for node %s: status %s", node_id, resp.status)
                    return {}

    async def change_power_state(self, home_id, node_id, power_on: bool, endpoint=None):
        """Turn power outlet on or off."""
        await self.check_connected()
        endpoint_query = f"?endpoints={endpoint}" if endpoint is not None else ""
        async with _session() as session, session.request(
            method="POST",
            url=f"{ENKI_URL}/api-enki-power-prod/v1/power/{node_id}/switch-electrical-power{endpoint_query}",
            headers={"Authorization": f"{self._token_type} {self._access_token}",
                     "homeId": home_id,
                     "X-Gateway-APIKey": ENKI_POWER_API_KEY},
            proxy=proxy,
            json={"value": "ON" if power_on else "OFF"}) as resp:
                if resp.status not in (200, 202):
                    response = await resp.json()
                    LOGGER.error("Error on change_power_state. status %s, response %s", resp.status, str(response))
                    raise ValueError("change_power_state failed")

    async def get_fan_details(self, home_id, node_id):
        power_details = await self.get_power_details(home_id, node_id, endpoint=2)
        speed_details = await self.get_fan_speed_details(home_id, node_id)
        return {
            "fanPowerValue": power_details.get("lastReportedValue"),
            "fanSpeedValue": speed_details.get("lastReportedValue"),
        }

    async def get_fan_speed_details(self, home_id, node_id):
        await self.check_connected()
        async with _session() as session, session.request(
            method="GET",
            url=f"{ENKI_URL}/api-enki-airflow-prod/v1/airflow/{node_id}/check-fan-speed",
            headers={"Authorization": f"{self._token_type} {self._access_token}",
                     "homeId": home_id,
                     "X-Gateway-APIKey": ENKI_AIRFLOW_API_KEY},
            proxy=proxy,) as resp:
                if resp.status == 200:
                    response = await resp.json()
                    LOGGER.debug("get_fan_speed_details : %s", response)
                    return response
                LOGGER.warning("get_fan_speed_details skipped for node %s: status %s", node_id, resp.status)
                return {}

    async def change_fan_speed(self, home_id, node_id, value: int):
        await self.check_connected()
        async with _session() as session, session.request(
            method="POST",
            url=f"{ENKI_URL}/api-enki-airflow-prod/v1/airflow/{node_id}/change-fan-speed",
            headers={"Authorization": f"{self._token_type} {self._access_token}",
                     "homeId": home_id,
                     "X-Gateway-APIKey": ENKI_AIRFLOW_API_KEY},
            proxy=proxy,
            json={"value": value}) as resp:
                if resp.status in (200, 202):
                    return
                response = await resp.json()
                LOGGER.error("Error on change_fan_speed. status %s, response %s", resp.status, str(response))
                raise ValueError("change_fan_speed failed")

# *******************************************************

    async def get_devices(self) -> list[dict[str, Any]]:
        """Get devices on api."""
        homes = await self.get_homes()
        devices = []
        for home in homes:
            devices.extend(await self.get_items_in_section_for_home(home))

        is_first_load = not hasattr(self, '_devices_cache')
        cache = {d["nodeId"]: d for d in self._devices_cache} if not is_first_load else {}
        for device in devices:
            node_id = device["nodeId"]
            if device.get("type") == "lights":
                if is_first_load:
                    await self.refresh_device(device, full=True)
                elif node_id in cache and "lastReportedValue" in cache[node_id]:
                    device["lastReportedValue"] = cache[node_id]["lastReportedValue"]
            elif device.get("type") in ("sensors", "outlets") or device.get("deviceType") == "ceiling_fans":
                await self.refresh_device(device, full=True)

        self._devices_cache = devices
        return devices

class APIAuthError(Exception):
    """Exception class for auth error."""

class APIConnectionError(Exception):
    """Exception class for connection error."""
