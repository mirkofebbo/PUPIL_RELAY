import logging
import time
import pylsl
from collections import Counter 

class LSLManager:
    def __init__(self, retry_interval=5):
        self.outlet = None
        self.test_outlet = None
        self.previous_id = [] 
        self.logger = logging.getLogger(__name__)
        self.retry_interval = retry_interval
        self.create_outlet()

    def create_outlet(self):
        print("[LSLManager] LSL Timestamp Stream created.")
        """Initialize the LSL stream outlet for timestamped messages."""
        try:
            info = pylsl.StreamInfo(
                name="TimestampStream",
                type="marker",
                channel_count=1,
                channel_format=pylsl.cf_string, 
                source_id="timestamp_stream_01"
            )
            self.outlet = pylsl.StreamOutlet(info)
            self.logger.info("[LSLManager] LSL Timestamp Stream created.")
        except Exception as e:
            self.logger.error(f"[LSLManager] Failed to create LSL outlet: {e}")
            self.outlet = None

    def create_test_outlet(self, number: int):
        """Function to test multiple outlets with the same name."""
        self.test_outlet = [] 
        for n in range(number):
            try:
                info = pylsl.StreamInfo(
                    name="MultiOutletTest",
                    type="marker",
                    channel_count=1,
                    channel_format=pylsl.cf_string,
                    source_id=f"multi_outlet_test"
                )
                outlet = pylsl.StreamOutlet(info)
                self.test_outlet.append(outlet)
                msg = f"Test Outlet Created {n+1}"
                self.logger.info(f"[LSLManager] {msg}")
                print(f"[LSLManager] {msg}")
            except Exception as e:
                self.logger.error(f"[LSLManager] Failed to create test LSL outlet {n}: {e}")
        
    async def close_test_outlet(self):
        if self.test_outlet:
            del self.test_outlet
            self.test_outlet = None

            self.logger.info("[LSLManager] LSL Test Stream closed.")
            print("[LSLManager] LSL Test Stream closed.")

    def send_message(self, message: str):
        """Send a message with the current Unix timestamp."""
        try:
            timestamp = int(time.time())
            data = f'T:{timestamp}_M:{message}'
            if self.outlet:
                self.outlet.push_sample([data])
                self.logger.info(f"[LSLManager] Sent message: {data}")
                
                print(f"[LSLManager] Sent message: {data}")
            else:
                self.logger.warning("[LSLManager] LSL outlet is not initialized. Attempting to recreate outlet.")
                print("[LSLManager] LSL outlet is not initialized. Attempting to recreate outlet.")
                self.create_outlet()
                if self.outlet:
                    self.outlet.push_sample([data])
                    self.logger.info(f"[LSLManager] Sent message after reinitializing outlet: {data}")
                else:
                    self.logger.error("[LSLManager] Failed to reinitialize LSL outlet.")
        except Exception as e:
            self.logger.error(f"[LSLManager] Failed to send message: {e}")

    async def close_outlet(self):
        if self.outlet:
            del self.outlet
            self.outlet = None
            self.logger.info("[LSLManager] LSL Timestamp Stream closed.")
            print("[LSLManager] LSL Timestamp Stream closed.")

    def get_stream_id(stream):
        return (stream.name(), stream.type(), stream.source_id())
    

# does not work for some reason 
    # async def get_streams(self):
    #     """Get the list of available LSL streams."""
    #     try:
    #         streams = pylsl.resolve_streams()
    #         stream_ids = [self.get_stream_id(stream) for stream in streams]
    #         stream_count = Counter(stream_ids)
    #         print(f"[LSLManager] LSL stream count: {streams}")
    #         # if stream_ids != self.previous_id:
    #         #     self.logger.info(f"[LSLManager] LSL stream count: {stream_count}")
    #         #     self.send_message(f"LSL stream count: {stream_count}")
    #         #     self.previous_id = stream_ids

    #         self.logger.info(f"[LSLManager] Available LSL streams: {streams}")
    #         return stream_ids
        
    #     except Exception as e:
    #         self.logger.error(f"[LSLManager] Failed to get LSL streams: {e}")
    #         return []