import csv
import json
from pathlib import Path

STATUS_FIELDS = ('trip', 'duration', 'strength', 'angle', 'pin', 'pot', 'mode',
                 'limit', 'peak', 'shock', 'tilt', 'opening', 'muted', 'saved', 'closed')
DUMP_FIELDS = ('trip', 'duration', 'mode', 'limit', 'peak', 'shock', 'tilt',
               'opening', 'total', 'retained', 'saved')
KINDS = {'S': '冲击', 'T': '持续倾斜', 'O': '开箱'}


def parse(line):
    p = line.strip().split(',')
    try:
        kind = p[0]
        if kind == '@S' and len(p) == 17 and p[1] in ('N', 'O', 'I', 'C', 'R', 'V'):
            result = dict(zip(STATUS_FIELDS, map(int, p[2:])))
            result.update(type='S', state=p[1])
            if result['pin'] not in (-1, 0, 1) or not 0 <= result['pot'] <= 1023 or result['mode'] not in (0, 1, 2):
                return None
            return result
        if kind == '@D' and len(p) == 12:
            result = dict(zip(DUMP_FIELDS, map(int, p[1:])))
            if any(value < 0 for value in result.values()) or result['mode'] not in (0, 1, 2) or result['retained'] > 16:
                return None
            result['type'] = 'D'
            return result
        if kind in ('@E', '@R') and len(p) == 6 and p[4] in KINDS:
            return dict(type=kind[1], trip=int(p[1]), id=int(p[2]),
                        elapsed=int(p[3]), kind=p[4], value=int(p[5]))
        if kind == '@DONE' and len(p) == 2:
            return dict(type='DONE', trip=int(p[1]))
        if kind == '@A' and len(p) == 2:
            return dict(type='A', message=p[1])
        if kind == '@HELLO' and len(p) == 4 and p[1] == 'PARCEL_BASIC':
            return dict(type='HELLO', sensor_range=int(p[2]), closed=int(p[3]))
    except (ValueError, OverflowError):
        pass
    return None


class Snapshot:
    def __init__(self):
        self.pending = None
        self.rows = []

    def feed(self, message):
        if message['type'] == 'D':
            self.pending = dict(message)
            self.rows = []
        elif message['type'] == 'R' and self.pending:
            self.rows.append(dict(message))
        elif message['type'] == 'DONE':
            meta, rows = self.pending, self.rows
            self.pending, self.rows = None, []
            if not meta or message['trip'] != meta['trip']:
                raise ValueError('记录快照缺少匹配的摘要')
            n = meta['total']
            if meta['retained'] != len(rows) or len(rows) != min(n, 16):
                raise ValueError('记录快照不完整，请重新读取')
            if meta['shock'] + meta['tilt'] + meta['opening'] != n:
                raise ValueError('累计次数与事件总数不一致')
            expected = list(range(n - len(rows) + 1, n + 1))
            if [r['id'] for r in rows] != expected or any(r['trip'] != meta['trip'] for r in rows):
                raise ValueError('事件序号不连续，请重新读取')
            return dict(summary=meta, events=rows)
        return None


def export_snapshot(snapshot, filename):
    path = Path(filename)
    m = snapshot['summary']
    if not m['trip']:
        raise ValueError('尚无运输记录')
    fields = ['记录类型', '运输编号', '事件序号', '启运后秒数', '事件', '数值', '单位',
              '冲击次数', '倾斜次数', '开箱次数', '最大采样加速度g', '冲击阈值g',
              '灵敏度', '板端闪存保存（基础版不支持）', '保留事件数', '累计事件数']
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(fields)
        writer.writerow(['摘要', m['trip'], '', m['duration'] / 1000, '', '', '',
                         m['shock'], m['tilt'], m['opening'], m['peak'] / 1000,
                         m['limit'] / 1000, ('低', '中', '高')[m['mode']], m['saved'],
                         m['retained'], m['total']])
        for e in snapshot['events']:
            value = e['value'] / 1000 if e['kind'] == 'S' else e['value']
            unit = {'S': 'g（采样值）', 'T': '度', 'O': '开关电平'}[e['kind']]
            writer.writerow(['事件', e['trip'], e['id'], e['elapsed'] / 1000,
                             KINDS[e['kind']], value, unit] + [''] * 9)
    path.with_suffix('.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
    return path
