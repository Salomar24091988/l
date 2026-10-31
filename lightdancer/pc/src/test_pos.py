import sys, os, time
sys.path.insert(0, os.getcwd())
os.environ["HOME"] = os.getcwd() + "/home"; os.makedirs("home", exist_ok=True)
import grandma2 as g
sent = []
g.Telnet.send = lambda self, c, key=None: sent.append(c)
import ma_wheel, ma_fxlink, ma_rig, ma_palette, ma_show, ma_bpm, ma_pos
for m in (ma_wheel, ma_fxlink, ma_rig, ma_palette, ma_show, ma_bpm, ma_pos): m.install()
ctl = g.MA2Control(None)
print("parse", hasattr(g, "parse_selection"), hasattr(g, "FX_ROLE_DEFAULTS"))
sc = g.position_script(10, ctl.settings.get("fx_roles"))
print("fallback:", len(sc), sc[1:4], sc[-3:])
ctl.settings["pos_group"] = "3 + 5"
sc = g.position_script(10, ctl.settings.get("fx_roles"))
for c, _ in sc[:12]: print(" ", c)
print(" ...", [c for c, _ in sc if "Cue 2" in c or "At Preset" in c][:6])
ctl.settings["pos_presets"] = False
print([c for c, _ in g.position_script(10)][:8])
print("FX_POSITIONS", len(g.FX_POSITIONS))
print("OK")
