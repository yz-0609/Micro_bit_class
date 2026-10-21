"""Hidden GUI / actual USB integration check on a clean idle board."""
import argparse
import json
import time

from board_link import ROOT
from parcel_monitor import Monitor


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', default='COM42')
parser.add_argument('--test-with-records', action='store_true')
args = parser.parse_args()

app = Monitor()
app.withdraw()
app.port.set(args.port)
app.toggle()
report = {}
with_records = args.test_with_records
folder = ROOT / 'verification' / 'parcel_basic_verification'
folder.mkdir(parents=True, exist_ok=True)
export_path = folder / 'GUI_SIMULATED_TEST_ONLY.csv'


def check_online():
    try:
        assert app.connected and time.monotonic() - app.last_sample < 3
        assert app.status_data['state'] == ('V' if with_records else 'I')
        assert app.status_data['trip'] == int(with_records)
        assert app.snapshot is not None
        assert app.snapshot['summary']['total'] == (43 if with_records else 0)
        report['live_status_and_snapshot'] = True
        if with_records:
            assert len(app.snapshot['events']) == 16
            app.export_path = str(export_path)
            app.send('DUMP')
        app.send('MUTE')
        app.after(1500, check_mute)
    except Exception as exc:
        fail(exc)


def check_mute():
    try:
        assert app.status_data['muted'] == 1
        report['mute_command'] = True
        app.send('MUTE')
        app.after(1500, finish)
    except Exception as exc:
        fail(exc)


def fail(exc):
    report['error'] = repr(exc)
    report['connected'] = app.connected
    report['status'] = app.status_data
    report['snapshot'] = app.snapshot
    report['notice'] = app.notice.get()
    app.close()


def finish():
    try:
        assert app.status_data['muted'] == 0
        report['sound_restore_command'] = True
        if with_records:
            assert app.export_path is None and export_path.is_file()
            saved = json.loads(export_path.with_suffix('.json').read_text(encoding='utf-8'))
            assert saved['summary']['total'] == 43 and len(saved['events']) == 16
            report['gui_export_csv_and_json'] = True
            report['test_data_only'] = True
        report['status'] = app.status_data
        report['all_passed'] = True
        app.close()
    except Exception as exc:
        fail(exc)


app.after(6000, check_online)
app.mainloop()
output = folder / ('gui_export_results.json' if with_records else 'gui_results.json')
output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
if not report.get('all_passed'):
    raise SystemExit(1)
