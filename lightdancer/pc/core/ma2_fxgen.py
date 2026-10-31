#!/usr/bin/env python3
"""
ma2_fxgen.py — универсальный генератор эффектов для grandMA2 через Telnet.

Что делает:
  * для каждой группы из конфига строит эффекты из библиотеки шаблонов
    (Dimmer / Position / Color RGB / Strobe / Combo) с учётом возможностей группы;
  * шаблоны можно КОМПОНОВАТЬ: эффект = набор слоёв, каждый слой — готовый
    шаблон (целиком или отдельные атрибуты) или своя строка, с переопределениями
    BPM / множителя скорости / фазы / ширины / амплитуды / wings / groups / blocks;
  * сохраняет эффекты в пул Effects (Delete + Store Effect 1.N /o, приборы во все строки, Label);
  * привязывает каждый эффект к Speed-группе своей категории и создаёт макросы
    скорости (пресеты BPM + Learn) для SpecialMaster 3.x.

Подготовка пульта:
  Setup -> Console -> Global Settings -> Telnet = "Login Enabled"  (TCP 30000)
  Проверь номера форм в пуле Forms и при необходимости поправь "forms" в конфиге.

Примеры:
  python ma2_fxgen.py --list                          # библиотека шаблонов
  python ma2_fxgen.py -c fxgen_config.json --list     # + свои шаблоны из конфига
  python ma2_fxgen.py -c fxgen_config.json --print    # только показать команды
  python ma2_fxgen.py -c fxgen_config.json 192.168.0.10
  python ma2_fxgen.py -c fxgen_config.json 192.168.0.10 --only dim_chase,combo_circle_rainbow
  python ma2_fxgen.py -c fxgen_config.json 192.168.0.10 --groups 1,2 --no-macros
  python ma2_fxgen.py -c fxgen_config.json 192.168.0.10 --pull-groups   # группы из шоу -> конфиг

Свой шаблон в конфиге ("custom": [...]):
  {"key": "my_combo", "name": "My Combo", "cat": "combo", "bpm": 60,
   "layers": [
     {"tpl": "pt_circle_spread", "speed": 0.5},                  # шаблон целиком, вдвое медленнее
     {"tpl": "rgb_rainbow", "phase": "0 Thru 720"},              # с другой фазой
     {"tpl": "dim_wave", "attrs": ["dim"], "lo": 30, "invert": true},
     {"line": ["shutter", "pwm", 0, 100, "0", 20], "bpm": 240}   # своя строка
   ]}
  Поля слоя: tpl | line, attrs, bpm, speed, phase, width, lo, hi, scale (%), invert,
             wings, groups, blocks. Если два слоя трогают один атрибут — побеждает верхний
             (последний в списке), генератор предупредит.
"""
import argparse
import copy
import json
import re
import socket
import sys
import time

# =====================================================================
#  ДЕФОЛТЫ (перекрываются конфигом)
# =====================================================================
DEFAULTS = {
    # Номера форм в пуле Forms (стандартный пул MA2 — ПРОВЕРЬ на своём шоу)
    "forms": {
        "chase": 1, "sin": 2, "cos": 3, "ramp_plus": 4, "ramp_minus": 5,
        "ramp": 6, "phase1": 7, "phase2": 8, "phase3": 9,
        "bump": 10, "swing": 11, "random": 12, "pwm": 13,
    },
    # Имена атрибутов MA2
    "attrs": {
        "dim": "DIM", "pan": "PAN", "tilt": "TILT",
        "r": "COLORRGB1", "g": "COLORRGB2", "b": "COLORRGB3",
        "shutter": "SHUTTER",
    },
    # Speed-группа (SpecialMaster 3.x) по категории строки
    "speed_groups": {"dimmer": 1, "position": 2, "color": 3, "strobe": 4},
    # Привязка эффекта к Speed-группе после Store ({sg} = номер SpeedMaster, {eff} = номер эффекта).
    # "EffectSpeedGroup N" пульт отвергает (Error #27). "" = не отправлять.
    "speed_group_cmd": 'Assign SpecialMaster "speedmaster".{sg} At Effect {eff}',
    "effect_start": 101,     # первый номер в пуле Effects
    "effect_stride": 100,    # шаг между группами (группа 1 -> 101.., группа 2 -> 201..)
    "macro_start": 201,      # первый номер макроса скорости
    "speed_presets": [30, 60, 90, 120, 128, 140],
    "groups": [],
    "custom": [],            # свои шаблоны / композиции
    "move_dim": True,        # в эффекты движения - строка диммера той же волной
    "move_dim_lo": 40,       # диммер в движении ходит от этого % до 100
}

# атрибут -> требуемая возможность группы и категория (для speed-группы)
ATTR_CAP = {"dim": "dim", "shutter": "shutter", "pan": "pt", "tilt": "pt",
            "r": "rgb", "g": "rgb", "b": "rgb"}
ATTR_CAT = {"dim": "dimmer", "shutter": "strobe", "pan": "position", "tilt": "position",
            "r": "color", "g": "color", "b": "color"}
LINE_FIELDS = ("attr", "form", "lo", "hi", "phase", "width")
LINE_EXTRAS = ("groups", "wings", "blocks")
LINE_ORDER = ("dim", "shutter", "pan", "tilt", "r", "g", "b")
CATEGORIES = ["dimmer", "position", "color", "strobe", "combo"]

# =====================================================================
#  БИБЛИОТЕКА ШАБЛОНОВ
#  lines: (attr, form, low, high, phase, width[, {extra}])
#    low/high для pan/tilt — относительные (± от базовой позиции),
#    "$size" / "$shut_lo" / "$shut_hi" берутся из настроек группы.
#    extra: bpm, scale (% амплитуды), groups / wings / blocks — для отдельной строки
#  opts:  groups / wings / blocks для всех строк шаблона
# =====================================================================
SP = "0 Thru 360"      # разброс по всей группе
SP2 = "0 Thru 720"     # две волны


def T(key, name, cat, bpm, lines, **opts):
    return dict(key=key, name=name, cat=cat, bpm=bpm, lines=lines, opts=opts)


