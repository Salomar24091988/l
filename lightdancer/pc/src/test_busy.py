import sys, os, time
sys.path.insert(0, os.getcwd())
os.environ["HOME"] = os.getcwd() + "/home"; os.makedirs("home", exist_ok=True)
import grandma2 as g
sent = []
g.Telnet.send = lambda self, c, key=None: sent.append(c)
import ma_wheel, ma_fxlink, ma_rig, ma_palette, ma_show
ma_wheel.install(); ma_fxlink.install(); ma_rig.install(); ma_palette.install(); ma_show.install()
ctl = g.MA2Control(None)
type(ctl).enabled = property(lambda self: True)
ctl.client = g.Telnet(lambda *a, **k: None); ctl.client.connected = True
ctl._rig_active = ["11.1", "12.2"]
busy = os.path.join(os.environ["HOME"], ".ma2_fxgen_busy")
ctl.send("A"); print("free:", sent)
open(busy, "w").write("1"); time.sleep(0.35)
ctl.send("B"); ctl.client.send("Executor 1.1 At 61", "fader"); print("busy:", sent)
os.remove(busy); time.sleep(0.35)
ctl.send("D"); time.sleep(0.3); print("after:", sent)
open(busy, "w").write("1"); os.utime(busy, (time.time() - 20, time.time() - 20)); time.sleep(0.35)
ctl.send("E"); print("stale:", sent[-1])
print([l for _, l in list(ctl.log_lines)[-3:]])
os.remove(busy)
