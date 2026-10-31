import sys, os, json, colorsys
sys.path.insert(0, os.getcwd())
os.environ["HOME"] = os.getcwd() + "/home"
import ma_wheel, ma_fxlink, ma_rig
ma_wheel.install(); ma_fxlink.install(); ma_rig.install()
import grandma2 as g
json.dump({"enabled": False, "host": "10.0.0.12", "host_10_0_0_12": True,
           "wheel_slots": "белый 0, красный 8, оранжевый 15, жёлтый 22, зелёный 29, голубой 36, синий 43, пурпурный 50"}, open(g.SETTINGS_FILE, "w"))
s = g.load_settings(); print("slots:", s["wheel_slots"]); print("reload:", g.load_settings()["wheel_slots"], g.load_settings()["wheel_no_yellow"])
for i in range(12):
    r, gg, b = g.key_rgb(i); h = colorsys.rgb_to_hsv(r/100, gg/100, b/100)[0]*360
    assert not (45 <= h <= 75), (i, h)
    print(g.FIFTHS[i], ma_wheel.KEY_PALETTE[i][0], (r, gg, b), round(h), "→", ma_wheel.nearest_slot(g.key_rgb(i), ma_wheel.parse_slots(s["wheel_slots"])[0])[0] if hasattr(ma_wheel, "parse_slots") else "")
sc = [c for c, _ in g.color_script(10)] if True else []
print([c for c in sc if "COLORRGB" in c][:6])
print("OK")