TEMPLATES = [
    # ---------------- DIMMER ----------------
    T("dim_chase", "DIM Chase", "dimmer", 120, [("dim", "chase", 0, 100, SP, 25)]),
    T("dim_reverse_chase", "DIM Reverse Chase", "dimmer", 120, [("dim", "chase", 0, 100, "360 Thru 0", 25)]),
    T("dim_wave", "DIM Wave", "dimmer", 60, [("dim", "sin", 0, 100, SP, 100)]),
    T("dim_double_wave", "DIM Double Wave", "dimmer", 60, [("dim", "sin", 0, 100, SP2, 100)]),
    T("dim_pulse", "DIM Pulse", "dimmer", 60, [("dim", "sin", 0, 100, "0", 100)]),
    T("dim_breath", "DIM Breath", "dimmer", 15, [("dim", "sin", 20, 100, "0", 100)]),
    T("dim_random", "DIM Random", "dimmer", 90, [("dim", "random", 0, 100, SP, 100)]),
    T("dim_flicker", "DIM Flicker", "dimmer", 300, [("dim", "random", 40, 100, SP, 100)]),
    T("dim_saw_up", "DIM Saw Up", "dimmer", 60, [("dim", "ramp_plus", 0, 100, SP, 100)]),
    T("dim_saw_down", "DIM Saw Down", "dimmer", 60, [("dim", "ramp_minus", 0, 100, SP, 100)]),
    T("dim_bump", "DIM Bump", "dimmer", 120, [("dim", "bump", 0, 100, SP, 100)]),
    T("dim_mirror", "DIM Mirror Chase", "dimmer", 120, [("dim", "chase", 0, 100, SP, 30)], wings=2),
    T("dim_center_out", "DIM Center Out", "dimmer", 90, [("dim", "chase", 0, 100, "0 Thru 300", 30)], wings=2),
    T("dim_out_center", "DIM Out Center", "dimmer", 90, [("dim", "chase", 0, 100, "300 Thru 0", 30)], wings=2),
    T("dim_odd_even", "DIM Odd/Even", "dimmer", 60, [("dim", "pwm", 0, 100, SP, 50)], groups=2),
    T("dim_blocks", "DIM Blocks of 2", "dimmer", 90, [("dim", "chase", 0, 100, SP, 50)], blocks=2),

    # ---------------- POSITION ----------------
    T("pt_circle", "PT Circle", "position", 30,
      [("pan", "sin", "-$size", "$size", "0", 100), ("tilt", "cos", "-$size", "$size", "0", 100)]),
    T("pt_circle_spread", "PT Circle Spread", "position", 30,
      [("pan", "sin", "-$size", "$size", SP, 100), ("tilt", "cos", "-$size", "$size", SP, 100)]),
    T("pt_figure8", "PT Figure 8", "position", 30,
      [("pan", "sin", "-$size", "$size", "0", 100),
       ("tilt", "sin", "-$size", "$size", "0", 100, {"bpm": 60, "scale": 50})]),
    T("pt_figure8_spread", "PT Figure 8 Spread", "position", 30,
      [("pan", "sin", "-$size", "$size", SP, 100),
       ("tilt", "sin", "-$size", "$size", SP, 100, {"bpm": 60, "scale": 50})]),
    T("pt_square", "PT Square", "position", 30,
      [("pan", "pwm", "-$size", "$size", "0", 50), ("tilt", "pwm", "-$size", "$size", "90", 50)]),
    T("pt_tilt_wave", "PT Tilt Wave", "position", 40, [("tilt", "sin", "-$size", "$size", SP, 100)]),
    T("pt_tilt_mirror", "PT Tilt Mirror", "position", 40, [("tilt", "sin", "-$size", "$size", SP, 100)], wings=2),
    T("pt_tilt_chase", "PT Tilt Lift Chase", "position", 60, [("tilt", "chase", 0, "$size", SP, 30)]),
    T("pt_tilt_bounce", "PT Tilt Bounce", "position", 60, [("tilt", "ramp", "-$size", "$size", SP, 100)]),
    T("pt_pan_fan", "PT Pan Fan", "position", 30, [("pan", "sin", "-$size", "$size", "0", 100)], wings=2),
    T("pt_pan_mirror", "PT Pan Mirror Wave", "position", 30, [("pan", "sin", "-$size", "$size", SP, 100)], wings=2),
    T("pt_pan_sweep", "PT Pan Sweep", "position", 20,
      [("pan", "sin", "-$size", "$size", "0 Thru 180", 100, {"scale": 200})]),
    T("pt_ballyhoo", "PT Ballyhoo", "position", 45,
      [("pan", "random", "-$size", "$size", SP, 100), ("tilt", "random", "-$size", "$size", SP, 100)]),

    # ---------------- COLOR (RGB) ----------------
    T("rgb_rainbow", "RGB Rainbow", "color", 20,
      [("r", "sin", 0, 100, "0 Thru 360", 100), ("g", "sin", 0, 100, "120 Thru 480", 100),
       ("b", "sin", 0, 100, "240 Thru 600", 100)]),
    T("rgb_rainbow_all", "RGB Rainbow All", "color", 20,
      [("r", "sin", 0, 100, "0", 100), ("g", "sin", 0, 100, "120", 100), ("b", "sin", 0, 100, "240", 100)]),
    T("rgb_rainbow_chase", "RGB Step Chase", "color", 60,
      [("r", "chase", 0, 100, SP, 33), ("g", "chase", 0, 100, "120 Thru 480", 33),
       ("b", "chase", 0, 100, "240 Thru 600", 33)]),
    T("rgb_cmy", "RGB CMY Step", "color", 40,
      [("r", "pwm", 0, 100, SP, 66), ("g", "pwm", 0, 100, "120 Thru 480", 66),
       ("b", "pwm", 0, 100, "240 Thru 600", 66)]),
    T("rgb_red_blue", "RGB Red/Blue Swap", "color", 60,
      [("r", "pwm", 0, 100, SP, 50), ("g", "pwm", 0, 0, "0", 50), ("b", "pwm", 0, 100, "180 Thru 540", 50)]),
    T("rgb_police", "RGB Police", "color", 120,
      [("r", "pwm", 0, 100, SP, 50), ("g", "pwm", 0, 0, "0", 50), ("b", "pwm", 0, 100, "180 Thru 540", 50)],
      groups=2),
    T("rgb_fire", "RGB Fire", "color", 90,
      [("r", "sin", 80, 100, SP, 100), ("g", "random", 0, 45, SP, 100), ("b", "pwm", 0, 0, "0", 50)]),
    T("rgb_ice", "RGB Ice", "color", 30,
      [("r", "sin", 0, 20, SP, 100), ("g", "sin", 40, 80, "180 Thru 540", 100), ("b", "sin", 80, 100, SP, 100)]),

    # ---------------- STROBE ----------------
    T("strobe_dim", "STROBE Dim", "strobe", 600, [("dim", "pwm", 0, 100, "0", 10)]),
    T("strobe_burst", "STROBE Burst", "strobe", 900, [("dim", "pwm", 0, 100, "0", 5)]),
    T("strobe_random", "STROBE Random", "strobe", 480, [("dim", "pwm", 0, 100, SP, 8)], groups=0),
    T("strobe_chase", "STROBE Chase", "strobe", 480, [("dim", "chase", 0, 100, SP, 10)]),
    T("strobe_odd_even", "STROBE Odd/Even", "strobe", 480, [("dim", "pwm", 0, 100, SP, 10)], groups=2),
    T("strobe_wings", "STROBE Wings", "strobe", 480, [("dim", "chase", 0, 100, SP, 10)], wings=2),
    T("strobe_shutter", "STROBE Shutter", "strobe", 300, [("shutter", "pwm", "$shut_lo", "$shut_hi", "0", 50)]),
]

