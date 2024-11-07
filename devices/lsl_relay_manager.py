# lsl_relay_manager.py

import asyncio
import logging
from pupil_labs.lsl_relay import relay
from utils.utils import read_json_file, write_json_file, DeviceModel

JSON_FILE_PATH = 'devices.json'
LOG_FILE_NAME = 'lsl_relay.log'

# Configure logging
logging.basicConfig(level=logging.DEBUG, filename=LOG_FILE_NAME, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Dictionary to keep track of relay tasks per device_id
relay_tasks = {}
relay_tasks_lock = asyncio.Lock()

# Event to signal shutdown
shutdown_event = asyncio.Event()

async def start_relays():
    """Start LSL relays for devices marked as available and not streaming."""
    devices = await read_json_file(JSON_FILE_PATH)
    logger.debug("Fetched devices from devices.json")

    tasks = []
    for device_data in devices:
        device_id = device_data.device_id
        if (device_data.available and 
            not device_data.lsl_streaming and 
            not device_data.error_message and
            device_id not in relay_tasks):
            tasks.append(start_device_relay(device_data))
            logger.debug(f"Queued relay start for device {device_id}")

    if tasks:
        logger.debug(f"Starting {len(tasks)} relay tasks")
        await asyncio.gather(*tasks)
    else:
        logger.debug("No new relays to start at this time")

async def stop_relays(devices):
    """Stop relays for devices that are no longer available."""
    current_device_ids = {device.device_id for device in devices if device.available}
    async with relay_tasks_lock:
        relay_device_ids = set(relay_tasks.keys())
    
    # Identify devices that have been removed or marked as unavailable
    devices_to_stop = relay_device_ids - current_device_ids

    for device_id in devices_to_stop:
        device_data = next((d for d in devices if d.device_id == device_id), None)
        if device_data:
            await stop_device_relay(device_data)
        else:
            # Device is no longer in the JSON, create a minimal DeviceModel to stop relay
            incomplete_device = DeviceModel(
                ip="",
                port=0,
                name="",
                device_id=device_id,
                available=False
            )
            await stop_device_relay(incomplete_device)

async def start_device_relay(device_data: DeviceModel):
    if device_data.lsl_streaming:
        logger.warning(f"[LSL Relay] Relay already running for device {device_data.device_id}.")
        return 
    
    device_ip = device_data.ip
    device_port = device_data.port
    device_identifier = device_data.device_id
    outlet_prefix = "pupil_labs"
    model = device_data.model if hasattr(device_data, 'model') else "Pupil Labs Device"
    module_serial = device_data.glasses_serial or "unknown"
    time_sync_interval = 60

    logger.debug(f"Attempting to start relay for device {device_identifier}")

    try:
        relay_task = asyncio.create_task(relay.Relay.run(
            device_ip=device_ip,
            device_port=device_port,
            device_identifier=device_identifier,
            outlet_prefix=outlet_prefix,
            model=model,
            module_serial=module_serial,
            time_sync_interval=time_sync_interval,
        ))

        async with relay_tasks_lock:
            relay_tasks[device_identifier] = relay_task
        logger.info(f"[LSL Relay] Started relay for device {device_identifier}")

        # Ensure that relay tasks are marked as streaming
        device_data.lsl_streaming = True
        device_data.error_message = ""

    except Exception as e:
        logger.error(f"[LSL Relay] Failed to start relay for device {device_identifier}: {e}")
        device_data.lsl_streaming = False
        device_data.error_message = str(e)
    # Update the JSON file with the new device data
    await update_device_in_json(device_data)

async def stop_device_relay(device_data: DeviceModel):
    device_identifier = device_data.device_id
    logger.debug(f"Attempting to stop relay for device {device_identifier}")
    async with relay_tasks_lock:
        relay_task = relay_tasks.get(device_identifier)
        if relay_task and not relay_task.done():
            relay_task.cancel()
            try:
                await relay_task
            except asyncio.CancelledError:
                logger.info(f"[LSL Relay] Relay task for device {device_identifier} cancelled")
            except Exception as e:
                logger.exception(f"[LSL Relay] Exception while cancelling relay for device {device_identifier}: {e}")
            finally:
                relay_task.cancelled()  # Ensure the task is marked as cancelled
            del relay_tasks[device_identifier]
            logger.info(f"[LSL Relay] Stopped relay for device {device_identifier}")
        else:
            logger.warning(f"[LSL Relay] No running relay found for device {device_identifier}")

    device_data.lsl_streaming = False
    await update_device_in_json(device_data)


async def update_device_in_json(device_data: DeviceModel):
    devices = await read_json_file(JSON_FILE_PATH)
    device_found = False
    for idx, d in enumerate(devices):
        if d.device_id == device_data.device_id:
            devices[idx] = device_data
            logger.debug(f"Updated device {device_data.device_id} in devices.json")
            device_found = True
            break
    if not device_found:
        devices.append(device_data)
        logger.debug(f"Added new device {device_data.device_id} to devices.json")

    await write_json_file(JSON_FILE_PATH, devices)
    logger.debug(f"devices.json updated for device {device_data.device_id}")

async def run_lsl_relay_manager():
    """Run the LSL relay manager loop."""
    logger.info("Starting LSL Relay Manager")
    while not shutdown_event.is_set():
        try:
            devices = await read_json_file(JSON_FILE_PATH)
            await start_relays()
            await stop_relays(devices)
        except Exception as e:
            logger.exception(f"[LSL Relay] Error during relay management: {e}")
        await asyncio.sleep(10)  # Check every 10 seconds

async def shutdown_manager():
    """Shutdown the relay manager and other resources gracefully."""
    logger.info("Shutting down LSL Relay Manager and cleaning up resources...")
    async with relay_tasks_lock:
        tasks = list(relay_tasks.values())
        for task in tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    logger.info(f"[Shutdown] Relay task {task} was cancelled")
                except Exception as e:
                    logger.exception(f"[Shutdown] Exception while cancelling task: {e}")
        # Ensure all relay tasks are awaited
        await asyncio.gather(*tasks, return_exceptions=True)

    logger.info("All relay tasks and resources have been cleaned up.")



def handle_signals():
    """Handle OS signals for graceful shutdown."""
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_event.set)

def main():
    """Main entry point."""
    handle_signals()
    try:
        asyncio.run(run_lsl_relay_manager())
    except KeyboardInterrupt:
        logger.info("[LSL Relay] Received keyboard interrupt.")
    finally:
        # Ensure that the shutdown process is initiated
        asyncio.run(shutdown_manager())
        logging.shutdown()

if __name__ == "__main__":
    import signal
    main()
