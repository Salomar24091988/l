import sys, os, json, time, collections
sys.path.insert(0, os.getcwd())
os.environ["HOME"] = os.getcwd() + "/home"; os.makedirs("home", exist_ok=True)
import ma_wheel, ma_fxlink, ma_rig, ma_palette
ma_wheel.install(); ma_fxlink.install(); ma_rig.install(); ma_palette.install()
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

lay = {"stage": {"w": 12, "d": 8}, "fix": {}}
def add(i, typ, x, y, caps, gid):
    lay["fix"][str(i)] = {"id": i, "type": typ, "x": x, "y": y, "z": 6, "caps": caps, "group": gid}
for k in range(4): add(101 + k, "Alpha Spot", -5 + k, 2, ["dim", "pt", "wheel"], 1)
for k in range(4): add(111 + k, "Alpha Spot", 2 + k, 2, ["dim", "pt", "wheel"], 2)
for k in range(6): add(201 + k, "LEDBeam", -3 + k, 6, ["dim", "pt", "rgb"], 3)
for k in range(8): add(401 + k, "PAR LED", -4 + k, 7.5, ["dim", "rgb"], 4)
ctl.settings["fxgen_layout"] = lay
for gr in ctl.settings["rig_groups"]:
    gr["id"] = {"Spot L": 1, "Spot R": 2, "Wash": 3, "Par": 4}.get(gr["name"], gr.get("id"))
ctl.settings["pal_created"] = True; ctl.settings["pal_over_gen"] = True   # палитра поверх генератора
print("palette active", g.palette_active(ctl), "color preset start (migr)", ctl.settings.get("color_preset_start"))
sent.clear()
ctl.auto_cmd = "fx:бег:0"
ctl.switch("fx:бег:0", None, True); time.sleep(0.3)
st = ctl._rig
print("layers color:", st["layers"]["color"], "dim_by_group", st.get("dim_by_group"))
assert not st["layers"]["color"], "цвет ведёт палитра - эффекты цвета генератора не включаются"
def bar(rate, notes, key=None):
    sent.clear()
    chroma_add(notes)
    if key: ctl.on_key(*key)
    ctl.on_bar({"interval_ms": 1000.0 / rate, "hits": [], "bpm": 120})
    time.sleep(0.8)
    return [c for c in sent if "Preset 4." in c or "COLOR1" in c or "Executor" in c and " At " in c]
seq = [(3, [0,4,7], (0, "major")), (3, [0,4,7], None), (3, [0,4,7], (9, "minor")), (3, [2,6,9], None), (3, [2,6,9], None),
       (6, [2,6,9], None), (6.5, [2,6,9], None), (6.5, [2,6,9], None), (3, [5,9,0], None), (1.5, [5,9,0], None)]
for i, (r, notes, key) in enumerate(seq):
    out = bar(r, notes, key)
    print(i, r, key, "|", g.palette_text(ctl))
    for c in out: print("     ", c)
print([l for _, l in list(ctl.log_lines) if "🎨" in l][-6:])
ctl.on_lull(); print("lull ok", ctl._palette.current == {})
print("OK")
