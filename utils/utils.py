# utils/utils.py
import threading
import asyncio
import json

file_lock = threading.Lock()

async def read_json_file(file_path):
    def read_file():
        with file_lock:
            with open(file_path, 'r') as f:
                data = json.load(f)
        return data

    # Run the blocking I/O operation in a thread
    return await asyncio.to_thread(read_file)

async def write_json_file(file_path, data):
    def write_file():
        with file_lock:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=4)

    # Run the blocking I/O operation in a thread
    await asyncio.to_thread(write_file)
