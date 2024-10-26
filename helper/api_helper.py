import asyncio
import logging
import json
import os

from pupil_labs.realtime_api.discovery import Network
from pupil_labs.lsl_relay.cli import main_async, logger_setup
from pupil_labs.realtime_api import Device

# Dictionary to keep track of relay tasks
relay_tasks = {}

#--------------------------------------------------------------------------------
# DEVICE DISCOVERY
#--------------------------------------------------------------------------------

async def is_device_available(ip, port):
    try:
        # Attempt to connect to the device
        async with Device(ip, port) as device:
            await device.get_status()
        return True
    except Exception:
        return False

async def get_devices():
    devices = []
    existing_devices_dict = load_device_configs()
    for device in existing_devices_dict.values():
        ip = device['ip']
        port = device['port']
        name = device['name']
        device_id = device['device_id']
        is_available = await is_device_available(ip, port)
        devices.append({
            'ip': ip,
            'port': port,
            'name': name,
            'device_id': device_id,
            'available': is_available,
            'source': 'config'
        })
    return devices

async def discover_new_devices():
    devices = []
    async with Network() as network:
        print("Discovering devices...")
        await network.wait_for_new_device(timeout_seconds=5)
        if not network.devices:
            print("No new devices found.")
            return devices
        print(f"Found {len(network.devices)} new device(s).")
        for device_info in network.devices:
            ip = device_info.addresses[0]
            port = device_info.port
            full_name = device_info.name
            device_name, device_id = parse_device_name(full_name)
            devices.append({
                'ip': ip,
                'port': port,
                'name': device_name,
                'device_id': device_id,
                'available': True,
                'source': 'discovery'
            })
    return devices

#--------------------------------------------------------------------------------
# RELAY MANAGEMENT
#--------------------------------------------------------------------------------

def start_relay_task(device_ip, device_port, device_name, device_id):
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
    relay_tasks[device_id] = {
        'loop': loop,
        'task': relay_task,
    }

    # Run the event loop
    try:
        loop.run_until_complete(relay_task)
    except asyncio.CancelledError:
        logging.info(f"[{device_name}] Relay task was cancelled.")
    except Exception as e:
        logging.error(f"[{device_name}] Relay task encountered an error: {e}")
    finally:
        # Clean up
        loop.close()
        del relay_tasks[device_id]

#--------------------------------------------------------------------------------
# OTHER UTILITIES
#--------------------------------------------------------------------------------

def parse_device_name(full_name: str):
    name_parts = full_name.split(':')
    if len(name_parts) >= 3:
        # Extract the device letter and device ID
        device_letter = name_parts[1]
        rest = name_parts[2]
        device_id_parts = rest.split('.')
        device_id = device_id_parts[0]
        device_name = device_letter  # Use only the letter as the device name
        return device_name, device_id
    else:
        return full_name, None

def load_device_configs():
    config_path = 'device_configs.json'
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            configs = json.load(f)
            return {device['device_id']: device for device in configs}
    else:
        return {}

def update_device_configs(new_devices):
    config_path = 'device_configs.json'
    existing_devices_dict = load_device_configs()

    # Update existing configs with new devices or add new ones
    for device in new_devices:
        device_id = device['device_id']
        if device_id in existing_devices_dict:
            # Update existing device info but retain the name
            existing_devices_dict[device_id]['ip'] = device['ip']
            existing_devices_dict[device_id]['port'] = device['port']
            existing_devices_dict[device_id]['available'] = True
            existing_devices_dict[device_id]['source'] = device['source']
        else:
            # Use the discovered name (device letter) as the default name
            device_name = device['name']
            existing_devices_dict[device_id] = {
                'ip': device['ip'],
                'port': device['port'],
                'name': device_name,
                'device_id': device_id,
                'available': True,
                'source': device['source']
            }

    # Save updated configurations
    with open(config_path, 'w') as f:
        json.dump(list(existing_devices_dict.values()), f, indent=4)