# Готовые композиции (слои ссылаются на шаблоны выше)
COMBOS = [
    dict(key="combo_circle_rainbow", name="CMB Circle + Rainbow", cat="combo",
         layers=[{"tpl": "pt_circle_spread"}, {"tpl": "rgb_rainbow"}]),
    dict(key="combo_ballyhoo_strobe", name="CMB Ballyhoo + Strobe", cat="combo",
         layers=[{"tpl": "pt_ballyhoo"}, {"tpl": "strobe_random"}]),
    dict(key="combo_wave_fire", name="CMB Wave + Fire", cat="combo",
         layers=[{"tpl": "dim_wave", "speed": 0.5, "lo": 30}, {"tpl": "rgb_fire"}]),
    dict(key="combo_fan_police", name="CMB Fan + Police", cat="combo",
         layers=[{"tpl": "pt_pan_fan"}, {"tpl": "rgb_police"}]),
    dict(key="combo_figure8_breath", name="CMB Figure 8 + Breath", cat="combo",
         layers=[{"tpl": "pt_figure8_spread"}, {"tpl": "dim_breath", "phase": SP}]),
    dict(key="combo_lift_chase", name="CMB Lift + Dim Chase", cat="combo",
         layers=[{"tpl": "pt_tilt_chase"}, {"tpl": "dim_chase", "bpm": 60, "width": 30}]),
    dict(key="combo_ice_breath", name="CMB Ice + Breath", cat="combo",
         layers=[{"tpl": "rgb_ice"}, {"tpl": "dim_breath"}]),
    dict(key="combo_rainbow_wave", name="CMB Rainbow + Tilt Wave", cat="combo",
         layers=[{"tpl": "rgb_rainbow_chase"}, {"tpl": "pt_tilt_wave"}]),
]

BUILTIN_KEYS = {t["key"] for t in TEMPLATES} | {c["key"] for c in COMBOS}


def library(cfg=None):
    """Все шаблоны: встроенные + комбо + свои из конфига (свои перекрывают по ключу)."""
    lib = {t["key"]: t for t in TEMPLATES}
    lib.update({c["key"]: c for c in COMBOS})
    for c in (cfg or {}).get("custom", []) or []:
        lib[c["key"]] = c
    return lib


# совместимость со старым кодом
TEMPLATE_BY_KEY = library()


# =====================================================================
#  РАЗВЁРТКА ШАБЛОНОВ В СТРОКИ
# =====================================================================
def norm_line(line, tpl_bpm, opts, cat=None):
    if isinstance(line, dict):
        d = dict(line)
    else:
        d = dict(zip(LINE_FIELDS, line[:6]))
        if len(line) > 6:
            d.update(line[6])
    d.setdefault("bpm", tpl_bpm)
    d.setdefault("scale", 100)
    for k in LINE_EXTRAS:
        if k in opts and k not in d:
            d[k] = opts[k]
    d["cat"] = cat if cat in ATTR_CAT.values() else ATTR_CAT.get(d["attr"], "dimmer")
    return d


def apply_layer(line, layer):
    d = dict(line)
    if layer.get("bpm") not in (None, ""):
        d["bpm"] = layer["bpm"]
    if layer.get("speed") not in (None, "", 1, 1.0):
        d["bpm"] = d["bpm"] * float(layer["speed"])
    for k in ("phase", "width", "lo", "hi"):
        if layer.get(k) not in (None, ""):
            d[k] = layer[k]
    if layer.get("scale") not in (None, "", 100):
        d["scale"] = d.get("scale", 100) * float(layer["scale"]) / 100.0
    if layer.get("invert"):
        d["lo"], d["hi"] = d["hi"], d["lo"]
    for k in LINE_EXTRAS:
        if layer.get(k) not in (None, ""):
            v = int(layer[k])
            if v < 0:              # -1 = убрать
                d.pop(k, None)
            else:
                d[k] = v
    return d


def expand(tpl, lib, depth=0):
    """Шаблон -> список строк (dict). Поддерживает lines и layers (вложенность до 6)."""
    if depth > 6:
        raise ValueError(f"Слишком глубокая вложенность в '{tpl.get('key')}'")
    bpm, opts = tpl.get("bpm", 60), tpl.get("opts", {}) or {}
    out = [norm_line(l, bpm, opts, tpl.get("cat")) for l in tpl.get("lines", [])]
    for layer in tpl.get("layers", []) or []:
        if layer.get("tpl"):
            src = lib.get(layer["tpl"])
            if src is None:
                raise ValueError(f"Неизвестный шаблон в слое: '{layer['tpl']}'")
            if src is tpl:
                raise ValueError(f"Шаблон '{tpl.get('key')}' ссылается сам на себя")
            sub = expand(src, lib, depth + 1)
            only = layer.get("attrs")
            if only:
                sub = [l for l in sub if l["attr"] in only]
        elif layer.get("line"):
            sub = [norm_line(layer["line"], bpm, {})]
        else:
            continue
        out += [apply_layer(l, layer) for l in sub]
    return out


