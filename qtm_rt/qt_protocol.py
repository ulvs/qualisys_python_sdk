# qt_protocol_handler.py

import struct
import logging
from PySide6.QtCore import QObject, Signal, QByteArray
from PySide6.QtNetwork import QTcpSocket

from qtm_rt.packet import QRTPacket, QRTComponentType, QRTPacketType, RTheader, QRTEvent

logger = logging.getLogger(__name__)


class QtQTMProtocol(QObject):
    """
    Low-level protocol handler for communication with QTM RT server.
    Manages socket connections, sends commands, parses incoming packets,
    and emits signals with structured responses.
    """

    # Signals
    connected = Signal()
    disconnected = Signal()
    error_occurred = Signal(str)
    response_received = Signal(dict)  # Unified signal for all responses

    def __init__(self, parent=None):
        super().__init__(parent)
        self.socket = QTcpSocket(self)
        self.socket.connected.connect(self._on_connected)
        self.socket.disconnected.connect(self._on_disconnected)
        self.socket.readyRead.connect(self._on_ready_read)
        self.socket.errorOccurred.connect(self._on_error)

        self.buffer = QByteArray()
        self.callback_queue = []
        self.connected_flag = False

        logger.debug("QTMProtocolHandler initialized.")

    def connect_to_server(self, host, port):
        """
        Connect to the QTM RT server.

        :param host: IP address or hostname of the QTM server.
        :param port: Port number to connect to.
        """
        logger.info(f"Connecting to QTM RT server at {host}:{port}...")
        self.socket.connectToHost(host, port)

    def disconnect(self):
        """
        Disconnect from the QTM RT server.
        """
        logger.info("Disconnecting from QTM RT server.")
        self.socket.disconnectFromHost()

    def is_connected(self):
        """
        Check if the socket is connected.

        :return: True if connected, False otherwise.
        """
        return self.connected_flag

    def send_command(self, command_str, callback=None):
        """
        Send a command to the QTM RT server.

        :param command_str: Command string to send.
        :param callback: Optional callback to be called when a response is received.
        """
        if not self.connected_flag:
            logger.error("Not connected to QTM RT server.")
            return

        logger.info(f"Sending command: {command_str}")
        command_bytes = command_str.encode('utf-8')
        size = RTheader.size + len(command_bytes) + 1  # +1 for NULL terminator
        packet_type = QRTPacketType.PacketCommand.value
        header = struct.pack('<II', size, packet_type)
        packet = header + command_bytes + b'\x00'
        self.socket.write(packet)

        if callback:
            self.callback_queue.append(callback)
        else:
            self.callback_queue.append(None)  # Placeholder for maintaining queue order

    def send_xml(self, xml_string, callback=None):
        """
        Send XML data to the QTM RT server.

        :param xml_string: XML string to send.
        :param callback: Optional callback to be called when a response is received.
        """
        if not self.connected_flag:
            logger.error("Not connected to QTM RT server.")
            return

        logger.info("Sending XML to server.")
        xml_bytes = xml_string.encode('utf-8') + b'\x00'
        size = RTheader.size + len(xml_bytes)
        packet_type = QRTPacketType.PacketXML.value
        header = struct.pack('<II', size, packet_type)
        packet = header + xml_bytes
        self.socket.write(packet)

        if callback:
            self.callback_queue.append(callback)
        else:
            self.callback_queue.append(None)

    def _on_connected(self):
        logger.info("Connected to QTM RT server.")
        self.connected_flag = True
        self.connected.emit()

        # Read the welcome message
        if self.socket.bytesAvailable():
            welcome_data = self.socket.readAll()
            welcome_message = bytes(welcome_data).decode('utf-8').rstrip('\x00')
            logger.info(f"Welcome message: {welcome_message}")
            # Emit the response
            response = {
                'type': QRTPacketType.PacketCommand,
                'data': welcome_message
            }
            self.response_received.emit(response)

    def _on_disconnected(self):
        logger.warning("Disconnected from QTM RT server.")
        self.connected_flag = False
        self.disconnected.emit()

    def _on_error(self, socket_error):
        error_message = self.socket.errorString()
        logger.error(f"Socket error: {error_message}")
        self.error_occurred.emit(error_message)

    def _on_ready_read(self):
        logger.debug("Data available to read from socket.")
        while self.socket.bytesAvailable():
            data = self.socket.readAll()
            self.buffer.append(data)
            self._process_buffer()

    def _process_buffer(self):
        logger.debug("Processing buffer...")
        while True:
            if len(self.buffer) < RTheader.size:
                logger.debug("Not enough data for header.")
                break  # Not enough data for header
            header_data = self.buffer[:RTheader.size]
            packet_size, packet_type = struct.unpack('<II', bytes(header_data))
            logger.debug(f"Packet size: {packet_size}, packet type: {packet_type}")
            if len(self.buffer) < packet_size:
                logger.debug("Incomplete packet received. Waiting for more data.")
                break  # Wait for the rest of the packet
            packet_data = self.buffer[:packet_size]
            self._handle_packet(packet_type, packet_data)
            self.buffer = self.buffer[packet_size:]

    def _handle_packet(self, packet_type, data):
        packet_type_enum = QRTPacketType(packet_type)
        logger.debug(f"Handling packet of type {packet_type_enum.name} ({packet_type}).")

        response = {
            'type': packet_type_enum,
            'data': None
        }

        if packet_type_enum == QRTPacketType.PacketError:
            error_message = bytes(data[RTheader.size:]).decode('utf-8').rstrip('\x00')
            logger.error(f"Server error: {error_message}")
            response['data'] = error_message
            self.error_occurred.emit(error_message)
            self._deliver_callback(response)
        elif packet_type_enum == QRTPacketType.PacketCommand:
            message = bytes(data[RTheader.size:]).decode('utf-8').rstrip('\x00')
            logger.info(f"Server response: {message}")
            response['data'] = message
            self._deliver_callback(response)
        elif packet_type_enum == QRTPacketType.PacketXML:
            xml_data = bytes(data[RTheader.size:]).decode('utf-8').rstrip('\x00')
            logger.info("XML data received.")
            response['data'] = xml_data
            self._deliver_callback(response)
        elif packet_type_enum == QRTPacketType.PacketData:
            logger.debug("Data packet received.")
            qrt_packet = QRTPacket(bytes(data[RTheader.size:]))
            response['data'] = qrt_packet
            self.response_received.emit(response)
        elif packet_type_enum == QRTPacketType.PacketEvent:
            event_data = bytes(data[RTheader.size:])
            if len(event_data) >= 1:
                event_type = struct.unpack('B', event_data[:1])[0]
                logger.info(f"Event received: {QRTEvent(event_type).name}")
                response['data'] = event_type
                self.response_received.emit(response)
        else:
            logger.warning(f"Unknown packet type: {packet_type_enum}")

    def _deliver_callback(self, response):
        if self.callback_queue:
            callback = self.callback_queue.pop(0)
            if callback:
                callback(response)
            else:
                self.response_received.emit(response)
        else:
            self.response_received.emit(response)
