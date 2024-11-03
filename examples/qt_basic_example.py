# main.py

from PySide6.QtWidgets import QApplication
from qtm_rt.qt_qrt import QtQRTConnection
import sys

def main():
    app = QApplication(sys.argv)
    connection = QtQRTConnection()
    
    # Connect signals
    connection.connected.connect(lambda: print("Connected to QTM"))
    connection.disconnected.connect(lambda: print("Disconnected from QTM"))
    connection.error_occurred.connect(lambda err: print(f"Error: {err}"))
    connection.response_received.connect(lambda resp: print(f"Response Received: {resp}"))
    connection.markers_3d_received.connect(lambda markers: print(f"Received {markers} 3D markers."))

    # Connect to QTM
    connection.connect_to_server('127.0.0.1', 22223)

    # After connected, you can call methods
    def on_connected():
        # Get QTM version
        connection.qtm_version()
        # Start streaming frames with 3D markers
        connection.stream_frames(components=['3d'])

    connection.connected.connect(on_connected)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
