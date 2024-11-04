# utils.py

import json
import os
import asyncio

file_lock = asyncio.Lock()

async def read_json_file(file_path):
    """Asynchronously read data from a JSON file."""
    async with file_lock:
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                data = json.load(f)
        else:
            data = []
    return data

async def write_json_file(file_path, data):
    """Asynchronously write data to a JSON file."""
    async with file_lock:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)