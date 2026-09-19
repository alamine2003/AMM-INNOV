import time
from lab import *
probe = Probe(users=10, think=0.3).start()
time.sleep(20)
probe.stop()
print(json.dumps(probe.window(0, 1e9), indent=1))
for kind in ("list","detail","analytics","alerts","write","me"):
    print(kind, probe.window(0, 1e9, kind))
