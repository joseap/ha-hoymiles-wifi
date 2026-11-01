"""Support for Hoymiles number sensors."""

import dataclasses
from dataclasses import dataclass
from enum import Enum
import logging
import math

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from hoymiles_wifi.const import (
    MAX_TEMPORARY_POWER_LIMIT_WATTS,
    MIN_TEMPORARY_POWER_LIMIT_WATTS,
)
from hoymiles_wifi.hoymiles import DTUType, get_dtu_model_type, BMSWorkingMode

from .const import (
    CONF_DTU_SERIAL_NUMBER,
    CONF_HYBRID_INVERTERS,
    CONF_INVERTERS,
    CONF_THREE_PHASE_INVERTERS,
    DOMAIN,
    HASS_CONFIG_COORDINATOR,
    HASS_DATA_COORDINATOR,
    HASS_ENERGY_STORAGE_DATA_COORDINATOR,
)
from .coordinator import HoymilesRealDataUpdateCoordinator
from .entity import HoymilesCoordinatorEntity, HoymilesEntityDescription


class SetAction(Enum):
    """Enum for set actions."""

    POWER_LIMIT = 1
    POWER_LIMIT_TEMPORARY = 2


@dataclass(frozen=True)
class HoymilesNumberSensorEntityDescriptionMixin:
    """Mixin for required keys."""


@dataclass(frozen=True)
class HoymilesNumberSensorEntityDescription(
    HoymilesEntityDescription, NumberEntityDescription
):
    """Describes Hoymiles number sensor entity."""

    set_action: SetAction = None
    serial_number: str = None
    is_dtu_sensor: bool = False


CONFIG_CONTROL_ENTITIES = (
    HoymilesNumberSensorEntityDescription(
        key="limit_power_mypower",
        translation_key="limit_power_mypower",
        mode=NumberMode.SLIDER,
        device_class=NumberDeviceClass.POWER_FACTOR,
        set_action=SetAction.POWER_LIMIT,
        is_dtu_sensor=True,
    ),
    HoymilesNumberSensorEntityDescription(
        key="power_limit_temporary",
        translation_key="power_limit_temporary",
        mode=NumberMode.BOX,
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_min_value=MIN_TEMPORARY_POWER_LIMIT_WATTS,
        native_max_value=MAX_TEMPORARY_POWER_LIMIT_WATTS,
        native_step=0.1,
        set_action=SetAction.POWER_LIMIT_TEMPORARY,
        is_dtu_sensor=True,
        supported_dtu_types=[DTUType.DTUBI],
    ),
)

_LOGGER = logging.getLogger(__name__)


