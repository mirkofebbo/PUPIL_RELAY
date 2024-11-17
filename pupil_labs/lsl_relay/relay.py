# relay.py

import asyncio
import logging
import uuid
from typing import List, Optional, Iterable, NoReturn

from pupil_labs.realtime_api import Device, StatusUpdateNotifier, receive_gaze_data
from pupil_labs.realtime_api.models import Component, Event, Sensor
from pupil_labs.realtime_api.simple.models import GazeDataType
from pupil_labs.realtime_api.time_echo import TimeOffsetEstimator

from pupil_labs.lsl_relay import outlets  # Ensure this is correctly implemented

LOG_FILE_NAME = 'pupi_relay.log'

logging.basicConfig(level=logging.DEBUG, filename=LOG_FILE_NAME, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger("pupil_labs.realtime_api.time_echo").setLevel("WARNING")

class Relay:
    @classmethod
    async def run(
        cls,
        device_ip: str,
        device_port: int,
        device_identifier: str,
        outlet_prefix: str,
        model: str,
        module_serial: str,
        time_sync_interval: int,
    ):
        logger.debug(f"[Relay] Initiating relay for device {device_identifier}")
        receiver = DataReceiver(device_ip, device_port, device_identifier)
        await receiver.estimate_clock_offset()
        relay_instance = cls(
            device_ip=device_ip,
            device_port=device_port,
            receiver=receiver,
            device_identifier=device_identifier,
            outlet_prefix=outlet_prefix,
            model=model,
            module_serial=module_serial,
            time_sync_interval=time_sync_interval,
        )
        try:
            await relay_instance.relay_receiver_to_publisher()
        except asyncio.CancelledError:
            logger.info(f"[Relay] Relay task for device {device_identifier} was cancelled")
            raise
        except Exception as e:
            logger.exception(f"[Relay] Relay task for device {device_identifier} encountered an exception: {e}")
        finally:
            await receiver.cleanup()
            logger.debug(f"[Relay] Relay run completed for device {device_identifier}")

    def __init__(
        self,
        device_ip: str,
        device_port: int,
        receiver: "DataReceiver",
        device_identifier: str,
        outlet_prefix: str,
        model: str,
        module_serial: str,
        time_sync_interval: int,
    ):
        logger.debug(f"[Relay] Initializing Relay instance for device {device_identifier}")
        self.device_ip = device_ip
        self.device_port = device_port
        self.device_name = device_identifier
        self.receiver = receiver
        self.session_id = str(uuid.uuid4())
        self.gaze_outlet = outlets.PupilCompanionGazeOutlet(
            device_id=device_identifier,
            outlet_prefix=outlet_prefix,
            model=model,
            module_serial=module_serial,
            session_id=self.session_id,
            clock_offset_ns=self.receiver.clock_offset_ns,
        )
        self.event_outlet = outlets.PupilCompanionEventOutlet(
            device_id=device_identifier,
            outlet_prefix=outlet_prefix,
            model=model,
            module_serial=module_serial,
            session_id=self.session_id,
            clock_offset_ns=self.receiver.clock_offset_ns,
        )
        self.gaze_sample_queue: asyncio.Queue[GazeAdapter] = asyncio.Queue()
        self.publishing_gaze_task = None
        self.publishing_event_task = None
        self.receiving_task = None
        self._time_sync_interval = time_sync_interval
        logger.debug(f"[Relay] Relay instance initialized for device {device_identifier}")

    async def receive_gaze_sample(self):
        logger.debug(f"[Relay] Starting gaze sample reception for device {self.device_name}")
        try:
            while True:
                if self.receiver.gaze_sensor_url:
                    try:
                        async for gaze in receive_gaze_data(
                            self.receiver.gaze_sensor_url, run_loop=True, log_level=30
                        ):
                            if isinstance(gaze, GazeDataType):
                                await self.gaze_sample_queue.put(
                                    GazeAdapter(gaze, self.receiver.clock_offset_ns)
                                )
                            else:
                                logger.warning(
                                    f"[Relay] Dropping unknown gaze data type: {gaze}"
                                )
                    except asyncio.CancelledError:
                        logger.info(f"[Relay] Gaze sample reception task cancelled for device {self.device_name}")
                        break
                    except Exception as e:
                        logger.exception(f"[Relay] Error receiving gaze data: {e}")
                        break
                else:
                    logger.debug(
                        f"[Relay] The gaze sensor was not yet identified for device {self.device_name}."
                    )
                    await asyncio.sleep(1)
        finally:
            logger.debug(f"[Relay] Exiting gaze sample reception for device {self.device_name}")

    async def publish_gaze_sample(self, timeout: float):
        logger.debug(f"[Relay] Starting gaze sample publishing for device {self.device_name}")
        missing_sample_duration = 0
        try:
            while True:
                try:
                    sample = await asyncio.wait_for(self.gaze_sample_queue.get(), timeout)
                    self.gaze_outlet.push_sample_to_outlet(sample)
                    if missing_sample_duration:
                        missing_sample_duration = 0
                except asyncio.TimeoutError:
                    missing_sample_duration += timeout
                    logger.warning(
                        f"[Relay] No gaze sample received for {missing_sample_duration} seconds on device {self.device_name}."
                    )
        except asyncio.CancelledError:
            logger.info(f"[Relay] Gaze sample publishing task cancelled for device {self.device_name}")
            raise
        except Exception as e:
            logger.exception(f"[Relay] Error publishing gaze sample: {e}")
            raise
        finally:
            logger.debug(f"[Relay] Exiting gaze sample publishing for device {self.device_name}")

    async def publish_event_from_queue(self):
        logger.debug(f"[Relay] Starting event publishing for device {self.device_name}")
        try:
            while True:
                try:
                    event = await self.receiver.event_queue.get()
                    self.event_outlet.push_sample_to_outlet(event)
                except asyncio.CancelledError:
                    logger.info(f"[Relay] Event publishing task cancelled for device {self.device_name}")
                    break
                except Exception as e:
                    logger.exception(f"[Relay] Error publishing event: {e}")
        finally:
            logger.debug(f"[Relay] Exiting event publishing for device {self.device_name}")

    async def start_receiving_task(self):
        if self.receiving_task and not self.receiving_task.done():
            logger.debug(
                "Tried to set a new receiving task, but the task is already running."
            )
            return
        self.receiving_task = asyncio.create_task(self.receive_gaze_sample())
        logger.debug(f"[Relay] Receiving task started for device {self.device_name}")

    async def start_publishing_gaze(self):
        if self.publishing_gaze_task and not self.publishing_gaze_task.done():
            logger.debug(
                "Tried to set a new gaze publishing task, but the task is already running."
            )
            return
        self.publishing_gaze_task = asyncio.create_task(
            self.publish_gaze_sample(10)
        )
        logger.debug(f"[Relay] Gaze publishing task started for device {self.device_name}")

    async def start_publishing_event(self):
        if self.publishing_event_task and not self.publishing_event_task.done():
            logger.debug(
                "Tried to set a new event publishing task, but the task is already running."
            )
            return
        self.publishing_event_task = asyncio.create_task(
            self.publish_event_from_queue()
        )
        logger.debug(f"[Relay] Event publishing task started for device {self.device_name}")

    async def relay_receiver_to_publisher(self):
        logger.debug(f"[Relay] Initializing tasks for device {self.device_name}")
        tasks = await self.initialise_tasks()
        logger.debug(f"[Relay] Awaiting tasks for device {self.device_name}")
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            handle_done_pending_tasks(done, pending)
        except asyncio.CancelledError:
            logger.info(f"[Relay] relay_receiver_to_publisher task cancelled for device {self.device_name}")
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.exception(f"[Relay] Exception in relay_receiver_to_publisher for device {self.device_name}: {e}")
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            logger.debug(f"[Relay] relay_receiver_to_publisher completed for device {self.device_name}")

    async def initialise_tasks(self) -> List["asyncio.Task[NoReturn]"]:
        await self.receiver.make_status_update_notifier()
        await self.start_receiving_task()
        await self.start_publishing_gaze()
        await self.start_publishing_event()
        tasks = [
            self.receiving_task,
            self.publishing_gaze_task,
            self.publishing_event_task,
        ]
        # Start time sync task
        if self._time_sync_interval:
            time_sync_task = asyncio.create_task(
                send_events_in_interval(
                    self.device_ip,
                    self.device_port,
                    self.session_id,
                    self._time_sync_interval,
                )
            )
            tasks.append(time_sync_task)
            logger.debug(f"[Relay] Time sync task started for device {self.device_name}")
        return [t for t in tasks if t is not None]

    async def get_device_info_for_outlet(cls, device_ip: str, device_port: int):
        from pupil_labs.lsl_relay.cli import get_device_info_for_outlet
        return await get_device_info_for_outlet(device_ip, device_port)

class DataReceiver:
    def __init__(self, device_ip: str, device_port: int, device_name: str):
        self.device_ip = device_ip
        self.device_port = device_port
        self.device_name = device_name
        self.notifier: Optional[StatusUpdateNotifier] = None
        self.gaze_sensor_url: Optional[str] = None
        self.event_queue: asyncio.Queue[EventAdapter] = asyncio.Queue()
        self.clock_offset_ns: int = 0
        self.gaze_outlet = None 
        self.event_outlet = None

    async def on_update(self, component: Component):
        if isinstance(component, Sensor):
            if component.sensor == "gaze" and component.conn_type == "DIRECT":
                self.gaze_sensor_url = component.url
                logger.debug(f"[DataReceiver] Gaze sensor URL updated: {self.gaze_sensor_url}")
        elif isinstance(component, Event):
            adapted_event = EventAdapter(component, self.clock_offset_ns)
            await self.event_queue.put(adapted_event)
            logger.debug(f"[DataReceiver] Event queued: {adapted_event.name}")

    async def make_status_update_notifier(self):
        logger.debug(f"[DataReceiver] Creating StatusUpdateNotifier for device {self.device_name}")
        async with Device(self.device_ip, self.device_port) as device:
            self.notifier = StatusUpdateNotifier(
                device, callbacks=[self.on_update]
            )
            await self.notifier.receive_updates_start()
            logger.debug(f"[DataReceiver] StatusUpdateNotifier started for device {self.device_name}")

    async def estimate_clock_offset(self):
        """Estimate the Companion-Device-to-Relay clock offset."""
        logger.debug(f"[DataReceiver] Estimating clock offset for device {self.device_name}")
        async with Device(self.device_ip, self.device_port) as device:
            status = await device.get_status()

            if status.phone.time_echo_port is None:
                logger.warning(
                    "[DataReceiver] Pupil Companion app is out-of-date and does not support "
                    "accurate time sync! Relying on less accurate NTP time sync."
                )
                return
            logger.debug(
                f"[DataReceiver] Device Time Echo port: {status.phone.time_echo_port}"
            )

            time_offset_estimator = TimeOffsetEstimator(
                status.phone.ip, status.phone.time_echo_port
            )
            estimated_offset = await time_offset_estimator.estimate()
            if estimated_offset is None:
                logger.warning(
                    f"[DataReceiver] Estimating clock offset failed for device {self.device_name}. "
                    "Relying on less accurate NTP time sync."
                )
                return
            self.clock_offset_ns = round(
                estimated_offset.time_offset_ms.mean * 1e6
            )
            logger.info(
                f"[DataReceiver] Estimated clock offset for device {self.device_name}: "
                f"{self.clock_offset_ns:_} ns"
            )

    async def cleanup(self):
        logger.debug(f"[DataReceiver] Cleaning up for device {self.device_name}")
        # Stop receiving updates
        if self.notifier is not None:
            await self.notifier.receive_updates_stop()
            logger.debug(f"[DataReceiver] StatusUpdateNotifier stopped for device {self.device_name}")
        # Close outlets if they exist
        if self.gaze_outlet:
            self.gaze_outlet.close()
            del self.gaze_outlet
            logger.debug(f"[DataReceiver] Gaze outlet closed for device {self.device_name}")
        if self.event_outlet:
            self.event_outlet.close()
            del self.gaze_outlet
            logger.debug(f"[DataReceiver] Event outlet closed for device {self.device_name}")

class GazeAdapter:
    def __init__(self, sample: GazeDataType, clock_offset_ns: int):
        self.x = sample.x
        self.y = sample.y
        self.timestamp_unix_seconds = (
            sample.timestamp_unix_seconds + clock_offset_ns * 1e-9
        )

class EventAdapter:
    def __init__(self, sample: Event, clock_offset_ns: int):
        self.name = sample.name
        self.timestamp_unix_seconds = (
            sample.timestamp + clock_offset_ns
        ) * 1e-9

def handle_done_pending_tasks(
    done: Iterable["asyncio.Task[NoReturn]"],
    pending: Iterable["asyncio.Task[NoReturn]"],
):
    for done_task in done:
        try:
            done_task.result()
        except asyncio.CancelledError:
            logger.warning(f"[Relay] Task cancelled: {done_task}")
        except Exception as e:
            logger.exception(f"[Relay] Task raised an exception: {e}")

    for pending_task in pending:
        try:
            pending_task.cancel()
            logger.debug(f"[Relay] Pending task cancelled: {pending_task}")
        except asyncio.CancelledError:
            # Cancelling is the intended behavior
            pass

async def send_events_in_interval(
    device_ip: str, device_port: int, session_id: str, sec: int = 60
):
    n_events_sent = 0
    while True:
        await send_timesync_event(
            device_ip, device_port, f"lsl.time_sync.{session_id}.{n_events_sent}"
        )
        await asyncio.sleep(sec)
        n_events_sent += 1
        logger.debug(f"[Relay] Sent time synchronization event no {n_events_sent} for device {device_ip}")

async def send_timesync_event(device_ip: str, device_port: int, message: str):
    async with Device(device_ip, device_port) as device:
        await device.send_event(message)
        logger.debug(f"[Relay] Sent time sync event: {message}")
