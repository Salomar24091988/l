import sys, os
sys.path.insert(0, os.getcwd())
os.environ["HOME"] = os.getcwd() + "/home"; os.makedirs("home", exist_ok=True)
import grandma2 as g
g.Telnet.send = lambda self, c, key=None: None
import ma_wheel, ma_fxlink, ma_rig, ma_palette, ma_show, ma_bpm, ma_pos, ma_colx
for m in (ma_wheel, ma_fxlink, ma_rig, ma_palette, ma_show, ma_bpm, ma_pos, ma_colx): m.install()
ctl = g.MA2Control(None)
old = g.color_script(10, ctl.settings.get("fx_roles"))
print("off -> old script:", len(old))
ctl.settings.update(colx_on=True, colx_ev="1", colx_odd="2")
sc = [c for c, _ in g.color_script(10, ctl.settings.get("fx_roles"))]
print(len(sc)); print(sc[:6])
print([c for c in sc if "Label Executor 10.1" in c or "Label Executor 10.2" in c][:12])
print([c for c in sc if "Label Executor 10.3" in c][:4])
print([c for c in sc if "10.50" in c][:8], len(ma_colx.exec_pairs()))
print(ma_colx.key_colors(g.key_rgb), [round(ma_colx.hue_of(g.key_rgb(p))) for p in range(12)])
print("OK")
