from pupil_labs.realtime_api.discovery import Network
from pupil_labs.lsl_relay.cli import main_async, logger_setup
import asyncio
import logging
import sys
import os
from typing import List, Optional

# Add the parent directory to the system path to find the pupil_labs package
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


async def main():
    # Set up logging
    log_file_name = 'lsl_relay.log'
    logger_setup(log_file_name)

    # Define default parameters
    device_addresses = ['192.168.0.201:8080',  # F
                        '192.168.0.13:8080',  # E
                        '192.168.0.240:8080',  # C
                        '192.168.0.177:8080',  # L
                        '192.168.0.230:8080',  # K
                        '192.168.0.42:8080'
                        ]   # Set to list of 'IP:port' strings if you know the device addresses
    outlet_prefix = 'pupil_labs'
    time_sync_interval = 60  # Interval in seconds for time-sync events
    timeout = 30  # Time limit in seconds to try to connect to the devices

    # Discover devices if device_addresses is not provided
    if device_addresses is None:
        device_addresses = await discover_devices(timeout)

    # Run relays for all devices
    relay_tasks = [
        asyncio.create_task(
            main_async(
                device_address=device_address,
                outlet_prefix=outlet_prefix,
                time_sync_interval=time_sync_interval,
                timeout=timeout,
            )
        )
        for device_address in device_addresses
    ]

    # Wait for all relays to complete (they run indefinitely)
    await asyncio.gather(*relay_tasks)


async def discover_devices(timeout: int) -> List[str]:
    device_addresses = []
    async with Network() as network:
        print("Discovering devices...")
        await network.wait_for_new_device(timeout_seconds=timeout)
        for device_info in network.devices:
            ip = device_info.addresses[0]
            port = device_info.port
            device_address = f"{ip}:{port}"
            device_addresses.append(device_address)
            print(f"Found device at {device_address}")
    return device_addresses

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("The relay was closed via keyboard interrupt")
    finally:
        logging.shutdown()
