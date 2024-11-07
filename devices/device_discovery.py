import asyncio
import json
import os
import time
from pupil_labs.realtime_api.discovery import discover_devices, DiscoveredDeviceInfo
from utils.utils import read_json_file, write_json_file, DeviceModel
import logging 

LOG_FILE_NAME = 'lsl_relay.log'
JSON_FILE_PATH = 'devices.json'

# Configure logging
LOG_FILE_NAME = 'device_monitor.log'
logging.basicConfig(level=logging.DEBUG, filename=LOG_FILE_NAME, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

async def discover_and_log_devices():
    """Continuously discover devices and update the devices.json file."""
    seen_devices = {}  # Dictionary to track changes by device_id

    async for device_info in discover_devices():
        device_ip = device_info.addresses[0]
        device_port = device_info.port

        # Extract device_id from device_info.name (adjust split logic as needed)
        if ':' in device_info.name:
            device_id = device_info.name.split(":")[1]
        else:
            device_id = device_info.name  # Fallback if format differs

        # Create a DeviceModel instance with discovered data
        device_data = DeviceModel(
            ip=device_ip,
            port=device_port,
            name=device_id, 
            device_id=device_id,
            available=True,
            connected=False,
            lsl_streaming=False,
            recording=False,
            battery_level=None,
            glasses_serial=None,
            world_camera_serial=None,
            error_message=""
        )

        # Only update if data has changed
        if device_id not in seen_devices or not compare_device_data(seen_devices[device_id], device_data):
            seen_devices[device_id] = device_data
            await update_devices_json(device_data)


        # Introduce a small delay to prevent flooding the discovery process
        await asyncio.sleep(1)  # Delay to prevent high-frequency updates

def compare_device_data(existing_data: DeviceModel, new_data: DeviceModel) -> bool:
    """Compare existing and new device data to avoid redundant updates."""
    return (
        existing_data.ip == new_data.ip and
        existing_data.port == new_data.port and
        existing_data.available == new_data.available
    )

async def update_devices_json(device_data: DeviceModel):
    """Update the devices.json file with the new or updated device data."""
    devices = await read_json_file(JSON_FILE_PATH)  # Returns List[DeviceModel]

    # Check if the device already exists
    existing_device = next((d for d in devices if d.device_id == device_data.device_id), None)
    if existing_device is None:
        devices.append(device_data)
        await write_json_file(JSON_FILE_PATH, devices)
        print(f"[Device Discovery] Added new device: {device_data.device_id}")
    else:
        # Only update if data has changed
        if not compare_device_data(existing_device, device_data):
            existing_device.ip = device_data.ip
            existing_device.port = device_data.port
            existing_device.available = device_data.available
            # Keep other fields intact (connected, lsl_streaming, etc.)
            await write_json_file(JSON_FILE_PATH, devices)
            print(f"[Device Discovery] Updated device: {device_data.device_id}")

async def run_device_discovery():
    """Run the device discovery loop."""
    try:
        while True:
            await discover_and_log_devices()
    except asyncio.CancelledError:
        logger.info("[Device Discovery] Device discovery task cancelled")
    except Exception as e:
        print(f"[Device Discovery] Error during discovery: {e}")
        await asyncio.sleep(10)
    finally:
        logger.info("[Device Discovery] Cleanup completed")
