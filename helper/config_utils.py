# config_utils.py
import json
import os
import threading

config_lock = threading.Lock()

def load_device_configs():
    with config_lock:
        config_path = 'device_configs.json'
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                configs = json.load(f)
                return {device['device_id']: device for device in configs}
        else:
            return {}

def save_device_configs(devices_dict):
    with config_lock:
        config_path = 'device_configs.json'
        with open(config_path, 'w') as f:
            json.dump(list(devices_dict.values()), f, indent=4)