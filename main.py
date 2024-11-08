import os
import asyncio
import signal
from devices.device_discovery import run_device_discovery
from devices.lsl_relay_manager import run_lsl_relay_manager, shutdown_manager, relay_tasks, relay_tasks_lock
from devices.device_monitor import monitor_device_status


import psutil

async def monitor_open_file_descriptors(interval=60):
    """Monitor and log the number of open file descriptors."""
    process = psutil.Process()
    while True:
        fd_count = process.num_fds()
        print(f"[Resource Monitor] Current open file descriptors: {fd_count}")
        if fd_count > 100: 
            print(f"[Resource Monitor] High number of open file descriptors: {fd_count}")
        await asyncio.sleep(interval)

async def main():
    """Main function to run all tasks concurrently."""
    print(f"Process PID: {os.getpid()}")
    
    tasks = [
        run_device_discovery(),
        # run_lsl_relay_manager(),
        monitor_device_status(),
        monitor_open_file_descriptors()  
    ]

    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.CancelledError:
        print("[Main] Main task cancelled")
    except Exception as e:
        print(f"[Main] Exception occurred: {e}")
    finally:
        print("[Main] Application cleanup completed")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[Main] Application was closed via keyboard interrupt")
        # Run the shutdown manager directly to ensure cleanup on keyboard interrupt
        asyncio.run(shutdown_manager())

