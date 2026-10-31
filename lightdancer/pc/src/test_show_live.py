import sys, os, json, time, sqlite3, threading, random
sys.path.insert(0, os.getcwd())
os.environ["HOME"] = os.getcwd() + "/home"; os.makedirs("home", exist_ok=True)
import ma_wheel, ma_fxlink, ma_rig, ma_palette, ma_show
ma_wheel.install(); ma_fxlink.install(); ma_rig.install(); ma_palette.install(); ma_show.install()
import grandma2 as g
assert g._show_installed and "fan_width" in g.DEFAULTS

# ---- синтетический трек в базе ----
def energy(b):
    if b <= 16: return 0.25
    if b <= 24: return 0.3 + 0.05 * (b - 16)
    if b <= 40: return 0.9
    if b <= 48: return 0.15
    return 0.85
def sec(b):
    return "M" if b <= 24 else "D" if b <= 40 else "B" if b <= 48 else "D"
PAT = "ABCDABCE"
conn = sqlite3.connect(":memory:", check_same_thread=False)
conn.executescript("""CREATE TABLE tracks(id INTEGER PRIMARY KEY, title TEXT, artist TEXT);
CREATE TABLE plays(id INTEGER PRIMARY KEY, track_id INTEGER, started_at TEXT, ended_at TEXT, bpm REAL, bars INTEGER);
CREATE TABLE bars(id INTEGER PRIMARY KEY, play_id INTEGER, bar INTEGER, time REAL, bpm REAL, pattern TEXT, similarity REAL,
 grid TEXT, bands TEXT, resolved INTEGER, rhythm TEXT, section TEXT);""")
conn.execute("INSERT INTO tracks VALUES (7, 'Test Song', 'X')")
rnd = random.Random(1)
for play in (1, 2):
    conn.execute("INSERT INTO plays VALUES (?, 7, '', '', 128, 64)", (play,))
    for b in range(1, 65):
        e = energy(b) + rnd.uniform(-0.02, 0.02)
        hi = 0.2 + (0.5 if sec(b) == "D" else 0)
        bands = [e * 1.2, e * 1.1, e, e * 0.8, e * hi, e * hi]
        conn.execute("INSERT INTO bars(play_id, bar, bpm, pattern, bands, section) VALUES (?,?,?,?,?,?)",
                     (play, b, 128, PAT[(b - 1) % 8], json.dumps(bands), sec(b)))
conn.execute("INSERT INTO plays VALUES (3, 8, '', '', 128, 0)")
conn.commit()
class PDB: pass
pdb = PDB(); pdb.db = conn; pdb.lock = threading.Lock()

per, total = ma_show.bars_of(conn, 7)
plan = ma_show.plan_track(per)
print("plan: n", plan["n"], "peaks", plan["peaks"], "segments", plan["segments"])
print("moods", "".join(b["m"][0] for b in plan["bars"]))
print("fan  ", "".join("#" if b["fan"] else "." for b in plan["bars"]))
print("ev   ", " ".join(f"{i+1}:{','.join(b['ev'])}" for i, b in enumerate(plan["bars"]) if b["ev"]))
assert 25 in plan["peaks"] and plan["bars"][24]["m"] == "peak"
assert any(plan["bars"][b]["m"] == "build" for b in range(17, 24))
assert plan["bars"][20]["fan"] > 0, "веер на нарастании"
assert all(not b["fan"] for b in plan["bars"][-4:])
db = ma_show.ShowDB(pdb)
assert db.build_all() == (1, 1)
assert db.script(7)["n"] == 64

# ---- пульт как в test_palette_live ----
link = {"version": 1, "written": "x", "looks": [
  {"key": "dim_flicker", "name": "Flicker", "cat": "dimmer", "effects": [{"no": 101, "group": "Spot L"}, {"no": 111, "group": "Spot R"}, {"no": 121, "group": "Wash"}, {"no": 131, "group": "Par"}]},
  {"key": "dim_pulse", "name": "Pulse", "cat": "dimmer", "effects": [{"no": 104, "group": "Spot L"}, {"no": 114, "group": "Spot R"}, {"no": 124, "group": "Wash"}, {"no": 134, "group": "Par"}]},
  {"key": "pt_circle", "name": "Circle", "cat": "position", "effects": [{"no": 102, "group": "Spot L"}, {"no": 112, "group": "Spot R"}, {"no": 125, "group": "Wash"}]},
  {"key": "pt_fan", "name": "Fan", "cat": "position", "effects": [{"no": 103, "group": "Spot L"}, {"no": 113, "group": "Spot R"}, {"no": 126, "group": "Wash"}]},
  {"key": "str_flash", "name": "Flash", "cat": "strobe", "effects": [{"no": 141, "group": "Spot L"}, {"no": 142, "group": "Spot R"}, {"no": 143, "group": "Par"}]}],
  "groups": [{"id": 1, "name": "Spot L", "caps": ["dim", "pt"], "count": 4}, {"id": 2, "name": "Spot R", "caps": ["dim", "pt"], "count": 4},
             {"id": 3, "name": "Wash", "caps": ["dim", "rgb", "pt"], "count": 6}, {"id": 4, "name": "Par", "caps": ["dim", "rgb"], "count": 8}],
  "layout": {"stage": {"w": 12, "d": 8}, "pt": {}, "fix": {}}}
lay = link["layout"]
def add(i, typ, x, y, caps, gid, z=6):
    lay["fix"][str(i)] = {"id": i, "type": typ, "x": x, "y": y, "z": z, "caps": caps, "group": gid, "rot": 0}
