import sys, json, random
sys.path.insert(0, "/tmp/claude-0/x/inst")
import ma2_fxgen as fx
random.seed(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
lib = fx.library()
keys = fx.ordered_keys(lib)
CAPS = ["dim", "pt", "rgb", "shutter"]
cases = []
for n in range(300):
    cfg = fx.load_config(None, require_groups=False)
    groups = []
    for gi in range(random.randint(1, 5)):
        caps = sorted(random.sample(CAPS, random.randint(1, 4)), key=CAPS.index)
        g = {"id": random.randint(1, 40), "name": random.choice(["Spot", "All Mac Viper Profile Extended", "Wash ⚡ Front", "Par", "Длинное имя группы приборов"]),
             "caps": caps, "size": random.choice([20, 25, 12.5, 33.33]), "shut_lo": 0, "shut_hi": random.choice([100, 80]),
             "count": 6, "templates": random.choice([None, random.sample(keys, random.randint(1, 10))])}
        groups.append(g)
    cfg["groups"] = groups
    cfg["move_dim"] = random.random() < 0.7
    cfg["move_dim_lo"] = random.choice([40, 25, 12.5])
    cfg["effect_start"] = random.choice([101, 1001])
    cfg["effect_stride"] = random.choice([100, 5])
    if random.random() < 0.3:
        cfg["custom"] = [{"key": "my", "name": "My Combo", "cat": "combo", "bpm": 60,
                          "layers": [{"tpl": "pt_circle_spread", "speed": 0.5}, {"tpl": "rgb_rainbow", "phase": "0 Thru 720"},
                                     {"tpl": "dim_wave", "attrs": ["dim"], "lo": 30, "invert": True},
                                     {"line": ["shutter", "pwm", 0, 100, "0", 20], "bpm": 240, "wings": 3, "scale": 75}]}]
        if groups[0]["templates"] is not None:
            groups[0]["templates"].append("my")
    only = random.choice([None, set(random.sample(keys, random.randint(1, 30)))])
    macros = random.random() < 0.5
    cmds, rep, warns = fx.build(json.loads(json.dumps(cfg)), only, None, macros)
    cases.append({"cfg": cfg, "only": sorted(only) if only else None, "macros": macros,
                  "cmds": cmds, "report": [[a, b, c] for a, b, c in rep], "warns": warns})
json.dump(cases, open("t/cases.json", "w", encoding="utf-8"), ensure_ascii=False)
print(len(cases), sum(len(c["cmds"]) for c in cases), "commands")
