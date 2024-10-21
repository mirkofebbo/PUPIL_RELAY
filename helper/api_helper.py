import asyncio
import logging

from pupil_labs.realtime_api.discovery import Network
from pupil_labs.lsl_relay.cli import main_async, logger_setup

relay_tasks = {}

async def get_devices():
    devices = []
    async with Network() as network:
        print("Discovering devices...")
        await network.wait_for_new_device(timeout_seconds=5)
        if not network.devices:
            print("No devices found.")
            return devices
        print(f"Found {len(network.devices)} device(s).")
        print(f"Devices {network.devices}")
        for device_info in network.devices:
            ip = device_info.addresses[0]
            port = device_info.port
            full_name = device_info.name  # e.g., 'PI monitor:B:cf631ddc673a7d1d._http._tcp.local.'
            # Parse the name to extract device_name and device_id
            device_name, device_id = parse_device_name(full_name)
            devices.append({
                'ip': ip,
                'port': port,
                'name': device_name,
                'device_id': device_id,
                'full_name': full_name,
            })
    return devices

def start_relay_task(device_ip, device_port, device_name):
    # Set up logging for the relay
    log_file_name = f'lsl_relay_{device_name}.log'
    logger_setup(log_file_name)
    
    # Run the relay asynchronously
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    relay_task = loop.create_task(main_async(
        device_address=f"{device_ip}:{device_port}",
        outlet_prefix='pupil_labs',
        time_sync_interval=60,
        timeout=10,
        device_name=device_name,
    ))
    
    # Keep track of the task
    relay_tasks[device_name] = {
        'loop': loop,
        'task': relay_task,
    }
    
    # Run the event loop
    try:
        loop.run_until_complete(relay_task)
    except Exception as e:
        logging.error(f"[{device_name}] Relay task encountered an error: {e}")
    finally:
        # Clean up
        loop.close()
        del relay_tasks[device_name]



#--------------------------------------------------------------------------------
# OTHER
#--------------------------------------------------------------------------------
def parse_device_name(full_name: str):
    name_parts = full_name.split(':')
    if len(name_parts) >= 3:
        service_name = name_parts[0] 
        device_letter = name_parts[1] 
        rest = name_parts[2]  
        device_id_parts = rest.split('.')
        device_id = device_id_parts[0] 
        device_name = f"{device_letter}:{device_id}"
        return device_name, device_id
    else:
        # If the format is unexpected, use full_name as device_name
        return full_name, None