def dedupe(lines):
    """Один атрибут — одна строка эффекта. Побеждает последний слой."""
    seen, out, warns = {}, [], []
    for l in lines:
        if l["attr"] in seen:
            warns.append(f"атрибут {l['attr'].upper()} задан несколько раз — используется последний слой")
            out[seen[l["attr"]]] = None
        seen[l["attr"]] = len(out)
        out.append(l)
    return [l for l in out if l is not None], sorted(set(warns))


def resolved_lines(tpl, lib):
    lines, warns = dedupe(expand(tpl, lib))
    return lines, warns


def needs(tpl, lib):
    try:
        return {ATTR_CAP[l["attr"]] for l in expand(tpl, lib)}
    except (ValueError, KeyError):
        return {"?"}


def resolve(value, group):
    if isinstance(value, str) and "$" in value:
        neg = value.startswith("-")
        v = group[value.lstrip("-").lstrip("$")]
        return -v if neg else v
    return value


def num(v):
    v = round(float(v), 2)
    return int(v) if v.is_integer() else v


def line_values(line, group):
    s = float(line.get("scale", 100)) / 100.0
    return num(float(resolve(line["lo"], group)) * s), num(float(resolve(line["hi"], group)) * s)


def move_dim_line(tpl, lines, group, cfg):
    """эффект движения → строка диммера той же волной (та же фаза, темп, крылья),
    если в настройках включено, у группы есть диммер и своей строки DIM нет"""
    if not cfg.get("move_dim", True) or tpl.get("cat") != "position":
        return None
    if "dim" not in (group.get("caps") or []) or any(l["attr"] == "dim" for l in lines):
        return None
    base = next((l for l in lines if l["attr"] in ("pan", "tilt")), None)
    if base is None:
        return None
    try:
        lo = max(0, min(100, float(cfg.get("move_dim_lo", 40))))
    except (TypeError, ValueError):
        lo = 40
    d = {"attr": "dim", "form": "sin", "lo": num(lo), "hi": 100, "phase": base["phase"], "width": 100,
         "bpm": base["bpm"], "scale": 100, "cat": base.get("cat", "position")}
    for k in LINE_EXTRAS:
        if base.get(k):
            d[k] = base[k]
    return d


def has_move_dim(tpl, group, cfg, lib=None):
    try:
        lines, _ = resolved_lines(tpl, lib or library(cfg))
    except ValueError:
        return False
    return move_dim_line(tpl, lines, group, cfg) is not None


# =====================================================================
#  ПОСТРОЕНИЕ КОМАНД
# =====================================================================
def effect_commands(tpl, group, eff_no, cfg, lib=None):
    lib = lib or library(cfg)
    forms, attrs = cfg["forms"], cfg["attrs"]
    lines, warns = resolved_lines(tpl, lib)
    extra = move_dim_line(tpl, lines, group, cfg)
    if extra:
        lines = lines + [extra]
    # MA2 сам сортирует строки эффекта по атрибутам прибора (DIM, PAN, TILT, ...);
    # в том же порядке шлём и мы, чтобы номер строки 1.N.L совпал.
    lines = sorted(lines, key=lambda l: LINE_ORDER.index(l["attr"]) if l["attr"] in LINE_ORDER else 99)
    label = f'{group["name"]} {tpl["name"]}'[:32]
    ref = f"Effect 1.{eff_no}"
    # Delete: иначе Store /o сливает новые строки со старыми (оставались PAN/TILT прошлого эффекта)
    cmds = [f"Delete {ref} /noconfirm", "ClearAll", f'Group {group["id"]}']
    for l in lines:
        lo, hi = line_values(l, group)
        cmds += [
            f'Attribute "{attrs[l["attr"]]}"',
            f"EffectForm {forms[l['form']]}",
            f"EffectLow {lo}",
            f"EffectHigh {hi}",
            f"EffectPhase {l['phase']}",
            f"EffectWidth {num(l['width'])}",
            f"EffectBPM {num(l['bpm'])}",
        ]
    cmds += [f"Store {ref} /o",
             f"Store {ref}.* /o",            # выделение (приборы группы) -> во все строки
             f'Label {ref} "{label}"']
    # Wings / Groups / Blocks — свойства строки: Assign Effect 1.N.L /wings=2. 0 = не трогать.
    for k in LINE_EXTRAS:
        vals = [int(l.get(k) or 0) for l in lines]
        if not any(vals):
            continue
        if len(set(vals)) == 1:
            cmds.append(f"Assign {ref}.* /{k}={vals[0]}")
        else:
            cmds += [f"Assign {ref}.{i} /{k}={v}" for i, v in enumerate(vals, 1) if v]
    # Speed-группа задаётся на весь эффект: категория шаблона, для combo — категория первой строки.
    cat = tpl.get("cat") if tpl.get("cat") in cfg["speed_groups"] else (lines[0]["cat"] if lines else None)
    sg = cfg["speed_groups"].get(cat)
    if sg and cfg.get("speed_group_cmd"):
        cmds.append(cfg["speed_group_cmd"].format(sg=sg, eff=eff_no))
    return cmds, warns


# =====================================================================
#  LUA-ПЛАГИН ДВИЖЕНИЙ: группа выбирается на пульте при запуске
# =====================================================================
def _lua_str(text):
    return "'" + str(text).replace("\\", "\\\\").replace("'", "\\'") + "'"


def _lua_value(value, scale):
    """значение строки → выражение Lua: $size → S (амплитуда, спрашивается при запуске)"""
    if isinstance(value, str) and "$" in value:
        neg = value.startswith("-")
        name = value.lstrip("-").lstrip("$")
        var = {"size": "S", "shut_lo": "0", "shut_hi": "100"}.get(name, "S")
        expr = f"{var}*{num(scale)}" if scale != 1 else var
        return f"-({expr})" if neg else expr
    return str(num(float(value) * scale))


