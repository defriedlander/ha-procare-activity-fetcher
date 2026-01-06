"""The Procare Activities integration."""
import asyncio
import logging
from datetime import timedelta, datetime, time
import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import ConfigEntryAuthFailed

from .const import DOMAIN, PLATFORMS, CONF_SCHOOL_NAME
from .api import ProcareApi, ProcareAuthError

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Procare Activities from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    username = entry.data["username"]
    password = entry.data["password"]
    selected_kid_id = entry.data["kid_id"]
    school_name = entry.data.get(CONF_SCHOOL_NAME)

    # Create a single, persistent session for the integration
    session = aiohttp.ClientSession()
    api = ProcareApi(session, username, password, school_name)

    async def async_update_data():
        """Fetch data from API endpoint."""
        # Check if current time is within polling hours (8 AM - 7 PM)
        now = datetime.now().time()
        start_time = time(7, 0)  # 8:00 AM
        end_time = time(19, 0)   # 7:00 PM
        
        if not (start_time <= now <= end_time):
            _LOGGER.debug(
                "Outside polling hours (8 AM - 7 PM). Current time: %s. Skipping update.",
                now.strftime("%H:%M")
            )
            # Return existing data if available, otherwise empty list
            return getattr(async_update_data, '_last_data', [])
        
        try:
            data = await api.async_get_activities(selected_kid_id)
            # Cache the last successful data
            async_update_data._last_data = data
            return data
        except ProcareAuthError as err:
            raise ConfigEntryAuthFailed from err
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="procare_activities_sensor",
        update_method=async_update_data,
        update_interval=timedelta(minutes=35),
    )
    
    # Fetch initial data so we have it when platforms are set up.
    await coordinator.async_refresh()

    # Store the coordinator and the session together
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "session": session
    }

    # Use the modern method to forward the setup to all platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Correctly unload all platforms associated with the config entry
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Properly close the session and remove the entry data
        await hass.data[DOMAIN][entry.entry_id]["session"].close()
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
