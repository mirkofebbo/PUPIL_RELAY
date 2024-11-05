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

async def update_device_info(device_data):
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
            print(f"Updated device info: {device_data['device_id']}")
    except Exception as e:
        print(f"Could not fetch info for device {device_data['device_id']}: {e}")
        device_data["available"] = False