BATTERY_RESERVE_SOC_ENTITY = HoymilesNumberSensorEntityDescription(
    key="battery_reserve_soc",
    translation_key="battery_reserve_soc",
    mode=NumberMode.SLIDER,
    device_class=NumberDeviceClass.BATTERY,
    native_unit_of_measurement=PERCENTAGE,
    native_min_value=0,
    native_max_value=100,
    native_step=1,
    icon="mdi:battery-heart",
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Hoymiles number entities."""
    hass_data = hass.data[DOMAIN][config_entry.entry_id]
    config_coordinator = hass_data.get(HASS_CONFIG_COORDINATOR, None)
    data_coordinator = hass_data.get(HASS_DATA_COORDINATOR)
    energy_storage_coordinator = hass_data.get(HASS_ENERGY_STORAGE_DATA_COORDINATOR)
    single_phase_inverters = config_entry.data.get(CONF_INVERTERS, [])
    three_phase_inverters = config_entry.data.get(CONF_THREE_PHASE_INVERTERS, [])
    hybrid_inverters = config_entry.data.get(CONF_HYBRID_INVERTERS, [])
    dtu_serial_number = config_entry.data[CONF_DTU_SERIAL_NUMBER]

    if single_phase_inverters or three_phase_inverters:
        sensors = []
        for description in CONFIG_CONTROL_ENTITIES:
            if description.supported_dtu_types is not None:
                try:
                    dtu_type = get_dtu_model_type(bytes.fromhex(dtu_serial_number))
                except ValueError:
                    _LOGGER.debug("Cannot determine DTU type for %s", dtu_serial_number)
                    continue
                if dtu_type not in description.supported_dtu_types:
                    continue
            if description.is_dtu_sensor is True:
                updated_description = dataclasses.replace(
                    description, serial_number=dtu_serial_number
                )
                sensors.append(
                    HoymilesNumberEntity(
                        config_entry,
                        updated_description,
                        data_coordinator
                        if description.set_action == SetAction.POWER_LIMIT_TEMPORARY
                        else config_coordinator,
                        data_coordinator,
                    )
                )
        async_add_entities(sensors)

    # Battery reserve SOC for hybrid inverters
    if hybrid_inverters and energy_storage_coordinator:
        battery_sensors = []
        for inverter in hybrid_inverters:
            inverter_serial = inverter["inverter_serial_number"]
            battery_description = dataclasses.replace(
                BATTERY_RESERVE_SOC_ENTITY,
                serial_number=inverter_serial,
            )
            battery_sensors.append(
                HoymilesBatteryReserveSOCNumber(
                    config_entry,
                    battery_description,
                    energy_storage_coordinator,
                    int(dtu_serial_number),
                    inverter_serial,
                )
            )
        async_add_entities(battery_sensors)


async_add_entities(battery_sensors)


BATTERY_RESERVE_SOC_ENTITY = HoymilesNumberSensorEntityDescription(
    key="battery_reserve_soc",
    translation_key="battery_reserve_soc",
    mode=NumberMode.SLIDER,
    device_class=NumberDeviceClass.BATTERY,
    native_unit_of_measurement=PERCENTAGE,
    native_min_value=0,
    native_max_value=100,
    native_step=1,
    icon="mdi:battery-heart",
)


class HoymilesBatteryReserveSOCNumber(HoymilesCoordinatorEntity, NumberEntity):
    """Hoymiles Battery Reserve SOC number entity."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        description: HoymilesNumberSensorEntityDescription,
        coordinator,
        dtu_serial_number: int,
        inverter_serial_number: int,
    ) -> None:
        """Initialize the HoymilesBatteryReserveSOCNumber."""
        super().__init__(config_entry, description, coordinator)
        self._dtu_serial_number = dtu_serial_number
        self._inverter_serial_number = inverter_serial_number
        self._native_value = None
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_native_min_value = 0
        self._attr_native_max_value = 100
        self._attr_native_step = 1
        self._attr_mode = NumberMode.SLIDER
        self._attr_device_class = NumberDeviceClass.BATTERY

    @property
    def native_value(self) -> float | None:
        """Return the current reserve SOC."""
        if self.coordinator.data is None:
            return self._native_value

        for inverter_data in self.coordinator.data or []:
            if (
                inverter_data
                and hasattr(inverter_data, "battery_management")
                and hasattr(inverter_data.battery_management, "working_mode")
                and inverter_data.battery_management.working_mode is not None
            ):
                # Get reserve SOC from working mode config
                if hasattr(inverter_data.battery_management, "selfu") and inverter_data.battery_management.selfu:
                    self._native_value = float(inverter_data.battery_management.selfu.rev_soc)
                return self._native_value

        return self._native_value

    async def async_set_native_value(self, value: float) -> None:
        """Set the reserve SOC."""
        if not isinstance(value, (int, float)) or not 0 <= value <= 100:
            raise HomeAssistantError("Reserve SOC must be between 0 and 100")

        soc = int(value)
        _LOGGER.debug("Setting reserve SOC to %s for inverter %s", soc, self._inverter_serial_number)

        hass_data = self.hass.data[DOMAIN][self.config_entry.entry_id]
        dtu = hass_data.get(HASS_DTU)
        
        if not dtu:
            raise HomeAssistantError("DTU not available")

        # Get current working mode from coordinator data
        current_mode = BMSWorkingMode.SELF_USE
        if self.coordinator.data is not None:
            for inv_data in self.coordinator.data or []:
                if inv_data and hasattr(inv_data, "battery_management") and inv_data.battery_management.working_mode is not None:
                    current_mode = BMSWorkingMode(inv_data.battery_management.working_mode)
                    break

        try:
            await dtu.async_set_energy_storage_working_mode(
                dtu_serial_number=self._dtu_serial_number,
                inverter_serial_number=self._inverter_serial_number,
                bms_working_mode=current_mode,
                rev_soc=soc,
            )
            self._native_value = float(soc)
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error("Failed to set reserve SOC: %s", e)
            raise HomeAssistantError(f"Failed to set reserve SOC: {e}")