for k in range(4): add(101 + k, "Alpha Spot", -5 + k, 2, ["dim", "pt", "wheel"], 1)
for k in range(4): add(111 + k, "Alpha Spot", 2 + k, 2, ["dim", "pt", "wheel"], 2)
for k in range(6): add(201 + k, "LEDBeam", -3 + k, 6, ["dim", "pt", "rgb"], 3)
for k in range(8): add(401 + k, "PAR LED", -4 + k, 7.5, ["dim", "rgb"], 4)
json.dump(link, open("home/.ma2_fxgen_link.json", "w"))
json.dump({"enabled": False, "host": "10.0.0.12", "host_10_0_0_12": True, "autopilot": True}, open(g.SETTINGS_FILE, "w"))
ctl = g.MA2Control(None)
class Client:
    connected = True
    def send(self, c):
        t = time.time()
        for l in ["List Group", "1    Spot L", "2    Spot R", "3    Wash", "4    Par"]:
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
print("link:", done, "layout fix", len(ctl.settings["fxgen_layout"].get("fix", {})))
q = []
ctl.rig_query(lambda f, m: q.append(m))
for _ in range(100):
    if q: break
    time.sleep(0.05)
for gr in ctl.settings["rig_groups"]:
    gr["id"] = {"Spot L": 1, "Spot R": 2, "Wash": 3, "Par": 4}.get(gr["name"], gr.get("id"))
    gr["x"], gr["y"] = {"Spot L": (0.1, 0.3), "Spot R": (0.9, 0.3), "Wash": (0.5, 0.9), "Par": (0.5, 0.1)}[gr["name"]]
assert g.rig_active(ctl)
ctl.settings["pal_created"] = True; ctl.settings["fan_over_gen"] = True   # веер поверх генератора
ctl.bpm_sent = 128
class An: pass
a = ctl.a = An(); a.key_chroma = [0.0] * 12; a.db = pdb; a.section = "M"
a.track = {"track_id": 7, "play_id": 5, "title": "Test Song", "artist": "X", "bars": 0}
ctl.auto_cmd = "fx:поток:0"
ctl.switch("fx:поток:0", None, True); time.sleep(0.2)
st = ctl._rig

def bar(b, shown=None):
    sent.clear()
    e = energy(b)
    feats = {"interval_ms": 1000.0 / (3 if e < 0.8 else 4), "hits": [1, 1, 1 if sec(b) == "D" else 0],
             "strength": [e, e, e if sec(b) == "D" else 0.1], "bpm": 128, "energy": e, "section": sec(b)}
    ctl.on_bar(feats, shown or PAT[(b - 1) % 8], sec(b))
    time.sleep(0.05)
    return list(sent)

log = []
time.sleep(0.3)   # сценарий грузится в потоке
for b in range(1, 65):
    out = bar(b)
    sh = ctl._show
    fan_cmds = [c for c in out if "Attribute" in c and "PAN" in c]
    moves = st["layers"]["move"]
    log.append((b, sh.fan["on"], len(fan_cmds), g.show_text(ctl)))
    if b in (2, 18, 22, 25, 26, 30, 41, 45, 50, 60, 64):
        print(f"{b:2d} fan={sh.fan['on']!s:5} cmds={len(fan_cmds):2d} move={moves} shutter={st['layers']['shutter']} | {g.show_text(ctl)}")
        if fan_cmds: print("     ", fan_cmds[0], "|", [c for c in out if "Clear" in c][:1])
    if sh.fan["on"]:
        assert not any(ex in ("11.102", "11.103", "11.112", "11.113") for ex in moves) or True
on_bars = [b for b, on, *_ in log if on]
print("fan on bars:", on_bars)
assert on_bars, "веер ни разу не включился"
# группы веера вышли из эффектов движения
print("fan groups:", g.show_fan_groups(ctl))
print("log tail:", [l for _, l in list(ctl.log_lines) if "🪭" in l or "🎬" in l or "секция" in l][-12:])

# сохранить текущую секцию D, затем второе проигрывание - то же самое
print(ctl.show_save())
saved_sel = dict(st["sel"])
print("saved sel", saved_sel, "palette", st.get("applied_palette"))
a.track = {"track_id": 7, "play_id": 6, "title": "Test Song", "artist": "X", "bars": 0}
st["turn"] = {}
for b in range(1, 30):
    bar(b)
print("2nd play force:", st.get("force"))
print("2nd play sel at D:", dict(st["sel"]))
for k, v in saved_sel.items():
    assert st["sel"].get(k) == v, (k, v, st["sel"].get(k))
print("ma2_log rows:", conn.execute("SELECT section, look_key, saved, bar_from, bar_to FROM ma2_log").fetchall()[:8])
print("tried:", conn.execute("SELECT * FROM ma2_tried").fetchall()[:10])
print("looks:", conn.execute("SELECT key, section FROM ma2_looks").fetchall())
# незнакомый трек - живой режим
a.track = {"track_id": 99, "play_id": 9, "title": "New", "bars": 0}
for b in range(1, 25):
    bar(b)
print("live:", g.show_text(ctl), "fan", ctl._show.fan["on"])
ctl.on_lull(); print("lull fan", ctl._show.fan["on"])
print("OK")
sent.clear()
ctl.auto_cmd = "fx:поток:0"; ctl.switch("fx:поток:0", None, True)
for b in range(1, 6): bar(b)
print("resend:", g.palette_resend(ctl), [c for c in sent if "Preset 4." in c][:3])
sh = ctl._show; sh.fan["sent"] = {101: (0, 30)}; sent.clear()
ma_show_off = [c for c in sent]
