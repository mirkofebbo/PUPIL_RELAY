# device_monitor.py
import os
import json
import asyncio
from pupil_labs.realtime_api import Device
from utils.utils import read_json_file, write_json_file

JSON_FILE_PATH = 'devices.json'

async def monitor_device_status():
    while True:
        if not os.path.exists(JSON_FILE_PATH):
            print("No devices.json file found.")
            await asyncio.sleep(10)
            continue

        with open(JSON_FILE_PATH, 'r') as f:
            devices = json.load(f)

        tasks = []
        for device_data in devices:
            tasks.append(update_device_status(device_data))

        await asyncio.gather(*tasks)

        # Save the updated device information
        with open(JSON_FILE_PATH, 'w') as f:
            json.dump(devices, f, indent=4)

        await asyncio.sleep(30) 

async def update_device_status(device_data):
    device_ip = device_data["ip"]
    device_port = device_data["port"]
    try:
        async with Device(device_ip, device_port) as device:
            status = await device.get_status()
            device_data.update({
                "available": True,
                "battery_level": status.phone.battery_level,
                "glasses_serial": status.hardware.glasses_serial or "unknown",
                "world_camera_serial": status.hardware.world_camera_serial or "unknown",
                # Additional status fields can be added here
            })
            device_data["relay_failed"] = False  # Reset relay_failed flag
            print(f"[Device Monitor] Updated status for device {device_data['device_id']}")
    except Exception as e:
        print(f"[Device Monitor] Could not update status for device {device_data['device_id']}: {e}")
        device_data["available"] = False

async def update_device_status(device_data):
    """Update the status of a single device."""
    device_ip = device_data["ip"]
    device_port = device_data["port"]
    try:
        async with Device(device_ip, device_port) as device:
            status = await device.get_status()
            device_data.update({
                "available": True,
                "battery_level": status.phone.battery_level,
                "glasses_serial": status.hardware.glasses_serial,
                "world_camera_serial": status.hardware.world_camera_serial,
                # Additional status fields can be added here
            })
            print(f"[Device Monitor] Updated status for device {device_data['device_id']}")
    except Exception as e:
        print(f"[Device Monitor] Could not update status for device {device_data['device_id']}: {e}")
        device_data["available"] = False

if __name__ == "__main__":
    asyncio.run(monitor_device_status())