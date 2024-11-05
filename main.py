# main.py
import os
import asyncio
import logging
from devices.device_discovery import run_device_discovery
from devices.lsl_relay_manager import run_lsl_relay_manager
from devices.device_monitor import monitor_device_status

async def main():
    """Main function to run all tasks concurrently."""
    logging.basicConfig(level=logging.INFO, filename='application.log')
    print(os.getpid())
    tasks = [
        run_device_discovery(),
        run_lsl_relay_manager(),
        monitor_device_status(),
    ]

    await asyncio.gather(*tasks, return_exceptions=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("[Main] Application was closed via keyboard interrupt")
    finally:
        logging.shutdown()