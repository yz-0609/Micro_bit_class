"""Parcel recorder desktop monitor; only actual serial data are displayed."""
from collections import deque
from datetime import datetime
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from board_link import serial, ports
from parcel_protocol import parse, Snapshot, export_snapshot, KINDS

STATE = {'N': '等待合盖标定', 'O': '等待开盖标定', 'I': '待机', 'C': '静止校准中',
         'R': '运输监测中', 'V': '检查记录'}
NOTICE = {
    'RELEASE_SWITCH': '合盖电平已采集：请松开开关，再点击“标定开盖”。',
    'CALIBRATED': '开盖状态已确认，合盖并将主控板放稳后可开始运输。',
    'SAME_LEVEL': '两次电平相同，请改变开关状态后重试。',
    'CLOSE_LID': '请先合盖（模块调试时按住开关）。',
    'STARTED': '运输监测已开始，灵敏度已锁定。',
    'STOPPED': '本次运输已结束，请导出记录后再断电。',
    'RAM_ONLY': '基础版使用内存记录，请导出到电脑。',
    'MUTED': '提示音已静音，事件继续记录。',
    'SOUND_ON': '提示音已恢复。',
    'NOT_READY': '当前状态不能执行此操作。',
}


class Transport(threading.Thread):
    def __init__(self, port, inbox):
        super().__init__(daemon=True)
        self.name_port = port
        self.inbox = inbox
        self.commands = queue.Queue()
        self.stopped = threading.Event()

    def run(self):
        try:
            with serial.Serial(self.name_port, 115200, timeout=0.1) as ser:
                self.inbox.put(('connection', True))
                buffer = b''
                while not self.stopped.is_set():
                    try:
                        cmd = self.commands.get_nowait()
                        ser.write((cmd + '\n').encode('ascii'))
                    except queue.Empty:
                        pass
                    buffer += ser.read(ser.in_waiting or 1)
                    while b'\n' in buffer:
                        raw, buffer = buffer.split(b'\n', 1)
                        line = raw.decode('utf-8', 'replace').strip()
                        msg = parse(line)
                        if msg:
                            self.inbox.put(('data', msg))
                        elif 'Traceback' in line or 'MemoryError' in line:
                            self.inbox.put(('error', '板端程序异常：' + line))
                    if len(buffer) > 4096:
                        buffer = b''
        except Exception as exc:
            self.inbox.put(('error', '串口连接失败：' + str(exc)))
        finally:
            self.inbox.put(('connection', False))


