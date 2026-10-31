import sys, json, os
sys.path.insert(0, os.path.dirname(__file__))
import ma_wheel
ma_wheel.install()
import grandma2 as g
assert g._wheel_installed
# старые настройки пользователя
json.dump({"host": "192.168.2.105", "user": "remote", "password": "1234",
           "fx_roles": {"bass": "Fixture1 Trhu 6", "mid": "Fixture 7 Thru 17", "back": "Fixture 21 Thru 999"}},
          open(g.SETTINGS_FILE, "w"))
s = g.load_settings()
assert s["host"] == "10.0.0.12" and s["user"] == "remote" and s["password"] == "1234", s
assert json.load(open(g.SETTINGS_FILE))["host"] == "10.0.0.12"
# второй раз другой IP не трогаем
s["host"] = "10.0.0.50"; g.save_settings(s); assert g.load_settings()["host"] == "10.0.0.50"

roles = s["fx_roles"]
class Ctl: pass
ctl = Ctl(); ctl.settings = dict(s); g._wheel_ctl = ctl

def show(sc, n=40):
    for c, _ in sc[:n]: print("   ", c)

print("== 1. колесо у всех (приборы с колесом пусто)")
sc = g.color_script(10, roles); show(sc, 14); print("  команд", len(sc))
assert 'Attribute "COLOR1" At 8' in [c for c, _ in sc]

print("== 2. споты 7-12 внутри середины, RGB у 1-6 и 13-17")
ctl.settings["wheel_fixtures"] = "7 thru 12"
sc = g.color_script(10, roles); show(sc, 16)
cmds = [c for c, _ in sc]
assert "Fixture 13 Thru 17" in cmds and "Fixture 7 Thru 12" in cmds
i = cmds.index("Store Executor 10.31 /o"); print("  пара C:"); [print("   ", c) for c in cmds[i-12:i+1]]

print("== 3. пресеты и мусор")
ctl.settings["wheel_slots"] = "белый Preset 4.1, красный P2; синий=Preset 4.3, зелёный 4, что-то 7"
print(g.parse_slots(ctl.settings["wheel_slots"]))
print(g.wheel_summary(ctl.settings))
sc = g.color_script(10, roles); show(sc, 10)

print("== 4. колесо выключено = как раньше")
ctl.settings["wheel_on"] = False
old = [c for c, _ in g.color_script(10, roles)]
assert not any("COLOR1" in c or "Preset" in c for c in old), old[:20]
print("  команд", len(old))
print("== 5. споты отдельно (21 Thru 30), не в ролях")
ctl.settings.update(wheel_on=True, wheel_fixtures="Fixture 21 Thru 30", wheel_slots=ma_wheel.WHEEL_DEFAULTS["wheel_slots"])
cmds = [c for c, _ in g.color_script(10, roles)]
i = cmds.index("Store Executor 10.16 /o"); [print("   ", c) for c in cmds[1:i+1]]
i = cmds.index("Store Executor 10.31 /o"); print("  пара:"); [print("   ", c) for c in cmds[i-13:i+1]]
print("== 6. полный fx_script собирается", len(g.fx_script(10, 128, 1, roles)))
print(g.wheel_summary(ctl.settings))
print("OK")
