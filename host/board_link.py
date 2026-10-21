"""USB raw REPL tools. No firmware flashing or filesystem erasure."""
import ast
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host" / "vendor"))
import serial
from serial.tools import list_ports


def ports():
    return [p.device for p in sorted(list_ports.comports(), key=lambda p: p.vid != 0x0D28)]


class BoardLink:
    def __init__(self, port="COM42"):
        self.port = serial.Serial(port, 115200, timeout=0.1)
        self.buffer = bytearray()

    def until(self, marker, timeout=8):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            index = self.buffer.find(marker)
            if index >= 0:
                stop = index + len(marker)
                result = bytes(self.buffer[:stop])
                del self.buffer[:stop]
                return result
            self.buffer.extend(self.port.read(self.port.in_waiting or 1))
        raise TimeoutError(repr(bytes(self.buffer)[-300:]))

    def enter(self):
        self.port.write(b"\x03")
        time.sleep(0.3)
        self.port.read(self.port.in_waiting)
        self.buffer = bytearray()
        self.port.write(b"\r\x01")
        self.until(b"raw REPL; CTRL-B to exit\r\n>")

    def execute(self, source, timeout=8):
        data = source.encode("utf-8") if isinstance(source, str) else source
        for i in range(0, len(data), 32):
            self.port.write(data[i:i + 32])
            self.port.flush()
            time.sleep(0.02)
        self.port.write(b"\x04")
        ack = self.until(b"OK")
        if ack != b"OK":
            raise RuntimeError("Raw REPL acknowledgement: " + repr(ack))
        output = self.until(b"\x04", timeout)[:-1]
        error = self.until(b"\x04>", timeout)[:-2]
        if error.strip():
            raise RuntimeError(error.decode("utf-8", "replace"))
        return output.decode("utf-8", "replace")

    def read_file(self, name):
        listing = ast.literal_eval(self.execute("import os\nprint(os.listdir())").strip())
        if name not in listing:
            return None
        self.execute("_file=open(%r,'rb')" % name)
        data = bytearray()
        try:
            while True:
                chunk = ast.literal_eval(self.execute("print(repr(_file.read(384)))").strip())
                data.extend(chunk)
                if len(chunk) < 384:
                    break
        finally:
            self.execute("_file.close()\ndel _file")
        return bytes(data)

    def write_file(self, name, data):
        self.execute("_file=open(%r,'wb')" % name)
        try:
            for i in range(0, len(data), 256):
                self.execute("_file.write(%r)" % data[i:i + 256])
        finally:
            self.execute("_file.close()\ndel _file")
        if self.read_file(name) != data:
            raise RuntimeError("Readback mismatch: " + name)

    def close(self):
        self.port.write(b"\x02")
        self.port.close()