class Monitor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('易碎品运输记录系统')
        self.geometry('1080x800')
        self.minsize(920, 710)
        self.configure(bg='#eef3f8')
        self.inbox = queue.Queue()
        self.worker = None
        self.connected = False
        self.last_sample = 0
        self.status_data = None
        self.snapshot = None
        self.assembler = Snapshot()
        self.export_path = None
        self.dump_deadline = 0
        self.series = deque(maxlen=160)
        self.current_trip = None
        self.event_rows = deque(maxlen=16)
        self.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TFrame', background='#eef3f8')
        style.configure('TLabel', background='#eef3f8', font=('Microsoft YaHei', 10))
        style.configure('TButton', font=('Microsoft YaHei', 10), padding=6)
        style.configure('Treeview', font=('Microsoft YaHei', 10), rowheight=28)
        style.configure('Treeview.Heading', font=('Microsoft YaHei', 10, 'bold'))
        self.build()
        self.refresh()
        self.after(100, self.poll)

    def build(self):
        root = ttk.Frame(self, padding=20)
        root.pack(fill='both', expand=True)
        ttk.Label(root, text='易碎品运输记录系统', font=('Microsoft YaHei', 22, 'bold')).pack(anchor='w')
        ttk.Label(root, text='冲击 · 持续倾斜 · 开箱事件    |    内存记录与 CSV 导出').pack(anchor='w', pady=(3, 14))
        bar = ttk.Frame(root)
        bar.pack(fill='x')
        self.port = ttk.Combobox(bar, state='readonly', width=14)
        self.port.pack(side='left')
        ttk.Button(bar, text='刷新串口', command=self.refresh).pack(side='left', padx=6)
        self.connect_button = ttk.Button(bar, text='连接设备', command=self.toggle)
        self.connect_button.pack(side='left')
        self.connection_text = tk.StringVar(value='未连接')
        ttk.Label(bar, textvariable=self.connection_text).pack(side='left', padx=12)
        cards = ttk.Frame(root)
        cards.pack(fill='x', pady=16)
        self.cards = {}
        for i, (key, title) in enumerate([('state', '运行状态'), ('strength', '采样加速度'),
                                         ('angle', '相对倾角'), ('shock', '冲击次数'),
                                         ('tilt', '倾斜次数'), ('opening', '开箱次数')]):
            cell = tk.Frame(cards, bg='white', padx=12, pady=12)
            cell.grid(row=0, column=i, sticky='nsew', padx=(0, 8))
            cards.columnconfigure(i, weight=1)
            tk.Label(cell, text=title, bg='white', fg='#52657b', font=('Microsoft YaHei', 10)).pack(anchor='w')
            value = tk.StringVar(value='—')
            tk.Label(cell, textvariable=value, bg='white', fg='#143859', font=('Microsoft YaHei', 17, 'bold')).pack(anchor='w', pady=(8, 0))
            self.cards[key] = value
        actions = ttk.Frame(root)
        actions.pack(fill='x')
        self.buttons = {}
        for cmd, text in [('CAL_CLOSE', '① 标定合盖'), ('CAL_OPEN', '② 标定开盖'),
                          ('START', '开始运输'), ('STOP', '结束运输'), ('MUTE', '静音 / 恢复'),
                          ('DUMP', '读取记录')]:
            button = ttk.Button(actions, text=text, command=lambda c=cmd: self.send(c), state='disabled')
            button.pack(side='left', padx=(0, 5))
            self.buttons[cmd] = button
        self.detail = tk.StringVar(value='连接后显示箱盖电平、灵敏度及阈值。')
        ttk.Label(root, textvariable=self.detail, wraplength=1000).pack(anchor='w', pady=(12, 4))
        self.notice = tk.StringVar(value='默认按住为合盖、松开为开盖；若电平相反，可用两步标定调整。开始时将板放稳。')
        ttk.Label(root, textvariable=self.notice, wraplength=1000, foreground='#215f90').pack(anchor='w', pady=(0, 12))
        self.chart = tk.Canvas(root, height=160, bg='white', highlightthickness=0)
        self.chart.pack(fill='x')
        self.chart.bind('<Configure>', lambda e: self.draw_chart())
        tablebar = ttk.Frame(root)
        tablebar.pack(fill='x', pady=(12, 5))
        ttk.Label(tablebar, text='最近 16 条事件', font=('Microsoft YaHei', 11, 'bold')).pack(side='left')
        self.export_button = ttk.Button(tablebar, text='导出 CSV 与摘要', command=self.export, state='disabled')
        self.export_button.pack(side='right')
        table = ttk.Frame(root)
        table.pack(fill='both', expand=True)
        columns = ('id', 'time', 'kind', 'value')
        self.tree = ttk.Treeview(table, columns=columns, show='headings', height=7)
        for key, title, width in [('id', '序号', 80), ('time', '启运后 / 秒', 150),
                                  ('kind', '事件', 170), ('value', '采样值 / 状态', 220)]:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor='center')
        scroll = ttk.Scrollbar(table, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        ttk.Label(root, text='板上：按 A 开始 / 结束；按 B 静音 / 恢复。开始前按住碰撞开关并将板放稳。\n基础版记录保存在内存中，断电或重启会清除；需要留存时请先导出到电脑。', foreground='#52657b').pack(anchor='w', pady=(10, 0))

    def refresh(self):
        available = ports()
        self.port['values'] = available
        if self.port.get() not in available and available:
            self.port.set(available[0])

    def toggle(self):
        if self.worker and self.worker.is_alive():
            self.worker.stopped.set()
            self.connect_button.configure(state='disabled')
            return
        if not self.port.get():
            self.notice.set('没有可用串口，请连接 micro:bit 后刷新。')
            return
        self.snapshot = None
        self.status_data = None
        self.last_sample = 0
        self.export_path = None
        self.assembler = Snapshot()
        self.series.clear()
        self.event_rows.clear()
        self.render_events()
        self.worker = Transport(self.port.get(), self.inbox)
        self.worker.start()

    def send(self, command):
        if self.connected and self.worker:
            if command == 'DUMP':
                self.assembler = Snapshot()
                self.dump_deadline = time.monotonic() + 5
            self.worker.commands.put(command)

    def export(self):
        path = filedialog.asksaveasfilename(parent=self, title='导出运输记录',
                                          defaultextension='.csv', filetypes=[('CSV 文件', '*.csv')],
                                          initialfile='运输记录_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.csv')
        if path:
            self.export_path = path
            self.send('DUMP')
            self.notice.set('正在读取设备快照，校验完整性后导出。')

    def handle(self, m):
        kind = m['type']
        if kind == 'S':
            self.last_sample = time.monotonic()
            self.status_data = m
            if self.current_trip != m['trip']:
                self.current_trip = m['trip']
                self.event_rows.clear()
                self.series.clear()
                self.snapshot = None
                self.render_events()
            self.cards['state'].set(STATE[m['state']])
            self.cards['strength'].set('{:.2f} g'.format(m['strength'] / 1000))
            self.cards['angle'].set('{}°'.format(m['angle']))
            for key in ('shock', 'tilt', 'opening'):
                self.cards[key].set(str(m[key]))
            self.series.append(m['strength'] / 1000)
            mode = min(2, m['pot'] * 3 // 1024) if m['state'] in ('N', 'O', 'I') else m['mode']
            lid = '未标定' if m['closed'] < 0 else ('合盖' if m['pin'] == m['closed'] else '开盖')
            self.detail.set('运输 #{}  ·  {:.1f} 秒  ·  箱盖 {}（P1={}）  ·  电位计 {}  ·  灵敏度 {}{}  ·  冲击阈值 {:.2f} g  ·  {}'.format(
                m['trip'], m['duration'] / 1000, lid, m['pin'], m['pot'], ('低', '中', '高')[mode],
                '（已锁定）' if m['state'] == 'R' else '', m['limit'] / 1000,
                '内存记录（重启清除，请导出留存）'))
            self.draw_chart()
        elif kind == 'E':
            self.current_trip = m['trip']
            self.event_rows.append(m)
            self.render_events()
        elif kind == 'A':
            self.notice.set(NOTICE.get(m['message'], m['message']))
            if m['message'] == 'STARTED':
                self.event_rows.clear()
                self.series.clear()
                self.snapshot = None
                self.render_events()
        elif kind == 'HELLO':
            self.notice.set('设备已启动，当前加速度量程 ±{}g。'.format(m['sensor_range']))
        if kind in ('D', 'R', 'DONE'):
            try:
                snapshot = self.assembler.feed(m)
                if snapshot:
                    self.dump_deadline = 0
                    self.snapshot = snapshot
                    self.current_trip = snapshot['summary']['trip']
                    self.event_rows = deque(snapshot['events'], maxlen=16)
                    self.render_events()
                    if self.export_path:
                        export_snapshot(snapshot, self.export_path)
                        self.notice.set('已导出：' + self.export_path + '；同目录保存 JSON 摘要。')
                        self.export_path = None
            except (ValueError, OSError) as exc:
                self.notice.set('读取或导出失败：' + str(exc))
                self.export_path = None
                self.dump_deadline = 0

    def render_events(self):
        self.tree.delete(*self.tree.get_children())
        for e in self.event_rows:
            value = '{:.2f} g'.format(e['value'] / 1000) if e['kind'] == 'S' else (
                '{}°'.format(e['value']) if e['kind'] == 'T' else '开盖，电平 {}'.format(e['value']))
            self.tree.insert('', 'end', values=(e['id'], '{:.2f}'.format(e['elapsed'] / 1000), KINDS[e['kind']], value))

    def draw_chart(self):
        c = self.chart
        c.delete('all')
        w, h = max(c.winfo_width(), 400), 160
        limit = (self.status_data or {}).get('limit', 1500) / 1000
        top = max(2.2, limit + 0.3, max(self.series, default=0) + 0.2)
        c.create_text(12, 14, text='采样加速度 / g（最近约 40 秒）', anchor='w', fill='#52657b', font=('Microsoft YaHei', 10))
        for value in (0, 1, 2):
            y = 140 - value / top * 110
            c.create_line(45, y, w - 12, y, fill='#e4ebf2')
            c.create_text(28, y, text=str(value), fill='#52657b')
        y = 140 - limit / top * 110
        c.create_line(45, y, w - 12, y, fill='#e5a237', dash=(5, 4))
        c.create_text(w - 18, y - 9, text='阈值 {:.2f}g'.format(limit), anchor='e', fill='#996613')
        points = []
        for i, value in enumerate(self.series):
            points.extend((45 + i / 159 * (w - 57), 140 - value / top * 110))
        if len(points) >= 4:
            c.create_line(*points, fill='#287bb5', width=2)

    def poll(self):
        for _ in range(300):
            try:
                kind, value = self.inbox.get_nowait()
            except queue.Empty:
                break
            if kind == 'connection':
                self.connected = value
                self.connect_button.configure(text='断开设备' if value else '连接设备', state='normal')
                self.connection_text.set('串口已连接，等待设备数据' if value else '未连接')
                if value:
                    self.send('DUMP')
            elif kind == 'error':
                self.notice.set(value)
            else:
                self.handle(value)
        fresh = self.connected and time.monotonic() - self.last_sample < 3
        if self.connected:
            self.connection_text.set('设备在线 · ' + self.port.get() if fresh else '未收到板端实时数据')
        st = (self.status_data or {}).get('state', '')
        enabled = {'CAL_CLOSE': st not in ('R', 'C'), 'CAL_OPEN': st == 'O',
                   'START': st in ('I', 'V'), 'STOP': st in ('R', 'C'), 'MUTE': True,
                   'DUMP': True}
        for cmd, button in self.buttons.items():
            button.configure(state='normal' if fresh and enabled[cmd] else 'disabled')
        self.export_button.configure(state='normal' if fresh and (self.status_data or {}).get('trip', 0) else 'disabled')
        if self.dump_deadline and time.monotonic() > self.dump_deadline:
            self.dump_deadline = 0
            self.export_path = None
            self.assembler = Snapshot()
            self.notice.set('读取记录超时，未导出不完整快照。请重新读取。')
        self.after(100, self.poll)

    def close(self):
        if self.worker:
            self.worker.stopped.set()
            self.worker.join(timeout=1)
        self.destroy()


if __name__ == '__main__':
    Monitor().mainloop()
