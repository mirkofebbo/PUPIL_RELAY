import os
import asyncio
import logging
import signal
from devices.device_discovery import run_device_discovery
from devices.lsl_relay_manager import run_lsl_relay_manager, shutdown_manager, relay_tasks, relay_tasks_lock
from devices.device_monitor import monitor_device_status

LOG_FILE_NAME = 'main.log'
logging.basicConfig(level=logging.DEBUG, filename=LOG_FILE_NAME, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

import psutil

async def monitor_open_file_descriptors(interval=60):
    """Monitor and log the number of open file descriptors."""
    process = psutil.Process()
    while True:
        fd_count = process.num_fds()
        logger.info(f"[Resource Monitor] Current open file descriptors: {fd_count}")
        if fd_count > 1000:  # Set a threshold to monitor potential leaks
            logger.warning(f"[Resource Monitor] High number of open file descriptors: {fd_count}")
        await asyncio.sleep(interval)

async def main():
    """Main function to run all tasks concurrently."""
    logging.basicConfig(level=logging.INFO, filename='application.log')
    print(f"Process PID: {os.getpid()}")
    
    tasks = [
        run_device_discovery(),
        run_lsl_relay_manager(),
        monitor_device_status(),
        monitor_open_file_descriptors()  
    ]

    # Create a signal handler to capture termination signals
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown_manager()))

    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.CancelledError:
        logger.info("[Main] Main task cancelled")
    except Exception as e:
        logger.error(f"[Main] Exception occurred: {e}")
    finally:
        logger.info("[Main] Application cleanup completed")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[Main] Application was closed via keyboard interrupt")
        # Run the shutdown manager directly to ensure cleanup on keyboard interrupt
        asyncio.run(shutdown_manager())
    finally:
        logging.shutdown()
