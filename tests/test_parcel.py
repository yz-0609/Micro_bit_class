from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'firmware'))
from parcel_core import Recorder

def running(pot=512):
    r=Recorder()
    r.step(0,(0,0,-1000),1)
    r.step(100,(0,0,-1000),1)
    assert r.cmd('START',200,pot)=='STARTED'
    return r

class RecorderTests(unittest.TestCase):
    def test_open_lid_prevents_start(self):
        r=Recorder()
        r.step(0,(0,0,-1000),0)
        r.step(100,(0,0,-1000),0)
        self.assertEqual(r.cmd('START',200),'CLOSE_LID')

    def test_optional_polarity_calibration(self):
        r=Recorder()
        r.step(0,(0,0,-1000),0)
        r.step(100,(0,0,-1000),0)
        self.assertEqual(r.cmd('CAL_CLOSE',200),'RELEASE_SWITCH')
        self.assertEqual(r.state,'O')
        self.assertEqual(r.cmd('CAL_OPEN',220),'SAME_LEVEL')
        r.step(240,(0,0,-1000),1)
        r.step(320,(0,0,-1000),1)
        self.assertEqual(r.cmd('CAL_OPEN',340),'CALIBRATED')
        self.assertEqual(r.closed,0)

    def test_stationary_and_short_tilt(self):
        r=running()
        for t in range(220,3000,20):
            xyz=(1000,0,0) if 1000<=t<1500 else (0,0,-1000)
            r.step(t,xyz,1)
        self.assertEqual(r.counts,[0,0,0])

    def test_sustained_tilt_and_rearm(self):
        r=running()
        for t in range(220,2700,20): r.step(t,(1000,0,0),1)
        self.assertEqual(r.counts[1],1)
        for t in range(2700,3000,20): r.step(t,(0,0,-1000),1)
        for t in range(3000,5500,20): r.step(t,(1000,0,0),1)
        self.assertEqual(r.counts[1],2)

    def test_shock_hysteresis_and_cooldown(self):
        r=running()
        for t in range(220,1000,20): r.step(t,(0,0,-1800),1)
        self.assertEqual(r.counts[0],1)
        self.assertEqual(r.record(0)[3],1800)
        r.step(1020,(0,0,-1000),1)
        r.step(1040,(0,0,-1950),1)
        self.assertEqual(r.counts[0],2)
        self.assertEqual(r.peak,1950)

    def test_lid_debounce(self):
        r=running()
        for t,level in [(220,0),(240,1),(260,0),(280,1)]: r.step(t,(0,0,-1000),level)
        self.assertEqual(r.counts[2],0)
        r.step(300,(0,0,-1000),0)
        r.step(380,(0,0,-1000),0)
        self.assertEqual(r.counts[2],1)

    def test_capacity_and_counts(self):
        r=running(1023)
        self.assertEqual(r.limit,1250)
        for i in range(40): r.event('O',400+i,0)
        self.assertEqual(r.n,40)
        self.assertEqual(r.counts,[0,0,40])
        self.assertEqual(len(r.events),16)
        self.assertEqual(r.record(0)[0],25)

    def test_stop_and_restart(self):
        r=running()
        r.event('O',300,0)
        self.assertEqual(r.cmd('STOP',500),'STOPPED')
        r.step(600,(0,0,-2000),1)
        self.assertEqual(r.counts,[0,0,1])
        self.assertEqual(r.duration,300)
        self.assertEqual(r.cmd('START',700),'STARTED')
        self.assertEqual(r.trip,2)
        self.assertEqual(r.events,[])

if __name__=='__main__': unittest.main()
