# utils/utils.py

import aiofiles
import json
import os
from pydantic import BaseModel, ValidationError
from typing import List, Optional
from filelock import AsyncFileLock

class DeviceModel(BaseModel):
    ip: str
    port: int
    name: str
    device_id: str
    available: bool
    battery_level: Optional[int] = None
    glasses_serial: Optional[str] = None
    world_camera_serial: Optional[str] = None
    connected: bool = False
    lsl_streaming: bool = False
    recording: bool = False
    error_message: str = ""

LOCK_PATH = 'devices.json.lock'

async def read_json_file(file_path: str) -> List[DeviceModel]:
    if not os.path.exists(file_path):
        return []
    async with AsyncFileLock(LOCK_PATH):
        async with aiofiles.open(file_path, 'r') as f:
            contents = await f.read()
            try:
                data = json.loads(contents)
                # Validate each device entry
                validated_devices = []
                for device in data:
                    try:
                        validated_device = DeviceModel(**device)
                        validated_devices.append(validated_device)
                    except ValidationError as ve:
                        print(f"Validation error for device {device.get('device_id', 'Unknown')}: {ve}")
                        # Optionally, handle incomplete devices here
                return validated_devices
            except json.JSONDecodeError:
                print("JSON decode error. Returning empty device list.")
                return []

async def write_json_file(file_path: str, devices: List[DeviceModel]):
    async with AsyncFileLock(LOCK_PATH):
        async with aiofiles.open(file_path, 'w') as f:
            # Convert Pydantic models to dicts
            data = [device.dict() for device in devices]
            await f.write(json.dumps(data, indent=4))



async def update_device_in_json(file_path: str,device_data: DeviceModel):
    """Update the devices.json file with the new or updated device data."""
    devices = await read_json_file(file_path)
    device_found = False
    for idx, d in enumerate(devices):
        if d.device_id == device_data.device_id:
            devices[idx] = device_data
            device_found = True
            break
    if not device_found:
        devices.append(device_data)

    await write_json_file(file_path, devices)
