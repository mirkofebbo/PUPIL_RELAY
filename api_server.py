# api_server.py

import asyncio
import logging
import time
from typing import List
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from pupil_labs.realtime_api import Device
from pupil_labs.realtime_api.time_echo import TimeOffsetEstimator
from utils.utils import read_json_file, write_json_file, DeviceModel
from pupil_labs.lsl_relay import relay  # Ensure relay.py is accessible as a module

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

# Dictionary to keep track of relay tasks per device_id
relay_tasks = {}
relay_tasks_lock = asyncio.Lock()

class DeviceActionRequest(BaseModel):
    device_ids: List[str]

class MessageTriggerRequest(BaseModel):
    device_ids: List[str]
    message: str

@app.get("/devices", response_model=List[DeviceModel])
async def get_devices():
    devices = await read_json_file(JSON_FILE_PATH)
    return devices

@app.post("/devices/start_lsl")
async def start_lsl_streams(request: DeviceActionRequest, background_tasks: BackgroundTasks):
    devices = await read_json_file(JSON_FILE_PATH)
    target_devices = [d for d in devices if d.device_id in request.device_ids]

    if not target_devices:
        raise HTTPException(status_code=404, detail="No matching devices found.")

    for device_data in target_devices:
        background_tasks.add_task(start_device_relay_task, device_data)

    return {"message": "LSL relay streams are starting."}

@app.post("/devices/stop_lsl")
async def stop_lsl_streams(request: DeviceActionRequest, background_tasks: BackgroundTasks):
    devices = await read_json_file(JSON_FILE_PATH)
    target_devices = [d for d in devices if d.device_id in request.device_ids]

    if not target_devices:
        raise HTTPException(status_code=404, detail="No matching devices found.")

    for device_data in target_devices:
        background_tasks.add_task(stop_device_relay_task, device_data)

    return {"message": "LSL relay streams are stopping."}

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

@app.post("/devices/send_message")
async def send_message_trigger(request: MessageTriggerRequest):
    devices = await read_json_file(JSON_FILE_PATH)
    target_devices = [d for d in devices if d.device_id in request.device_ids]

    if not target_devices:
        raise HTTPException(status_code=404, detail="No matching devices found.")

    tasks = []
    for device_data in target_devices:
        # Send message asynchronously
        tasks.append(send_message_to_device(device_data, request.message))

    # Await all tasks
    await asyncio.gather(*tasks, return_exceptions=True)

    return {"message": "Messages have been sent."}

# Helper functions

async def start_device_relay_task(device_data: DeviceModel):
    """Start the LSL relay for a single device."""
    device_id = device_data.device_id
    async with relay_tasks_lock:
        if device_id in relay_tasks:
            logger.warning(f"[API Server] Relay already running for device {device_id}. Skipping.")
            return
        # Start the relay task
        relay_task = asyncio.create_task(relay.Relay.run(
            device_ip=device_data.ip,
            device_port=device_data.port,
            device_identifier=device_id,
            outlet_prefix="pupil_labs",
            model=device_data.name,  # Assuming 'name' corresponds to 'model'
            module_serial=device_data.glasses_serial or "unknown",
            time_sync_interval=60,
        ))
        relay_tasks[device_id] = relay_task
        logger.info(f"[API Server] Started relay for device {device_id}")

    # Update device status
    device_data.lsl_streaming = True
    device_data.error_message = ""  # Clear any previous error message
    await update_device_in_json(device_data)

async def stop_device_relay_task(device_data: DeviceModel):
    """Stop the LSL relay for a single device."""
    device_id = device_data.device_id
    async with relay_tasks_lock:
        relay_task = relay_tasks.get(device_id)
        if relay_task:
            relay_task.cancel()
            try:
                await relay_task
                logger.info(f"[API Server] Stopped relay for device {device_id}")
            except asyncio.CancelledError:
                logger.info(f"[API Server] Relay task for device {device_id} cancelled successfully.")
            except Exception as e:
                logger.exception(f"[API Server] Exception while stopping relay for device {device_id}: {e}")
            del relay_tasks[device_id]
        else:
            logger.warning(f"[API Server] No relay task found for device {device_id}. Cannot stop.")

    # Update device status
    device_data.lsl_streaming = False
    await update_device_in_json(device_data)

async def start_device_recording_task(device_data: DeviceModel):
    """Start recording on a single device."""
    device_ip = device_data.ip
    device_port = device_data.port
    device_id = device_data.device_id
    try:
        async with Device(device_ip, device_port) as device:
            recording_id = await device.recording_start()
            logger.info(f"[API Server] Recording started for device {device_id}")
            device_data.recording = True
    except Exception as e:
        logger.error(f"[API Server] Could not start recording for device {device_id}: {e}")
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
            logger.info(f"[API Server] Recording stopped for device {device_id}")
            device_data.recording = False
    except Exception as e:
        logger.error(f"[API Server] Could not stop recording for device {device_id}: {e}")
        device_data.recording = False

    # Update the devices.json file
    await update_device_in_json(device_data)

async def send_message_to_device(device_data: DeviceModel, message: str):
    device_ip = device_data.ip
    device_port = device_data.port
    device_id = device_data.device_id
    try:
        async with Device(device_ip, device_port) as device:
            status = await device.get_status()
            time_echo_port = status.phone.time_echo_port
            if time_echo_port is None:
                logger.warning(f"[API Server] Device {device_id} does not support Time Echo protocol.")
                # Proceed without time adjustment
                await device.send_event(message)
                logger.info(f"[API Server] Sent message to device {device_id} without time adjustment")
                return

            time_offset_estimator = TimeOffsetEstimator(
                status.phone.ip, time_echo_port
            )
            # Reduce the number of measurements to speed up estimation
            estimated_offset = await time_offset_estimator.estimate(number_of_measurements=10)
            if estimated_offset is None:
                logger.warning(f"[API Server] Time offset estimation failed for device {device_id}. Sending message without adjustment.")
                await device.send_event(message)
                logger.info(f"[API Server] Sent message to device {device_id} without time adjustment")
                return

            time_offset_ms = estimated_offset.time_offset_ms.mean

            # Get the current time on the server
            server_time_ns = time.time_ns()
            # Adjust the timestamp
            adjusted_timestamp_ns = server_time_ns - int(time_offset_ms * 1e6)  # Convert ms to ns
            # Send the message with adjusted timestamp
            await device.send_event(message, event_timestamp_unix_ns=adjusted_timestamp_ns)
            logger.info(f"[API Server] Sent message to device {device_id} with adjusted timestamp")
    except Exception as e:
        logger.error(f"[API Server] Could not send message to device {device_id}: {e}")

async def update_device_in_json(device_data: DeviceModel):
    """Update the devices.json file with the new or updated device data."""
    devices = await read_json_file(JSON_FILE_PATH)  # Returns List[DeviceModel]
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

# Health Check Endpoint (Optional)
@app.get("/health")
async def health_check():
    relay_status = {device_id: not task.done() for device_id, task in relay_tasks.items()}
    return {"status": "ok", "relay_status": relay_status}

# Start Resource Monitoring (Optional)
async def monitor_open_file_descriptors():
    import psutil
    process = psutil.Process()
    while True:
        fd_count = process.num_fds()
        logger.debug(f"Current open file descriptors: {fd_count}")
        if fd_count > 80000:  # Example threshold; adjust as needed
            logger.warning(f"High number of open file descriptors: {fd_count}")
        await asyncio.sleep(60)  # Check every minute

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(monitor_open_file_descriptors())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
