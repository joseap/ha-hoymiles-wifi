"""Support for Hoymiles select entities."""

import dataclasses
from dataclasses import dataclass
from enum import Enum
import logging

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from hoymiles_wifi.hoymiles import BMSWorkingMode

from .const import (
    CONF_DTU_SERIAL_NUMBER,
    CONF_HYBRID_INVERTERS,
    DOMAIN,
    HASS_DTU,
    HASS_ENERGY_STORAGE_DATA_COORDINATOR,
)
from .coordinator import HoymilesEnergyStorageUpdateCoordinator
from .entity import HoymilesCoordinatorEntity, HoymilesEntityDescription


@dataclass(frozen=True)
class HoymilesSelectSensorEntityDescriptionMixin:
    """Mixin for required keys."""


@dataclass(frozen=True)
class HoymilesSelectSensorEntityDescription(
    HoymilesEntityDescription, SelectEntityDescription
):
    """Describes Hoymiles select sensor entity."""

    serial_number: str = None


BMS_WORKING_MODE_OPTIONS = {
    "self_use": "Self Use",
    "economic": "Economic",
    "backup_power": "Backup Power",
    "pure_off_grid": "Pure Off-Grid",
    "forced_charging": "Forced Charging",
    "forced_discharge": "Forced Discharge",
    "peak_shaving": "Peak Shaving",
    "time_of_use": "Time of Use",
}

BMS_WORKING_MODE_OPTIONS_LIST = list(BMS_WORKING_MODE_OPTIONS.keys())

BATTERY_WORKING_MODE_SELECT = HoymilesSelectSensorEntityDescription(
    key="battery_working_mode",
    translation_key="battery_working_mode",
    options=BMS_WORKING_MODE_OPTIONS_LIST,
    icon="mdi:battery-charging",
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Hoymiles select entities."""
    hass_data = hass.data[DOMAIN][config_entry.entry_id]
    dtu = hass_data.get(HASS_DTU)
    energy_storage_coordinator = hass_data.get(HASS_ENERGY_STORAGE_DATA_COORDINATOR)
    hybrid_inverters = config_entry.data.get(CONF_HYBRID_INVERTERS, [])
    dtu_serial_number = config_entry.data[CONF_DTU_SERIAL_NUMBER]

    if not hybrid_inverters or not dtu or not energy_storage_coordinator:
        return

    sensors = []
    for inverter in hybrid_inverters:
        inverter_serial = inverter["inverter_serial_number"]
        updated_description = dataclasses.replace(
            BATTERY_WORKING_MODE_SELECT,
            serial_number=inverter_serial,
        )
        sensors.append(
            HoymilesBatteryWorkingModeSelect(
                config_entry,
                updated_description,
                energy_storage_coordinator,
                dtu,
                int(dtu_serial_number),
                inverter_serial,
            )
        )

    async_add_entities(sensors)


class HoymilesBatteryWorkingModeSelect(HoymilesCoordinatorEntity, SelectEntity):
    """Hoymiles Battery Working Mode select entity."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        description: HoymilesSelectSensorEntityDescription,
        coordinator: HoymilesEnergyStorageUpdateCoordinator,
        dtu,
        dtu_serial_number: int,
        inverter_serial_number: int,
    ) -> None:
        """Initialize the HoymilesBatteryWorkingModeSelect."""
        super().__init__(config_entry, description, coordinator)
        self._dtu = dtu
        self._dtu_serial_number = dtu_serial_number
        self._inverter_serial_number = inverter_serial_number
        self._attr_options = BMS_WORKING_MODE_OPTIONS_LIST
        self._current_mode = None

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        if self.coordinator.data is None:
            return None

        # Find the inverter data in the coordinator
        for inverter_data in self.coordinator.data or []:
            if (
                inverter_data
                and hasattr(inverter_data, "battery_management")
                and inverter_data.battery_management.internal_charge_mode is not None
            ):
                # We need to fetch the working mode separately
                return self._current_mode

        return None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option not in BMS_WORKING_MODE_OPTIONS:
            raise HomeAssistantError(f"Invalid battery working mode: {option}")

        bms_mode = BMSWorkingMode[option.upper()]

        # Get current reserve SOC from sensor or default
        rev_soc = 20  # Default, should be read from sensor

        _LOGGER.debug("Setting BMS mode to %s for inverter %s", option, self._inverter_serial_number)

        try:
            await self._dtu.async_set_energy_storage_working_mode(
                dtu_serial_number=self._dtu_serial_number,
                inverter_serial_number=self._inverter_serial_number,
                bms_working_mode=bms_mode,
                rev_soc=rev_soc,
            )
            self._current_mode = option
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error("Failed to set BMS mode: %s", e)
            raise HomeAssistantError(f"Failed to set battery mode: {e}")

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        super()._handle_coordinator_update()
        # Try to read current mode from coordinator data
        # Note: Working mode is fetched separately, not in regular polling