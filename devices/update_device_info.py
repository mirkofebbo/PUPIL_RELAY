# update_device_info.py

import asyncio
import json
import os
from pupil_labs.realtime_api import Device

async def fetch_device_info(json_file_path):
    if not os.path.exists(json_file_path):
        print("No devices.json file found.")
        return

    with open(json_file_path, 'r') as f:
        devices = json.load(f)

    tasks = []
    for device_data in devices:
        tasks.append(update_device_info(device_data))

    await asyncio.gather(*tasks)

    # Save the updated device information
    with open(json_file_path, 'w') as f:
        json.dump(devices, f, indent=4)

async def update_device_status(device_data):
    device_ip = device_data["ip"]
    device_port = device_data["port"]
    try:
        async with Device(device_ip, device_port) as device:
            status = await device.get_status()
            device_data.update({
                "available": True,
                "battery_level": status.phone.battery_level if status.phone.battery_level is not None else 0,
                "glasses_serial": status.hardware.glasses_serial or "unknown",
                "world_camera_serial": status.hardware.world_camera_serial or "unknown",
            })
            print(f"[Device Monitor] Updated status for device {device_data['device_id']}")
    except Exception as e:
        print(f"[Device Monitor] Could not update status for device {device_data['device_id']}: {e}")
        device_data["available"] = False

