import sys, os; sys.path.insert(0, os.getcwd())
import ma_palette as P, ma_wheel
print("hues", [round(P.hue_of(i)) for i in range(24)])
assert not any(50 <= P.hue_of(i) < 85 for i in range(24)), "жёлтого быть не должно"
print("red", P.rgb_of(0), P.rgb_of(0, 1), P.rgb_of(0, 2), P.color_name(0, 2), P.preset_no(101, 23, 2))
assert P.preset_no(101, 23, 2) == 172
KP = ma_wheel.KEY_PALETTE
for pos in range(12):
    b = P.base_index(pos, "major", KP); bm = P.base_index(pos, "minor", KP)
    print(pos, KP[pos][0], "→", P.color_name(b), "/ минор", P.color_name(bm))
for h in P.HARMONIES: print(h, [P.color_name(*c) for c in P.harmony_colors(0, h, 1)])
layout = {"stage": {"w": 12, "d": 8}, "fix": {}}
def add(i, typ, x, y, caps, group):
    layout["fix"][str(i)] = {"id": i, "type": typ, "x": x, "y": y, "z": 6, "caps": caps, "group": group}
for k, i in enumerate(range(101, 107)): add(i, "Alpha Spot", -5 + 2 * k, 2.4, ["dim", "pt", "wheel"], 1)
add(201, "Robin LEDBeam", 0, 4.3, ["dim", "pt", "rgb"], 2)
for k, i in enumerate(range(401, 411)): add(i, "PAR LED", -5.4 + 1.2 * k, 7.5, ["dim", "rgb"], 12)
add(1000, "Fog", 4, 8, [], None)
s = {"fxgen_layout": layout, "wheel_slots": ma_wheel.WHEEL_DEFAULTS["wheel_slots"], **P.DEFAULTS}
units, stage = P.units_of(s)
print("units", len(units), P.type_order(units))
cols = P.harmony_colors(P.base_index(0, "major", KP), "триада", 0)
tg = P.assign(units, cols, 0, False)
by_type = {}
for u in units: by_type.setdefault(u["type"], set()).add(tg[u["key"]])
print("по типам", {t: [P.color_name(*c) for c in v] for t, v in by_type.items()})
assert all(len(v) == 1 for v in by_type.values()) and len({next(iter(v)) for v in by_type.values()}) == 3
tg2 = P.assign(units, cols, 0, True); tg3 = P.assign(units, cols, 1, True)
par = [P.color_name(*tg2[f"f{i}"]) for i in range(401, 411)]; par3 = [P.color_name(*tg3[f"f{i}"]) for i in range(401, 411)]
print("PAR половины", par); print("PAR через один", par3)
assert len(set(par)) == 2 and par[0] != par[-1] and par3[0] != par3[1]
ev = P.plan_change(s, units, stage, tg, {}, "из центра", False, 0.5, ma_wheel.parse_slots, {1: ["11.1"]})
for t, c in ev: print(f"  {t:.3f}  {c}")
assert any("At Preset 4." in c and "Fade" in c for _, c in ev)
assert any(c.startswith("Executor 11.1 At 0") for _, c in ev) and any("Executor 11.1 At 100" in c for _, c in ev)
ev2 = P.plan_change(s, units, stage, tg, tg, "из центра", False, 0.5, ma_wheel.parse_slots, {})
assert ev2 == [], "без изменений - без команд"
sc, made = P.create_script(s, units, ma_wheel.parse_slots)
pre = [c for c, _ in sc if c.startswith("Store Preset")]
print("create:", len(sc), "команд,", len(pre), "пресетов", pre[:2], pre[-2:], made[:2])
print([c for c, _ in sc[:8]])
assert len(pre) == 72 + len([m for m in made if m["preset"].startswith("4.18")])
print(P.sel_cmd([401, 402, 403, 405, 101, 102]))
print("OK")
