from flask import Blueprint, jsonify, request
import asyncio
from helper.api_helper import (
    get_devices,
    discover_new_devices,
    update_device_configs,
    load_device_configs,
    is_device_available,
    parse_device_name,
)

import json

device_blueprint = Blueprint('device', __name__)

#--------------------------------------------------------------------------------
# DISCOVER DEVICES 
#--------------------------------------------------------------------------------
@device_blueprint.route('/get_devices', methods=['GET'])
def get_devices_route():
    devices = asyncio.run(get_devices())
    return jsonify({'devices': devices})

@device_blueprint.route('/discover_new_devices', methods=['GET'])
def discover_new_devices_route():
    new_devices = asyncio.run(discover_new_devices())
    print(new_devices)
    # Update configurations
    update_device_configs(new_devices)
    return jsonify({'new_devices': new_devices})

#--------------------------------------------------------------------------------
# UPDATE DEVICE NAME
#--------------------------------------------------------------------------------
@device_blueprint.route('/update_device_name', methods=['POST'])
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