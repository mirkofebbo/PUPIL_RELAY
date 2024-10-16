# pupil_labs/lsl_relay/discovery.py

import asyncio
from typing import List
from pupil_labs.realtime_api.discovery import Network, DiscoveredDeviceInfo

async def discover_devices(timeout: int = 10) -> List[DiscoveredDeviceInfo]:
    devices = []
    async with Network() as network:
        await network.wait_for_new_device(timeout_seconds=timeout)
        devices = network.devices
    return devices