# lsl_relay_manager.py

import asyncio
import logging
from pupil_labs.lsl_relay import relay
from utils.utils import read_json_file, write_json_file

JSON_FILE_PATH = 'devices.json'
LOG_FILE_NAME = 'lsl_relay.log'

# Configure logging
logging.basicConfig(level=logging.DEBUG, filename=LOG_FILE_NAME, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Dictionary to keep track of relay tasks per device_id
relay_tasks = {}
relay_tasks_lock = asyncio.Lock()

async def start_relays():
    """Start LSL relays for devices marked as available and not streaming."""
    devices = await read_json_file(JSON_FILE_PATH)
    logger.debug("Fetched devices from devices.json")

    tasks = []
    for device_data in devices:
        if (device_data.get("available") and 
            not device_data.get("lsl_streaming") and 
            not device_data.get("relay_failed", False)):
            tasks.append(start_device_relay(device_data))
            logger.debug(f"Queued relay start for device {device_data['device_id']}")

    if tasks:
        logger.debug(f"Starting {len(tasks)} relay tasks")
        await asyncio.gather(*tasks)
    else:
        logger.debug("No relays to start at this time")

async def start_device_relay(device_data):
    device_ip = device_data["ip"]
    device_port = device_data["port"]
    device_identifier = device_data["device_id"]
    outlet_prefix = "pupil_labs"
    model = "Pupil Labs Device"
    module_serial = device_data.get("glasses_serial") or "unknown"
    time_sync_interval = 60

    logger.debug(f"Attempting to start relay for device {device_identifier}")

    try:
        # Start the relay as a background task
        relay_task = asyncio.create_task(relay.Relay.run(
            device_ip=device_ip,
            device_port=device_port,
            device_identifier=device_identifier,
            outlet_prefix=outlet_prefix,
            model=model,
            module_serial=module_serial,
            time_sync_interval=time_sync_interval,
        ))
        # Store the task
        async with relay_tasks_lock:
            relay_tasks[device_identifier] = relay_task
        logger.info(f"[LSL Relay] Started relay for device {device_identifier}")

        # Update device status
        device_data["lsl_streaming"] = True
        device_data["error_message"] = ""  # Clear any previous error message
        device_data["relay_failed"] = False

    except Exception as e:
        error_message = f"Failed to start relay for device {device_identifier}: {e}"
        logger.error(f"[LSL Relay] {error_message}")
        device_data["lsl_streaming"] = False
        device_data["error_message"] = error_message
        device_data["relay_failed"] = True  # Prevent endless retries

    # Update the JSON file with the new device data
    await update_device_in_json(device_data)

async def stop_device_relay(device_data):
    device_identifier = device_data["device_id"]
    logger.debug(f"Attempting to stop relay for device {device_identifier}")

    async with relay_tasks_lock:
        relay_task = relay_tasks.get(device_identifier)
        if relay_task and not relay_task.done():
            relay_task.cancel()
            try:
                await relay_task
            except asyncio.CancelledError:
                logger.info(f"[LSL Relay] Relay task for device {device_identifier} cancelled")
            del relay_tasks[device_identifier]
            logger.info(f"[LSL Relay] Stopped relay for device {device_identifier}")
        else:
            logger.warning(f"[LSL Relay] No running relay found for device {device_identifier}")

    device_data["lsl_streaming"] = False
    await update_device_in_json(device_data)

async def update_device_in_json(device_data):
    devices = await read_json_file(JSON_FILE_PATH)
    for idx, d in enumerate(devices):
        if d["device_id"] == device_data["device_id"]:
            devices[idx] = device_data
            logger.debug(f"Updated device {device_data['device_id']} in devices.json")
            break
    else:
        devices.append(device_data)  # If device is not in the list, add it
        logger.debug(f"Added new device {device_data['device_id']} to devices.json")

    await write_json_file(JSON_FILE_PATH, devices)
    logger.debug(f"devices.json updated for device {device_data['device_id']}")

async def run_lsl_relay_manager():
    """Run the LSL relay manager loop."""
    logger.info("Starting LSL Relay Manager")
    while True:
        try:
            await start_relays()
        except Exception as e:
            logger.exception(f"[LSL Relay] Error during relay management: {e}")
        await asyncio.sleep(10)  # Check every 10 seconds

if __name__ == "__main__":
    try:
        asyncio.run(run_lsl_relay_manager())
    except KeyboardInterrupt:
        logger.info("[LSL Relay] The relay manager was closed via keyboard interrupt")
    finally:
        logging.shutdown()