def moves_plugin(cfg, lib=None, name="MovesExec", keys=None, size=20):
    """эффекты движений генератора → плагин MA2 (lua + xml) в духе PosExec:
    при запуске спрашивает экзекьютор, группу, амплитуду и диммер, и пишет по кью на эффект"""
    lib = lib or library(cfg)
    forms, attrs = cfg["forms"], cfg["attrs"]
    sg = (cfg.get("speed_groups") or {}).get("position")
    keys = keys or [k for k in ordered_keys(lib) if lib[k].get("cat") == "position"]
    cues = []
    for k in keys:
        tpl = lib[k]
        try:
            lines, _ = resolved_lines(tpl, lib)
        except ValueError:
            continue
        lines = [l for l in lines if l["attr"] in ("pan", "tilt", "dim")]
        if not lines:
            continue
        base = next((l for l in lines if l["attr"] in ("pan", "tilt")), lines[0])
        extras = {x: int(base.get(x) or 0) for x in LINE_EXTRAS}
        rows = []
        for l in sorted(lines, key=lambda l: LINE_ORDER.index(l["attr"]) if l["attr"] in LINE_ORDER else 99):
            sc = float(l.get("scale", 100)) / 100.0
            rows.append("{" + ", ".join([
                _lua_str(attrs[l["attr"]]), str(forms[l["form"]]),
                _lua_value(l["lo"], sc), _lua_value(l["hi"], sc),
                _lua_str(l["phase"]), str(num(l["width"])), str(num(l["bpm"]))]) + "}")
        has_dim = any(l["attr"] == "dim" for l in lines)
        dim = "nil"
        if not has_dim and tpl.get("cat") == "position":
            try:
                lo = max(0, min(100, float(cfg.get("move_dim_lo", 40))))
            except (TypeError, ValueError):
                lo = 40
            dim = "{" + ", ".join([_lua_str(attrs["dim"]), str(forms["sin"]), str(num(lo)), "100",
                                   _lua_str(base["phase"]), "100", str(num(base["bpm"]))]) + "}"
        cues.append("        {name=" + _lua_str(tpl["name"][:28]) +
                    ", wings=" + str(extras["wings"]) + ", groups=" + str(extras["groups"]) +
                    ", blocks=" + str(extras["blocks"]) + ", dim=" + dim +
                    ", lines={" + ", ".join(rows) + "}},")
    lua = LUA_MOVES.replace("%NAME%", name).replace("%SIZE%", str(num(size))) \
        .replace("%SG%", str(int(sg)) if sg else "nil").replace("%CUES%", "\n".join(cues)) \
        .replace("%DIMDEF%", "yes" if cfg.get("move_dim", True) else "no")
    xml = ('<?xml version="1.0" encoding="utf-8"?>\n'
           '<MA xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
           'xmlns="http://schemas.malighting.de/grandma2/xml/MA" '
           'xsi:schemaLocation="http://schemas.malighting.de/grandma2/xml/MA '
           'http://schemas.malighting.de/grandma2/xml/3.9.60/MA.xsd" '
           'major_vers="3" minor_vers="9" stream_vers="60">\n'
           f'\t<Info datetime="{time.strftime("%Y-%m-%dT%H:%M:%S")}" showfile="ma2_fxgen" />\n'
           f'\t<Plugin index="1" execute_on_load="0" name="{name}" luafile="{name}.lua" />\n'
           '</MA>\n')
    return lua, xml, len(cues)


LUA_MOVES = r"""-- ------------------------------------------------------------------
-- %NAME%: экзекьютор с эффектами движений из ma2_fxgen
-- Группа выбирается при запуске (как в PosExec): одна и та же раскладка
-- эффектов ставится на любую группу, уже во время работы.
-- Каждый эффект - отдельная кью; Goto на экзекьюторе, Fade 2.
-- ------------------------------------------------------------------

-- S - амплитуда в градусах (спрашивается при запуске)
local function Cues(S)
    return {
%CUES%
    }
end

local SPEED_GROUP = %SG%   -- Speed-группа движений (SpecialMaster 3.N), nil - не задавать

local function yes(v)
    v = string.lower(v or '')
    return v == 'yes' or v == 'y' or v == 'да' or v == '1'
end

local function MovesExec()
    local execNumber = gma.textinput('Exec number', '111')
    if not execNumber then return end
    local group = gma.textinput('Group (1, 1 + 3, 1 Thru 4)', '1')
    if not group or group == '' then return end
    local execLabel = gma.textinput('Exec label', 'MOVES '..group)
    local S = tonumber(gma.textinput('Amplitude, degrees', '%SIZE%')) or %SIZE%
    local withDim = yes(gma.textinput('Dimmer wave in moves?', '%DIMDEF%'))

    local CUES = Cues(S)
    gma.cmd('Blind On')
    for i, c in ipairs(CUES) do
        gma.cmd('ClearAll')
        gma.cmd('Group '..group)
        gma.cmd('MAtricksReset')
        if c.wings > 0 then gma.cmd('MAtricksWings '..c.wings) end
        if c.groups > 0 then gma.cmd('MAtricksGroups '..c.groups) end
        if c.blocks > 0 then gma.cmd('MAtricksBlocks '..c.blocks) end
        local lines = c.lines
        if withDim and c.dim then
            lines = {c.dim}
            for _, l in ipairs(c.lines) do lines[#lines + 1] = l end
        end
        for _, l in ipairs(lines) do
            gma.cmd('Attribute "'..l[1]..'"')
            gma.cmd('EffectForm '..l[2])
            gma.cmd('EffectLow '..l[3])
            gma.cmd('EffectHigh '..l[4])
            gma.cmd('EffectPhase '..l[5])
            gma.cmd('EffectWidth '..l[6])
            gma.cmd('EffectBPM '..l[7])
            if SPEED_GROUP then gma.cmd('EffectSpeedGroup '..SPEED_GROUP) end
        end
        gma.cmd('Store Cue '..i..' Exec '..execNumber..' /o /nc')
        gma.cmd('Label Cue '..i..' Exec '..execNumber..' "'..c.name..'"')
    end
    gma.cmd('ClearAll')
    gma.cmd('MAtricksReset')

    gma.cmd('Assign Goto Executor '..execNumber)
    gma.cmd('Label Executor '..execNumber..' "'..execLabel..'"')
    gma.cmd('Assign Fade 2 Cue 1 Thru Executor '..execNumber)
    gma.cmd('Assign Executor '..execNumber..' /offtime=2 /ooo=off')
    gma.cmd('Assign Seq "'..execLabel..'" /track=off')
    gma.cmd('Blind Off')
    gma.feedback('%NAME%: '..#CUES..' cues -> Exec '..execNumber..', group '..group)
end

return MovesExec
"""