class HoymilesNumberEntity(HoymilesCoordinatorEntity, NumberEntity):
    """Hoymiles Number entity."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        description: HoymilesNumberSensorEntityDescription,
        coordinator: HoymilesCoordinatorEntity,
        power_limit_coordinator: HoymilesRealDataUpdateCoordinator,
    ) -> None:
        """Initialize the HoymilesNumberEntity."""
        super().__init__(config_entry, description, coordinator)
        self._set_action = description.set_action
        self._power_limit_coordinator = power_limit_coordinator
        self._native_value = None
        self._assumed_state = False

        self.update_state_value()

    async def async_added_to_hass(self) -> None:
        """Listen to live readback as well as configuration fallback changes."""
        await super().async_added_to_hass()
        if (
            self._set_action == SetAction.POWER_LIMIT
            and self._power_limit_coordinator is not self.coordinator
        ):
            self.async_on_remove(
                self._power_limit_coordinator.async_add_listener(
                    self._handle_coordinator_update
                )
            )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.update_state_value()
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> float:
        """Get the native value of the entity."""
        return self._native_value

    @property
    def assumed_state(self):
        """Return the assumed state of the entity."""
        return self._assumed_state or (
            self._set_action == SetAction.POWER_LIMIT_TEMPORARY
            and self._power_limit_coordinator.data_is_stale
        )

    @property
    def available(self) -> bool:
        """Keep persistent controls available when either read source is responding."""
        if self._set_action == SetAction.POWER_LIMIT_TEMPORARY:
            return super().available
        return any(
            source.last_update_success and source.data is not None
            for source in (self.coordinator, self._power_limit_coordinator)
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set the native value of the entity.

        Args:
            value (float): The value to set.
        """
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not self.native_min_value <= value <= self.native_max_value
        ):
            raise HomeAssistantError("Power limit value out of range")

        dtu = self.coordinator.get_dtu()
        if self._set_action == SetAction.POWER_LIMIT:
            response = await dtu.async_set_power_limit(value)
            self._validate_command_response(response)
            self._power_limit_coordinator.set_persistent_power_limit_target(value)
            await self._power_limit_coordinator.async_request_refresh()
            if self.coordinator.last_update_success:
                await self.coordinator.async_request_refresh()
            self.update_state_value()
            return
        elif self._set_action == SetAction.POWER_LIMIT_TEMPORARY:
            response = await dtu.async_set_power_limit_temporary(value)
            self._validate_command_response(response)
            value = math.floor(value * 10 + 0.5) / 10
            self._power_limit_coordinator.set_temporary_power_limit_target(value)
            await self.coordinator.async_request_refresh()
            self.update_state_value()
            return
        else:
            raise HomeAssistantError("Invalid set action")

    def _validate_command_response(self, response) -> None:
        """Keep the previous interpretation when the DTU rejects a command."""
        if response is None:
            raise HomeAssistantError("DTU did not acknowledge the power limit")
        if response.err_code != 0:
            raise HomeAssistantError(
                f"DTU rejected the power limit (error {response.err_code})"
            )

    def update_state_value(self):
        """Read persistent configuration or the temporary live-data echo."""

        if self._set_action == SetAction.POWER_LIMIT_TEMPORARY:
            self._native_value = self._power_limit_coordinator.temporary_power_limit
            self._assumed_state = (
                self._native_value is not None
                and not self._power_limit_coordinator.temporary_power_limit_confirmed
            )
            return

        self._native_value, self._assumed_state = (
            self._power_limit_coordinator.resolve_persistent_power_limit(
                self.coordinator
            )
        )
