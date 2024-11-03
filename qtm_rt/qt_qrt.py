# qrt_connection.py

from PySide6.QtCore import QObject, Signal
import logging

from qtm_rt.packet import QRTPacketType, QRTEvent, QRTComponentType
from qtm_rt.qt_protocol import QtQTMProtocol

logger = logging.getLogger(__name__)


class QtQRTConnection(QObject):
    """
    High-level connection interface for interacting with the QTM RT server.
    Provides methods to send commands and handles responses using the QtQTMProtocol.
    """

    # Signals
    response_received = Signal(dict)
    error_occurred = Signal(str)
    connected = Signal()
    disconnected = Signal()
    
    calibration_completed = Signal(str)
    
    # Signals for data recived.
    markers_3d_received = Signal(list)
    markers_3d_no_labels_received = Signal(list)
    analog_received = Signal(dict)
    force_received = Signal(dict)
    six_d_received = Signal(list)
    six_d_euler_received = Signal(list)
    two_d_received = Signal(list)
    two_d_lin_received = Signal(list)
    markers_3d_residuals_received = Signal(list)
    markers_3d_no_labels_residuals_received = Signal(list)
    six_d_residuals_received = Signal(list)
    six_d_euler_residuals_received = Signal(list)
    analog_single_received = Signal(dict)
    image_received = Signal(dict)
    force_single_received = Signal(dict)
    gaze_vector_received = Signal(dict)
    timecode_received = Signal(dict)
    skeleton_received = Signal(dict)
    eye_tracker_received = Signal(dict)
    # Additional signals can be added as needed

    def __init__(self, parent=None):
        super().__init__(parent)
        self.protocol = QtQTMProtocol()
        self._setup_signals()
        self.current_callback = None
        self.event_callback = None
        self.expected_event = None
        self.calibration_in_progress = False

        logger.debug("QRTConnection initialized.")

    def _setup_signals(self):
        self.protocol.connected.connect(self.connected)
        self.protocol.disconnected.connect(self.disconnected)
        self.protocol.error_occurred.connect(self.error_occurred)
        self.protocol.response_received.connect(self._on_response_received)

    def connect_to_server(self, host, port=22223):
        """
        Connect to the QTM server.

        :param host: IP address or hostname of the QTM server.
        :param port: Port number to connect to (default is 22223).
        """
        logger.info(f"Connecting to QTM at {host}:{port}")
        self.protocol.connect_to_server(host, port)

    def disconnect(self):
        """
        Disconnect from the QTM server.
        """
        logger.info("Disconnecting from QTM.")
        self.protocol.disconnect()

    def is_connected(self):
        """
        Check if connected to QTM.

        :return: True if connected, False otherwise.
        """
        return self.protocol.is_connected()

    def qtm_version(self, callback=None):
        """
        Get the QTM version.

        :param callback: Optional callback to receive the version string.
        """
        logger.debug("Requesting QTM version.")
        self.current_callback = callback or self._on_qtm_version
        self.protocol.send_command("qtmversion", callback=self.current_callback)

    def _on_qtm_version(self, response):
        version = response['data']
        logger.info(f"QTM Version: {version}")
        self.response_received.emit(response)

    def byte_order(self, callback=None):
        """
        Get the byte order used when communicating.

        :param callback: Optional callback to receive the byte order string.
        """
        logger.debug("Requesting byte order.")
        self.current_callback = callback or self._on_byte_order
        self.protocol.send_command("byteorder", callback=self.current_callback)

    def _on_byte_order(self, response):
        byte_order = response['data']
        logger.info(f"Byte Order: {byte_order}")
        self.response_received.emit(response)

    def get_state(self, callback=None):
        """
        Get the latest state change of QTM.

        :param callback: Optional callback to receive the state string.
        """
        logger.debug("Requesting QTM state.")
        self.current_callback = callback or self._on_get_state
        self.protocol.send_command("getstate", callback=self.current_callback)

    def _on_get_state(self, response):
        state = response['data']
        logger.info(f"QTM State: {state}")
        self.response_received.emit(response)

    def await_event(self, event=None, timeout=30, callback=None):
        """
        Wait for an event from QTM.

        :param event: A QRTEvent to wait for a specific event. Otherwise, wait for any event.
        :param timeout: Max time to wait for the event.
        :param callback: Optional callback to receive the event.
        """
        logger.debug(f"Awaiting event: {event}, timeout: {timeout}")
        self.expected_event = event
        self.event_callback = callback
        # Timeout handling can be implemented if needed

    def _on_event_received(self, event_type):
        event_enum = QRTEvent(event_type)
        logger.info(f"Event received: {event_enum.name}")
        if (self.expected_event is None) or (self.expected_event == event_enum):
            if self.event_callback:
                self.event_callback(event_type)
            self.expected_event = None
            self.event_callback = None

    def get_parameters(self, parameters=None, callback=None):
        """
        Get the settings for the requested components of QTM in XML format.

        :param parameters: A list of parameters to request. Defaults to ['All'].
        :param callback: Optional callback to receive the XML string.
        """
        logger.debug(f"Requesting parameters: {parameters}")
        if parameters is None:
            parameters = ['All']
        else:
            self._validate_parameters(parameters)

        cmd = f"GetParameters {' '.join(parameters)}"
        self.current_callback = callback or self._on_parameters_received
        self.protocol.send_command(cmd, callback=self.current_callback)

    def _on_parameters_received(self, response):
        xml_data = response['data']
        logger.info("Parameters received.")
        self.response_received.emit(response)

    def get_current_frame(self, components=None, callback=None):
        """
        Get measured values from QTM for a single frame.

        :param components: A list of components to receive.
        :param callback: Optional callback to receive the data packet.
        """
        self._validate_components(components)
        cmd = f"getcurrentframe {' '.join(components)}"
        logger.debug(f"Requesting current frame with components: {components}")
        self.current_callback = callback or self._on_current_frame_received
        self.protocol.send_command(cmd, callback=self.current_callback)

    def _on_current_frame_received(self, response):
        qrt_packet = response['data']
        logger.info("Current frame data received.")
        if QRTComponentType.Component3d in qrt_packet.components:
            _, markers = qrt_packet.get_3d_markers()
            self.markers_3d_received.emit(markers)
        self.response_received.emit(response)

    def stream_frames(self, frames="allframes", components=None):
        """
        Stream measured frames from QTM until stream_frames_stop is called.

        :param frames: Which frames to receive ('allframes', 'frequency:n', 'frequencydivisor:n').
        :param components: A list of components to receive.
        """
        self._validate_components(components)
        cmd = f"streamframes {frames} {' '.join(components)}"
        logger.debug(f"Starting frame streaming with command: {cmd}")
        self.protocol.send_command(cmd, callback=self._on_stream_frames_started)

    def _on_stream_frames_started(self, response):
        message = response['data']
        if message.startswith("Ok"):
            logger.info("Streaming frames started.")
        else:
            logger.error(f"Failed to start streaming: {message}")
            self.error_occurred.emit(f"Failed to start streaming: {message}")

    def stream_frames_stop(self):
        """
        Stop streaming frames.
        """
        cmd = "streamframes stop"
        logger.debug("Stopping frame streaming.")
        self.protocol.send_command(cmd, callback=self._on_stream_frames_stopped)

    def _on_stream_frames_stopped(self, response):
        message = response['data']
        if message.startswith("Ok"):
            logger.info("Streaming frames stopped.")
        else:
            logger.error(f"Failed to stop streaming: {message}")
            self.error_occurred.emit(f"Failed to stop streaming: {message}")

    def take_control(self, password, callback=None):
        """
        Take control of QTM.

        :param password: Password as entered in QTM.
        :param callback: Optional callback to receive the response.
        """
        cmd = f"takecontrol {password}"
        logger.debug("Sending takecontrol command.")
        self.current_callback = callback or self._on_take_control
        self.protocol.send_command(cmd, callback=self.current_callback)

    def _on_take_control(self, response):
        message = response['data']
        if message == "You are now master":
            logger.info("Control taken successfully.")
            self.response_received.emit(response)
        else:
            logger.error(f"Failed to take control: {message}")
            self.error_occurred.emit(f"Failed to take control: {message}")

    def release_control(self, callback=None):
        """
        Release control of QTM.

        :param callback: Optional callback to receive the response.
        """
        cmd = "releasecontrol"
        logger.debug("Sending releasecontrol command.")
        self.current_callback = callback or self._on_release_control
        self.protocol.send_command(cmd, callback=self.current_callback)

    def _on_release_control(self, response):
        message = response['data']
        if message == "You are now a regular client":
            logger.info("Control released successfully.")
            self.response_received.emit(response)
        else:
            logger.error(f"Failed to release control: {message}")
            self.error_occurred.emit(f"Failed to release control: {message}")

    def new(self, callback=None):
        """
        Create a new measurement.

        :param callback: Optional callback to receive the response.
        """
        cmd = "new"
        logger.debug("Sending new command.")
        self.current_callback = callback or self._on_new
        self.protocol.send_command(cmd, callback=self.current_callback)

    def _on_new(self, response):
        message = response['data']
        if message in ["Creating new connection", "Already connected"]:
            logger.info("New measurement created or already connected.")
            self.response_received.emit(response)
        else:
            logger.error(f"Failed to create new measurement: {message}")
            self.error_occurred.emit(f"Failed to create new measurement: {message}")

    def close(self, callback=None):
        """
        Close a measurement.

        :param callback: Optional callback to receive the response.
        """
        cmd = "close"
        logger.debug("Sending close command.")
        self.current_callback = callback or self._on_close
        self.protocol.send_command(cmd, callback=self.current_callback)

    def _on_close(self, response):
        message = response['data']
        if message in ["Closing connection", "File closed", "Closing file", "No connection to close"]:
            logger.info("Measurement closed.")
            self.response_received.emit(response)
        else:
            logger.error(f"Failed to close measurement: {message}")
            self.error_occurred.emit(f"Failed to close measurement: {message}")

    def start(self, rtfromfile=False, callback=None):
        """
        Start measurement or RT from file.

        :param rtfromfile: If True, start RT from file.
        :param callback: Optional callback to receive the response.
        """
        cmd = "start" + (" rtfromfile" if rtfromfile else "")
        logger.debug(f"Sending start command: {cmd}")
        self.current_callback = callback or self._on_start
        self.protocol.send_command(cmd, callback=self.current_callback)

    def _on_start(self, response):
        message = response['data']
        if message in ["Starting measurement", "Starting RT from file"]:
            logger.info("Measurement started.")
            self.response_received.emit(response)
        else:
            logger.error(f"Failed to start measurement: {message}")
            self.error_occurred.emit(f"Failed to start measurement: {message}")

    def stop(self, callback=None):
        """
        Stop measurement or RT from file.

        :param callback: Optional callback to receive the response.
        """
        cmd = "stop"
        logger.debug("Sending stop command.")
        self.current_callback = callback or self._on_stop
        self.protocol.send_command(cmd, callback=self.current_callback)

    def _on_stop(self, response):
        message = response['data']
        if message == "Stopping measurement":
            logger.info("Measurement stopped.")
            self.response_received.emit(response)
        else:
            logger.error(f"Failed to stop measurement: {message}")
            self.error_occurred.emit(f"Failed to stop measurement: {message}")

    def load(self, filename, callback=None):
        """
        Load a measurement.

        :param filename: Path to the measurement file.
        :param callback: Optional callback to receive the response.
        """
        cmd = f"load {filename}"
        logger.debug(f"Sending load command: {cmd}")
        self.current_callback = callback or self._on_load
        self.protocol.send_command(cmd, callback=self.current_callback)

    def _on_load(self, response):
        message = response['data']
        if message == "Measurement loaded":
            logger.info("Measurement loaded.")
            self.response_received.emit(response)
        else:
            logger.error(f"Failed to load measurement: {message}")
            self.error_occurred.emit(f"Failed to load measurement: {message}")

    def save(self, filename, overwrite=False, callback=None):
        """
        Save a measurement.

        :param filename: Filename to save as.
        :param overwrite: If True, overwrite existing measurement.
        :param callback: Optional callback to receive the response.
        """
        cmd = f"save {filename}" + (" overwrite" if overwrite else "")
        logger.debug(f"Sending save command: {cmd}")
        self.current_callback = callback or self._on_save
        self.protocol.send_command(cmd, callback=self.current_callback)

    def _on_save(self, response):
        message = response['data']
        if message == "Measurement saved":
            logger.info("Measurement saved.")
            self.response_received.emit(response)
        else:
            logger.error(f"Failed to save measurement: {message}")
            self.error_occurred.emit(f"Failed to save measurement: {message}")

    def load_project(self, project_path, callback=None):
        """
        Load a project.

        :param project_path: Path to the project.
        :param callback: Optional callback to receive the response.
        """
        cmd = f"loadproject {project_path}"
        logger.debug(f"Sending loadproject command: {cmd}")
        self.current_callback = callback or self._on_load_project
        self.protocol.send_command(cmd, callback=self.current_callback)

    def _on_load_project(self, response):
        message = response['data']
        if message == "Project loaded":
            logger.info("Project loaded.")
            self.response_received.emit(response)
        else:
            logger.error(f"Failed to load project: {message}")
            self.error_occurred.emit(f"Failed to load project: {message}")

    def trig(self, callback=None):
        """
        Trigger QTM (when configured to use Software/Wireless trigger).

        :param callback: Optional callback to receive the response.
        """
        cmd = "trig"
        logger.debug("Sending trig command.")
        self.current_callback = callback or self._on_trig
        self.protocol.send_command(cmd, callback=self.current_callback)

    def _on_trig(self, response):
        message = response['data']
        if message == "Trig ok":
            logger.info("Trigger successful.")
            self.response_received.emit(response)
        else:
            logger.error(f"Failed to trigger: {message}")
            self.error_occurred.emit(f"Failed to trigger: {message}")

    def set_qtm_event(self, event=None, callback=None):
        """
        Set event in QTM.

        :param event: Event name (optional).
        :param callback: Optional callback to receive the response.
        """
        cmd = "event" + (f" {event}" if event else "")
        logger.debug(f"Sending event command: {cmd}")
        self.current_callback = callback or self._on_set_qtm_event
        self.protocol.send_command(cmd, callback=self.current_callback)

    def _on_set_qtm_event(self, response):
        message = response['data']
        if message == "Event set":
            logger.info("Event set in QTM.")
            self.response_received.emit(response)
        else:
            logger.error(f"Failed to set event: {message}")
            self.error_occurred.emit(f"Failed to set event: {message}")

    def send_xml(self, xml_string, callback=None):
        """
        Send XML to update QTM settings.

        :param xml_string: XML string to send.
        :param callback: Optional callback to receive the response.
        """
        logger.debug("Sending XML to server.")
        self.current_callback = callback or self._on_send_xml
        self.protocol.send_xml(xml_string, callback=self.current_callback)

    def _on_send_xml(self, response):
        message = response['data']
        logger.info("XML response received.")
        self.response_received.emit(response)

    def calibrate(self, callback=None):
        """
        Start calibration and return calibration result.

        :param callback: Optional callback to receive the calibration result.
        """
        cmd = "calibrate"
        logger.debug("Sending calibrate command.")
        self.calibration_in_progress = True
        self.current_callback = callback or self._on_calibration_started
        self.protocol.send_command(cmd, callback=self.current_callback)

    def _on_calibration_started(self, response):
        message = response['data']
        if message == "Starting calibration":
            logger.info("Calibration started.")
            # The calibration result will be received as an XML packet
            # The response_received signal will handle it
        else:
            logger.error(f"Calibration error: {message}")
            self.error_occurred.emit(f"Calibration error: {message}")
            self.calibration_in_progress = False

    def _on_response_received(self, response):
        """
        Internal method to handle responses received from the protocol handler.

        :param response: Dictionary containing 'type' and 'data'.
        """
        response_type = response['type']
        data = response['data']

        # Handle calibration result
        if self.calibration_in_progress and response_type == QRTPacketType.PacketXML:
            self.calibration_completed.emit(data)
            self.calibration_in_progress = False
            return

        # Handle events
        if response_type == QRTPacketType.PacketEvent:
            event_type = data
            self._on_event_received(event_type)
            return

        # Handle data packets
        if response_type == QRTPacketType.PacketData:
            qrt_packet = data
            qrt_packet
            if QRTComponentType.Component3d in qrt_packet.components:
                _, markers = qrt_packet.get_3d_markers()
                self.markers_3d_received.emit(markers)
            return

        # Deliver the response to the current callback
        if self.current_callback:
            self.current_callback(response)
            self.current_callback = None
        else:
            # Emit the response_received signal for unsolicited responses
            self.response_received.emit(response)

    def _validate_components(self, components):
        """
        Validate that the components are valid.

        :param components: List of components to validate.
        """
        valid_components = [
            "2d", "2dlin", "3d", "3dres", "3dnolabels",
            "3dnolabelsres", "analog", "analogsingle", "force", "forcesingle",
            "6d", "6dres", "6deuler", "6deulerres", "gazevector", "eyetracker",
            "image", "timecode", "skeleton", "skeleton:global",
        ]
        for component in components:
            if component.lower() not in valid_components:
                raise ValueError(f"{component} is not a valid component")

    def _validate_parameters(self, parameters):
        """
        Validate that the parameters are valid.

        :param parameters: List of parameters to validate.
        """
        valid_parameters = [
            'All', 'General', '3D', '6D', 'Analog', 'Force', 'GazeVector',
            'EyeTracker', 'Image', 'Skeleton', 'Skeleton:Global', 'Calibration'
        ]
        for param in parameters:
            if param not in valid_parameters:
                raise ValueError(f"Invalid parameter: {param}")
