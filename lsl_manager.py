# lsl_manager.py

import logging
import time
import pylsl

class LSLManager:
    def __init__(self, retry_interval=5):
        self.outlet = None
        self.logger = logging.getLogger(__name__)
        self.retry_interval = retry_interval
        self.create_outlet()

    def create_outlet(self):
        print("[LSLManager] LSL Timestamp Stream created.")
        """Initialize the LSL stream outlet for timestamped messages."""
        try:
            info = pylsl.StreamInfo(
                name="TimestampStream",
                type="Timestamp",
                channel_count=1,
                channel_format=pylsl.cf_string, 
                source_id="timestamp_stream_01"
            )
            self.outlet = pylsl.StreamOutlet(info)
            self.logger.info("[LSLManager] LSL Timestamp Stream created.")
        except Exception as e:
            self.logger.error(f"[LSLManager] Failed to create LSL outlet: {e}")
            self.outlet = None

    def send_message(self, message: str):
        """Send a message with the current Unix timestamp."""
        try:
            timestamp = int(time.time())
            data = f'T:{timestamp}_M:{message}'
            if self.outlet:
                self.outlet.push_sample([data])
                self.logger.debug(f"[LSLManager] Sent message: {data}")
                
                print(f"[LSLManager] Sent message: {data}")
            else:
                self.logger.warning("[LSLManager] LSL outlet is not initialized. Attempting to recreate outlet.")
                print("[LSLManager] LSL outlet is not initialized. Attempting to recreate outlet.")
                self.create_outlet()
                if self.outlet:
                    self.outlet.push_sample([data])
                    self.logger.debug(f"[LSLManager] Sent message after reinitializing outlet: {data}")
                else:
                    self.logger.error("[LSLManager] Failed to reinitialize LSL outlet.")
        except Exception as e:
            self.logger.error(f"[LSLManager] Failed to send message: {e}")

    async def close_outlet(self):
        """Close the LSL outlet gracefully."""

        if self.outlet:
            del self.outlet
            self.outlet = None
            self.logger.info("[LSLManager] LSL Timestamp Stream closed.")
            print("[LSLManager] LSL Timestamp Stream closed.")
