# api_server.py

import asyncio
import time
from typing import Optional
from typing import List
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from pupil_labs.realtime_api import Device
from pupil_labs.realtime_api.time_echo import TimeOffsetEstimator
from utils.utils import read_json_file, write_json_file
from typing import Optional

app = FastAPI()
JSON_FILE_PATH = 'devices.json'

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update with your frontend's origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    target_devices = [
        d for d in devices if d["device_id"] in request.device_ids]

    if not target_devices:
        raise HTTPException(
            status_code=404, detail="No matching devices found.")

    for device_data in target_devices:
        background_tasks.add_task(start_device_relay_task, device_data)

    return {"message": "LSL relay streams are starting."}

# api_server.py

@app.post("/devices/stop_lsl")
async def stop_lsl_streams(request: DeviceActionRequest, background_tasks: BackgroundTasks):
    devices = await read_json_file(JSON_FILE_PATH)
    target_devices = [d for d in devices if d["device_id"] in request.device_ids]

    if not target_devices:
        raise HTTPException(status_code=404, detail="No matching devices found.")

    for device_data in target_devices:
        background_tasks.add_task(stop_device_relay_task, device_data)

    return {"message": "LSL relay streams are stopping."}

# Helper function
def stop_device_relay_task(device_data):
    asyncio.run(stop_device_relay(device_data))

@app.post("/devices/start_recording")
async def start_recordings(request: DeviceActionRequest, background_tasks: BackgroundTasks):
    devices = await read_json_file(JSON_FILE_PATH)
    target_devices = [
        d for d in devices if d["device_id"] in request.device_ids]

    if not target_devices:
        raise HTTPException(
            status_code=404, detail="No matching devices found.")

    for device_data in target_devices:
        background_tasks.add_task(start_device_recording_task, device_data)

    return {"message": "Recordings are starting."}


@app.post("/devices/stop_recording")
async def stop_recordings(request: DeviceActionRequest, background_tasks: BackgroundTasks):
    devices = await read_json_file(JSON_FILE_PATH)
    target_devices = [d for d in devices if d["device_id"] in request.device_ids]

    if not target_devices:
        raise HTTPException(status_code=404, detail="No matching devices found.")

    for device_data in target_devices:
        background_tasks.add_task(stop_device_recording_task, device_data)

    return {"message": "Recordings are stopping."}


@app.get("/devices/stream_status")
async def get_stream_status():
    """Get the current streaming status of all devices."""
    devices = await read_json_file(JSON_FILE_PATH)
    status = {device["device_id"]: device.get(
        "lsl_streaming", False) for device in devices}
    return {"status": status}


@app.post("/devices/send_message")
async def send_message_trigger(request: MessageTriggerRequest):
    devices = await read_json_file(JSON_FILE_PATH)
    target_devices = [d for d in devices if d["device_id"] in request.device_ids]

    if not target_devices:
        raise HTTPException(status_code=404, detail="No matching devices found.")

    tasks = []
    for device_data in target_devices:
        # Send message asynchronously
        tasks.append(send_message_to_device(device_data, request.message))

    # Await all tasks
    await asyncio.gather(*tasks)

    return {"message": "Messages have been sent."}

# Helper functions


def start_device_relay_task(device_data):
    asyncio.run(start_device_relay(device_data))


def stop_device_relay_task(device_id):
    asyncio.run(stop_device_relay(device_id))

def start_device_recording_task(device_data):
    asyncio.run(start_device_recording(device_data))

def stop_device_recording_task(device_data):
    asyncio.run(stop_device_recording(device_data))

def send_message_to_device_task(device_data, message):
    asyncio.run(send_message_to_device(device_data, message))


async def start_device_relay(device_data):
    """Start the LSL relay for a single device."""
    # Similar to the function in lsl_relay_manager.py
    # You may need to adjust imports and code accordingly
    pass  # Implement as needed


async def stop_device_relay(device_data):
    """Stop the LSL relay for a single device."""
    # Similar to the function in lsl_relay_manager.py
    # You may need to adjust imports and code accordingly
    pass  # Implement as needed

async def start_device_recording(device_data):
    """Start recording on a single device."""
    device_ip = device_data["ip"]
    device_port = device_data["port"]
    try:
        async with Device(device_ip, device_port) as device:
            recording_id = await device.recording_start()
            print(
                f"[API Server] Recording started for device {device_data['device_id']}")
            device_data["recording"] = True
    except Exception as e:
        print(
            f"[API Server] Could not start recording for device {device_data['device_id']}: {e}")
        device_data["recording"] = False
    
    # Update the devices.json file
    devices = await read_json_file(JSON_FILE_PATH)
    for idx, d in enumerate(devices):
        if d["device_id"] == device_data["device_id"]:
            devices[idx] = device_data
            break
    await update_device_in_json(device_data)



async def send_message_to_device(device_data, message):
    device_ip = device_data["ip"]
    device_port = device_data["port"]
    try:
        async with Device(device_ip, device_port) as device:
            status = await device.get_status()
            time_echo_port = status.phone.time_echo_port
            if time_echo_port is None:
                print(f"[API Server] Device {device_data['device_id']} does not support Time Echo protocol.")
                # Proceed without time adjustment
                await device.send_event(message)
                print(f"[API Server] Sent message to device {device_data['device_id']} without time adjustment")
                return

            time_offset_estimator = TimeOffsetEstimator(
                status.phone.ip, time_echo_port
            )
            # Reduce the number of measurements to speed up estimation
            estimated_offset = await time_offset_estimator.estimate(number_of_measurements=10)
            time_offset_ms = estimated_offset.time_offset_ms.mean

            # Get the current time on the server
            server_time_ns = time.time_ns()
            # Adjust the timestamp
            adjusted_timestamp_ns = server_time_ns - int(time_offset_ms * 1e6)  # Convert ms to ns
            # Send the message with adjusted timestamp
            await device.send_event(message, event_timestamp_unix_ns=adjusted_timestamp_ns)
            print(f"[API Server] Sent message to device {device_data['device_id']} with adjusted timestamp")
    except Exception as e:
        print(f"[API Server] Could not send message to device {device_data['device_id']}: {e}")


async def stop_device_recording(device_data):
    device_ip = device_data["ip"]
    device_port = device_data["port"]
    try:
        async with Device(device_ip, device_port) as device:
            await device.recording_stop_and_save()
            print(f"[API Server] Recording stopped for device {device_data['device_id']}")
            device_data["recording"] = False
    except Exception as e:
        print(f"[API Server] Could not stop recording for device {device_data['device_id']}: {e}")
        device_data["recording"] = False

    # Update the devices.json file
    await update_device_in_json(device_data)

async def update_device_in_json(device_data):
    devices = await read_json_file(JSON_FILE_PATH)
    for idx, d in enumerate(devices):
        if d["device_id"] == device_data["device_id"]:
            devices[idx] = device_data
            break
    await write_json_file(JSON_FILE_PATH, devices)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
