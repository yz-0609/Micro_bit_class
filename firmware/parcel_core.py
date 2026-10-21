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
