# main.py

import asyncio
import logging
import sys
import os

from pupil_labs.lsl_relay.cli import main_async, logger_setup

# Add the parent directory to the system path to find the pupil_labs package
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# device_configs = [
#     {'address': '192.168.1.244:8080', 'name': 'A'},
#     {'address': '192.168.1.243:8080', 'name': 'B'},
# ]

# TEST
device_configs = [
    {'address': '192.168.8.180:8080', 'name': 'A'},
    {'address': '192.168.8.160:8080', 'name': 'B'},
    {'address': '192.168.8.227:8080', 'name': 'C'},
    {'address': '192.168.8.244:8080', 'name': 'D'},
    {'address': '192.168.8.125:8080', 'name': 'E'},
    {'address': '192.168.8.224:8080', 'name': 'F'},
    {'address': '192.168.8.111:8080', 'name': 'G'},
    {'address': '192.168.8.217:8080', 'name': 'H'},
]

async def main():
    """Main function to run the LSL relay for multiple devices."""
    # Set up logging
    log_file_name = 'lsl_relay.log'
    logger_setup(log_file_name)

    # Define default parameters
    outlet_prefix = 'pupil_labs'
    time_sync_interval = 60  # Interval in seconds for time-sync events
    timeout = 30  # Time limit in seconds to try to connect to the devices

    # Run relays for all devices
    relay_tasks = []
    for config in device_configs:
        device_address = config['address']
        device_name = config['name']
        print(f"Starting relay for device {device_name} at {device_address}")
        task = asyncio.create_task(
            main_async(
                device_address=device_address,
                outlet_prefix=outlet_prefix,
                time_sync_interval=time_sync_interval,
                timeout=timeout,
                device_name=device_name,  
            )
        )
        relay_tasks.append(task)

    # Wait for all relays to complete (they run indefinitely)
    results = await asyncio.gather(*relay_tasks, return_exceptions=True)

    # Check for exceptions
    for config, result in zip(device_configs, results):
        device_name = config['name']
        if isinstance(result, Exception):
            logging.error(f"[{device_name}] An error occurred in a relay task: {result}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("The relay was closed via keyboard interrupt")
    finally:
        logging.shutdown()