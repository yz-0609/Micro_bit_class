"""Back up board files, upload the recorder, verify bytes, then soft reset."""
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
import time

from board_link import BoardLink, ROOT


def main():
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', default='COM42')
    parser.add_argument('--no-start', action='store_true')
    args = parser.parse_args()
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S')
    backup = ROOT / 'backups' / stamp
    backup.mkdir(parents=True, exist_ok=True)
    names = ['parcel_core.py', 'parcel_actions.py', 'parcel_hardware.py']
    files = [(name, name) for name in names]
    files.append(('parcel_main.py', 'main.py'))
    link = BoardLink(args.port)
    link.enter()
    try:
        for _, name in files:
            original = link.read_file(name)
            if original is not None:
                (backup / name).write_bytes(original)
                print('BACKUP', name, len(original), flush=True)
        # Dependencies first; commit the startup file last.
        for source, target in files:
            data = (ROOT / 'firmware' / source).read_bytes()
            link.write_file(target, data)
            print('VERIFIED', target, len(data), flush=True)
        print('BACKUP_DIRECTORY', backup)
        if not args.no_start:
            link.port.write(b'\x02')
            link.port.flush()
            time.sleep(0.2)
            link.port.write(b'\x04')
            link.port.flush()
            boot = bytearray()
            end = time.monotonic() + 8
            while time.monotonic() < end:
                boot.extend(link.port.read(link.port.in_waiting or 1))
                if b'@S,' in boot:
                    break
            print(boot.decode('utf-8', 'replace'))
            if b'@S,' not in boot or b'Traceback' in boot or b'MemoryError' in boot:
                link.enter()
                raise RuntimeError('Board startup validation failed')
    except Exception:
        # Restore the prior startup file if upload fails partway through.
        if (backup / 'main.py').exists():
            link.write_file('main.py', (backup / 'main.py').read_bytes())
            print('RESTORED_PREVIOUS_MAIN')
        raise
    finally:
        link.port.close()


if __name__ == '__main__':
    main()
