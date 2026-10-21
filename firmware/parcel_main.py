import gc,micropython
micropython.opt_level(3)
gc.collect()
from parcel_core import Recorder
gc.collect()
from parcel_actions import command
gc.collect()
import parcel_hardware
gc.collect()
r=Recorder()
parcel_hardware.run(r)
