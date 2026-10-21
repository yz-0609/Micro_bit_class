# 易碎品运输记录系统：micro:bit V1 / Mu 单文件版
# Mu 中选择 BBC micro:bit 模式，打开本文件并点击“刷入 / Flash”。
# P1：碰撞开关（按住为合盖）；P2：电位计；P0：扩展板蜂鸣器。
# A：开始 / 结束；B：静音 / 恢复；开始前按住开关并将板放稳。
# 记录在内存中，断电、重启或开始下一次运输会清除，请及时导出。
# 本文件已包含全部板端逻辑，无需上传其他 parcel_*.py 文件。

import gc,micropython
micropython.opt_level(3)
gc.collect()

# ---------- 事件检测与记录 ----------
from math import sqrt,acos
MAX_EVENTS=16

class Recorder:
    def __init__(self,closed=1,sensor_range=2):
        self.closed=closed
        self.range=sensor_range
        self.state='I'
        self.trip=self.duration=self.peak=self.n=self.angle=0
        self.counts=[0,0,0]
        self.events=[]
        self.mode=1
        self.limit=1500
        self.pin=self.raw=-1
        self.changed=0
        self.strength=self.g0=1000

    def record(self,i):
        t,v=self.events[i]
        return self.n-len(self.events)+i+1,t,'STO'[v//65536],v%65536

    def event(self,kind,now,value):
        k='STO'.index(kind)
        self.n+=1
        self.counts[k]+=1
        if len(self.events)==MAX_EVENTS:
            self.events.pop(0)
        self.events.append((now-self.start,k*65536+value))

    def cmd(self,cmd,now,pot=0):
        if cmd=='CAL_CLOSE' and self.state!='R':
            self.closed=self.pin
            self.state='O'
            return 'RELEASE_SWITCH'
        if cmd=='CAL_OPEN' and self.state!='R':
            if self.pin==self.closed:
                return 'SAME_LEVEL'
            self.state='V' if self.trip else 'I'
            return 'CALIBRATED'
        if cmd=='START' and self.state!='R':
            if self.pin!=self.closed:
                return 'CLOSE_LID'
            self.base=self.xyz
            self.g0=max(1,self.strength)
            self.mode=min(2,pot*3//1024)
            self.limit=((1750,1500,1250) if self.range==2 else (2500,2000,1500))[self.mode]
            self.trip+=1
            self.start=now
            self.duration=self.peak=self.n=self.angle=0
            self.counts=[0,0,0]
            self.events=[]
            self.high=self.tilt=False
            self.tilt_at=-1
            self.ready=self.angle_at=now
            self.state='R'
            return 'STARTED'
        if cmd=='STOP' and self.state=='R':
            self.duration=now-self.start
            self.state='V'
            return 'STOPPED'
        return 'NOT_READY'

    def step(self,now,xyz,switch):
        self.xyz=xyz
        x,y,z=xyz
        self.strength=int(sqrt(x*x+y*y+z*z))
        if switch!=self.raw:
            self.raw=switch
            self.changed=now
        if now-self.changed>=60 and self.pin!=switch:
            old=self.pin
            self.pin=switch
            if self.state=='R' and old==self.closed and switch!=self.closed:
                self.event('O',now,switch)
        if self.state!='R':
            return
        self.duration=now-self.start
        g=self.strength*1000//self.g0
        self.peak=max(self.peak,g)
        if g>=self.limit and not self.high and now>=self.ready:
            self.event('S',now,g)
            self.high=True
            self.ready=now+500
        if g<self.limit*85//100:
            self.high=False
        if now-self.angle_at>=100:
            dot=(x*self.base[0]+y*self.base[1]+z*self.base[2])/(max(1,self.strength)*self.g0)
            self.angle=int(acos(max(-1,min(1,dot)))*57.2958)
            self.angle_at=now
        if 800<=g<=1200 and self.angle>=45:
            if self.tilt_at<0:
                self.tilt_at=now
            if not self.tilt and now-self.tilt_at>=2000:
                self.event('T',now,self.angle)
                self.tilt=True
        else:
            self.tilt_at=-1
            if self.angle<=35:
                self.tilt=False

gc.collect()

# ---------- 串口命令 ----------
def command(r,s,cmd,now,pot):
    if cmd=='DUMP':
        print('@D,{},{},{},{},{},{},{},{},{},{},0'.format(r.trip,r.duration,r.mode,r.limit,r.peak,r.counts[0],r.counts[1],r.counts[2],r.n,len(r.events)))
        for i in range(len(r.events)):
            print('@R,{},{},{},{},{}'.format(r.trip,*r.record(i)))
        print('@DONE,{}'.format(r.trip))
        return
    if cmd=='MUTE':
        s[0]=not s[0]
        result='MUTED' if s[0] else 'SOUND_ON'
    elif cmd=='SAVE':
        result='RAM_ONLY'
    else:
        result=r.cmd(cmd,now,pot)
    print('@A,'+result)

gc.collect()

# ---------- 硬件与主循环 ----------
import microbit as m
import music,gc

def run(r):
    m.uart.init(115200)
    m.pin1.set_pull(m.pin1.PULL_DOWN)
    s=[False]
    rx=b''
    report=n=0
    m.display.on()
    print('@HELLO,PARCEL_BASIC,{},{}'.format(r.range,r.closed))
    while True:
        now=m.running_time()
        pot=m.pin2.read_analog()
        r.step(now,m.accelerometer.get_values(),m.pin1.read_digital())
        if m.uart.any():
            rx+=m.uart.read() or b''
            if len(rx)>96:
                rx=b''
            while b'\n' in rx:
                line,rx=rx.split(b'\n',1)
                command(r,s,str(line,'utf-8').strip(),now,pot)
        if m.button_a.was_pressed():
            command(r,s,'STOP' if r.state=='R' else 'START',now,pot)
        if m.button_b.was_pressed():
            command(r,s,'MUTE',now,pot)
        if r.n<n:
            n=0
        if r.n>n:
            for i in range(max(0,len(r.events)-(r.n-n)),len(r.events)):
                print('@E,{},{},{},{},{}'.format(r.trip,*r.record(i)))
            if not s[0]:
                music.pitch(880,120,pin=m.pin0,wait=False)
            n=r.n
        if now>=report:
            screen=str(min(2,pot*3//1024)+1) if r.state=='I' else (r.record(len(r.events)-1)[2] if r.n else r.state)
            m.display.show(screen)
            print('@S,'+','.join(str(v) for v in (r.state,r.trip,r.duration,r.strength*1000//r.g0,r.angle,r.pin,pot,r.mode,r.limit,r.peak,r.counts[0],r.counts[1],r.counts[2],int(s[0]),0,r.closed)))
            report=now+250
            gc.collect()
        m.sleep(20)

gc.collect()
r=Recorder()
run(r)
