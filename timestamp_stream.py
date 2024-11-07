# api_server.py

import asyncio
import logging
from typing import List
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from pupil_labs.realtime_api import Device
from pupil_labs.realtime_api.time_echo import TimeOffsetEstimator
from utils.utils import read_json_file, write_json_file, DeviceModel

# Configuration
CUSTOM_MESSAGE_PORT = 9999  # Must match the port in timestamp_stream.py

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
        # Send message asynchronously to the timestamp_stream.py via TCP
        tasks.append(send_custom_message_to_timestamp_stream(request.message))

        # Optionally, handle relay task cleanup if necessary
        # For example, stopping relay tasks if sending a message implies stopping streaming
        # This depends on your specific application logic

    # Await all tasks
    await asyncio.gather(*tasks, return_exceptions=True)

    return {"message": "Messages have been sent."}

# Helper Functions

async def send_custom_message_to_timestamp_stream(message: str):
    """
    Sends a custom message to timestamp_stream.py via TCP.
    """
    try:
        reader, writer = await asyncio.open_connection('127.0.0.1', CUSTOM_MESSAGE_PORT)
        writer.write(f"{message}\n".encode())
        await writer.drain()
        logger.info(f"Sent custom message to timestamp_stream: '{message}'")
        writer.close()
        await writer.wait_closed()
    except ConnectionRefusedError:
        logger.error("Failed to connect to timestamp_stream.py. Is it running?")
    except Exception as e:
        logger.exception(f"Exception while sending custom message: {e}")

# Existing helper functions like start_device_relay_task, stop_device_relay_task, etc.
# should remain unchanged and handle relay management as previously implemented.

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)