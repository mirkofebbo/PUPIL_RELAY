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
import pylsl  # Added for LSL functionality

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
devices_tasks = {}

heartbeat_task = None
monitor_task = None

# Define Pydantic Models
class DeviceActionRequest(BaseModel):
    device_ids: List[str]

class MessageTriggerRequest(BaseModel):
    message: str


# Define LSL Timestamp Outlet Class
class LSLTimestampOutlet:
    def __init__(self):
        self.outlet = None
        self.create_outlet()

    def create_outlet(self):
        """Initialize the LSL stream outlet for timestamped messages."""
        info = pylsl.StreamInfo(
            name="TimestampStream",
            type="Timestamp",
            channel_count=1,
            channel_format=pylsl.cf_string, 
            source_id="timestamp_stream_01"
        )
        print("starting timestamp relay", info)
        self.outlet = pylsl.StreamOutlet(info)
        logger.info("[LSL Timestamp] LSL Timestamp Stream created.")

    def send_message(self, message: str):
        """Send a message with the current Unix timestamp."""
        try:
            timestamp = int(time.time())
            data = f'T:{timestamp}_M:{message}'
            if self.outlet:
                self.outlet.push_sample([data])
                print(data)
                logger.debug(f"[LSL Timestamp] Sent message: {data}")
            else:
                logger.error("[LSL Timestamp] LSL outlet is not initialized.")
        except Exception as e:
            logger.error(f"[LSL Timestamp] Failed to send message: {e}")

# Instantiate the LSL Timestamp Outlet
timestamp_outlet = LSLTimestampOutlet()

# Background task to send "H" every 10 seconds
async def send_heartbeat():
    while True:
        timestamp_outlet.send_message("H")
        await asyncio.sleep(10)

# Health Check Endpoint (Optional)
@app.get("/health")
async def health_check():
    relay_status = {device_id: not task.done() for device_id, task in relay_tasks.items()}
    return {"status": "ok", "relay_status": relay_status}

# Define API Endpoints
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

@app.post("/devices/send_message")
async def send_message_trigger(request: MessageTriggerRequest):
    devices = await read_json_file(JSON_FILE_PATH)

    if not devices:
        raise HTTPException(status_code=404, detail="No devices found.")
    timestamp = int(time.time())
    data = f'T:{timestamp}_M:{request.message}'
    tasks = [send_message_to_device(device_data, data) for device_data in devices]
    tasks.append(send_custom_timestamp_message(request.message))

    try:
        # Wait for tasks with a timeout
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=30)
    except asyncio.TimeoutError:
        logger.error("Timeout occurred while sending messages to devices. Tasks were cancelled.")
        # Cancel and safely handle the tasks
        for task in tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    logger.info("A task was cancelled during timeout handling.")
    except Exception as e:
        logger.error(f"An error occurred during message sending: {e}")

    return {"message": "Messages have been processed, including handling of cancellations."}



async def send_custom_timestamp_message(message: str):
    """Send a custom message to the LSL timestamp stream."""
    try:
        timestamp_outlet.send_message(message)
        logger.info(f"[LSL Timestamp] Custom message sent: {message}")
    except Exception as e:
        logger.error(f"[LSL Timestamp] Failed to send custom message: {e}")

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
    """Send a message to a single device."""
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
    finally:
        logger.debug(f"[API Server] Exiting context for device {device_id}")


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


# Start Resource Monitoring (Optional)
async def monitor_open_file_descriptors():
    import psutil
    process = psutil.Process()

    while True:
        fd_count = process.num_fds()
        print(f"Current open file descriptors: {fd_count}")
        logger.debug(f"Current open file descriptors: {fd_count}")
        if fd_count > 80000:  # Example threshold; adjust as needed
            logger.warning(f"High number of open file descriptors: {fd_count}")
        await asyncio.sleep(10)  # Check every minute

# Start background tasks on app startup
@app.on_event("startup")
async def startup_event():
    global heartbeat_task, monitor_task
    heartbeat_task = asyncio.create_task(send_heartbeat())
    monitor_task = asyncio.create_task(monitor_open_file_descriptors())

@app.on_event("shutdown")
async def shutdown_event():
    global heartbeat_task, monitor_task
    logger.info("[LSL Timestamp] Shutting down Timestamp Stream.")
    if heartbeat_task and not heartbeat_task.done():
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            logger.info("Heartbeat task was cancelled.")
    if monitor_task and not monitor_task.done():
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            logger.info("Monitoring task was cancelled.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
