# device_monitor.py

import os
import asyncio
import logging
from pupil_labs.realtime_api import Device
from utils.utils import read_json_file, write_json_file, DeviceModel

JSON_FILE_PATH = 'devices.json'

# Configure logging
LOG_FILE_NAME = 'device_monitor.log'
logging.basicConfig(level=logging.DEBUG, filename=LOG_FILE_NAME, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def monitor_device_status():
    while True:
        if not os.path.exists(JSON_FILE_PATH):
            logger.warning("No devices.json file found.")
            await asyncio.sleep(60)
            continue

        devices = await read_json_file(JSON_FILE_PATH)

        tasks = []
        for device_data in devices:
            tasks.append(update_device_status(device_data))

        # Run all update tasks concurrently
        await asyncio.gather(*tasks)

        # Save the updated device information
        await write_json_file(JSON_FILE_PATH, devices)

        await asyncio.sleep(30)  # Wait for 30 seconds before next check

async def update_device_status(device_data: DeviceModel):
    device_ip = device_data.ip
    device_port = device_data.port
    device_id = device_data.device_id
    try:
        async with Device(device_ip, device_port) as device:
            status = await device.get_status()
            device_data.available = True
            device_data.battery_level = status.phone.battery_level
            device_data.glasses_serial = status.hardware.glasses_serial or "unknown"
            device_data.world_camera_serial = status.hardware.world_camera_serial or "unknown"
            device_data.connected = True
            device_data.error_message = ""
            logger.info(f"[Device Monitor] Updated status for device {device_id}")
    except asyncio.CancelledError:
        logger.info(f"[Device Monitor] Task for device {device_id} cancelled")
    except Exception as e:
        logger.error(f"[Device Monitor] Could not update status for device {device_id}: {e}")
        device_data.available = False
        device_data.connected = False
        device_data.error_message = str(e)
    finally:
        logger.info(f"[Device Monitor] Finished updating status for device {device_id}")

if __name__ == "__main__":
    asyncio.run(monitor_device_status())