def macro_commands(cfg):
    cmds, m = [], cfg["macro_start"]
    names = {v: k for k, v in cfg["speed_groups"].items()}
    for sg in sorted(names):
        cat = names[sg].upper()
        master = f"SpecialMaster 3.{sg}"
        # строка макроса - «Macro 1.N.1»: «Macro N.1» пульт читает как пул N, макрос 1 (Error #14)
        for bpm in cfg["speed_presets"]:
            cmds += [f"Store Macro 1.{m} /o", f"Store Macro 1.{m}.1",
                     f'Assign Macro 1.{m}.1 /cmd="{master} At {bpm}"',
                     f'Label Macro 1.{m} "{cat} {bpm}"']
            m += 1
        cmds += [f"Store Macro 1.{m} /o", f"Store Macro 1.{m}.1",
                 f'Assign Macro 1.{m}.1 /cmd="Learn {master}"',
                 f'Label Macro 1.{m} "{cat} LEARN"']
        m += 1
    return cmds


def ordered_keys(lib):
    """Порядок: встроенные шаблоны, комбо, свои."""
    keys = [t["key"] for t in TEMPLATES] + [c["key"] for c in COMBOS]
    keys += [k for k in lib if k not in keys]
    return keys


def build(cfg, only=None, group_ids=None, make_macros=True):
    """-> (команды, отчёт [(effect, группа, шаблон)], предупреждения)"""
    lib = library(cfg)
    cmds, report, warnings = [], [], []
    for gi, group in enumerate(cfg["groups"]):
        if group_ids and group["id"] not in group_ids:
            continue
        caps = set(group["caps"])
        base = cfg["effect_start"] + gi * cfg["effect_stride"]
        wanted = group.get("templates") or ordered_keys(lib)
        slot = 0
        for key in wanted:
            tpl = lib.get(key)
            if not tpl:
                warnings.append(f"группа {group['id']}: неизвестный шаблон '{key}'")
                continue
            if only and key not in only:
                continue
            try:
                if not needs(tpl, lib) <= caps:
                    continue
                if slot >= cfg["effect_stride"]:
                    warnings.append(f"группа {group['id']}: эффектов больше effect_stride "
                                    f"({cfg['effect_stride']}), остальные пропущены")
                    break
                eff_no = base + slot
                c, w = effect_commands(tpl, group, eff_no, cfg, lib)
            except ValueError as e:
                warnings.append(f"{key}: {e}")
                continue
            cmds += c
            warnings += [f"{tpl['name']}: {x}" for x in w]
            report.append((eff_no, group["name"], tpl["name"]))
            slot += 1
    cmds.append("ClearAll")
    if make_macros:
        cmds += macro_commands(cfg)
    return cmds, report, sorted(set(warnings), key=warnings.index)


# =====================================================================
#  КОНФИГ
# =====================================================================
def load_config(path, require_groups=True):
    cfg = copy.deepcopy(DEFAULTS)
    if path:
        with open(path, encoding="utf-8") as f:
            user = json.load(f)
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    if require_groups and not cfg["groups"]:
        sys.exit("В конфиге нет групп (\"groups\": [...]).")
    for g in cfg["groups"]:
        g.setdefault("caps", ["dim"])
        g.setdefault("size", 20)          # амплитуда pan/tilt, градусы
        g.setdefault("shut_lo", 0)        # shutter closed
        g.setdefault("shut_hi", 100)      # shutter open
        g.setdefault("templates", None)   # None = все подходящие
    cfg["custom"] = cfg.get("custom") or []
    return cfg


# =====================================================================
#  TELNET
# =====================================================================
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def clean_text(text):
    """Убрать ANSI-цвета и \\r из ответа пульта."""
    return ANSI_RE.sub("", text).replace("\r", "")


def own_reply(reply, cmd):
    """Ответ пульта только на свою команду. Под тем же пользователем пульту пишет
    и анализатор: его «Executing : …» и ошибки приходят в этот же сокет."""
    out, mine = [], True
    want = " ".join(cmd.split()).lower()
    for line in clean_text(reply).split("\n"):
        low = " ".join(line.split()).lower()
        if "executing :" in low:
            mine = low.split("executing :", 1)[1].strip() == want
        elif low.startswith("error :"):
            mine = low.split("error :", 1)[1].strip() == want
        if mine:
            out.append(line)
    return "\n".join(out)


class MA2Telnet:
    def __init__(self, host, port=30000, timeout=5.0):
        self.host, self.port = host, port
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(0.05)   # короткий дренаж после паузы; паузу задаёт --delay
        self.eol = b"\r\n"          # конец строки; login() подбирает тот, что пульт принимает

    def _write(self, line):
        # sendall с таймаутом 0.05 с падает, если пульт не успевает читать
        self.sock.settimeout(5.0)
        try:
            self.sock.sendall(line.encode("utf-8") + self.eol)
        finally:
            self.sock.settimeout(0.05)

    @staticmethod
    def _decode(data):
        out, i = bytearray(), 0
        while i < len(data):           # выкинуть telnet IAC
            if data[i] == 255 and i + 2 < len(data):
                i += 3
            else:
                out.append(data[i])
                i += 1
        return out.decode("utf-8", errors="ignore")

    def read(self, wait=0.3):
        time.sleep(wait)
        data = b""
        while True:
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                data += chunk
            except socket.timeout:
                break
        return self._decode(data)

    def send(self, line, wait=0.15):
        self._write(line)
        return self.read(wait)

    def query(self, line, settle=0.4, max_wait=6.0):
        """Отправить команду и читать ответ, пока пульт не замолчит на settle секунд."""
        self._write(line)
        data, t0 = b"", time.time()
        last = t0
        while time.time() - t0 < max_wait:
            try:
                chunk = self.sock.recv(65536)
                if not chunk:
                    break
                data += chunk
                last = time.time()
            except socket.timeout:
                if data and time.time() - last >= settle:
                    break
                if not data and time.time() - t0 > max(settle * 3, 1.5):
                    break
        return self._decode(data)

    def login(self, user, password):
        """-> (ok, ответ пульта)"""
        self.read(1.0)
        line = f'Login "{user}" "{password}"'
        r = self.send(line, wait=0.8)
        if "illegal character" in r.lower():
            # часть пультов / onPC не принимает \r\n: лишний символ даёт
            # «Error #3: ILLEGAL CHARACTER» на каждую команду. Пробуем другой конец строки.
            for eol in (b"\r", b"\n"):
                self.eol = eol
                r2 = self.send(line, wait=0.8)
                if "illegal character" not in r2.lower():
                    r = r2
                    break
            else:
                self.eol = b"\r\n"
        low = r.lower()
        if "logged in" in low:
            return True, clean_text(r).strip()
        bad = any(w in low for w in ("error", "denied", "invalid", "wrong"))
        return not bad, clean_text(r).strip()

    def close(self, logout=False):
        try:
            if logout:
                self.send("Logout", wait=0.2)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


