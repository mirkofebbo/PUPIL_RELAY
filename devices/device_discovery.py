# api_server.py

import asyncio
import logging
from typing import List
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from pupil_labs.realtime_api import Device
from pupil_labs.realtime_api.discovery import discover_devices
from utils.utils import read_json_file, write_json_file, DeviceModel

app = FastAPI()
JSON_FILE_PATH = 'devices.json'

# Configure logging
LOG_FILE_NAME = 'api_server.log'
logging.basicConfig(level=logging.DEBUG, filename=LOG_FILE_NAME, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update with your frontend's origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Models
class DeviceActionRequest(BaseModel):
    device_ids: List[str]

# API Endpoints
@app.get("/devices", response_model=List[DeviceModel])
async def get_devices():
    devices = await read_json_file(JSON_FILE_PATH)
    return devices

@app.post("/devices/start_recording")
async def start_recordings(request: DeviceActionRequest, background_tasks: BackgroundTasks):
    devices = await read_json_file(JSON_FILE_PATH)
    target_devices = [d for d in devices if d.device_id in request.device_ids]

    if not target_devices:
        raise HTTPException(status_code=404, detail="No matching devices found.")

    for device_data in target_devices:
        background_tasks.add_task(start_device_recording_task, device_data)

    return {"message": "Recordings are starting."}

@app.post("/devices/stop_recording")
async def stop_recordings(request: DeviceActionRequest, background_tasks: BackgroundTasks):
    devices = await read_json_file(JSON_FILE_PATH)
    target_devices = [d for d in devices if d.device_id in request.device_ids]

    if not target_devices:
        raise HTTPException(status_code=404, detail="No matching devices found.")
            
    for device_data in target_devices:
        background_tasks.add_task(stop_device_recording_task, device_data)

    return {"message": "Recordings are stopping."}

async def start_device_recording_task(device_data: DeviceModel):
    """Start recording on a single device."""
    device_ip = device_data.ip
    device_port = device_data.port
    device_id = device_data.device_id
    try:
        async with Device(device_ip, device_port) as device:
            await device.recording_start()
            logger.info(f"Recording started for device {device_id}")
            device_data.recording = True
    except Exception as e:
        logger.error(f"Could not start recording for device {device_id}: {e}")
        device_data.recording = False
    
    # Update the devices.json file
    await update_device_in_json(device_data)

async def stop_device_recording_task(device_data: DeviceModel):
    """Stop recording on a single device."""
    device_ip = device_data.ip
    device_port = device_data.port
    device_id = device_data.device_id
    try:
        async with Device(device_ip, device_port) as device:
            await device.recording_stop_and_save()
            logger.info(f"Recording stopped for device {device_id}")
            device_data.recording = False
    except Exception as e:
        logger.error(f"Could not stop recording for device {device_id}: {e}")
        device_data.recording = False

    # Update the devices.json file
    await update_device_in_json(device_data)

async def update_device_in_json(device_data: DeviceModel):
    """Update the devices.json file with the new or updated device data."""
    devices = await read_json_file(JSON_FILE_PATH)
    device_found = False
    for idx, d in enumerate(devices):
        if d.device_id == device_data.device_id:
            devices[idx] = device_data
            device_found = True
            logger.debug(f"Updated device {device_data.device_id} in devices.json")
            break
    if not device_found:
        devices.append(device_data)
        logger.debug(f"Added new device {device_data.device_id} to devices.json")

    await write_json_file(JSON_FILE_PATH, devices)
    logger.debug(f"devices.json updated for device {device_data.device_id}")

@app.on_event("startup")
async def startup_event():
    """Run device discovery loop on startup."""
    asyncio.create_task(run_device_discovery())

async def discover_and_log_devices():
    """Continuously discover devices and update the devices.json file."""
    seen_devices = {}

    async for device_info in discover_devices():
        device_ip = device_info.addresses[0]
        device_port = device_info.port
        device_id = device_info.name.split(":")[1] if ':' in device_info.name else device_info.name

        device_data = DeviceModel(
            ip=device_ip,
            port=device_port,
            name=device_id, 
            device_id=device_id,
            available=True,
            connected=False,
            recording=False
        )

        if device_id not in seen_devices or not compare_device_data(seen_devices[device_id], device_data):
            seen_devices[device_id] = device_data
            await update_device_in_json(device_data)

        await asyncio.sleep(1)  # Delay to prevent high-frequency updates

def compare_device_data(existing_data: DeviceModel, new_data: DeviceModel) -> bool:
    """Compare existing and new device data to avoid redundant updates."""
    return (
        existing_data.ip == new_data.ip and
        existing_data.port == new_data.port and
        existing_data.available == new_data.available
    )

async def run_device_discovery():
    """Run the device discovery loop."""
    try:
        while True:
            await discover_and_log_devices()
    except asyncio.CancelledError:
        logger.info("Device discovery task cancelled")
    except Exception as e:
        logger.error(f"Error during discovery: {e}")
        await asyncio.sleep(10)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
