# lsl.py
from flask import Blueprint, jsonify, request
from threading import Thread
import asyncio
import logging
from helper.api_helper import (
    get_devices,
    start_relay_task,
    relay_tasks,  # Import relay_tasks
    discover_new_devices,
    update_device_configs,
    update_device_status,
    load_device_configs,
)

from pupil_labs.lsl_relay.cli import main_async, logger_setup
from pupil_labs.realtime_api.discovery import Network

lsl_blueprint = Blueprint('lsl', __name__)


logger = logging.getLogger(__name__)
# Remove the local relay_tasks definition
# relay_tasks = {}

# --------------------------------------------------------------------------------
# DISCOVER DEVICES
# --------------------------------------------------------------------------------


@lsl_blueprint.route('/get_devices', methods=['GET'])
def get_devices_route():
    devices = asyncio.run(get_devices())
    return jsonify({'devices': devices})


@lsl_blueprint.route('/discover_new_devices', methods=['GET'])
def discover_new_devices_route():
    new_devices = asyncio.run(discover_new_devices())
    # Update configurations
    update_device_configs(new_devices)
    return jsonify({'new_devices': new_devices})

# --------------------------------------------------------------------------------
# START LSL RELAY
# --------------------------------------------------------------------------------
@lsl_blueprint.route('/start_relay', methods=['POST'])
def start_relay():
    data = request.get_json()
    device_ip = data.get('device_ip')
    device_port = data.get('device_port')
    device_name = data.get('device_name', f"{device_ip}:{device_port}")
    device_id = data.get('device_id')

    if not device_ip or not device_port or not device_id:
        return jsonify({'error': 'device_ip, device_port, and device_id are required'}), 400

    # Check if the device is detected
    devices = asyncio.run(get_devices())
    device_available = any(
        device for device in devices if device['ip'] == device_ip and device['port'] == device_port
    )

    if not device_available:
        return jsonify({'error': f'Device {device_name} is not available on the network'}), 404

    # Check if the relay is already running for this device using device_id
    if device_id in relay_tasks:
        return jsonify({'message': f'Relay already running for device {device_name}'}), 200

    # Start the relay in a new thread to avoid blocking
    thread = Thread(target=start_relay_task, args=(
        device_ip, device_port, device_name, device_id))
    thread.start()

    return jsonify({'message': f'Started relay for device {device_name}'})

# --------------------------------------------------------------------------------
# STOP LSL RELAY
# --------------------------------------------------------------------------------
@lsl_blueprint.route('/stop_relay', methods=['POST'])
def stop_relay():
    data = request.get_json()
    device_id = data.get('device_id')
    device_name = data.get('device_name')

    if not device_id:
        return jsonify({'error': 'device_id is required'}), 400

    if device_id not in relay_tasks:
        return jsonify({'message': f'No relay running for device {device_name}'}), 404

    relay_info = relay_tasks.get(device_id)
    loop = relay_info['loop']
    task = relay_info['task']

    def cancel_task_and_cleanup():
        if not task.cancelled():
            task.cancel()
            try:
                asyncio.ensure_future(task)
            except Exception as e:
                logging.error(f"Error while stopping task for {device_name}: {e}")
            finally:
                if device_id in relay_tasks:
                    del relay_tasks[device_id]
                # Update device 'connected' and 'lsl_streaming' statuses
                update_device_status(device_id, connected=False, lsl_streaming=False)

    loop.call_soon_threadsafe(cancel_task_and_cleanup)

    return jsonify({'message': f'Stopped relay for device {device_name}'})

# --------------------------------------------------------------------------------
# STREAM STATUS
# --------------------------------------------------------------------------------
@lsl_blueprint.route('/get_stream_status', methods=['GET'])
def get_stream_status():
    # Create a dictionary to represent the current status of all streaming tasks
    status = {}
    for device_id, task_info in relay_tasks.items():
        is_streaming = not task_info['task'].cancelled()  # Check if the task is still active
        status[device_id] = {
            'device_name': task_info.get('device_name', 'Unknown'),
            'is_streaming': is_streaming,
        }
    return jsonify({'status': status})



@lsl_blueprint.route('/update_device_name', methods=['POST'])
def update_device_name():
    data = request.get_json()
    device_id = data.get('device_id')
    new_name = data.get('name')

    if not device_id or not new_name:
        return jsonify({'error': 'device_id and name are required'}), 400

    existing_devices = load_device_configs()
    if device_id in existing_devices:
        existing_devices[device_id]['name'] = new_name
        # Save updated configurations
        with open('device_configs.json', 'w') as f:
            json.dump(list(existing_devices.values()), f, indent=4)
        return jsonify({'message': f'Device name updated to {new_name}'})
    else:
        return jsonify({'error': 'Device not found'}), 404



@lsl_blueprint.route('/start_recording', methods=['POST'])
def start_recording():
    data = request.get_json()
    device_id = data.get('device_id')

    if not device_id:
        return jsonify({'error': 'device_id is required'}), 400

    if device_id not in relay_tasks or relay_tasks[device_id].get('device') is None:
        return jsonify({'error': f'No valid device instance found for {device_id}'}), 404

    device = relay_tasks[device_id]['device']

    async def initiate_recording(device):
        try:
            recording_id = await device.recording_start()
            relay_tasks[device_id]['recording_id'] = recording_id
            logger.info(f"Recording started on device {device_id} with ID {recording_id}")
            # Update device 'recording' status
            update_device_status(device_id, recording=True)
            return {'message': f'Recording started on device {device_id}', 'recording_id': recording_id}
        except Exception as e:
            logger.error(f"Error starting recording on device {device_id}: {e}")
            return {'error': str(e)}

    try:
        result = asyncio.run(initiate_recording(device))
        if 'error' in result:
            return jsonify(result), 500
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error running start_recording: {e}")
        return jsonify({'error': str(e)}), 500