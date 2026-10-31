import sys, os, json, time
sys.path.insert(0, os.getcwd())
os.environ["HOME"] = os.getcwd() + "/home"; os.makedirs("home", exist_ok=True)
import ma_wheel, ma_fxlink, ma_rig, ma_palette, ma_show
ma_wheel.install(); ma_fxlink.install(); ma_rig.install(); ma_palette.install(); ma_show.install()
import grandma2 as g
link = {"version": 1, "written": "x", "looks": [
  {"key": "dim_chase", "name": "DIM Chase", "cat": "dimmer", "effects": [{"no": 101, "group": "Spot L"}, {"no": 121, "group": "Wash"}]},
  {"key": "dim_wave", "name": "DIM Wave", "cat": "dimmer", "effects": [{"no": 102, "group": "Spot L"}, {"no": 122, "group": "Wash"}]},
  {"key": "pt_circle", "name": "PT Circle", "cat": "position", "effects": [{"no": 103, "group": "Spot L", "dim": True}, {"no": 123, "group": "Wash"}]},
  {"key": "pt_fan", "name": "PT Fan", "cat": "position", "effects": [{"no": 104, "group": "Spot L", "dim": True}, {"no": 124, "group": "Wash", "dim": True}]},
  {"key": "rgb_rainbow", "name": "RGB Rainbow", "cat": "color", "effects": [{"no": 125, "group": "Wash"}]},
  {"key": "rgb_fire", "name": "RGB Fire", "cat": "color", "effects": [{"no": 126, "group": "Wash"}]},
  {"key": "strobe_dim", "name": "STROBE Dim", "cat": "strobe", "effects": [{"no": 105, "group": "Spot L"}, {"no": 127, "group": "Wash"}]},
  {"key": "cmb", "name": "CMB Lift", "cat": "combo", "effects": [{"no": 106, "group": "Spot L"}]}],
  "groups": [{"id": 1, "name": "Spot L", "caps": ["dim", "pt"]}, {"id": 3, "name": "Wash", "caps": ["dim", "rgb", "pt"]}],
  "layout": {"stage": {"w": 12, "d": 8}, "pt": {}, "fix": {
      "101": {"id": 101, "type": "Spot", "x": -1, "y": 2, "z": 6, "caps": ["dim", "pt"], "group": 1},
      "102": {"id": 102, "type": "Spot", "x": 1, "y": 2, "z": 6, "caps": ["dim", "pt"], "group": 1},
      "201": {"id": 201, "type": "Wash", "x": 0, "y": 4, "z": 6, "caps": ["dim", "pt", "rgb"], "group": 3}}}}
json.dump(link, open("home/.ma2_fxgen_link.json", "w"))
json.dump({"enabled": False, "host": "10.0.0.12", "autopilot": True, "pal_created": True}, open(g.SETTINGS_FILE, "w"))
ctl = g.MA2Control(None)
class Client:
    connected = True
    def send(self, c, key=None):
        t = time.time()
        for l in ["List Group", "1    Spot L", "3    Wash"]:
            ctl.log_lines.append((t, l))
ctl.client = Client()
type(ctl).enabled = property(lambda self: True)
sent = []
ctl.run_checked = lambda c: (sent.append(c), False)[1]
ctl.send = lambda c, key=None: sent.append(c)
done = []
ctl.fxgen_link(lambda e: done.append(e))
for _ in range(100):
    if done: break
    time.sleep(0.05)
q = []
ctl.rig_query(lambda f, m: q.append(m))
for _ in range(100):
    if q: break
    time.sleep(0.05)
for gr in ctl.settings["rig_groups"]:
    gr["id"] = {"Spot L": 1, "Wash": 3}.get(gr["name"], gr.get("id"))
    gr["type"] = {"Spot L": "spot", "Wash": "wash"}.get(gr["name"], gr.get("type"))
    gr["x"], gr["y"] = 0.5, 0.5
print("execs dim flags:", [(a["key"], [e.get("dim") for e in a["execs"]]) for a in ctl.settings["fxgen_assigned"]][:4])
print("gen_main", g.gen_main(ctl), "palette active", g.palette_active(ctl))
assert g.gen_main(ctl) and not g.palette_active(ctl)
ctl.color_cmd = "10.16"; sent.clear()
ctl.color_apply("тон"); ctl.fill_tick(); ctl.on_beat(1, "D", 0.5)
print("own gate sent:", sent)
assert any("10.30" in c for c in sent) and ctl.color_cmd is None
print("chase map:", g.fx_exec(10, "круг", 1))
class An: pass
ctl.a = An(); ctl.a.key_chroma = [0.0] * 12; ctl.a.track = None; ctl.a.db = None
ctl.bpm_sent = 120
ctl.auto_cmd = "fx:бег:0"; ctl.switch("fx:бег:0", None, True); time.sleep(0.2)
st = ctl._rig
print("sel:", st["sel"], "| layers dim", st["layers"]["dim"], "move", st["layers"]["move"], "color", st["layers"]["color"])
mv = st["sel"].get(("move", "spot"))
print("why:", ctl._rig_why)
assert st["layers"]["color"], "цвет генератора в работе"
keys_seen = set()
for i in range(12):
    ctl.a.key_chroma = [float((i * 7 + k) % 12 == 0) * 5 for k in range(12)]
    ctl.on_bar({"interval_ms": 300 if i in (5, 6) else 800, "hits": [], "bpm": 120, "energy": 0.5}, "A", "M")
    time.sleep(0.05)
    keys_seen |= set(st["sel"].values())
print("seen keys:", sorted(keys_seen))
print("why:", ctl._rig_why)
# движение со своим диммером - отдельный диммер у группы снят
st["sel"][("move", "spot")] = "pt_fan"; st["sel"][("move", "wash")] = "pt_fan"
ctl._rig["force"] = {"move|spot": "pt_fan", "move|wash": "pt_fan"}
sent.clear()
g.rig_all_off  # exists
ma_rig_refresh = None
ctl.switch("fx:поток:0", "fx:бег:0", True); time.sleep(0.2)
print("pt_fan → dim layer:", st["layers"]["dim"], "| why", ctl._rig_why)
assert not st["layers"]["dim"], "у обеих групп диммер внутри движения"
print("OK")
