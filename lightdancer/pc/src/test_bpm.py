import sys, os, time
sys.path.insert(0, os.getcwd())
os.environ["HOME"] = os.getcwd() + "/home"; os.makedirs("home", exist_ok=True)
import grandma2 as g
sent = []
g.Telnet.send = lambda self, c, key=None: sent.append(c)
import ma_wheel, ma_fxlink, ma_rig, ma_palette, ma_show, ma_bpm
for m in (ma_wheel, ma_fxlink, ma_rig, ma_palette, ma_show, ma_bpm): m.install()
ctl = g.MA2Control(None)
type(ctl).enabled = property(lambda self: True)
ctl.client = g.Telnet(lambda *a, **k: None); ctl.client.connected = True
s = ctl.settings
s.update(bpm_on=True, bpm_div=2, bpm_integer=True, bpm_mode="beat")
ctl.on_bpm(128); ctl.on_bpm(128)
print("beat:", sent); assert "SpecialMaster 3.1 At 64" in sent and "SpecialMaster 3.2 At 32" in sent and "SpecialMaster 3.3 At 16" in sent and "SpecialMaster 3.4 At 128" in sent
sent.clear(); s["bpm_mode"] = "section"; ctl.on_section("D"); time.sleep(1.1); ma_bpm.push(ctl)
print("drop:", sent); assert "SpecialMaster 3.4 At 256" in sent
sent.clear(); s["bpm_mode"] = "stop"; ctl.on_section("B"); ma_bpm.push(ctl, force=True)
print("stop:", sent); assert "SpecialMaster 3.1 At 0" in sent
sent.clear(); s["bpm_mode"] = "manual"; s["bpm_manual"] = 100; ma_bpm.push(ctl, force=True)
print("manual:", sent, ma_bpm.state(ctl).why); assert "SpecialMaster 3.1 At 100" in sent
sent.clear(); ctl.on_bpm(140); ctl.on_bpm(140); print("manual ignores track:", sent)
for i in range(4): ctl.bpm_tap(); time.sleep(0.5)
print("tap ->", s["bpm_manual"])
sent.clear(); s["bpm_multi"] = False; ctl.bpm_candidate = None; ctl.bpm_sent = None; ctl.on_bpm(128); ctl.on_bpm(128); print("legacy:", sent)
# fxlink: master by category
master = lambda cat: g.bpm_master_of(s, cat)
d = {"looks": [{"key": "a", "cat": "position", "effects": [{"no": 5, "group": "1"}]},
               {"key": "b", "cat": "combo", "effects": [{"no": 6, "group": "1"}]},
               {"key": "c", "cat": "strobe", "effects": [{"no": 7, "group": "1"}]}]}
print([c for c, _ in ma_fxlink.assign_script(d, 11, master)[0] if "SpecialMaster" in c])
print("OK")