# =====================================================================
#  ИМПОРТ ГРУПП ИЗ ШОУ
#  Формат вывода List Group в Telnet зависит от версии MA2, поэтому разбор
#  терпимый: "1  Spot Back", "Group 1 \"Spot Back\"", "1 Name=Spot Back ..." и т.п.
# =====================================================================
SKIP_PREFIXES = ("executing", "list", "[", "no.", "no ", "#", "name", "ok", "error", "welcome",
                 "logged", "login", "user", "command")


def parse_group_list(text):
    groups = {}
    for raw in clean_text(text).split("\n"):
        line = raw.strip()
        if not line or line.lower().startswith(SKIP_PREFIXES):
            continue
        m = re.match(r"^(?:group\s+)?(\d+)\s*[:.)]?\s+(.*)$", line, re.I)
        if not m:
            continue
        gid, rest = int(m.group(1)), m.group(2).strip()
        dup = re.match(r"^(\d+)\s+(.*)$", rest)       # 3.9.x: «Group  1 1    All Spots»
        if dup and int(dup.group(1)) == gid:
            rest = dup.group(2).strip()
        nm = re.search(r'name\s*=\s*"([^"]*)"', rest, re.I) or \
            re.search(r"name\s*=\s*(.+?)(?=\s{2,}|\s+\w+\s*=|$)", rest, re.I)
        q = re.match(r'^"([^"]*)"', rest) or re.match(r"^'([^']*)'", rest)
        if nm:
            name = nm.group(1)
        elif q:
            name = q.group(1)
        else:
            name = re.split(r"\s{2,}|\t|\s+:\s+", rest)[0]
        name = name.strip().strip('"')
        if name and gid > 0:
            groups.setdefault(gid, name)
    return [{"id": k, "name": v} for k, v in sorted(groups.items())]


def parse_fixture_count(text):
    """Посчитать приборы в выражениях вида 'Fixture 101 Thru 106 + 201'. None — если не нашли."""
    t = clean_text(text)
    ids = set()
    for m in re.finditer(r"\b(?:fixture|fix|channel|chan)s?\s+((?:[\d.]+|\s|\+|-|thru)+)", t, re.I):
        expr = re.sub(r"\s+", " ", m.group(1).lower()).strip()
        sign, toks, i = 1, re.findall(r"[\d.]+|thru|\+|-", expr), 0
        while i < len(toks):
            tok = toks[i]
            if tok == "+":
                sign = 1
            elif tok == "-":
                sign = -1
            elif tok != "thru":
                a = int(float(tok))
                if i + 2 < len(toks) and toks[i + 1] == "thru" and toks[i + 2] not in ("+", "-", "thru"):
                    b = int(float(toks[i + 2]))
                    rng = set(range(min(a, b), max(a, b) + 1))
                    i += 2
                else:
                    rng = {a}
                ids = ids | rng if sign > 0 else ids - rng
            i += 1
    if not ids:
        # запасной вариант: таблица, где каждая строка начинается с ID прибора
        rows = [l for l in t.split("\n") if re.match(r"^\s*\d+\s+\S", l)]
        return len(rows) or None
    return len(ids)


CAP_HINTS = [
    # (ключевые слова в имени группы, возможности)
    (("par64", "par 64", "dimmer", "front", "fresnel", "profile", "blinder", "pc ", "фронт", "диммер"), {"dim"}),
    (("spot", "alpha", "viper", "pointe", "sharpy", "mh", "moving", "head", "спот", "голов"),
     {"dim", "pt", "shutter"}),
    (("beam", "бим"), {"dim", "pt", "rgb"}),
    (("wash", "aura", "mac", "вош"), {"dim", "pt", "rgb"}),
    (("led", "rgb", "q7", "batten", "pixel", "strip", "bar", "cyc", "лед"), {"dim", "rgb"}),
]


def guess_caps(name):
    n = " " + name.lower() + " "
    caps = {"dim"}
    for words, c in CAP_HINTS:
        if any(w in n for w in words):
            caps |= c
    return [c for c in ("dim", "pt", "rgb", "shutter") if c in caps]


def pull_groups(ma, list_cmd="List Group", detail_cmd="List Group {id}", counts=True, progress=None):
    """-> (группы [{id,name,count?,caps}], сырой текст ответов)"""
    raw = ma.query(list_cmd, settle=0.5, max_wait=8.0)
    log = [f">>> {list_cmd}", clean_text(raw)]
    groups = parse_group_list(raw)
    for i, g in enumerate(groups):
        g["caps"] = guess_caps(g["name"])
        if counts and detail_cmd:
            cmd = detail_cmd.format(id=g["id"])
            r = ma.query(cmd, settle=0.3, max_wait=4.0)
            log += [f">>> {cmd}", clean_text(r)]
            n = parse_fixture_count(r)
            if n:
                g["count"] = n
        if progress:
            progress(i + 1, len(groups))
    return groups, "\n".join(log)


# Имена форм в пуле Forms пульта -> ключ генератора. Номера в пуле на разных шоу
# разные (на скрине у пользователя Form 1 = Stomp, 12 = Ramp), поэтому перед
# отправкой читаем List Form и подставляем реальные номера по имени.
FORM_NAMES = {
    "chase": ("chase",), "sin": ("sin", "sine"), "cos": ("cos", "cosine"),
    "ramp_plus": ("rampplus", "ramp+", "rampup"), "ramp_minus": ("rampminus", "ramp-", "rampdown"),
    "ramp": ("ramp",), "phase1": ("phase1",), "phase2": ("phase2",), "phase3": ("phase3",),
    "bump": ("bump",), "swing": ("swing",), "random": ("random",), "pwm": ("pwm",),
}


def pull_forms(ma, list_cmd="List Form"):
    """-> ({ключ: номер формы на пульте}, [ключи без пары], сырой ответ)"""
    raw = ma.query(list_cmd, settle=0.5, max_wait=6.0)
    by_name = {}
    for f in parse_group_list(raw):
        by_name.setdefault(re.sub(r"[\s_]+", "", f["name"].lower()), f["id"])
    found, missing = {}, []
    for key, names in FORM_NAMES.items():
        hit = next((by_name[n] for n in names if n in by_name), None)
        if hit is None:
            missing.append(key)
        else:
            found[key] = hit
    return found, missing, clean_text(raw)


