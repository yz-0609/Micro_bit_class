import microbit as m
import music,gc
from parcel_actions import command

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
