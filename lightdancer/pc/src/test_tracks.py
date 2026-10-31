import sys, os, json, time, collections
sys.path.insert(0, os.getcwd())
os.environ["HOME"] = os.getcwd() + "/home"; os.makedirs("home", exist_ok=True)
import ma_wheel, ma_fxlink, ma_rig
ma_wheel.install(); ma_fxlink.install(); ma_rig.install()
import grandma2 as g
assert g._rig_installed
# parse
lines = ["12:00:01 › List Group", "Executing : List Group", "No.  Name            Info",
         "1    Spots All", "2    Wash Front L     ", "3    \"Par Back\"", "Group 4 Name=Beam Center", "OK", "[Channel]>"]
print("parse:", ma_rig.parse_groups(lines))
link = {"version": 1, "written": "x", "looks": [
  {"key": "dim_flicker", "name": "Flicker", "cat": "dimmer", "effects": [{"no": 101, "group": "Spot L"}, {"no": 111, "group": "Spot R"}, {"no": 121, "group": "Wash"}, {"no": 131, "group": "Par"}]},
  {"key": "pt_circle", "name": "Circle", "cat": "position", "effects": [{"no": 102, "group": "Spot L"}, {"no": 112, "group": "Spot R"}]},
  {"key": "pt_fan", "name": "Fan", "cat": "position", "effects": [{"no": 103, "group": "Spot L"}, {"no": 113, "group": "Spot R"}]},
  {"key": "rgb_rb", "name": "Red Blue", "cat": "color", "effects": [{"no": 122, "group": "Wash"}, {"no": 132, "group": "Par"}]},
  {"key": "str_flash", "name": "Flash", "cat": "strobe", "effects": [{"no": 141, "group": "Spot L"}, {"no": 142, "group": "Spot R"}, {"no": 143, "group": "Par"}]},
  {"key": "rgb_rainbow", "name": "Rainbow", "cat": "color", "effects": [{"no": 123, "group": "Wash"}, {"no": 133, "group": "Par"}]}],
  "groups": [{"id": 1, "name": "Spot L", "caps": ["dim", "pt"], "count": 4}, {"id": 2, "name": "Spot R", "caps": ["dim", "pt"], "count": 4},
             {"id": 3, "name": "Wash", "caps": ["dim", "rgb", "pt"], "count": 6}, {"id": 4, "name": "Par", "caps": ["dim", "rgb"], "count": 8}]}
json.dump(link, open("home/.ma2_fxgen_link.json", "w"))
json.dump({"enabled": False, "host": "10.0.0.12", "host_10_0_0_12": True, "autopilot": True}, open(g.SETTINGS_FILE, "w"))
ctl = g.MA2Control(None)
class Client:
    connected = True
    def send(self, c):
        t = time.time()
        for l in ["List Group", "1    Spot L", "2    Spot R", "3    Wash", "4    Par", "7    Strobe Back"]:
            ctl.log_lines.append((t, l))
ctl.client = Client()
type(ctl).enabled = property(lambda self: True)
sent = []
ctl.run_checked = lambda c: (sent.append(c), False)[1]
ctl.send = lambda c, key=None: sent.append("SEND " + c)
done = []
ctl.fxgen_link(lambda e: done.append(e))
for _ in range(100):
    if done: break
    time.sleep(0.05)
print("link errors:", done)
for a in ctl.settings["fxgen_assigned"]: print(" ", a["name"], a["exec"], a["execs"])
print("active before types:", g.rig_active(ctl))
q = []
ctl.rig_query(lambda f, m: q.append(m))
for _ in range(100):
    if q: break
    time.sleep(0.05)
print("query:", q)
for gr in ctl.settings["rig_groups"]: print("  ", gr)
assert g.rig_active(ctl)
# место: Spot L слева, Spot R справа
for gr in ctl.settings["rig_groups"]:
    if gr["name"] == "Spot L": gr["x"], gr["y"] = 0.1, 0.3
    if gr["name"] == "Spot R": gr["x"], gr["y"] = 0.9, 0.3
    if gr["name"] == "Wash": gr["x"], gr["y"] = 0.5, 0.9
    if gr["name"] == "Par": gr["x"], gr["y"] = 0.5, 0.1
print("fx_exec:", [g.fx_exec(10, r, 0) for r in ("пульс", "бег", "поток", "искры", "круг")])
import math
ctl.bpm_sent = 128
class An: pass
ctl.a = An(); ctl.a.key_chroma = [0.0]*12
def chroma_add(notes, amt=1.0):
    c = list(ctl.a.key_chroma)
    for n in notes: c[n] += amt
    ctl.a.key_chroma = c
sent.clear()
ctl.auto_cmd = "fx:бег:0"
ctl.switch("fx:бег:0", None, True); time.sleep(0.45)
st = ctl._rig
print("start:", ctl._rig_why); print("   ", sent)
assert st["layers"]["dim"] and st["layers"]["move"] and st["layers"]["color"] and not st["layers"]["shutter"]
def bar(rate, notes, key=False):
    sent.clear()
    chroma_add(notes)
    if key: ctl.on_key(2, "major")
    f = {"interval_ms": 1000.0 / rate, "hits": [], "bpm": 128}
    try:
        ctl.on_bar(f)
    except Exception as e:
        import traceback; traceback.print_exc()
    time.sleep(0.45)
    return list(sent)
log = []
seq = [(3, [0,4,7]), (3, [0,4,7]), (3, [0,4,7]), (3, [0,4,7]), (3, [2,6,9]), (3, [2,6,9]), (6, [2,6,9]), (6.5, [2,6,9]), (6.5, [2,6,9]), (3, [2,6,9]), (3, [2,6,9]), (1.5, [5,9,0])]
for i, (r, notes) in enumerate(seq):
    out = bar(r, notes, key=(i == 3))
    print(i, r, "|", ctl._rig_why, "|", out)
print([l for _, l in list(ctl.log_lines) if "🎚" in l][-8:])
# луч
ctl.settings["rig_groups"][0]["id"] = 1
sc, asg = ma_rig.beam_script(ctl.settings, 16, 1, 128)
print(len(sc), asg[:3]); print([c for c, _ in sc[:16]])
ctl.settings["rig_beam_assigned"] = asg
for r in (3, 3, 7, 7, 3, 1.0, 1.0):
    out = bar(r, [0, 4])
    print("beam", r, st["beam"], st.get("beam_name"), [c for c in out if "16." in c])
print(ma_rig.parse_recipe("zoom=40, prism~sin 10-60 x0.5, bogus=1, iris~Sin 20-100"))
ctl.on_lull(); print("lull:", ctl._rig_active, ctl.auto_why)
print("OK")
