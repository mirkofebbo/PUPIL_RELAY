# device_discovery.py

import asyncio
import json
import os
import time
from pupil_labs.realtime_api.discovery import discover_devices, DiscoveredDeviceInfo
from utils.utils import read_json_file, write_json_file

JSON_FILE_PATH = 'devices.json'
async def discover_and_log_devices():
    """Continuously discover devices and update the devices.json file."""
    async for device_info in discover_devices():
        device_ip = device_info.addresses[0]
        device_port = device_info.port
        device_id = device_info.name.split(":")[1]

        device_data = {
            "ip": device_ip,
            "port": device_port,
            "name": device_id, 
            "device_id": device_id,
            "available": True,
            "connected": False,
            "lsl_streaming": False,
            "recording": False,
            "battery_level": None,
            "glasses_serial": None,
            "world_camera_serial": None,
        }

        await update_devices_json(device_data)

async def update_devices_json(device_data):
    """Update the devices.json file with the new or updated device data."""
    devices = await read_json_file(JSON_FILE_PATH)

    # Check if the device already exists
    existing_device = next((d for d in devices if d["device_id"] == device_data["device_id"]), None)
    if existing_device is None:
        devices.append(device_data)
        await write_json_file(JSON_FILE_PATH, devices)
        print(f"[Device Discovery] Added new device: {device_data['device_id']}")
    else:
        # Update existing device data
        existing_device.update(device_data)
        await write_json_file(JSON_FILE_PATH, devices)
        print(f"[Device Discovery] Updated device: {device_data['device_id']}")

async def run_device_discovery():
    """Run the device discovery loop."""
    while True:
        try:
            await discover_and_log_devices()
        except Exception as e:
            print(f"[Device Discovery] Error during discovery: {e}")
            await asyncio.sleep(5)  # Wait before retrying

if __name__ == "__main__":
    asyncio.run(run_device_discovery())