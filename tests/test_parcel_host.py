import csv
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'host'))
from parcel_protocol import parse, Snapshot, export_snapshot


class ProtocolTests(unittest.TestCase):
    def test_real_status_frame_and_noise(self):
        frame = parse('@S,R,1,1000,1024,5,1,1023,2,1250,1300,1,0,0,0,0,1')
        self.assertEqual(frame['state'], 'R')
        self.assertEqual(frame['pot'], 1023)
        self.assertIsNone(parse('>>>'))
        self.assertIsNone(parse('@S,,1,1000,1024,5,1,1023,2,1250,1300,1,0,0,0,0,1'))
        self.assertIsNone(parse('@S,R,1,1000,1024,5,1,1023,9,1250,1300,1,0,0,0,0,1'))

    def test_snapshot_ignores_interleaved_live_events(self):
        s = Snapshot()
        s.feed(parse('@D,1,5000,1,1500,1900,1,0,0,1,1,1'))
        s.feed(parse('@E,1,2,5001,O,0'))
        s.feed(parse('@R,1,1,1200,S,1900'))
        result = s.feed(parse('@DONE,1'))
        self.assertEqual(len(result['events']), 1)

    def test_incomplete_and_mismatched_snapshots_rejected(self):
        for done in ('@DONE,1', '@DONE,2'):
            s = Snapshot()
            s.feed(parse('@D,1,5000,1,1500,1900,1,0,0,1,1,1'))
            with self.assertRaises(ValueError):
                s.feed(parse(done))

    def test_last_16_of_40_and_export_units(self):
        s = Snapshot()
        s.feed(parse('@D,2,5000,1,1500,1900,40,0,0,40,16,0'))
        for i in range(25, 41):
            s.feed(parse('@R,2,{},1200,S,1900'.format(i)))
        result = s.feed(parse('@DONE,2'))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'events.csv'
            export_snapshot(result, path)
            with path.open(encoding='utf-8-sig') as f:
                rows = list(csv.reader(f))
            self.assertEqual(len(rows), 18)
            self.assertEqual(rows[2][5], '1.9')
            self.assertTrue(path.with_suffix('.json').exists())


if __name__ == '__main__':
    unittest.main()
