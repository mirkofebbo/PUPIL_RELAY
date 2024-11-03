import asyncio
import logging
import json
import os
import threading

from pupil_labs.realtime_api.discovery import Network
from pupil_labs.realtime_api import Device, Network
from pupil_labs.realtime_api.discovery import discover_devices

# api_helper.py
from helper.config_utils import load_device_configs, save_device_configs

config_lock = threading.Lock()
# Dictionary to keep track of relay tasks
relay_tasks = {}

# --------------------------------------------------------------------------------
# DEVICE DISCOVERY
# --------------------------------------------------------------------------------


def update_device_status(device_id, **kwargs):
    with config_lock:
        existing_devices_dict = load_device_configs()
        if device_id in existing_devices_dict:
            device = existing_devices_dict[device_id]
            for key, value in kwargs.items():
                if value is not None:
                    device[key] = value
            save_device_configs(existing_devices_dict)


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
    for device_id, device in existing_devices_dict.items():
        ip = device['ip']
        port = device['port']
        name = device['name']
        # Check if the device is available
        is_available = await is_device_available(ip, port)
        # Update the 'available' status in the device config
        device['available'] = is_available
        devices.append({
            'ip': ip,
            'port': port,
            'name': name,
            'device_id': device_id,
            'available': is_available,
            'battery_level': device.get('battery_level'),
            'glasses_serial': device.get('glasses_serial'),
            'world_camera_serial': device.get('world_camera_serial'),
            'connected': device.get('connected', False),
            'lsl_streaming': device.get('lsl_streaming', False),
            'recording': device.get('recording', False),
        })
    # Save updated configurations
    save_device_configs(existing_devices_dict)
    return devices


async def discover_new_devices():
    devices = []
    print("Discovering devices...")
    try:
        # Use the discover_devices async generator
        async for device_info in discover_devices(timeout_seconds=5):
            ip = device_info.addresses[0]
            port = device_info.port
            full_name = device_info.name
            print(f"Discovered device with full_name: {full_name}")

            # Create a Device instance to get more metadata
            async with Device.from_discovered_device(device_info) as device:
                status = await device.get_status()
                device_id = status.phone.device_id
                device_name = status.phone.name or full_name
                battery_level = status.phone.battery_level
                glasses_serial = status.hardware.glasses_serial
                world_camera_serial = status.hardware.world_camera_serial

                devices.append({
                    'ip': ip,
                    'port': port,
                    'name': device_name,
                    'device_id': device_id,
                    'available': True,
                    'battery_level': battery_level,
                    'glasses_serial': glasses_serial,
                    'world_camera_serial': world_camera_serial,
                    'connected': False,
                    'lsl_streaming': False,
                    'recording': False,
                })
        if not devices:
            print("No new devices found.")
    except Exception as e:
        print(f"Error during device discovery: {e}")
    return devices

# --------------------------------------------------------------------------------
# RELAY MANAGEMENT
# --------------------------------------------------------------------------------


def start_relay_task(device_ip, device_port, device_name, device_id):
    from pupil_labs.lsl_relay.cli import main_async, logger_setup
    # Set up logging for the relay
    log_file_name = f'lsl_relay_{device_name}.log'
    logger_setup(log_file_name)

    # Create a new event loop for this thread
    loop = asyncio.new_event_loop()

    # Keep track of the task
    relay_tasks[device_id] = {
        'loop': loop,
        'task': None,  # Will set later
        'device': None,  # Will set later
        'device_name': device_name,
    }

    async def setup_device_and_relay():
        asyncio.set_event_loop(loop)
        async with Network() as network:
            await network.wait_for_new_device(timeout_seconds=5)
            matching_device_info = next(
                (d for d in network.devices if device_ip in d.addresses), None)
            if matching_device_info:
                device = await Device.from_discovered_device(matching_device_info)
            else:
                logging.error(f"Could not find device info for {device_name}")
                return

            # Update device 'connected' and 'lsl_streaming' statuses
            update_device_status(device_id, connected=True, lsl_streaming=True)

            # Store the device instance
            relay_tasks[device_id]['device'] = device

            # Run the relay task
            relay_task = asyncio.create_task(main_async(
                device_address=f"{device_ip}:{device_port}",
                outlet_prefix='pupil_labs',
                time_sync_interval=60,
                timeout=10,
                device_name=device_name,
                config_updater=update_device_status,
            ))

            relay_tasks[device_id]['task'] = relay_task

            # Wait for relay task to finish
            await relay_task

    # Start the event loop in a separate thread
    def run_loop():
        asyncio.set_event_loop(loop)
        loop.create_task(setup_device_and_relay())
        try:
            loop.run_forever()
        except Exception as e:
            logging.error(f"Error in event loop: {e}")
        finally:
            # Clean up after loop stops
            loop.close()
            if device_id in relay_tasks:
                del relay_tasks[device_id]
            update_device_status(
                device_id, connected=False, lsl_streaming=False)
            logger.info(f"[{device_name}] Event loop stopped and cleaned up.")

    thread = threading.Thread(target=run_loop)
    thread.start()

    relay_tasks[device_id]['thread'] = thread

# --------------------------------------------------------------------------------
# OTHER UTILITIES
# --------------------------------------------------------------------------------


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


def update_device_configs(new_devices):
    existing_devices_dict = load_device_configs()

    # Update existing configs with new devices or add new ones
    for device in new_devices:
        device_id = device['device_id']
        if device_id in existing_devices_dict:
            # Update existing device info but retain the name
            existing_device = existing_devices_dict[device_id]
            existing_device['ip'] = device['ip']
            existing_device['port'] = device['port']
            existing_device['available'] = True
            # Remove 'source' if it exists
            existing_device.pop('source', None)
            # Update or add new metadata fields
            existing_device['battery_level'] = device.get(
                'battery_level', existing_device.get('battery_level'))
            existing_device['glasses_serial'] = device.get(
                'glasses_serial', existing_device.get('glasses_serial'))
            existing_device['world_camera_serial'] = device.get(
                'world_camera_serial', existing_device.get('world_camera_serial'))
            # Ensure statuses are present
            existing_device['connected'] = existing_device.get(
                'connected', False)
            existing_device['recording'] = existing_device.get(
                'recording', False)
            existing_device['lsl_streaming'] = existing_device.get(
                'lsl_streaming', False)
        else:
            # Use the discovered name (device letter) as the default name
            device_name = device['name']
            existing_devices_dict[device_id] = {
                'ip': device['ip'],
                'port': device['port'],
                'name': device_name,
                'device_id': device_id,
                'available': True,
                # 'source' is omitted
                'battery_level': device.get('battery_level'),
                'glasses_serial': device.get('glasses_serial'),
                'world_camera_serial': device.get('world_camera_serial'),
                'connected': False,
                'lsl_streaming': False,
                'recording': False,
            }

    # Save updated configurations
    save_device_configs(existing_devices_dict)


def save_device_configs(devices_dict):
    config_path = 'device_configs.json'
    with open(config_path, 'w') as f:
        json.dump(list(devices_dict.values()), f, indent=4)
