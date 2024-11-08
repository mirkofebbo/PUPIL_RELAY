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
from lsl_manager import LSLManager 

from contextlib import asynccontextmanager

import cProfile
import re

# Define Pydantic Models
class DeviceActionRequest(BaseModel):
    device_ids: List[str]

class MessageTriggerRequest(BaseModel):
    message: str

# Configure Logging
LOG_FILE_NAME = 'api_server.log'
logging.basicConfig(level=logging.DEBUG, filename=LOG_FILE_NAME, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Instantiate the LSL Manager
lsl_manager = LSLManager()

# Background task to send "H" every 10 seconds
async def send_heartbeat():
    logger.info("Heartbeat task started.")
    try:
        while True:
            lsl_manager.send_message("H")
            await asyncio.sleep(10)
    except asyncio.CancelledError:
        logger.info("Heartbeat task received cancellation.")
    except Exception as e:
        logger.error(f"Exception in heartbeat task: {e}")

# Background task to monitor open file descriptors
async def monitor_open_file_descriptors(interval=60):
    logger.info("File descriptor monitoring task started.")
    import psutil
    process = psutil.Process()
    print(cProfile.run('re.compile("foo|bar")', 'restats'))

    try:
        while True:
            fd_count = process.num_fds()
            logger.debug(f"[Resource Monitor] Current open file descriptors: {fd_count}")
            print(f"[Resource Monitor] Current open file descriptors: {fd_count}")
            if fd_count > 100:
                logger.warning(f"[Resource Monitor] High number of open file descriptors: {fd_count}")
                print(f"[Resource Monitor] High number of open file descriptors: {fd_count}")
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("File descriptor monitoring task received cancellation.")
    except Exception as e:
        logger.error(f"Exception in file descriptor monitoring task: {e}")

# Lifespan Event Handler
@asynccontextmanager
async def lifespan_handler(app: FastAPI):
    logger.info("Application startup initiated.")
    # Create background tasks
    heartbeat_task = asyncio.create_task(send_heartbeat())
    monitor_task = asyncio.create_task(monitor_open_file_descriptors())

    # Yield control to run the application
    try:
        yield
    finally:
        logger.info("Application shutdown initiated.")
        # Cancel background tasks
        heartbeat_task.cancel()
        monitor_task.cancel()
        await lsl_manager.close_outlet()

        logger.info("Application cleanup completed.")

# Initialize FastAPI with Lifespan
app = FastAPI(lifespan=lifespan_handler)

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update with your frontend's origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Endpoints
@app.get("/devices", response_model=List[DeviceModel])
async def get_devices():
    devices = await read_json_file('devices.json')
    return devices

@app.post("/devices/start_recording")
async def start_recordings(request: DeviceActionRequest, background_tasks: BackgroundTasks):
    devices = await read_json_file('devices.json')
    target_devices = [d for d in devices if d.device_id in request.device_ids]

    if not target_devices:
        raise HTTPException(status_code=404, detail="No matching devices found.")

    for device_data in target_devices:
        background_tasks.add_task(start_device_recording_task, device_data)

    return {"message": "Recordings are starting."}

@app.post("/devices/stop_recording")
async def stop_recordings(request: DeviceActionRequest, background_tasks: BackgroundTasks):
    devices = await read_json_file('devices.json')
    target_devices = [d for d in devices if d.device_id in request.device_ids]

    if not target_devices:
        raise HTTPException(status_code=404, detail="No matching devices found.")

    for device_data in target_devices:
        background_tasks.add_task(stop_device_recording_task, device_data)

    return {"message": "Recordings are stopping."}

@app.post("/devices/send_message")
async def send_message_trigger(request: MessageTriggerRequest):
    devices = await read_json_file('devices.json')
    tasks = []
    if not devices or not devices:
        raise HTTPException(status_code=404, detail="No devices found.")

    # Prepare messages
    for device_data in devices:
        if device_data.available:
            tasks.append(send_message_to_device(device_data, request.message))
    tasks.append(send_custom_timestamp_message(request.message))

    try:
        # Wait for tasks with a timeout
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=30)
    except asyncio.TimeoutError:
        logger.error("Timeout occurred while sending messages to devices. Tasks were cancelled.")
        # Cancel and safely handle the tasks
        for task in tasks:
            if not await task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    logger.info("A task was cancelled during timeout handling.")
    except Exception as e:
        logger.error(f"An error occurred during message sending: {e}")

    return {"message": "Messages have been processed, including LSL broadcast."}

async def send_custom_timestamp_message(message: str):
    """Send a custom message to the LSL timestamp stream."""
    lsl_manager.send_message(message)

async def start_device_recording_task(device_data: DeviceModel):
    """Start recording on a single device."""
    try:
        async with Device(device_data.ip, device_data.port) as device:
            recording_id = await device.recording_start()
            logger.info(f"[API Server] Recording started for device {device_data.device_id}")
            device_data.recording = True
    except Exception as e:
        logger.error(f"[API Server] Could not start recording for device {device_data.device_id}: {e}")
        device_data.recording = False
    await update_device_in_json(device_data)

async def stop_device_recording_task(device_data: DeviceModel):
    """Stop recording on a single device."""
    try:
        async with Device(device_data.ip, device_data.port) as device:
            await device.recording_stop_and_save()
            logger.info(f"[API Server] Recording stopped for device {device_data.device_id}")
            device_data.recording = False
    except Exception as e:
        logger.error(f"[API Server] Could not stop recording for device {device_data.device_id}: {e}")
        device_data.recording = False
    await update_device_in_json(device_data)

async def send_message_to_device(device_data: DeviceModel, message: str):
    """Send a message to a single device."""
    try:
        async with Device(device_data.ip, device_data.port) as device:
            status = await device.get_status()
            time_echo_port = status.phone.time_echo_port
            if time_echo_port is None:
                logger.warning(f"[API Server] Device {device_data.device_id} does not support Time Echo protocol.")
                # Proceed without time adjustment
                await device.send_event(message)
                logger.info(f"[API Server] Sent message to device {device_data.device_id} without time adjustment")
                return

            time_offset_estimator = TimeOffsetEstimator(
                status.phone.ip, time_echo_port
            )
            # Reduce the number of measurements to speed up estimation vcv
            estimated_offset = await time_offset_estimator.estimate(number_of_measurements=10)
            if estimated_offset is None:
                logger.warning(f"[API Server] Time offset estimation failed for device {device_data.device_id}. Sending message without adjustment.")
                await device.send_event(message)
                logger.info(f"[API Server] Sent message to device {device_data.device_id} without time adjustment")
                return

            time_offset_ms = estimated_offset.time_offset_ms.mean

            # Get the current time on the server
            server_time_ns = time.time_ns()
            # Adjust the timestamp
            adjusted_timestamp_ns = server_time_ns - int(time_offset_ms * 1e6)  # Convert ms to ns
            # Send the message with adjusted timestamp
            await device.send_event(message, event_timestamp_unix_ns=adjusted_timestamp_ns)
            logger.info(f"[API Server] Sent message to device {device_data.device_id} with adjusted timestamp")
    except Exception as e:
        logger.error(f"[API Server] Could not send message to device {device_data.device_id}: {e}")
    finally:
        logger.debug(f"[API Server] Exiting context for device {device_data.device_id}")

async def update_device_in_json(device_data: DeviceModel):
    """Update the devices.json file with the new or updated device data."""
    devices = await read_json_file('devices.json')  # Returns List[DeviceModel]
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
    await write_json_file('devices.json', devices)
    logger.debug(f"devices.json updated for device {device_data.device_id}")

# Run the app using uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