def remap_forms(cmds, old, new):
    """Заменить номера в EffectForm N: old/new — {ключ: номер}."""
    m = {old[k]: new[k] for k in old if k in new}
    out = []
    for c in cmds:
        if c.startswith("EffectForm "):
            n = int(c.split()[1])
            c = f"EffectForm {m.get(n, n)}"
        out.append(c)
    return out


def merge_groups(existing, pulled, replace=False):
    """Добавить/обновить группы по ID. Свои настройки (caps, size, templates) у существующих сохраняются."""
    if replace:
        out = []
        for g in pulled:
            n = {"caps": g.get("caps", ["dim"]), "size": 20, "shut_lo": 0, "shut_hi": 100,
                 "count": g.get("count", 6), "templates": None}
            n.update({"id": g["id"], "name": g["name"]})
            out.append(n)
        return out
    out = [dict(g) for g in existing]
    by_id = {g["id"]: g for g in out}
    for g in pulled:
        if g["id"] in by_id:
            by_id[g["id"]]["name"] = g["name"]
            if g.get("count"):
                by_id[g["id"]]["count"] = g["count"]
        else:
            n = {"id": g["id"], "name": g["name"], "caps": g.get("caps", ["dim"]), "size": 20,
                 "shut_lo": 0, "shut_hi": 100, "count": g.get("count", 6), "templates": None}
            out.append(n)
            by_id[g["id"]] = n
    return out


# =====================================================================
def main():
    ap = argparse.ArgumentParser(description="grandMA2 effect generator (Telnet)")
    ap.add_argument("host", nargs="?", help="IP пульта / onPC")
    ap.add_argument("-c", "--config", help="JSON-конфиг групп")
    ap.add_argument("--port", type=int, default=30000)
    ap.add_argument("-u", "--user", default="administrator")
    ap.add_argument("-p", "--password", default="")
    ap.add_argument("--delay", type=float, default=0.12, help="пауза между командами, сек")
    ap.add_argument("--only", help="ключи шаблонов через запятую")
    ap.add_argument("--groups", help="ID групп через запятую")
    ap.add_argument("--no-macros", action="store_true")
    ap.add_argument("--print", dest="print_only", action="store_true")
    ap.add_argument("--list", action="store_true", help="показать библиотеку шаблонов")
    ap.add_argument("--pull-groups", action="store_true",
                    help="прочитать группы из шоу и записать в конфиг (-c), затем выйти")
    ap.add_argument("--replace-groups", action="store_true",
                    help="с --pull-groups: заменить список групп целиком, а не добавить/обновить")
    args = ap.parse_args()

    if args.pull_groups:
        if not args.host or not args.config:
            sys.exit("--pull-groups требует IP пульта и -c конфиг")
        try:
            with open(args.config, encoding="utf-8") as f:
                raw_cfg = json.load(f)
        except FileNotFoundError:
            raw_cfg = {}
        ma = MA2Telnet(args.host, args.port)
        ok, resp = ma.login(args.user, args.password)
        if not ok:
            ma.close()
            sys.exit("Login failed: " + resp)
        groups, raw = pull_groups(ma, progress=lambda i, n: print(f"  группа {i}/{n}", end="\r"))
        ma.close(logout=True)
        if not groups:
            print(raw)
            sys.exit("\nНе удалось разобрать список групп — выше сырой ответ пульта.")
        raw_cfg["groups"] = merge_groups(raw_cfg.get("groups", []), groups, args.replace_groups)
        with open(args.config, "w", encoding="utf-8") as f:
            json.dump(raw_cfg, f, ensure_ascii=False, indent=2)
        print(f"\nЗаписано групп: {len(raw_cfg['groups'])} в {args.config}")
        for g in raw_cfg["groups"]:
            print(f"  {g['id']:4}  {g['name']:24} {g.get('count', '?'):>3} пр.  {' '.join(g['caps'])}")
        print("Проверь возможности (caps) — они угаданы по имени группы.")
        return

    if args.list:
        cfg = load_config(args.config, require_groups=False)
        lib = library(cfg)
        for k in ordered_keys(lib):
            t = lib[k]
            src = "builtin" if k in BUILTIN_KEYS else "custom"
            print(f"{k:24} {t.get('cat', 'combo'):9} needs={','.join(sorted(needs(t, lib))):12} "
                  f"{src:8} {t['name']}")
        return

    cfg = load_config(args.config)
    only = set(args.only.split(",")) if args.only else None
    gids = {int(x) for x in args.groups.split(",")} if args.groups else None
    cmds, report, warns = build(cfg, only, gids, not args.no_macros)
    for w in warns:
        print("! " + w, file=sys.stderr)

    if args.print_only or not args.host:
        print("\n".join(cmds))
        print(f"\n# {len(report)} эффектов, {len(cmds)} команд", file=sys.stderr)
        return

    print("Будут созданы эффекты:")
    for no, g, n in report:
        print(f"  Effect {no:4}  {g} / {n}")
    if input(f"Отправить {len(cmds)} команд на {args.host}? [y/N] ").strip().lower() != "y":
        return

    ma = MA2Telnet(args.host, args.port)
    ok, resp = ma.login(args.user, args.password)
    print(resp)
    if not ok:
        print("Login failed.")
        ma.close()
        sys.exit(1)

    forms, missing, _ = pull_forms(ma)
    if forms:
        cmds = remap_forms(cmds, cfg["forms"], forms)
        print("Формы с пульта: " + ", ".join(f"{k}={v}" for k, v in forms.items()))
    if missing:
        print("! Нет на пульте форм: " + ", ".join(missing) + " — оставлены номера из конфига")

    errors = []
    for i, c in enumerate(cmds, 1):
        r = ma.send(c, wait=args.delay)
        bad = any(w in r.lower() for w in ("error", "illegal", "unknown"))
        print(f"[{i:4}/{len(cmds)}] {'ERR' if bad else 'ok '} {c}")
        if bad:
            errors.append((c, r.strip()))

    ma.send("ClearAll", wait=0.2)
    ma.send("Logout", wait=0.3)
    ma.close()
    print(f"\nГотово: {len(report)} эффектов, {len(errors)} ошибок.")
    for c, r in errors:
        print(f"  ! {c}\n    {r[:200]}")


if __name__ == "__main__":
    main()
