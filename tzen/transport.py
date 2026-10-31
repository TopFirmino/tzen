"""Byte transports used by the harness client; protocol codecs live in ttp."""
import time


class SerialTransport:
    def __init__(self, port, baudrate=115200, reset_wait=2.0):
        import serial
        self.serial = serial.Serial(port, baudrate, timeout=0.05, write_timeout=2.0)
        try:
            time.sleep(reset_wait)  # Mega resets when the USB serial port opens.
            self.serial.reset_input_buffer()
        except BaseException:
            self.serial.close()
            raise

    def read(self, size=1):
        return self.serial.read(size)

    def write(self, data):
        if self.serial.write(data) != len(data):
            raise OSError("short serial write")

    def close(self):
        self.serial.close()
