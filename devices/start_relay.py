# start_relay.py

import asyncio
import json
import logging
import os
from pupil_labs.lsl_relay import relay

async def start_relays(json_file_path):
    if not os.path.exists(json_file_path):
        print("No devices.json file found.")
        return

    with open(json_file_path, 'r') as f:
        devices = json.load(f)

    tasks = []
    for device_data in devices:
        if device_data.get("available"):
            tasks.append(start_device_relay(device_data))
        else:
            print(f"Device {device_data['device_id']} is not available.")

    await asyncio.gather(*tasks, return_exceptions=True)

def start_device_relay_task(device_data):
    asyncio.run(start_device_relay(device_data))

async def start_device_relay(device_data):
    device_ip = device_data["ip"]
    device_port = device_data["port"]
    device_identifier = device_data["device_id"]
    outlet_prefix = "pupil_labs"
    model = "Pupil Labs Device"
    module_serial = device_data.get("glasses_serial", "unknown")
    time_sync_interval = 60

    try:
        await relay.Relay.run(
            device_ip=device_ip,
            device_port=device_port,
            device_identifier=device_identifier,
            outlet_prefix=outlet_prefix,
            model=model,
            module_serial=module_serial,
            time_sync_interval=time_sync_interval,
        )
        print(f"Started relay for device {device_identifier}")
        device_data["lsl_streaming"] = True
    except Exception as e:
        print(f"Failed to start relay for device {device_identifier}: {e}")
        device_data["lsl_streaming"] = False

