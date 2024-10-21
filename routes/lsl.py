from flask import Blueprint, jsonify, request
from threading import Thread
import asyncio
import logging
from helper.api_helper import get_devices, start_relay_task

# Import your existing LSL relay code
from pupil_labs.lsl_relay.cli import main_async, logger_setup
from pupil_labs.realtime_api.discovery import Network

lsl_blueprint = Blueprint('lsl', __name__)

# Dictionary to keep track of relay tasks
relay_tasks = {}

#--------------------------------------------------------------------------------
# DISCOVER DEVICES 
#--------------------------------------------------------------------------------
@lsl_blueprint.route('/discover_devices', methods=['GET'])
def discover_devices():
    devices = asyncio.run(get_devices())
    return jsonify({'devices': devices})

#--------------------------------------------------------------------------------
# START LSL RELAY
#--------------------------------------------------------------------------------
@lsl_blueprint.route('/start_relay', methods=['POST'])
def start_relay():
    data = request.get_json()
    device_ip = data.get('device_ip')
    device_port = data.get('device_port')
    device_name = data.get('device_name', f"{device_ip}:{device_port}")
    
    if not device_ip or not device_port:
        return jsonify({'error': 'device_ip and device_port are required'}), 400
    
    # Check if the device is detected
    devices = asyncio.run(get_devices())
    device_available = any(
        device for device in devices if device['ip'] == device_ip and device['port'] == device_port
    )
    
    if not device_available:
        return jsonify({'error': f'Device {device_name} is not available on the network'}), 404

    # Check if the relay is already running for this device
    if device_name in relay_tasks:
        return jsonify({'message': f'Relay already running for device {device_name}'}), 200
    
    # Start the relay in a new thread to avoid blocking
    thread = Thread(target=start_relay_task, args=(device_ip, device_port, device_name))
    thread.start()
    
    return jsonify({'message': f'Started relay for device {device_name}'})

#--------------------------------------------------------------------------------
# STOP LSL RELAY
#--------------------------------------------------------------------------------
@lsl_blueprint.route('/stop_relay', methods=['POST'])
def stop_relay():
    data = request.get_json()
    device_name = data.get('device_name')
    
    if not device_name:
        return jsonify({'error': 'device_name is required'}), 400
    
    if device_name not in relay_tasks:
        return jsonify({'message': f'No relay running for device {device_name}'}), 404
    
    # Cancel the relay task
    relay_info = relay_tasks[device_name]
    loop = relay_info['loop']
    task = relay_info['task']
    
    def cancel_task():
        task.cancel()
    
    loop.call_soon_threadsafe(cancel_task)
    
    return jsonify({'message': f'Stopped relay for device {device_name}'})