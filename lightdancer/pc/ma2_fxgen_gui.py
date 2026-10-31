#!/usr/bin/env python3
"""
ma2_fxgen_gui.py — графическая оболочка для ma2_fxgen.py (grandMA2 effect generator).

Положи рядом с ma2_fxgen.py и запусти:  python ma2_fxgen_gui.py
Нужен только стандартный Python 3.8+ (Tkinter входит в поставку).

При запуске предлагает подключиться к пульту (MA2 → Подключить…) и сразу
импортировать группы из шоу (⇩ Группы из шоу). Подключение держится открытым
и используется для отправки; при обрыве отправка переподключается сама.

Вкладки:
  Группы       — список групп, возможности (dim/pt/rgb/shutter), кол-во приборов
  Шаблоны      — библиотека по категориям: галочки, превью, «Скомпоновать» выбранные
  Компоновщик  — свои эффекты из слоёв: шаблоны целиком/по атрибутам + свои строки,
                 переопределения BPM/скорости/фазы/ширины/амплитуды/wings/groups/blocks
  Настройки    — нумерация Effects/Macros, пресеты BPM, номера форм, атрибуты
  Команды      — предпросмотр всех команд и предупреждений, экспорт в .txt
  Пульт        — подключение по Telnet, тест, отправка с логом и прогрессом

Связь с анализатором LightDancer (бывш. MusicAnalyzer): после отправки (или кнопкой «→ Анализатору») список
созданных эффектов пишется в ~/.ma2_fxgen_link.json. Анализатор в окне
«🎛 grandMA2…» → «FX-ГЕНЕРАТОР» ставит их на экзекьюторы и сам включает
под музыку: Dimmer → пульс, Position → бег, Color → поток, Strobe → искры.
"""
import copy
import json
import math
import os
import queue
import random
import re
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import ma2_fxgen as fx

CAPS = ["dim", "pt", "rgb", "wheel", "shutter", "zoom", "focus", "iris", "prism", "gobo", "frost"]
ATTRS = ["dim", "pan", "tilt", "r", "g", "b", "shutter"]
CAT_TITLES = {"dimmer": "Dimmer", "position": "Position", "color": "Color RGB",
              "strobe": "Strobe", "combo": "Комбо", "custom": "Свои"}
PHASE_PRESETS = ["", "0", "0 Thru 360", "360 Thru 0", "0 Thru 180", "0 Thru 720",
                 "0 Thru 300", "300 Thru 0", "90", "180"]

BG, PANEL, FG, MUTED, ACCENT, ERR = "#16181d", "#1f232b", "#e6e6e6", "#8a909c", "#f0a830", "#ff5c5c"
WARN = "#e0b050"
ON, OFF = "☑", "☐"


# =====================================================================
#  КОНФИГ
# =====================================================================
def make_config(user=None):
    cfg = copy.deepcopy(fx.DEFAULTS)
    if user:
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    for g in cfg["groups"]:
        g.setdefault("caps", ["dim"])
        g.setdefault("size", 20)
        g.setdefault("shut_lo", 0)
        g.setdefault("shut_hi", 100)
        g.setdefault("count", 6)
        g.setdefault("templates", None)
    cfg["custom"] = cfg.get("custom") or []
    return cfg


EXAMPLE_GROUPS = [
    {"id": 1, "name": "Spot", "caps": ["dim", "pt", "shutter"], "size": 25, "count": 6},
    {"id": 2, "name": "Beam", "caps": ["dim", "pt", "rgb"], "size": 30, "count": 8},
    {"id": 3, "name": "ParLED", "caps": ["dim", "rgb"], "count": 8},
]


def parse_val(s):
    """'' -> None, число -> число, '$size'/'-$size' -> строка."""
    s = str(s).strip()
    if s == "":
        return None
    try:
        return fx.num(float(s))
    except ValueError:
        if "$" in s:
            return s
        raise ValueError(f"'{s}' — не число и не $-ссылка ($size, $shut_lo, $shut_hi)")


def show(v):
    return "" if v is None else str(v)


# =====================================================================
#  ПАТЧ С ПУЛЬТА: типы приборов → возможности групп
# =====================================================================
# возможности по словам в имени типа прибора (библиотека MA2); первое совпадение
TYPE_RULES = (
    (r"fog|haze|smoke|hazer|дым", "-", []),
    # частые головы по моделям (до общих слов: «Profile», «Beam», «RGBW» в имени режима)
    (r"impression|x4 ?(?:l|s|xs)\b|aura|spiider|b-?eye|mac ?(?:quantum ?wash|wash)|led ?wash",
     "wash", ["dim", "pt", "shutter", "rgb", "zoom"]),
    (r"flare|atomic|jdc|strobe|blinder|molefay", "par", ["dim", "rgb", "shutter"]),
    (r"quantum ?profile|bmfl|viper|encore|forte|tarrantula|mac ?ultra|esprite|scenius|ghibli|pearl",
     "spot", ["dim", "pt", "shutter", "rgb", "wheel", "zoom", "focus", "iris", "prism", "gobo", "frost"]),
    (r"ledbeam|led ?beam|b-?eye|spiider|zoom ?wash", "wash", ["dim", "pt", "shutter", "rgb", "zoom"]),
    (r"blinder|molefay|strobe|atomic|jdc|x4 ?bar", "par", ["dim", "shutter"]),
    (r"front|source ?four|zoom ?profile|ellipsoidal|leko|fresnel|conventional", "par", ["dim"]),
    (r"sharpy|beam|pointe|mythos|b-?eye|k10|k20|megapointe", "spot",
     ["dim", "pt", "shutter", "wheel", "prism", "gobo", "frost", "focus"]),
    (r"spot|profile|bmfl|robin.*(?:600|800|1200)e?|viper|encore|forte|pearl|scenius|ghibli|tarrantula",
     "spot", ["dim", "pt", "shutter", "wheel", "zoom", "focus", "iris", "prism", "gobo", "frost"]),
    (r"wash|aura|lyre|led ?beam|spiider|b-?eye|quantum|zoom", "wash", ["dim", "pt", "shutter", "rgb", "zoom"]),
    (r"par|rgb|led|bar|batten|cyc|panel|flood|hex|tri|quad", "par", ["dim", "rgb", "shutter"]),
    (r"dimmer|generic|conventional|halogen|fresnel|pc", "par", ["dim"]),
)
KINDS = ("spot", "wash", "par", "-")


def guess_fixture_type(name):
    n = (name or "").lower()
    for pattern, kind, caps in TYPE_RULES:
        if re.search(pattern, n):
            return kind, list(caps)
    return "par", ["dim"]


def _rows(text):
    for line in (text or "").splitlines():
        line = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", line).rstrip()
        line = re.sub(r"^\s*\d+h\d+m[\d.]+s\s*:\s?", "", line)     # время из Command Line Feedback
        if line.strip():
            yield line


# «Fixture 101 SPOT 1   101   -   12 Alpha Spot HPE 700 Standard - Lamp on   1.001   No»
FIXTURE_LINE = re.compile(r"^\s*Fixture\s+(\d+)\s+(.+?)\s+(\d+|-)\s+(\d+(?:\.\d+)?|-)\s+(\d+)\s+(.+?)"
                          r"(?:\s+(\d+\.\d+|-))?(?:\s+(Yes|No))?\s*$", re.I)


# ---- ответы 3.9.x: строки таблиц разбираются по самим строкам, без шапки
# (шапка бывает сдвинута: «[Channel]>Executing : …» съедает её отступ)
def _num(v, default=0.0):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return default


# «Fixture  101 BMFL 1   101   -   3 Robin BMFL Spot Mode 2   1.001  No  0.00 … 0.00   (1)»
# «Fixture 1 Thomas 2 Lite Par 36 1   -   1   2 Dimmer 00   13.001  No …» (List Channel)
FIX_ROW = re.compile(
    r"^\s*(?:Fixture|Channel)\s+\d+\s+(?P<name>.*?)\s{2,}(?P<fid>\d+|-)\s+(?P<cid>\d+|-)\s+"
    r"(?P<tno>\d+)\s+(?P<type>.+?)\s{2,}(?P<patch>\d+\.\d+|-)\s+(?:Yes|No)\s+"
    r"(?P<px>-?[\d.]+)\s+(?P<py>-?[\d.]+)\s+(?P<pz>-?[\d.]+)\s+"
    r"(?P<rx>-?[\d.]+)\s+(?P<ry>-?[\d.]+)\s+(?P<rz>-?[\d.]+)(?P<rest>.*)$", re.I)


def parse_fixture_type_table(text):
    """List FixtureType → [{no, name (LongName + режим, как в List Fixture), long, mode, instances}]"""
    out = []
    for line in _rows(text):
        m = re.match(r"^\s*(?:\[[^\]]*\]>)?\s*FixtureType\s+\d+\s+(\d+)\s+(.*)$", line, re.I)
        if not m:
            continue
        f = [c.strip() for c in re.split(r"\s{2,}", m.group(2).strip())]
        # LongName ShortName Manufacturer ShortManu DMXFootprint Instances [Mode] Used …
        ints = [i for i, c in enumerate(f) if re.fullmatch(r"\d+", c)]
        if len(f) < 3 or len(ints) < 2:
            continue
        i = next((k for k in ints if k + 1 in ints), None)   # footprint, instances
        if i is None:
            continue
        rest = f[i + 2:]
        mode = rest[0] if len(rest) >= 2 and not rest[1].startswith("[") else ""
        if mode and re.fullmatch(r"\d+", mode) and mode != "00":
            mode = ""
        long_ = f[0]
        out.append({"no": int(m.group(1)), "long": long_, "mode": mode,
                    "name": f"{long_} {mode}".strip(), "instances": int(f[i + 1] or 1)})
    return out


def parse_fixture_types(text):
    """ответ «List FixtureType» → имена типов приборов (как в List Fixture)"""
    table = parse_fixture_type_table(text)
    if table:
        return [t["name"] for t in table]
    names = []
    for line in _rows(text):
        m = re.match(r'^\s*(?:FixtureType\s+)?(\d+)(?:\.\d+)?\s+"?([^"\t]+?)"?(?:\s{2,}.*)?$', line, re.I)
        if not m:
            continue
        name = re.split(r"\s{2,}|\t", m.group(2))[0].strip()
        if name and not re.fullmatch(r"[\d.\s]+", name) and name.lower() not in ("name", "fixturetype"):
            names.append(name)
    return names


def parse_fixture_table(text):
    """List Fixture / List Channel (3.9.x) → [{id, name, type, type_no, patch, subs, chan, pos, rot}].
    Приборы без FixId (диммеры только с ChaId) - id = ChaId, chan=True."""
    out, seen = [], set()
    for line in _rows(text):
        line = re.sub(r"^\s*\[[^\]]*\]>\s*", "", line)
        m = FIX_ROW.match(line)
        if not m or (m["fid"] == "-" and m["cid"] == "-"):
            continue
        chan = m["fid"] == "-"
        fid = int(m["cid"] if chan else m["fid"])
        if fid in seen:
            continue
        seen.add(fid)
        pos = tuple(_num(m[k]) for k in ("px", "py", "pz"))
        subs = re.search(r"\((\d+)\)\s*$", m["rest"])
        f = {"id": fid, "name": m["name"].strip(), "type": m["type"].strip(), "type_no": int(m["tno"]),
             "patch": m["patch"].strip("-"), "subs": int(subs.group(1)) if subs else 1, "chan": chan}
        if any(pos):
            f["pos"], f["rot"] = pos, tuple(_num(m[k]) for k in ("rx", "ry", "rz"))
        out.append(f)
    return out


def parse_fixtures(text, type_names=()):
    """ответ «List Fixture» (+ «List Channel») → [{id, name, type}]. Сначала - по строкам
    таблицы 3.9.x; иначе тип ищется по именам из List FixtureType (самое длинное вхождение)."""
    table = parse_fixture_table(text)
    if table:
        return table
    out, seen = [], set()
    types = sorted({t for t in type_names if t}, key=len, reverse=True)
    for line in _rows(text):
        full = FIXTURE_LINE.match(line)
        if full:
            fid = int(full.group(1))
            if fid not in seen:
                seen.add(fid)
                typ = next((t for t in types if t.lower() in full.group(6).lower()), full.group(6).strip())
                out.append({"id": fid, "name": full.group(2).strip(), "type": typ,
                            "type_no": int(full.group(5)), "patch": full.group(7) or ""})
            continue
        m = re.match(r"^\s*(?:Fixture\s+)?(\d+)(?:\.\d+)?\s+(.+)$", line, re.I)
        if not m or re.search(r"^\s*(?:executing|list\s)", line, re.I):
            continue
        fid, rest = int(m.group(1)), m.group(2)
        cols = [c.strip(' "') for c in re.split(r"\s{2,}|\t", rest) if c.strip(' "')]
        if not cols or fid in seen:
            continue
        typ = next((t for t in types if t.lower() in rest.lower()), None)
        if typ is None:
            typ = next((c for c in cols[1:] if re.search(r"[A-Za-zА-Яа-я]{3}", c)
                        and not re.fullmatch(r"(?i)(?:dmx|patch|universe)?\s*[\d.\s:/-]+", c)), "")
        seen.add(fid)
        out.append({"id": fid, "name": cols[0], "type": typ})
    return out


def group_fixture_ids(text):
    """«Fixture 1 Thru 6 + 11» и т.п. из ответа про группу → номера приборов"""
    ids = set()
    for m in re.finditer(r"(?i)fixture\s+(\d+)(?:\s+thru\s+(\d+))?((?:\s*\+\s*\d+(?:\s+thru\s+\d+)?)*)", text or ""):
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        ids.update(range(a, min(b, a + 999) + 1))
        for p in re.finditer(r"\+\s*(\d+)(?:\s+thru\s+(\d+))?", m.group(3) or ""):
            x, y = int(p.group(1)), int(p.group(2) or p.group(1))
            ids.update(range(x, min(y, x + 999) + 1))
    return ids


def match_group_types(groups, fixtures, members=None):
    """группа → типы её приборов: по составу группы, если пульт его дал,
    иначе по похожести имени группы на имя / тип приборов"""
    members = members or {}
    out = {}
    for g in groups:
        ids = members.get(g["id"]) or set()
        types = [f["type"] for f in fixtures if f["id"] in ids and f["type"]]
        how = "состав группы"
        if not types:
            words = [w for w in re.findall(r"[a-zа-я0-9]{3,}", g["name"].lower())]
            scored = []
            subs = 0
            for f in fixtures:
                text = (f["name"] + " " + f["type"]).lower()
                hit = sum(1 for w in words if w in text)
                if hit:
                    scored.append((hit, f["type"], f.get("subs") or 1))
            best = max((h for h, _, _ in scored), default=0)
            types = [t for h, t, _ in scored if h == best and t]
            subs = sum(n for h, t, n in scored if h == best and t)
            how = "по имени"
            if not types:
                # «Wash», «Spots front» - по виду прибора в имени группы
                kinds = [k for k in KINDS if k != "-" and k in g["name"].lower()]
                types = [f["type"] for f in fixtures if f["type"] and guess_fixture_type(f["type"])[0] in kinds]
                how = "по виду"
        if types:
            common = max(set(types), key=types.count)
            out[g["id"]] = {"type": common, "mixed": len(set(types)) > 1, "how": how,
                            "count": (subs or len(types)) if how == "по имени" else
                            len(types) if how != "по виду" else None}
    return out


# ---- XML из «Export …»: если onPC на этом компьютере, файл можно прочитать
def _xml_root(text):
    import xml.etree.ElementTree as ET
    text = (text or "").lstrip("\ufeff \r\n\t")
    root = ET.fromstring(text.encode("utf-8"))
    for el in root.iter():                       # без пространства имён MA
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def _xyz(el, tag):
    p = el.find(f"AbsolutePosition/{tag}") if el is not None else None
    return tuple(_num(p.get(k)) for k in "xyz") if p is not None else None


def parse_fixtures_xml(text):
    """ma2fx_fixtures.xml → [{id, name, type, type_no, patch «U.AAA», subs, pos, rot}]"""
    out, seen = [], set()
    for fe in _xml_root(text).iter("Fixture"):
        fid = fe.get("fixture_id") or fe.get("channel_id")
        if not (fid or "").isdigit() or int(fid) in seen:
            continue
        seen.add(int(fid))
        ft = fe.find("FixtureType")
        tname = (ft.get("name") if ft is not None else "") or ""
        tno = ft.findtext("No") if ft is not None else None
        tm = re.match(r"(\d+)\s+(.*)", tname)
        subs = fe.findall("SubFixture")
        first = subs[0] if subs else None
        addr = first.findtext("Patch/Address") if first is not None else None
        patch = ""
        if (addr or "").strip().isdigit() and int(addr) > 0:
            a = int(addr) - 1
            patch = f"{a // 512 + 1}.{a % 512 + 1:03d}"
        pos = _xyz(fe, "Location") or _xyz(first, "Location")
        rot = _xyz(fe, "Rotation") or _xyz(first, "Rotation")
        f = {"id": int(fid), "name": fe.get("name", ""), "type": tm.group(2).strip() if tm else tname,
             "type_no": int(tno) if (tno or "").strip().isdigit() else (int(tm.group(1)) if tm else None),
             "patch": patch, "subs": max(1, len(subs))}
        if pos and any(pos):
            f["pos"], f["rot"] = pos, rot or (0.0, 0.0, 0.0)
        out.append(f)
    return out


def parse_groups_xml(text, numbers=None):
    """ma2fx_groups.xml → [{id, name, members {номер прибора}, size (элементов с инстансами)}].
    Номер группы - index+1; если есть List Group (numbers: имя → номер), берём оттуда."""
    numbers = numbers or {}
    out = []
    for ge in _xml_root(text).iter("Group"):
        name = ge.get("name", "")
        try:
            gid = int(ge.get("index")) + 1
        except (TypeError, ValueError):
            continue
        gid = numbers.get(name, gid)
        ids, size = set(), 0
        for s in ge.iter("Subfixture"):
            fid = s.get("fix_id") or s.get("cha_id")
            if (fid or "").isdigit():
                ids.add(int(fid))
                size += 1
        out.append({"id": gid, "name": name, "members": ids, "size": size})
    return out


def is_local_host(host):
    """пульт на этом компьютере (onPC)? - тогда файлы Export можно прочитать"""
    import socket
    try:
        ip = socket.gethostbyname(host)
        if ip.startswith("127."):
            return True
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.bind((ip, 0))
        return True
    except OSError:
        return False


def find_export(name, since):
    """свежий файл Export (папки grandma\\gma2_V_*\\{fixtures,importexport}), не старше since"""
    import glob
    base = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "MA Lighting Technologies", "grandma")
    files = [f for f in glob.glob(os.path.join(base, "**", name), recursive=True)
             if os.path.getmtime(f) >= since - 5]
    return max(files, key=os.path.getmtime) if files else None


def export_patch_xml(ma, log=None, wait=5.0):
    """Export Fixture / Group в XML и чтение файлов. → (fixtures | None, groups_xml_text | None)"""
    t0 = time.time()
    got = {}
    for what, fname in (("Fixture 1 Thru 99999", "ma2fx_fixtures"), ("Group 1 Thru 9999", "ma2fx_groups")):
        ma.query(f'Export {what} "{fname}" /o', settle=0.6, max_wait=10.0)
        path, t1 = None, time.time()
        while time.time() - t1 < wait:
            path = find_export(fname + ".xml", t0)
            if path:
                break
            time.sleep(0.3)
        if path:
            time.sleep(0.3)                      # пульт мог ещё дописывать
            with open(path, encoding="utf-8-sig", errors="replace") as fh:
                got[fname] = fh.read()
            if log:
                log(f"Патч: прочитан {path}")
    fixtures = None
    if got.get("ma2fx_fixtures"):
        try:
            fixtures = parse_fixtures_xml(got["ma2fx_fixtures"])
        except Exception as e:
            if log:
                log(f"Патч: XML приборов не разобран: {e}")
    return fixtures, got.get("ma2fx_groups")


# =====================================================================
#  ПРЕВЬЮ: приближённая модель эффекта MA2
# =====================================================================
def parse_phase(spec):
    parts = [p.strip() for p in str(spec).split("Thru")]
    try:
        a = float(parts[0])
        b = float(parts[1]) if len(parts) > 1 else a
    except ValueError:
        a = b = 0.0
    return a, b


def form_value(form, t, width, seed):
    """t in [0,1) -> 0..1"""
    w = max(float(width), 1) / 100.0
    if form in ("chase", "pwm"):
        return 1.0 if t < w else 0.0
    if form == "random":
        return random.Random(seed).random() if t < w else 0.0
    if t >= w:
        return 0.0
    u = t / w
    if form == "sin":
        return 0.5 + 0.5 * math.sin(2 * math.pi * u)
    if form == "cos":
        return 0.5 + 0.5 * math.cos(2 * math.pi * u)
    if form == "ramp_plus":
        return u
    if form == "ramp_minus":
        return 1 - u
    if form == "ramp":
        return 1 - abs(2 * u - 1)
    if form == "bump":
        return math.sin(math.pi * u) ** 2
    if form == "swing":
        return 0.5 + 0.5 * math.sin(2 * math.pi * u) * abs(math.sin(math.pi * u))
    return 0.5 + 0.5 * math.sin(2 * math.pi * u)


def fixture_phase(i, n, spec, wings=None, groups=None, blocks=None):
    a, b = parse_phase(spec)
    if a == b or n <= 1:
        return a
    idx, count = i, n
    if blocks and blocks > 1:
        idx, count = i // blocks, math.ceil(n / blocks)
    if groups and groups > 0:
        idx, count = idx % groups, min(groups, count)
    if wings and wings > 1:
        seg = max(count / wings, 1)
        k, pos = int(idx // seg), idx % seg
        if k % 2:
            pos = seg - 1 - pos
        return a + (b - a) * pos / seg
    return a + (b - a) * idx / max(count, 1)


PHASE_RE = re.compile(r"(phase\W{0,3})(-?\d+(?:\.\d+)?)(\s*thru\s*)?(-?\d+(?:\.\d+)?)?", re.I)


def group_offsets(groups):
    """сдвиг фазы каждой группы: свой (phase_shift) или авто - группы с одинаковыми
    возможностями делят круг поровну по порядку списка: 2 → 0/180, 3 → 0/120/240"""
    kinds = {}
    for g in groups:
        kinds.setdefault(tuple(sorted(g.get("caps") or [])), []).append(g)
    out = {}
    for same in kinds.values():
        for i, g in enumerate(same):
            own = str(g.get("phase_shift", "")).strip()
            try:
                out[g["name"]] = float(own) if own else (360.0 * i / len(same) if len(same) > 1 else 0.0)
            except ValueError:
                out[g["name"]] = 0.0
    return out


def shift_phase(cmd, offset):
    """«phase 0 Thru 360» → «phase 180 Thru 540»; → (команда, сколько сдвинуто)"""
    hits = [0]

    def sub(m):
        hits[0] += 1
        a = fx.num(float(m.group(2)) + offset)
        if m.group(4) is None:
            return f"{m.group(1)}{a}"
        return f"{m.group(1)}{a}{m.group(3) or ' Thru '}{fx.num(float(m.group(4)) + offset)}"

    return PHASE_RE.sub(sub, cmd), hits[0]


EFFECT_NO_RE = re.compile(r"(\bEffect\s+(?:1\.)?)(\d+)", re.I)   # «Effect 1.N» и «At Effect N»


def phase_copies(cmds, report, groups, shift_no=500):
    """противофаза включается не всегда, поэтому эффект не переписывается, а
    рядом создаётся копия со сдвигом фазы (номер Effect + shift_no). Анализатор
    сам решает, какую из двух включить. Эффект = блок команд от ClearAll до
    следующего ClearAll. → (команды, копии [(номер копии, группа, имя, сдвиг, номер)], сводка)"""
    offsets = group_offsets(groups)
    if not any(v % 360 for v in offsets.values()):
        return cmds, [], "противофаза: групп с одинаковыми возможностями нет"
    # эффект = блок от своего «Delete Effect 1.N» до следующего Delete / последнего ClearAll
    # (раньше блок шёл от ClearAll и захватывал Delete следующего эффекта - копия его стирала)
    starts = [i for i, c in enumerate(cmds) if c.startswith("Delete Effect ")]
    tail = max((i for i, c in enumerate(cmds) if c == "ClearAll"), default=len(cmds))
    if len(starts) < len(report):
        return cmds, [], f"противофаза не создана: эффектов {len(report)}, блоков {len(starts)}"
    extra, copies, shifted = [], [], 0
    for k, (no, group, name) in enumerate(report):
        off = offsets.get(group, 0.0) % 360
        if not off:
            continue
        try:
            no = int(no)
        except (TypeError, ValueError):
            continue
        end = starts[k + 1] if k + 1 < len(starts) else tail
        block, hits = [], 0
        for c in cmds[starts[k]:end]:
            if "macro" in c.lower():
                continue
            c = EFFECT_NO_RE.sub(lambda m: m.group(1) + str(no + shift_no) if int(m.group(2)) == no else m.group(0), c)
            c, n = shift_phase(c, off)
            hits += n
            block.append(c)
        if hits:
            extra += block
            copies.append((no + shift_no, group, name, fx.num(off), no))
            shifted += hits
    if not copies:
        return cmds, [], "противофаза не создана: в командах не нашёл phase - пришли экспорт TXT"
    return list(cmds) + extra, copies, (f"противофаза: {len(copies)} копий со сдвигом фазы (Effect +{shift_no}): "
                                        + ", ".join(f"{n} {fx.num(v)}°" for n, v in offsets.items() if v % 360))


def draw_effect(c, lines, group, elapsed, speed):
    """Рисует эффект на canvas. lines — развёрнутые строки fx.resolved_lines."""
    c.delete("all")
    n = max(int(group.get("count", 6)), 1)
    W, H = max(c.winfo_width(), 200), max(c.winfo_height(), 150)
    dim = [1.0] * n
    rgb = [None] * n
    pan = [0.0] * n
    tilt = [0.0] * n
    has_pt = False
    for l in lines:
        lo, hi = fx.line_values(l, group)
        bpm = min(float(l["bpm"]), 300) * speed
        beats = elapsed * bpm / 60.0
        for i in range(n):
            ph = fixture_phase(i, n, l["phase"], l.get("wings"), l.get("groups"), l.get("blocks")) / 360.0
            t = (beats + ph) % 1.0
            f = form_value(l["form"], t, l["width"], seed=f'{l["attr"]}:{i}:{int(beats + ph)}')
            v = lo + (hi - lo) * f
            a = l["attr"]
            if a in ("dim", "shutter"):
                dim[i] = min(dim[i], max(0.0, min(1.0, v / 100.0))) if a == "shutter" else max(0.0, min(1.0, v / 100.0))
            elif a in ("r", "g", "b"):
                if rgb[i] is None:
                    rgb[i] = [0.0, 0.0, 0.0]
                rgb[i]["rgb".index(a)] = max(0.0, min(1.0, v / 100.0))
            elif a == "pan":
                pan[i], has_pt = v, True
            elif a == "tilt":
                tilt[i], has_pt = v, True

    cell = min((W - 40) / n, 110)
    x0 = (W - cell * n) / 2
    size = max(float(group.get("size", 20)), 1) * 2
    for i in range(n):
        cx = x0 + cell * i + cell / 2
        r = min(cell * 0.32, 40)
        if has_pt:
            half = cell * 0.38
            cy = H * 0.42 - r - 10
            c.create_rectangle(cx - half, cy - half, cx + half, cy + half, outline="#2a2e37")
            c.create_line(cx - half, cy, cx + half, cy, fill="#1d2027")
            c.create_line(cx, cy - half, cx, cy + half, fill="#1d2027")
            px = cx + max(-1, min(1, pan[i] / size)) * half * 0.95
            py = cy - max(-1, min(1, tilt[i] / size)) * half * 0.95
            c.create_oval(px - 6, py - 6, px + 6, py + 6, fill=ACCENT, outline="")
            ly = cy + half + r + 18
        else:
            ly = H * 0.45
        col = rgb[i] if rgb[i] is not None else [1.0, 0.92, 0.75]
        fill = "#%02x%02x%02x" % tuple(int(14 + (255 - 14) * ch * dim[i]) for ch in col)
        c.create_oval(cx - r - 6, ly - r - 6, cx + r + 6, ly + r + 6, outline="#2a2e37")
        c.create_oval(cx - r, ly - r, cx + r, ly + r, fill=fill, outline="")
        c.create_text(cx, ly + r + 16, text=str(i + 1), fill=MUTED, font=("Segoe UI", 9))


def lines_summary(lines):
    parts = []
    for l in lines:
        s = f'{l["attr"].upper()}:{l["form"]} {fx.num(l["bpm"])}bpm'
        for k in fx.LINE_EXTRAS:
            if k in l:
                s += f" {k[0]}{l[k]}"
        parts.append(s)
    return " · ".join(parts)


# =====================================================================
#  GUI
# =====================================================================
# =====================================================================
#  ПРОКРУТКА: содержимое больше окна - появляются ползунки
# =====================================================================
_SCROLL_AREAS = []
_SCROLL_SKIP = ("Text", "Listbox", "Treeview", "Canvas", "Spinbox", "TCombobox", "Scale", "TScale")


def _on_wheel(event):
    w = event.widget
    try:
        if isinstance(w, str):
            return
        target = None
        while w is not None:
            for canvas, inner in _SCROLL_AREAS:
                if w is canvas or w is inner:
                    target = canvas
                    break
            if target is not None:
                break
            if w.winfo_class() in _SCROLL_SKIP:
                return          # у виджета своя прокрутка (список, текст, рисунок)
            w = w.master
        if target is None:
            return
        num = getattr(event, "num", None)
        step = -1 if num == 4 else 1 if num == 5 else (-1 if event.delta > 0 else 1)
        if event.state & 0x1:
            target.xview_scroll(step * 3, "units")
        else:
            target.yview_scroll(step * 3, "units")
    except Exception:
        pass


def scroll_box(parent, bg=None):
    """холст с ползунками во весь parent → внутренний ttk.Frame для содержимого"""
    canvas = tk.Canvas(parent, highlightthickness=0, bd=0, bg=bg or BG)
    vs = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    hs = ttk.Scrollbar(parent, orient="horizontal", command=canvas.xview)
    canvas.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
    canvas.grid(row=0, column=0, sticky="nsew")
    parent.rowconfigure(0, weight=1)
    parent.columnconfigure(0, weight=1)
    inner = ttk.Frame(canvas)
    item = canvas.create_window(0, 0, window=inner, anchor="nw")
    _SCROLL_AREAS.append((canvas, inner))
    state = {"req": None, "size": None}
    maxw = max(400, canvas.winfo_screenwidth() - 60)
    maxh = max(300, canvas.winfo_screenheight() - 140)

    def fit(_e=None):
        try:
            bw, bh = inner.winfo_reqwidth(), inner.winfo_reqheight()
            if (bw, bh) != state["req"]:
                state["req"] = (bw, bh)
                canvas.configure(width=min(bw, maxw), height=min(bh, maxh))
            cw, ch = canvas.winfo_width(), canvas.winfo_height()
            if cw <= 1 or ch <= 1:
                return
            size = (max(bw, cw), max(bh, ch))
            if size != state["size"]:
                state["size"] = size
                canvas.itemconfigure(item, width=size[0], height=size[1])
                canvas.configure(scrollregion=(0, 0, size[0], size[1]))
            if bh > ch + 1:
                vs.grid(row=0, column=1, sticky="ns")
            else:
                vs.grid_remove()
                canvas.yview_moveto(0)
            if bw > cw + 1:
                hs.grid(row=1, column=0, sticky="ew")
            else:
                hs.grid_remove()
                canvas.xview_moveto(0)
        except tk.TclError:
            pass

    def poll():
        try:
            if not canvas.winfo_exists():
                return
        except tk.TclError:
            return
        fit()
        canvas.after(400, poll)

    canvas.bind("<Configure>", fit, add="+")
    top = parent.winfo_toplevel()
    if not getattr(top, "_wheel_bound", False):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            top.bind_all(seq, _on_wheel, add="+")
        top._wheel_bound = True
    canvas.after(30, poll)
    return inner


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LightDancer — генератор эффектов MA2")
        self.geometry("1180x760")
        self.minsize(560, 380)       # меньше содержимого - ползунки
        self.configure(bg=BG)
        self.cfg = make_config({"groups": copy.deepcopy(EXAMPLE_GROUPS)})
        self.cfg_path = None
        self.checked = {}          # key -> bool
        self.make_macros = tk.BooleanVar(value=True)
        self.antiphase = tk.BooleanVar(value=True)
        self.copy_shift = tk.StringVar(value="500")
        self.phase_copies = []
        self.q = queue.Queue()
        self.stop_flag = threading.Event()
        self.worker = None
        self.t0 = time.time()
        self.cur_custom = None     # индекс в cfg["custom"]
        self.ma = None             # постоянное Telnet-подключение к пульту
        self.layout = {}           # Layout: приборы X/Y/Z, сцена, пресеты позиций (хранится в настройках)
        self._conn_cb = (None, None)
        self.conn = {k: tk.StringVar(value=v) for k, v in
                     (("host", "10.0.0.12"), ("port", "30000"), ("user", "remote"),
                      ("password", "1234"), ("delay", "0.12"))}

        self._style()
        self._menu()
        self._build()
        self.load_prefs()
        self.refresh_all()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(40, self.animate)
        self.after(100, self.poll_queue)
        self.after(300, self.startup)

    # ---------------- стиль ----------------
    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG, fieldbackground=PANEL,
                    bordercolor="#2c313b", lightcolor=PANEL, darkcolor=PANEL, font=("Segoe UI", 10))
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(14, 6))
        s.map("TNotebook.Tab", background=[("selected", BG)], foreground=[("selected", ACCENT)])
        s.configure("TLabelframe", background=BG, bordercolor="#2c313b")
        s.configure("TLabelframe.Label", background=BG, foreground=ACCENT)
        s.configure("TButton", background=PANEL, foreground=FG, padding=(10, 3))
        s.map("TButton", background=[("active", "#2c313b"), ("disabled", BG)],
              foreground=[("disabled", "#555a64")])
        s.configure("Accent.TButton", background=ACCENT, foreground="#111")
        s.map("Accent.TButton", background=[("active", "#ffbf4d")])
        s.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, rowheight=22)
        s.configure("Treeview.Heading", background="#262a33", foreground=MUTED)
        s.map("Treeview", background=[("selected", "#3a3220")], foreground=[("selected", ACCENT)])
        s.configure("TCheckbutton", background=BG, foreground=FG, indicatorbackground=PANEL,
                    indicatorforeground=ACCENT)
        s.configure("TRadiobutton", background=BG, foreground=FG, indicatorbackground=PANEL,
                    indicatorforeground=ACCENT)
        s.configure("Small.TButton", padding=(6, 2))
        for w in ("TCheckbutton", "TRadiobutton"):
            s.map(w, background=[("disabled", BG), ("active", BG)],
                  foreground=[("disabled", "#555a64")],
                  indicatorbackground=[("disabled", BG)])
        s.configure("TLabel", background=BG, foreground=FG)
        s.configure("Muted.TLabel", foreground=MUTED)
        s.configure("Warn.TLabel", foreground=WARN)
        s.configure("TEntry", foreground=FG, insertcolor=FG)
        s.map("TEntry", fieldbackground=[("readonly", BG)])
        s.configure("TCombobox", foreground=FG, fieldbackground=PANEL, background=PANEL, arrowcolor=FG)
        s.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", FG)],
              selectbackground=[("readonly", PANEL)], selectforeground=[("readonly", ACCENT)])
        self.option_add("*TCombobox*Listbox.background", PANEL)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", "#3a3220")
        s.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=PANEL)
        s.configure("TPanedwindow", background=BG)

    def _menu(self):
        m = tk.Menu(self)
        f = tk.Menu(m, tearoff=0)
        f.add_command(label="Открыть конфиг…", command=self.open_cfg, accelerator="Ctrl+O")
        f.add_command(label="Сохранить", command=self.save_cfg, accelerator="Ctrl+S")
        f.add_command(label="Сохранить как…", command=lambda: self.save_cfg(True))
        f.add_separator()
        f.add_command(label="Импорт своих шаблонов…", command=self.import_custom)
        f.add_command(label="Экспорт своих шаблонов…", command=self.export_custom)
        f.add_separator()
        f.add_command(label="Перенос в Capture…", command=self.open_capture)
        f.add_separator()
        f.add_command(label="Выход", command=self.on_close)
        m.add_cascade(label="Файл", menu=f)
        mm = tk.Menu(m, tearoff=0)
        mm.add_command(label="Подключить…", command=self.open_connect_dialog)
        mm.add_command(label="Отключить", command=self.disconnect)
        mm.add_separator()
        mm.add_command(label="Импорт групп из шоу…", command=self.open_import)
        m.add_cascade(label="MA2", menu=mm)
        self.config(menu=m)
        self.bind("<Control-o>", lambda e: self.open_cfg())
        self.bind("<Control-s>", lambda e: self.save_cfg())

    def open_capture(self):
        """Окно «Перенос MA2 → Capture» (ma2_capture.py); с пульта - Export в XML, если onPC здесь."""
        try:
            import ma2_capture
        except ImportError:
            messagebox.showerror("Capture", "Нет файла ma2_capture.py в папке программы.\nПереустановите LightDancer.")
            return

        def fetch():
            ma = self.ma
            if not ma:
                raise RuntimeError("Нет связи с пультом: MA2 → Подключить…\n\nИли откройте XML вручную.")
            if not is_local_host(getattr(ma, "host", "")):
                raise RuntimeError("Пульт не на этом компьютере: его файлы Export отсюда не прочитать.\n\n"
                                   "Сделайте Export Layer (Only XML) на USB и откройте XML вручную.")
            t0, paths = time.time(), []
            for what, fname in (("Fixture 1 Thru 99999", "ma2cap_fixtures"), ("Group 1 Thru 9999", "ma2cap_groups")):
                ma.query(f'Export {what} "{fname}" /o', settle=0.6, max_wait=10.0)
                path, t1 = None, time.time()
                while not path and time.time() - t1 < 8.0:
                    path = find_export(fname + ".xml", t0)
                    time.sleep(0.3)
                if path:
                    time.sleep(0.3)
                    paths.append(path)
            if not paths:
                raise RuntimeError("Пульт не выгрузил XML. Сделайте Export Layer (Only XML) и откройте файл вручную.")
            return paths

        ma2_capture.open_window(self, fetch)

    def _build(self):
        self._build_conn_bar()
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.tabs, self.tab_frames = {}, {}
        for key, name in [("groups", "Группы"), ("lay", "Layout"), ("tpl", "Шаблоны"), ("cmp", "Компоновщик"),
                          ("set", "Настройки"), ("cmd", "Команды"), ("send", "Пульт")]:
            fr = ttk.Frame(self.nb)
            self.nb.add(fr, text=name)
            self.tab_frames[key] = fr
            self.tabs[key] = scroll_box(fr)      # содержимое вкладки - с ползунками
        self._build_groups()
        self.layout_ui = LayoutTab(self, self.tabs["lay"])
        self._build_templates()
        self._build_composer()
        self._build_settings()
        self._build_commands()
        self._build_send()
        self.nb.bind("<<NotebookTabChanged>>", self.on_tab)
        self.status = ttk.Label(self, text="", style="Muted.TLabel")
        self.status.pack(fill="x", padx=10, pady=(0, 6))

    def tab_is(self, key):
        return self.nb.select() == str(self.tab_frames[key])

    def lib(self):
        return fx.library(self.cfg)

    def refresh_all(self):
        self.refresh_groups()
        self.refresh_tpl_tree()
        self.refresh_custom_list()
        self.update_status()

    # =================================================================
    #  ГРУППЫ
    # =================================================================
    def _build_groups(self):
        tab = self.tabs["groups"]
        cols = ("id", "name", "count", "caps", "size", "shut", "phase", "tpl")
        heads = ("ID", "Имя", "Приборов", "Возможности", "Ампл. P/T°", "Shutter lo–hi", "Фаза°", "Шаблоны")
        self.gtree = ttk.Treeview(tab, columns=cols, show="headings", selectmode="browse")
        for c, h, w in zip(cols, heads, (50, 180, 80, 260, 90, 110, 70, 240)):
            self.gtree.heading(c, text=h)
            self.gtree.column(c, width=w, anchor="w")
        self.gtree.pack(fill="both", expand=True, padx=10, pady=10)
        self.gtree.bind("<Double-1>", lambda e: self.edit_group())
        bar = ttk.Frame(tab)
        bar.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(bar, text="+ Добавить", command=self.add_group).pack(side="left")
        ttk.Button(bar, text="Изменить", command=self.edit_group).pack(side="left", padx=6)
        ttk.Button(bar, text="Удалить", command=self.del_group).pack(side="left")
        ttk.Button(bar, text="▲", width=3, command=lambda: self.move_group(-1)).pack(side="left", padx=(16, 2))
        ttk.Button(bar, text="▼", width=3, command=lambda: self.move_group(1)).pack(side="left")
        ttk.Button(bar, text="⇩ Патч с пульта", style="Accent.TButton",
                   command=self.pull_patch).pack(side="left", padx=(16, 0))
        ttk.Button(bar, text="🩺 Диагностика патча", command=self.diag_patch).pack(side="left", padx=(6, 0))
        ttk.Label(bar, text="Порядок строк задаёт блоки номеров в пуле Effects",
                  style="Muted.TLabel").pack(side="right")

    def refresh_groups(self):
        self.gtree.delete(*self.gtree.get_children())
        offsets = group_offsets(self.cfg["groups"])
        for i, g in enumerate(self.cfg["groups"]):
            tpl = ", ".join(g["templates"]) if g.get("templates") else "все подходящие"
            ph = fx.num(offsets.get(g["name"], 0)) if self.antiphase.get() else "-"
            if self.antiphase.get() and str(g.get("phase_shift", "")).strip() == "":
                ph = f"{ph} авто"
            self.gtree.insert("", "end", iid=str(i), values=(
                g["id"], g["name"], g.get("count", ""), " ".join(g["caps"]),
                g["size"], f'{g["shut_lo"]}–{g["shut_hi"]}', ph, tpl))
        names = [f'{g["id"]}  {g["name"]}' for g in self.cfg["groups"]]
        if getattr(self, "layout_ui", None) is not None:
            self.layout_ui.refresh()
        for cb in (getattr(self, "pv_group", None), getattr(self, "cp_group", None)):
            if cb is not None:
                cb["values"] = names
                if names and cb.get() not in names:
                    cb.current(0)
        self.update_status()

    def sel_group(self):
        s = self.gtree.selection()
        return int(s[0]) if s else None

    def add_group(self):
        nid = max([g["id"] for g in self.cfg["groups"]] or [0]) + 1
        g = {"id": nid, "name": f"Group {nid}", "caps": ["dim"], "size": 20,
             "shut_lo": 0, "shut_hi": 100, "count": 6, "templates": None}
        if GroupDialog(self, g, self.lib()).ok:
            self.cfg["groups"].append(g)
            self.refresh_groups()

    def edit_group(self):
        i = self.sel_group()
        if i is None:
            return
        g = copy.deepcopy(self.cfg["groups"][i])
        if GroupDialog(self, g, self.lib()).ok:
            self.cfg["groups"][i] = g
            self.refresh_groups()

    def del_group(self):
        i = self.sel_group()
        if i is not None and messagebox.askyesno("Удалить", f'Удалить группу {self.cfg["groups"][i]["name"]}?'):
            del self.cfg["groups"][i]
            self.refresh_groups()

    def move_group(self, d):
        i = self.sel_group()
        if i is None:
            return
        j, gs = i + d, self.cfg["groups"]
        if 0 <= j < len(gs):
            gs[i], gs[j] = gs[j], gs[i]
            self.refresh_groups()
            self.gtree.selection_set(str(j))

    def group_by_label(self, label):
        for g in self.cfg["groups"]:
            if label.startswith(f'{g["id"]} '):
                return g
        return self.cfg["groups"][0] if self.cfg["groups"] else None

    # =================================================================
    #  ШАБЛОНЫ
    # =================================================================
    def _build_templates(self):
        tab = self.tabs["tpl"]
        pw = ttk.Panedwindow(tab, orient="horizontal")
        pw.pack(fill="both", expand=True, padx=10, pady=10)

        left = ttk.Frame(pw)
        pw.add(left, weight=2)
        self.ttree = ttk.Treeview(left, columns=("on", "bpm", "needs"), selectmode="extended")
        self.ttree.heading("#0", text="Шаблон")
        self.ttree.heading("on", text="Вкл")
        self.ttree.heading("bpm", text="BPM")
        self.ttree.heading("needs", text="Нужно")
        self.ttree.column("#0", width=200)
        self.ttree.column("on", width=40, anchor="center")
        self.ttree.column("bpm", width=50, anchor="center")
        self.ttree.column("needs", width=90)
        sb = ttk.Scrollbar(left, orient="vertical", command=self.ttree.yview)
        self.ttree.configure(yscrollcommand=sb.set)
        self.ttree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.ttree.tag_configure("cat", foreground=ACCENT)
        self.ttree.tag_configure("off", foreground="#6b707a")
        self.ttree.tag_configure("custom", foreground="#9ad1ff")
        self.ttree.bind("<Button-1>", self.on_tpl_click)
        self.ttree.bind("<space>", lambda e: self.toggle_selected())
        self.ttree.bind("<<TreeviewSelect>>", self.on_tpl_select)
        self.ttree.bind("<Double-1>", lambda e: self.compose_selected())
        bar = ttk.Frame(left)
        bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(bar, text="Все", command=lambda: self.set_all_tpl(True)).pack(side="left")
        ttk.Button(bar, text="Ничего", command=lambda: self.set_all_tpl(False)).pack(side="left", padx=4)
        ttk.Button(bar, text="Скомпоновать выбранные →", style="Accent.TButton",
                   command=self.compose_selected).pack(side="right")
        ttk.Label(left, text="Клик по «Вкл» или Пробел — включить/выключить. Ctrl/Shift — выбрать "
                             "несколько и скомпоновать. Двойной клик — открыть в компоновщике.",
                  style="Muted.TLabel", wraplength=380).grid(row=2, column=0, columnspan=2, sticky="w", pady=4)

        right = ttk.Labelframe(pw, text="Превью (приблизительная модель)")
        pw.add(right, weight=3)
        top = ttk.Frame(right)
        top.pack(fill="x", padx=8, pady=6)
        ttk.Label(top, text="Группа").pack(side="left")
        self.pv_group = ttk.Combobox(top, state="readonly", width=20)
        self.pv_group.pack(side="left", padx=6)
        ttk.Label(top, text="Скорость").pack(side="left", padx=(12, 0))
        self.pv_speed = tk.DoubleVar(value=1.0)
        ttk.Scale(top, from_=0.1, to=2.0, variable=self.pv_speed, length=120).pack(side="left", padx=6)
        self.pv_canvas = tk.Canvas(right, bg="#0c0d10", highlightthickness=0)
        self.pv_canvas.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        self.pv_info = ttk.Label(right, text="", style="Muted.TLabel", wraplength=600)
        self.pv_info.pack(fill="x", padx=8, pady=(0, 8))
        self.pv_key = fx.TEMPLATES[0]["key"]

    def tpl_category(self, key, t):
        if key not in fx.BUILTIN_KEYS:
            return "custom"
        return t.get("cat", "combo")

    def refresh_tpl_tree(self):
        lib = self.lib()
        for k in lib:
            self.checked.setdefault(k, True)
        for k in list(self.checked):
            if k not in lib:
                del self.checked[k]
        open_state = {c: self.ttree.item(c, "open") for c in self.ttree.get_children()}
        sel = self.ttree.selection()
        self.ttree.delete(*self.ttree.get_children())
        by_cat = {c: [] for c in CAT_TITLES}
        for k in fx.ordered_keys(lib):
            by_cat[self.tpl_category(k, lib[k])].append(k)
        for cat, keys in by_cat.items():
            if not keys:
                continue
            n_on = sum(self.checked[k] for k in keys)
            cid = f"cat:{cat}"
            self.ttree.insert("", "end", iid=cid, text=f"{CAT_TITLES[cat]}  ({n_on}/{len(keys)})",
                              values=(ON if n_on == len(keys) else (OFF if n_on == 0 else "◩"), "", ""),
                              open=open_state.get(cid, True), tags=("cat",))
            for k in keys:
                t = lib[k]
                try:
                    bpm = ", ".join(sorted({str(fx.num(l["bpm"])) for l in fx.resolved_lines(t, lib)[0]}))
                except ValueError:
                    bpm = "!"
                tags = [] if self.checked[k] else ["off"]
                if cat == "custom":
                    tags.append("custom")
                self.ttree.insert(cid, "end", iid=k, text=t["name"],
                                  values=(ON if self.checked[k] else OFF, bpm,
                                          " ".join(sorted(fx.needs(t, lib)))), tags=tags)
        keep = [s for s in sel if self.ttree.exists(s)]
        if keep:
            self.ttree.selection_set(keep)
        self.update_status()

    def on_tpl_click(self, e):
        row = self.ttree.identify_row(e.y)
        if row and self.ttree.identify_column(e.x) == "#1":
            self.toggle(row)
            return "break"

    def toggle(self, row):
        if row.startswith("cat:"):
            kids = self.ttree.get_children(row)
            v = not all(self.checked[k] for k in kids)
            for k in kids:
                self.checked[k] = v
        else:
            self.checked[row] = not self.checked[row]
        self.refresh_tpl_tree()

    def toggle_selected(self):
        sel = [s for s in self.ttree.selection() if not s.startswith("cat:")]
        if sel:
            v = not all(self.checked[k] for k in sel)
            for k in sel:
                self.checked[k] = v
            self.refresh_tpl_tree()

    def set_all_tpl(self, v):
        for k in self.checked:
            self.checked[k] = v
        self.refresh_tpl_tree()

    def on_tpl_select(self, _e=None):
        sel = [s for s in self.ttree.selection() if not s.startswith("cat:")]
        if sel:
            self.pv_key = sel[-1]
            self.t0 = time.time()

    def compose_selected(self):
        keys = [s for s in self.ttree.selection() if not s.startswith("cat:")]
        if not keys:
            messagebox.showinfo("Компоновка", "Выбери один или несколько шаблонов (Ctrl+клик).")
            return
        lib = self.lib()
        if len(keys) == 1 and keys[0] not in fx.BUILTIN_KEYS:
            idx = next(i for i, c in enumerate(self.cfg["custom"]) if c["key"] == keys[0])
        else:
            names = [lib[k]["name"].split(" ", 1)[-1] for k in keys]
            new = {"key": self.new_custom_key(), "name": ("MY " + " + ".join(names))[:32],
                   "cat": "combo", "bpm": 60, "layers": [{"tpl": k} for k in keys]}
            self.cfg["custom"].append(new)
            idx = len(self.cfg["custom"]) - 1
            self.checked[new["key"]] = True
            self.refresh_tpl_tree()
        self.refresh_custom_list()
        self.select_custom(idx)
        self.nb.select(self.tab_frames["cmp"])

    # =================================================================
    #  КОМПОНОВЩИК
    # =================================================================
    def _build_composer(self):
        tab = self.tabs["cmp"]
        pw = ttk.Panedwindow(tab, orient="horizontal")
        pw.pack(fill="both", expand=True, padx=10, pady=10)

        # --- список своих шаблонов
        left = ttk.Labelframe(pw, text="Свои шаблоны")
        pw.add(left, weight=1)
        self.ctree = ttk.Treeview(left, columns=("n",), show="headings", selectmode="browse", height=12)
        self.ctree.heading("n", text="Имя")
        self.ctree.column("n", width=170)
        self.ctree.pack(fill="both", expand=True, padx=6, pady=6)
        self.ctree.bind("<<TreeviewSelect>>", self.on_custom_select)
        b = ttk.Frame(left)
        b.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(b, text="Новый", style="Small.TButton", command=self.new_custom).pack(side="left")
        ttk.Button(b, text="Копия", style="Small.TButton", command=self.dup_custom).pack(side="left", padx=4)
        ttk.Button(b, text="Удалить", style="Small.TButton", command=self.del_custom).pack(side="left")

        # --- редактор
        right = ttk.Frame(pw)
        pw.add(right, weight=4)
        head = ttk.Frame(right)
        head.pack(fill="x")
        self.cp_name = tk.StringVar()
        self.cp_cat = tk.StringVar()
        self.cp_bpm = tk.StringVar()
        ttk.Label(head, text="Имя").pack(side="left")
        self.cp_name_e = ttk.Entry(head, textvariable=self.cp_name, width=26)
        self.cp_name_e.pack(side="left", padx=(4, 12))
        ttk.Label(head, text="Категория").pack(side="left")
        ttk.Combobox(head, textvariable=self.cp_cat, state="readonly", width=10,
                     values=fx.CATEGORIES).pack(side="left", padx=(4, 12))
        ttk.Label(head, text="BPM строк").pack(side="left")
        ttk.Entry(head, textvariable=self.cp_bpm, width=6).pack(side="left", padx=4)
        self.cp_key = ttk.Label(right, text="", style="Muted.TLabel")
        self.cp_key.pack(fill="x", pady=(2, 0))
        for v in (self.cp_name, self.cp_cat, self.cp_bpm):
            v.trace_add("write", lambda *_: self.on_custom_meta())

        lf = ttk.Labelframe(right, text="Слои (сверху вниз; при совпадении атрибута побеждает нижний)")
        lf.pack(fill="x", pady=(8, 0))
        cols = ("src", "attrs", "bpm", "speed", "phase", "width", "lo", "hi", "scale", "inv", "wgb")
        heads = ("Источник", "Атрибуты", "BPM", "×Скор", "Phase", "Width", "Low", "High", "Ампл%", "Инв", "W/G/B")
        widths = (160, 70, 45, 50, 90, 50, 55, 55, 52, 35, 60)
        self.ltree = ttk.Treeview(lf, columns=cols, show="headings", selectmode="browse", height=6)
        for c, h, w in zip(cols, heads, widths):
            self.ltree.heading(c, text=h)
            self.ltree.column(c, width=w, anchor="w", stretch=c in ("src", "phase"))
        self.ltree.pack(fill="x", padx=6, pady=6)
        self.ltree.bind("<Double-1>", lambda e: self.edit_layer())
        lb = ttk.Frame(lf)
        lb.pack(fill="x", padx=6, pady=(0, 6))
        self.add_tpl_cb = ttk.Combobox(lb, state="readonly", width=18)
        self.add_tpl_cb.pack(side="left")
        ttk.Button(lb, style="Small.TButton", text="+ Шаблон", command=self.add_layer_tpl).pack(side="left", padx=4)
        ttk.Button(lb, style="Small.TButton", text="+ Строка", command=self.add_layer_line).pack(side="left")
        ttk.Button(lb, style="Small.TButton", text="▼", width=3, command=lambda: self.move_layer(1)).pack(side="right")
        ttk.Button(lb, style="Small.TButton", text="▲", width=3, command=lambda: self.move_layer(-1)).pack(side="right", padx=2)
        ttk.Button(lb, style="Small.TButton", text="Удалить", command=self.del_layer).pack(side="right", padx=(4, 8))
        ttk.Button(lb, style="Small.TButton", text="Изменить", command=self.edit_layer).pack(side="right")

        pv = ttk.Labelframe(right, text="Превью")
        pv.pack(fill="both", expand=True, pady=(8, 0))
        top = ttk.Frame(pv)
        top.pack(fill="x", padx=8, pady=4)
        ttk.Label(top, text="Группа").pack(side="left")
        self.cp_group = ttk.Combobox(top, state="readonly", width=20)
        self.cp_group.pack(side="left", padx=6)
        ttk.Label(top, text="Скорость").pack(side="left", padx=(12, 0))
        self.cp_speed = tk.DoubleVar(value=1.0)
        ttk.Scale(top, from_=0.1, to=2.0, variable=self.cp_speed, length=120).pack(side="left", padx=6)
        self.cp_canvas = tk.Canvas(pv, bg="#0c0d10", highlightthickness=0, height=200)
        self.cp_canvas.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self.cp_info = ttk.Label(pv, text="", style="Muted.TLabel", wraplength=760)
        self.cp_info.pack(fill="x", padx=8)
        self.cp_warn = ttk.Label(pv, text="", style="Warn.TLabel", wraplength=760)
        self.cp_warn.pack(fill="x", padx=8, pady=(0, 6))
        self.set_editor_state(False)

    def new_custom_key(self):
        lib, i = self.lib(), 1
        while f"custom_{i}" in lib:
            i += 1
        return f"custom_{i}"

    def refresh_custom_list(self):
        self.ctree.delete(*self.ctree.get_children())
        for i, c in enumerate(self.cfg["custom"]):
            self.ctree.insert("", "end", iid=str(i), values=(c["name"],))
        lib = self.lib()
        cur = self.cur_custom_obj()
        self.add_tpl_cb["values"] = [k for k in fx.ordered_keys(lib) if not cur or k != cur["key"]]
        if self.add_tpl_cb.get() not in self.add_tpl_cb["values"] and self.add_tpl_cb["values"]:
            self.add_tpl_cb.current(0)
        if self.cur_custom is not None and self.cur_custom < len(self.cfg["custom"]):
            self.ctree.selection_set(str(self.cur_custom))
        else:
            self.cur_custom = None
            self.set_editor_state(False)

    def cur_custom_obj(self):
        if self.cur_custom is None or self.cur_custom >= len(self.cfg["custom"]):
            return None
        return self.cfg["custom"][self.cur_custom]

    def select_custom(self, idx):
        self.cur_custom = idx
        self.refresh_custom_list()
        self.load_custom_to_editor()

    def on_custom_select(self, _e=None):
        s = self.ctree.selection()
        if s and int(s[0]) != self.cur_custom:
            self.cur_custom = int(s[0])
            self.load_custom_to_editor()
            self.refresh_custom_list()

    def set_editor_state(self, on):
        self._loading = True
        if not on:
            self.cp_name.set("")
            self.cp_cat.set("")
            self.cp_bpm.set("")
            self.cp_key.config(text="← выбери или создай свой шаблон")
            self.ltree.delete(*self.ltree.get_children())
            self.cp_canvas.delete("all")
            self.cp_info.config(text="")
            self.cp_warn.config(text="")
        self._loading = False

    def load_custom_to_editor(self):
        c = self.cur_custom_obj()
        if not c:
            self.set_editor_state(False)
            return
        self._loading = True
        self.cp_name.set(c["name"])
        self.cp_cat.set(c.get("cat", "combo"))
        self.cp_bpm.set(str(c.get("bpm", 60)))
        self.cp_key.config(text=f'ключ: {c["key"]}')
        self._loading = False
        self.refresh_layers()
        self.t0 = time.time()

    def on_custom_meta(self):
        if getattr(self, "_loading", False):
            return
        c = self.cur_custom_obj()
        if not c:
            return
        c["name"] = self.cp_name.get()[:32] or c["key"]
        c["cat"] = self.cp_cat.get() or "combo"
        try:
            c["bpm"] = fx.num(float(self.cp_bpm.get()))
        except ValueError:
            pass
        if self.ctree.exists(str(self.cur_custom)):
            self.ctree.item(str(self.cur_custom), values=(c["name"],))
        self.refresh_tpl_tree()

    def refresh_layers(self):
        c = self.cur_custom_obj()
        self.ltree.delete(*self.ltree.get_children())
        if not c:
            return
        lib = self.lib()
        for i, L in enumerate(c.get("layers", [])):
            if L.get("tpl"):
                src = lib[L["tpl"]]["name"] if L["tpl"] in lib else f'?? {L["tpl"]}'
            else:
                ln = L["line"]
                src = f'строка {ln[0].upper()} {ln[1]} {ln[2]}..{ln[3]}'
            wgb = "/".join(show(L.get(k)) or "·" for k in ("wings", "groups", "blocks"))
            self.ltree.insert("", "end", iid=str(i), values=(
                src, " ".join(L.get("attrs") or []) or "все", show(L.get("bpm")), show(L.get("speed")),
                show(L.get("phase")), show(L.get("width")), show(L.get("lo")), show(L.get("hi")),
                show(L.get("scale")), "✓" if L.get("invert") else "", wgb))
        self.refresh_tpl_tree()

    def sel_layer(self):
        s = self.ltree.selection()
        return int(s[0]) if s else None

    def new_custom(self):
        c = {"key": self.new_custom_key(), "name": "MY New Effect", "cat": "combo", "bpm": 60, "layers": []}
        self.cfg["custom"].append(c)
        self.checked[c["key"]] = True
        self.select_custom(len(self.cfg["custom"]) - 1)
        self.refresh_tpl_tree()
        self.cp_name_e.focus_set()

    def dup_custom(self):
        c = self.cur_custom_obj()
        if not c:
            return
        n = copy.deepcopy(c)
        n["key"] = self.new_custom_key()
        n["name"] = (c["name"] + " copy")[:32]
        self.cfg["custom"].append(n)
        self.checked[n["key"]] = True
        self.select_custom(len(self.cfg["custom"]) - 1)
        self.refresh_tpl_tree()

    def del_custom(self):
        c = self.cur_custom_obj()
        if not c:
            return
        refs = [o["name"] for o in self.cfg["custom"]
                if o is not c and any(L.get("tpl") == c["key"] for L in o.get("layers", []))]
        refs += [f'группа {g["id"]}' for g in self.cfg["groups"] if c["key"] in (g.get("templates") or [])]
        if refs:
            messagebox.showwarning("Удалить", f'«{c["name"]}» используется: ' + ", ".join(refs) +
                                   "\nСначала убери ссылки.")
            return
        if messagebox.askyesno("Удалить", f'Удалить «{c["name"]}»?'):
            del self.cfg["custom"][self.cur_custom]
            self.cur_custom = None
            self.refresh_custom_list()
            self.refresh_tpl_tree()

    def add_layer_tpl(self):
        c = self.cur_custom_obj()
        k = self.add_tpl_cb.get()
        if not c or not k:
            return
        c.setdefault("layers", []).append({"tpl": k})
        if not self.valid_custom(c):
            c["layers"].pop()
            return
        self.refresh_layers()
        self.ltree.selection_set(str(len(c["layers"]) - 1))

    def add_layer_line(self):
        c = self.cur_custom_obj()
        if not c:
            return
        L = {"line": ["dim", "sin", 0, 100, "0 Thru 360", 100]}
        if LayerDialog(self, L, self.lib(), c["key"], self.cfg).ok:
            c.setdefault("layers", []).append(L)
            self.refresh_layers()

    def edit_layer(self):
        c, i = self.cur_custom_obj(), self.sel_layer()
        if not c or i is None:
            return
        L = copy.deepcopy(c["layers"][i])
        if LayerDialog(self, L, self.lib(), c["key"], self.cfg).ok:
            old = c["layers"][i]
            c["layers"][i] = L
            if not self.valid_custom(c):
                c["layers"][i] = old
                return
            self.refresh_layers()
            self.ltree.selection_set(str(i))

    def del_layer(self):
        c, i = self.cur_custom_obj(), self.sel_layer()
        if c and i is not None:
            del c["layers"][i]
            self.refresh_layers()

    def move_layer(self, d):
        c, i = self.cur_custom_obj(), self.sel_layer()
        if not c or i is None:
            return
        j, Ls = i + d, c["layers"]
        if 0 <= j < len(Ls):
            Ls[i], Ls[j] = Ls[j], Ls[i]
            self.refresh_layers()
            self.ltree.selection_set(str(j))

    def valid_custom(self, c):
        try:
            fx.expand(c, self.lib())
            return True
        except ValueError as e:
            messagebox.showerror("Компоновщик", str(e))
            return False

    # =================================================================
    #  АНИМАЦИЯ
    # =================================================================
    def animate(self):
        try:
            if self.tab_is("tpl"):
                self.draw_tpl_preview()
            elif self.tab_is("cmp"):
                self.draw_cmp_preview()
        except Exception as e:  # превью не должно ронять приложение
            (self.pv_info if self.tab_is("tpl") else self.cp_info).config(text=f"превью: {e}")
        self.after(40, self.animate)

    def draw_tpl_preview(self):
        lib = self.lib()
        t = lib.get(self.pv_key)
        g = self.group_by_label(self.pv_group.get())
        if not t or not g:
            return
        lines, warns = fx.resolved_lines(t, lib)
        draw_effect(self.pv_canvas, lines, g, time.time() - self.t0, self.pv_speed.get())
        miss = fx.needs(t, lib) - set(g["caps"])
        txt = f'{t["name"]}  ·  {lines_summary(lines)}'
        if miss:
            txt += f'   ⚠ группе {g["name"]} не хватает: {", ".join(sorted(miss))} — эффект не создастся'
        self.pv_info.config(text=txt)

    def draw_cmp_preview(self):
        c = self.cur_custom_obj()
        g = self.group_by_label(self.cp_group.get())
        if not c or not g:
            return
        lib = self.lib()
        lines, warns = fx.resolved_lines(c, lib)
        if not lines:
            self.cp_canvas.delete("all")
            self.cp_info.config(text="Добавь слои: шаблон из списка или свою строку.")
            self.cp_warn.config(text="")
            return
        draw_effect(self.cp_canvas, lines, g, time.time() - self.t0, self.cp_speed.get())
        self.cp_info.config(text=f'{len(lines)} строк эффекта · нужно: '
                                 f'{", ".join(sorted(fx.needs(c, lib)))}  ·  {lines_summary(lines)}')
        miss = fx.needs(c, lib) - set(g["caps"])
        w = list(warns)
        if miss:
            w.append(f'группе {g["name"]} не хватает: {", ".join(sorted(miss))} — для неё эффект не создастся')
        self.cp_warn.config(text=("⚠ " + "\n⚠ ".join(w)) if w else "")

    # =================================================================
    #  НАСТРОЙКИ
    # =================================================================
    def _build_settings(self):
        fr = ttk.Frame(self.tabs["set"])
        fr.pack(fill="both", expand=True, padx=14, pady=12)
        num = ttk.Labelframe(fr, text="Нумерация")
        num.grid(row=0, column=0, sticky="nw", padx=(0, 14))
        self.set_vars = {}
        for r, (k, label) in enumerate([("effect_start", "Первый Effect"),
                                        ("effect_stride", "Шаг на группу"),
                                        ("macro_start", "Первый Macro")]):
            ttk.Label(num, text=label).grid(row=r, column=0, sticky="w", padx=8, pady=4)
            v = tk.StringVar(value=str(self.cfg[k]))
            ttk.Entry(num, textvariable=v, width=8).grid(row=r, column=1, padx=8)
            self.set_vars[k] = v
        ttk.Label(num, text="Пресеты BPM").grid(row=3, column=0, sticky="w", padx=8, pady=4)
        self.bpm_var = tk.StringVar(value=", ".join(map(str, self.cfg["speed_presets"])))
        ttk.Entry(num, textvariable=self.bpm_var, width=24).grid(row=3, column=1, padx=8)
        ttk.Checkbutton(num, text="Создавать макросы скорости",
                        variable=self.make_macros).grid(row=4, column=0, columnspan=2, sticky="w", padx=8, pady=6)
        ttk.Checkbutton(num, text="Противофаза группа к группе (копии эффектов)",
                        variable=self.antiphase,
                        command=self.save_prefs_later).grid(row=5, column=0, columnspan=2, sticky="w", padx=8)
        ttk.Label(num, text="Номер копии = Effect +").grid(row=6, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(num, textvariable=self.copy_shift, width=8).grid(row=6, column=1, sticky="w", padx=8)
        ttk.Label(num, text="группы с одинаковыми возможностями делят круг:\n2 → 0/180°, 3 → 0/120/240° "
                            "(свой сдвиг - в группе).\nАнализатор включает копию на бег и поток,\n"
                            "на пульс и искры - обычный эффект", style="Muted.TLabel").grid(
            row=7, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 6))

        sg = ttk.Labelframe(fr, text="Speed-группы (SpecialMaster 3.x)")
        sg.grid(row=1, column=0, sticky="nw", pady=12)
        self.sg_vars = {}
        for r, cat in enumerate(["dimmer", "position", "color", "strobe"]):
            ttk.Label(sg, text=CAT_TITLES[cat]).grid(row=r, column=0, sticky="w", padx=8, pady=3)
            v = tk.StringVar(value=str(self.cfg["speed_groups"].get(cat, "")))
            ttk.Entry(sg, textvariable=v, width=6).grid(row=r, column=1, padx=8)
            self.sg_vars[cat] = v
        ttk.Label(sg, text="В комбо каждая строка идёт\nв speed-группу своей категории",
                  style="Muted.TLabel").grid(row=4, column=0, columnspan=2, sticky="w", padx=8, pady=4)

        forms = ttk.Labelframe(fr, text="Номера форм (пул Forms на пульте)")
        forms.grid(row=0, column=1, rowspan=2, sticky="nw", padx=(0, 14))
        self.form_vars = {}
        for r, (k, v) in enumerate(self.cfg["forms"].items()):
            ttk.Label(forms, text=k).grid(row=r, column=0, sticky="w", padx=8, pady=2)
            var = tk.StringVar(value=str(v))
            ttk.Entry(forms, textvariable=var, width=6).grid(row=r, column=1, padx=8)
            self.form_vars[k] = var

        attrs = ttk.Labelframe(fr, text="Имена атрибутов")
        attrs.grid(row=0, column=2, rowspan=2, sticky="nw")
        self.attr_vars = {}
        for r, (k, v) in enumerate(self.cfg["attrs"].items()):
            ttk.Label(attrs, text=k).grid(row=r, column=0, sticky="w", padx=8, pady=2)
            var = tk.StringVar(value=v)
            ttk.Entry(attrs, textvariable=var, width=14).grid(row=r, column=1, padx=8)
            self.attr_vars[k] = var

        mv = ttk.Labelframe(fr, text="Движение")
        mv.grid(row=2, column=1, columnspan=2, sticky="nw", pady=12)
        self.move_dim_var = tk.BooleanVar(value=bool(self.cfg.get("move_dim", True)))
        ttk.Checkbutton(mv, text="Диммер в движениях (та же волна, что и движение)",
                        variable=self.move_dim_var).grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        ttk.Label(mv, text="диммер от, %").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        self.move_dim_lo_var = tk.StringVar(value=str(self.cfg.get("move_dim_lo", 40)))
        ttk.Entry(mv, textvariable=self.move_dim_lo_var, width=6).grid(row=1, column=1, sticky="w", padx=8)
        ttk.Label(mv, text="до 100%. Чтобы попало на пульт - отправить эффекты заново",
                  style="Muted.TLabel").grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 6))

        ttk.Button(fr, text="Применить", style="Accent.TButton",
                   command=self.apply_settings).grid(row=2, column=0, sticky="w", pady=10)

    def apply_settings(self, quiet=False):
        try:
            for k, v in self.set_vars.items():
                self.cfg[k] = int(v.get())
            self.cfg["speed_presets"] = [int(x) for x in self.bpm_var.get().replace(";", ",").split(",") if x.strip()]
            self.cfg["speed_groups"] = {k: int(v.get()) for k, v in self.sg_vars.items() if v.get().strip()}
            self.cfg["forms"] = {k: int(v.get()) for k, v in self.form_vars.items()}
            self.cfg["attrs"] = {k: v.get().strip() for k, v in self.attr_vars.items()}
            self.cfg["move_dim"] = bool(self.move_dim_var.get())
            self.cfg["move_dim_lo"] = max(0, min(100, int(float(self.move_dim_lo_var.get().replace(",", ".")))))
        except ValueError as e:
            messagebox.showerror("Настройки", f"Неверное число: {e}")
            return False
        if not quiet:
            self.update_status("Настройки применены")
        return True

    def load_settings_to_ui(self):
        for k, v in self.set_vars.items():
            v.set(str(self.cfg[k]))
        self.bpm_var.set(", ".join(map(str, self.cfg["speed_presets"])))
        for k, v in self.sg_vars.items():
            v.set(str(self.cfg["speed_groups"].get(k, "")))
        for k, v in self.form_vars.items():
            v.set(str(self.cfg["forms"].get(k, "")))
        for k, v in self.attr_vars.items():
            v.set(self.cfg["attrs"].get(k, ""))
        self.move_dim_var.set(bool(self.cfg.get("move_dim", True)))
        self.move_dim_lo_var.set(str(self.cfg.get("move_dim_lo", 40)))

    # =================================================================
    #  КОМАНДЫ
    # =================================================================
    def _build_commands(self):
        tab = self.tabs["cmd"]
        bar = ttk.Frame(tab)
        bar.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Button(bar, text="Обновить", command=self.render_commands).pack(side="left")
        ttk.Button(bar, text="Экспорт .txt…", command=self.export_txt).pack(side="left", padx=6)
        self.cmd_info = ttk.Label(bar, text="", style="Muted.TLabel")
        self.cmd_info.pack(side="right")
        self.cmd_warn = ttk.Label(tab, text="", style="Warn.TLabel", wraplength=1100)
        self.cmd_warn.pack(fill="x", padx=10)
        pw = ttk.Panedwindow(tab, orient="horizontal")
        pw.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.rep_tree = ttk.Treeview(pw, columns=("no", "grp", "fx"), show="headings")
        for c, h, w in (("no", "Effect", 60), ("grp", "Группа", 120), ("fx", "Эффект", 180)):
            self.rep_tree.heading(c, text=h)
            self.rep_tree.column(c, width=w)
        pw.add(self.rep_tree, weight=1)
        self.cmd_text = tk.Text(pw, bg=PANEL, fg=FG, insertbackground=FG, font=("Consolas", 10),
                                relief="flat", wrap="none")
        pw.add(self.cmd_text, weight=2)

    def current_build(self):
        if not self.apply_settings(quiet=True):
            return None, None, None
        only = {k for k, v in self.checked.items() if v}
        if not only:
            return [], [], []
        cmds, report, warns = fx.build(copy.deepcopy(self.cfg), only, None, self.make_macros.get())
        self.phase_info, self.phase_copies = "", []
        self.order_info = ""
        if cmds and (self.layout.get("order", "по номеру") != "по номеру" or self.layout.get("group_order")):
            cmds, n, self.order_info = apply_layout_order(cmds, self.layout, self.cfg["groups"],
                                                          self.layout.get("order", "по номеру"))
            if not n or "нет приборов" in self.order_info:
                warns = list(warns) + [self.order_info]
        if cmds and self.antiphase.get():
            try:
                shift_no = int(self.copy_shift.get())
            except ValueError:
                shift_no = 500
            cmds, self.phase_copies, self.phase_info = phase_copies(cmds, report, self.cfg["groups"], shift_no)
            if "не " in self.phase_info:
                warns = list(warns) + [self.phase_info]
        return cmds, report, warns

    def render_commands(self):
        cmds, report, warns = self.current_build()
        if cmds is None:
            return
        self.cmd_text.delete("1.0", "end")
        self.cmd_text.insert("1.0", "\n".join(cmds))
        self.rep_tree.delete(*self.rep_tree.get_children())
        for no, g, n in report:
            self.rep_tree.insert("", "end", values=(no, g, n))
        self.cmd_info.config(text=f"{len(report)} эффектов · {len(cmds)} команд")
        shown = warns[:6]
        more = f"  … и ещё {len(warns) - 6}" if len(warns) > 6 else ""
        self.cmd_warn.config(text=("⚠ " + "   ⚠ ".join(shown) + more) if warns else "")

    def export_txt(self):
        cmds, _, _ = self.current_build()
        if not cmds:
            return
        p = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if p:
            with open(p, "w", encoding="utf-8") as f:
                f.write("\n".join(cmds))
            self.update_status(f"Сохранено: {p}")

    # =================================================================
    #  ПУЛЬТ: подключение, импорт групп, отправка
    # =================================================================
    def _build_conn_bar(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=10, pady=(8, 0))
        self.conn_dot = tk.Label(bar, text="●", fg="#555a64", bg=BG, font=("Segoe UI", 14))
        self.conn_dot.pack(side="left")
        self.conn_lbl = ttk.Label(bar, text="MA2: офлайн")
        self.conn_lbl.pack(side="left", padx=(4, 12))
        self.btn_conn = ttk.Button(bar, text="Подключить…", style="Small.TButton",
                                   command=self.open_connect_dialog)
        self.btn_conn.pack(side="left")
        self.btn_disc = ttk.Button(bar, text="Отключить", style="Small.TButton",
                                   command=self.disconnect, state="disabled")
        self.btn_disc.pack(side="left", padx=4)
        ttk.Button(bar, text="⇩ Группы из шоу", style="Accent.TButton",
                   command=self.open_import).pack(side="right")

    def _build_send(self):
        tab = self.tabs["send"]
        top = ttk.Labelframe(tab, text="Подключение")
        top.pack(fill="x", padx=10, pady=10)
        for i, (k, label, w) in enumerate((("host", "IP", 16), ("port", "Порт", 7), ("user", "User", 14),
                                           ("password", "Pass", 10), ("delay", "Пауза, с", 6))):
            ttk.Label(top, text=label).grid(row=0, column=i * 2, padx=(8, 4), pady=8)
            ttk.Entry(top, textvariable=self.conn[k], width=w,
                      show="•" if k == "password" else "").grid(row=0, column=i * 2 + 1)
        ttk.Button(top, text="Подключить", command=lambda: self.connect_async()).grid(row=0, column=10, padx=(8, 4))
        ttk.Button(top, text="Отключить", command=self.disconnect).grid(row=0, column=11)

        act = ttk.Frame(tab)
        act.pack(fill="x", padx=10)
        self.btn_send = ttk.Button(act, text="Отправить на пульт", style="Accent.TButton",
                                   command=self.start_send)
        self.btn_send.pack(side="left")
        self.btn_stop = ttk.Button(act, text="Стоп", command=self.stop_flag.set, state="disabled")
        self.btn_stop.pack(side="left", padx=6)
        ttk.Button(act, text="→ Анализатору", command=self.link_to_analyzer).pack(side="left")
        ttk.Button(act, text="📜 Плагин движений", command=self.save_moves_plugin).pack(side="left", padx=(6, 0))
        self.prog = ttk.Progressbar(act, mode="determinate")
        self.prog.pack(side="left", fill="x", expand=True, padx=10)
        self.prog_lbl = ttk.Label(act, text="", style="Muted.TLabel", width=18)
        self.prog_lbl.pack(side="left")

        self.log = tk.Text(tab, bg="#0c0d10", fg=FG, font=("Consolas", 10), relief="flat")
        self.log.pack(fill="both", expand=True, padx=10, pady=10)
        self.log.tag_config("ok", foreground="#7ccf7c")
        self.log.tag_config("err", foreground=ERR)
        self.log.tag_config("info", foreground=ACCENT)

    def log_line(self, text, tag=None):
        self.log.insert("end", text + "\n", tag)
        self.log.see("end")

    def conn_params(self):
        c = {k: v.get().strip() for k, v in self.conn.items()}
        return c["host"], int(c["port"]), c["user"], c["password"], float(c["delay"])

    def busy(self):
        return self.worker is not None and self.worker.is_alive()

    BUSY_PATH = os.path.join(os.path.expanduser("~"), ".ma2_fxgen_busy")

    def busy_mark(self, on):
        """метка «генератор пишет на пульт»: анализатор (тот же пользователь, тот же
        программер) на это время замолкает, чтобы не сбить выбор приборов"""
        try:
            if on:
                with open(self.BUSY_PATH, "w", encoding="utf-8") as f:
                    f.write(str(os.getpid()))
            elif os.path.exists(self.BUSY_PATH):
                os.remove(self.BUSY_PATH)
        except OSError:
            pass

    def run_worker(self, fn):
        def run():
            stop = threading.Event()

            def beat():
                while not stop.wait(5.0):
                    self.busy_mark(True)     # свежая метка; брошенная устаревает за 15 с

            self.busy_mark(True)
            threading.Thread(target=beat, daemon=True).start()
            try:
                fn()
            finally:
                stop.set()
                self.busy_mark(False)

        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()

    def set_conn_state(self, ma=None, msg=None):
        self.ma = ma
        if ma:
            self.conn_dot.config(fg="#5fd35f")
            self.conn_lbl.config(text=f"MA2: {ma.host}:{ma.port} — подключено ({self.conn['user'].get()})")
            self.btn_disc.config(state="normal")
            self.btn_conn.config(text="Переподключить…")
        else:
            self.conn_dot.config(fg="#555a64")
            self.conn_lbl.config(text="MA2: офлайн" + (f" — {msg}" if msg else ""))
            self.btn_disc.config(state="disabled")
            self.btn_conn.config(text="Подключить…")

    def connect_async(self, on_ok=None, on_fail=None):
        """Подключиться и залогиниться в фоне. Колбэки вызываются в GUI-потоке."""
        if self.busy():
            if on_fail:
                on_fail("пульт занят другой операцией")
            return
        try:
            host, port, user, pw, _ = self.conn_params()
        except ValueError:
            msg = "Проверь порт и паузу"
            on_fail(msg) if on_fail else messagebox.showerror("Подключение", msg)
            return
        self._conn_cb = (on_ok, on_fail)
        self.log_line(f"Подключение к {host}:{port}…", "info")
        old = self.ma

        def run():
            if old:
                old.close(logout=True)
            try:
                ma = fx.MA2Telnet(host, port)
                ok, resp = ma.login(user, pw)
                if not ok:
                    ma.close()
                    self.q.put(("conn_fail", "логин не прошёл: " + resp[:120]))
                else:
                    self.q.put(("connected", ma, resp))
            except OSError as e:
                self.q.put(("conn_fail", f"нет связи: {e}"))

        self.run_worker(run)

    def disconnect(self):
        if self.busy():
            messagebox.showinfo("Отключить", "Дождись окончания текущей операции.")
            return
        if self.ma:
            self.ma.close(logout=True)
            self.log_line("Отключено от пульта", "info")
        self.set_conn_state(None)

    def open_connect_dialog(self, import_after=None):
        ConnectDialog(self, import_after)

    def open_import(self):
        if self.busy():
            messagebox.showinfo("Импорт", "Дождись окончания текущей операции.")
            return
        if not self.ma:
            self.open_connect_dialog(import_after=True)
            return
        ImportGroupsDialog(self)

    def pull_async(self, list_cmd, detail_cmd, counts, on_done):
        """Прочитать группы из шоу в фоне. on_done(groups, raw, error) — в GUI-потоке."""
        if self.busy() or not self.ma:
            on_done([], "", "нет подключения или пульт занят")
            return
        self._pull_cb = on_done
        ma = self.ma

        def run():
            try:
                groups, raw = fx.pull_groups(ma, list_cmd, detail_cmd, counts,
                                             progress=lambda i, n: self.q.put(("pull_prog", i, n)))
                self.q.put(("pulled", groups, raw, None))
            except OSError as e:
                self.q.put(("conn_lost", str(e)))
                self.q.put(("pulled", [], "", f"связь потеряна: {e}"))

        self.run_worker(run)

    def start_send(self):
        if self.busy():
            return
        cmds, report, warns = self.current_build()
        if not cmds:
            messagebox.showinfo("Отправка", "Нечего отправлять: нет групп или шаблонов.")
            return
        try:
            host, port, user, pw, delay = self.conn_params()
        except ValueError:
            messagebox.showerror("Подключение", "Проверь порт и паузу")
            return
        target = f"{self.ma.host}:{self.ma.port} (текущее подключение)" if self.ma else f"{host}:{port}"
        est = len(cmds) * (delay + 0.06)
        if not messagebox.askyesno("Отправка",
                                   f"Создать {len(report)} эффектов ({len(cmds)} команд, ~{est / 60:.0f} мин) "
                                   f"на {target}?\nСуществующие Effects/Macros с этими номерами будут перезаписаны."):
            return
        self.stop_flag.clear()
        self.btn_send.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.prog.config(maximum=len(cmds), value=0)
        self.log_line(f"Отправка на {target} — {len(cmds)} команд", "info")
        for w in warns:
            self.log_line("⚠ " + w, "info")
        if self.phase_info and "не " not in self.phase_info:
            self.log_line(self.phase_info, "info")
        persistent = self.ma

        def connect_new():
            ma = fx.MA2Telnet(host, port)
            ok, resp = ma.login(user, pw)
            if not ok:
                ma.close()
                raise ConnectionError("логин не прошёл: " + resp[:120])
            return ma

        def run():
            errors, ma, reconnected = 0, persistent, False
            skip = set()   # ключевые слова, которые пульт уже отверг, — дальше не шлём
            try:
                if ma is None:
                    ma = connect_new()
                nonlocal cmds
                forms, missing, raw = fx.pull_forms(ma)
                if forms:
                    cmds = fx.remap_forms(cmds, self.cfg["forms"], forms)
                    self.q.put(("log", "Формы с пульта: " + ", ".join(f"{k}={v}" for k, v in forms.items()), "info"))
                else:
                    self.q.put(("log", "List Form не разобран — номера форм из конфига:\n" + raw[:300], "err"))
                if forms and missing:
                    self.q.put(("log", "Нет на пульте форм: " + ", ".join(missing) + " — номера из конфига", "err"))
                i = 0
                while i < len(cmds):
                    if self.stop_flag.is_set():
                        self.q.put(("log", "Остановлено пользователем", "err"))
                        break
                    c = cmds[i]
                    kw = "speed" if c.startswith("Assign SpecialMaster") and " At Effect " in c else c.split(" ", 1)[0]
                    if kw in skip:
                        i += 1
                        self.q.put(("prog", i, len(cmds)))
                        continue
                    try:
                        r = ma.send(c, wait=delay)
                    except OSError as e:
                        if reconnected:
                            raise
                        reconnected = True
                        self.q.put(("log", f"Связь оборвалась ({e}) — переподключаюсь…", "err"))
                        ma.close()
                        ma = connect_new()
                        if persistent:
                            self.q.put(("connected", ma, "переподключено"))
                        if not c.startswith(("ClearAll", "Group")):
                            # повторяем эффект с начала: откатываемся к его ClearAll
                            while i > 0 and cmds[i] != "ClearAll":
                                i -= 1
                        continue
                    own = fx.own_reply(r, c) if hasattr(fx, "own_reply") else r
                    bad = any(w in own.lower() for w in ("error", "illegal", "unknown"))
                    if bad and c.startswith("Delete "):
                        bad = False      # пустая ячейка пула — не ошибка
                    if bad:
                        errors += 1
                        self.q.put(("log", f"ERR {c}\n    {fx.clean_text(own).strip()[:200]}", "err"))
                        if kw == "speed":
                            skip.add(kw)
                            self.q.put(("log", "Привязка к SpeedMaster не принята пультом — дальше не отправляю "
                                               "(Speed-группу можно выставить в Effect Editor)", "err"))
                    else:
                        self.q.put(("log", f"ok  {c}", "ok"))
                    i += 1
                    self.q.put(("prog", i, len(cmds)))
                ma.send("ClearAll", wait=0.2)
                if not persistent:
                    ma.close(logout=True)
                self.q.put(("log", f"Готово. Ошибок: {errors}", "err" if errors else "info"))
                if not self.stop_flag.is_set():
                    self.q.put(("link", report))
            except (OSError, ConnectionError) as e:
                self.q.put(("log", f"Отправка прервана: {e}", "err"))
                if persistent:
                    self.q.put(("conn_lost", str(e)))
            finally:
                self.q.put(("done",))

        self.run_worker(run)

    def poll_queue(self):
        try:
            while True:
                m = self.q.get_nowait()
                kind = m[0]
                if kind == "log":
                    self.log_line(m[1], m[2])
                elif kind == "prog":
                    self.prog.config(value=m[1])
                    self.prog_lbl.config(text=f"{m[1]} / {m[2]}")
                elif kind == "link":
                    self.write_link(m[1])
                elif kind == "patch":
                    self.show_patch(*m[1:])
                elif kind == "follow_off":
                    self.layout_ui.follow_stopped()
                elif kind == "call":
                    m[1](*m[2:])
                elif kind == "done":
                    self.btn_send.config(state="normal")
                    self.btn_stop.config(state="disabled")
                elif kind == "connected":
                    self.set_conn_state(m[1])
                    self.log_line(f"Подключено: {m[2]}", "ok")
                    self.save_prefs()
                    ok_cb = getattr(self, "_conn_cb", (None, None))[0]
                    self._conn_cb = (None, None)
                    if ok_cb:
                        ok_cb()
                elif kind == "conn_fail":
                    self.set_conn_state(None, m[1])
                    self.log_line(f"Не подключено: {m[1]}", "err")
                    fail_cb = getattr(self, "_conn_cb", (None, None))[1]
                    self._conn_cb = (None, None)
                    if fail_cb:
                        fail_cb(m[1])
                elif kind == "conn_lost":
                    self.set_conn_state(None, "связь потеряна")
                elif kind == "pull_prog":
                    dlg = getattr(self, "import_dlg", None)
                    if dlg and dlg.winfo_exists():
                        dlg.set_progress(m[1], m[2])
                elif kind == "pulled":
                    cb, self._pull_cb = getattr(self, "_pull_cb", None), None
                    if cb:
                        cb(m[1], m[2], m[3])
        except queue.Empty:
            pass
        self.after(80, self.poll_queue)

    def pull_patch(self):
        """спросить у пульта патч: List FixtureType, List Fixture и состав групп"""
        if self.busy():
            messagebox.showinfo("Патч", "Дождись окончания текущей операции.")
            return
        if not self.ma:
            messagebox.showinfo("Патч", "Сначала подключись к пульту.")
            return
        ma, groups = self.ma, [dict(g) for g in self.cfg["groups"]]
        self.update_status("Запрашиваю патч с пульта…")

        def run():
            def ask(cmd, wait=10.0):
                return fx.own_reply(ma.query(cmd, settle=0.6, max_wait=wait), cmd)

            try:
                raw_types = ask("List FixtureType")
                raw_fix = ask("List Fixture", 15.0)
                raw_chan = ask("List Channel", 10.0)          # диммеры без FixID - только тут
                if parse_fixture_table(raw_chan):
                    raw_fix = raw_fix + "\n" + raw_chan
                raw_glist = ask("List Group")
                console = fx.parse_group_list(raw_glist)
                names = [g["name"] for g in console]
                numbers = {g["name"]: g["id"] for g in console if names.count(g["name"]) == 1}
                xml_fix, xml_groups = None, None
                if is_local_host(getattr(ma, "host", "")):
                    # onPC на этом компьютере: Export в XML даёт состав групп, адреса и 3D-позиции
                    xml_fix, gtext = export_patch_xml(ma, log=lambda t: self.q.put(("log", t, "info")))
                    listed = {f["id"] for f in parse_fixture_table(raw_fix)}
                    if xml_fix and listed and len(listed & {f["id"] for f in xml_fix}) < 0.8 * len(listed):
                        # файл от другого шоу (Export не перезаписал) - верим List Fixture
                        self.q.put(("log", "Патч: XML приборов не совпадает с List Fixture - не беру его", "info"))
                        xml_fix, gtext = None, None
                    if gtext:
                        try:
                            xml_groups = parse_groups_xml(gtext, numbers)
                            if console and not {g["name"] for g in xml_groups} & {g["name"] for g in console}:
                                self.q.put(("log", "Патч: XML групп от другого шоу - не беру его", "info"))
                                xml_groups = None
                        except Exception as e:
                            self.q.put(("log", f"Патч: XML групп не разобран: {e}", "err"))
                members, sizes, raw_groups = {}, {}, []
                if xml_groups:
                    known = {g["id"] for g in console}
                    for g in xml_groups:
                        members[g["id"]], sizes[g["id"]] = g["members"], g["size"]
                        if g["id"] not in known:
                            console.append({"id": g["id"], "name": g["name"]})
                    console.sort(key=lambda g: g["id"])
                else:
                    # пульт по сети: состав групп - из ответа List Group N (3.9.x его не даёт)
                    for g in groups:
                        r = ask(f"List Group {g['id']}", 4.0)
                        raw_groups.append(f"--- Group {g['id']}\n{r}")
                        ids = group_fixture_ids(r)
                        if ids:
                            members[g["id"]] = ids
                for g in console:
                    if sizes.get(g["id"]):
                        g["count"] = sizes[g["id"]]
                extra = {"xml_fix": xml_fix, "console": console, "sizes": sizes,
                         "raw_glist": raw_glist, "xml_groups": bool(xml_groups)}
                self.q.put(("patch", raw_types, raw_fix, members, "\n".join(raw_groups), extra))
            except OSError as e:
                self.q.put(("conn_lost", str(e)))

        self.run_worker(run)

    def save_moves_plugin(self):
        """эффекты движений → Lua-плагин MA2 (как PosExec): группа выбирается на пульте при запуске"""
        import glob
        size = next((g.get("size") for g in self.cfg["groups"] if "pt" in (g.get("caps") or []) and g.get("size")), 20)
        try:
            lua, xml, n = fx.moves_plugin(self.cfg, size=size)
        except Exception as e:
            messagebox.showerror("Плагин движений", f"Не собрался: {e}")
            return
        if not n:
            messagebox.showinfo("Плагин движений", "Нет шаблонов движений (категория Position).")
            return
        dirs = sorted(glob.glob(os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                                             "MA Lighting Technologies", "grandma", "gma2_V_*", "plugins")))
        start = dirs[-1] if dirs else os.path.expanduser("~")
        folder = filedialog.askdirectory(title="Куда сохранить MovesExec (папка plugins пульта / onPC / флешки)",
                                         initialdir=start)
        if not folder:
            return
        try:
            for ext, text in ((".lua", lua), (".xml", xml)):
                with open(os.path.join(folder, "MovesExec" + ext), "w", encoding="utf-8") as fh:
                    fh.write(text)
        except OSError as e:
            messagebox.showerror("Плагин движений", f"Не записать: {e}")
            return
        self.log_line(f"Плагин движений: {n} эффектов → {folder}\\MovesExec.lua / .xml", "ok")
        messagebox.showinfo("Плагин движений",
                            f"Сохранено {n} эффектов движений:\n{folder}\\MovesExec.lua и .xml\n\n"
                            "На пульте: Plugins → Import → MovesExec, затем запустить плагин. "
                            "Он спросит номер экзекьютора, группу (можно «1 + 3» или «1 Thru 4»), "
                            "амплитуду и диммер - и запишет по кью на каждый эффект.")

    def diag_patch(self):
        """сырые ответы пульта про патч → файл: по нему подстраивается разбор под версию MA2"""
        if self.busy():
            messagebox.showinfo("Патч", "Дождись окончания текущей операции.")
            return
        if not self.ma:
            messagebox.showinfo("Патч", "Сначала подключись к пульту.")
            return
        ma, groups = self.ma, [dict(g) for g in self.cfg["groups"]][:12]
        self.update_status("Диагностика патча: опрашиваю пульт…")

        def ask(out, cmd, wait=6.0):
            r = ma.query(cmd, settle=0.6, max_wait=wait)
            out.append(f"\n===== > {cmd}\n{r}")
            return r

        def run():
            out = [f"ma2_fxgen: диагностика патча {time.strftime('%Y-%m-%d %H:%M:%S')}"
                   f" · {getattr(ma, 'host', '')}:{getattr(ma, 'port', '')}"]
            try:
                for cmd in ("List FixtureType", "List Fixture", "List Channel", "List Group", "List Layer"):
                    ask(out, cmd, 10.0)
                # дерево шоу: Setup → Layers (FixID / ChaID / тип / режим / адрес)
                ask(out, "cd /")
                r = ask(out, "cd EditSetup")
                if "error" in r.lower():
                    ask(out, "cd 10")
                ask(out, "list")
                ask(out, "cd Layers")
                ask(out, "list")
                ask(out, "cd 1")
                ask(out, "list", 10.0)
                ask(out, "cd 1")
                ask(out, "list")
                ask(out, "cd /")
                # типы приборов: режимы и каналы с атрибутами
                ask(out, "cd EditSetup")
                r = ask(out, "cd FixtureTypes")
                r = ask(out, "list", 10.0)
                nums = []
                for line in _rows(r):
                    m = re.match(r"^\s*(?:FixtureType\s+)?(\d+)\s", line, re.I)
                    if m and int(m.group(1)) not in nums:
                        nums.append(int(m.group(1)))
                for n in (nums or [1, 2, 3])[:10]:
                    ask(out, f"cd {n}")
                    ask(out, "list")
                    for depth in range(3):
                        ask(out, "cd 1")
                        ask(out, "list")
                    for depth in range(4):
                        ask(out, "cd ..")
                ask(out, "cd /")
                for g in groups:
                    ask(out, f"List Group {g['id']}")
                    ask(out, f"Info Group {g['id']}")
                # XML: если onPC на этом же компьютере, файлы ляжут в importexport
                ask(out, 'Export Fixture 1 Thru 99999 "ma2fx_fixtures" /o', 10.0)
                ask(out, 'Export FixtureType 1 Thru 999 "ma2fx_types" /o', 15.0)
                ask(out, 'Export Group 1 Thru 9999 "ma2fx_groups" /o', 10.0)
            except OSError as e:
                out.append(f"\n!!! связь потеряна: {e}")
            finally:
                try:
                    ma.query("cd /", settle=0.4, max_wait=2.0)
                except OSError:
                    pass
            import glob
            roots = [os.environ.get("ProgramData", r"C:\ProgramData"), os.path.expanduser("~")]
            found = []
            for root in roots:
                found += glob.glob(os.path.join(root, "MA Lighting Technologies", "**", "ma2fx_*.xml"), recursive=True)
            for f in sorted(set(found)):
                try:
                    with open(f, encoding="utf-8", errors="replace") as fh:
                        text = fh.read(400000)
                    out.append(f"\n===== файл {f} ({os.path.getsize(f)} байт)\n{text}")
                except OSError as e:
                    out.append(f"\n===== файл {f}: {e}")
            if not found:
                out.append("\n===== XML-файлы ma2fx_* не найдены (пульт по сети или Export не сработал)")
            path = os.path.join(os.path.expanduser("~"), "ma2_patch_diag.txt")
            desk = os.path.join(os.path.expanduser("~"), "Desktop")
            if os.path.isdir(desk):
                path = os.path.join(desk, "ma2_patch_diag.txt")
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("\n".join(out))
            except OSError as e:
                self.q.put(("log", f"Диагностика: не записать {path}: {e}", "err"))
                return
            self.q.put(("call", self.diag_done, path, len(found)))

        self.run_worker(run)

    def diag_done(self, path, xml_count):
        self.log_line(f"Диагностика патча сохранена: {path} (XML-файлов: {xml_count})", "ok")
        self.update_status("Диагностика патча готова")
        messagebox.showinfo("Диагностика патча",
                            f"Файл сохранён:\n{path}\n\nПришлите его в чат - по нему разбор патча "
                            f"подстроится под вашу версию MA2.")
        try:
            os.startfile(os.path.dirname(path))
        except (AttributeError, OSError):
            pass

    def show_patch(self, raw_types, raw_fix, members, raw_groups, extra=None):
        extra = extra or {}
        types = parse_fixture_types(raw_types)
        fixtures = extra.get("xml_fix") or parse_fixtures(raw_fix, types)
        src = "XML Export" if extra.get("xml_fix") else "List Fixture"
        raw = (f"> List FixtureType\n{raw_types}\n> List Fixture\n{raw_fix}\n"
               f"> List Group\n{extra.get('raw_glist', '')}\n{raw_groups}")
        console = extra.get("console") or []
        sizes = extra.setdefault("sizes", {})
        if not extra.get("xml_groups"):
            # без XML состав групп не виден; группа «All <тип прибора>» (так их делает MA2
            # при патче) - это все приборы этого типа
            members = dict(members or {})
            types_long = sorted({f["type"] for f in fixtures if f.get("type")}, key=len, reverse=True)
            for g in console:
                t = next((t for t in types_long if t.lower() in g["name"].lower()), None)
                if t and not members.get(g["id"]):
                    sel = [f for f in fixtures if f.get("type") == t]
                    members[g["id"]] = {f["id"] for f in sel}
                    sizes[g["id"]] = g["count"] = sum(f.get("subs") or 1 for f in sel)
        self.log_line(f"Патч ({src}): типов {len(types)}, приборов {len(fixtures)}, групп на пульте {len(console)}"
                      f", состав известен у {len(members)}"
                      + ("" if extra.get("xml_groups") else
                         " (пульт по сети - состав групп угадывается по именам)"), "info")
        if fixtures:
            new = self.layout_ui.merge(fixtures, members)
            if new:
                self.log_line(f"Layout: новых приборов {new}"
                              + (" - стоят по 3D-позициям пульта" if any(f.get("pos") for f in fixtures)
                                 else " - расставлены по группам") + ", поправьте на вкладке Layout", "info")
        PatchDialog(self, fixtures, members, raw, console, sizes)

    def type_caps(self, type_name):
        """возможности типа прибора: поправка пользователя или угадано по имени"""
        own = (self.prefs.get("type_caps") or {}).get(type_name)
        if own:
            return own["kind"], list(own["caps"])
        return guess_fixture_type(type_name)

    def apply_imported(self, rows, replace):
        """rows: [{id, name, count, caps}] — выбранные в диалоге импорта."""
        before = {g["id"] for g in self.cfg["groups"]}
        self.cfg["groups"] = fx.merge_groups(self.cfg["groups"], rows, replace)
        by_id = {g["id"]: g for g in self.cfg["groups"]}
        for r in rows:  # правки из диалога (возможности/кол-во) применяем и к существующим
            g = by_id[r["id"]]
            g["caps"] = r["caps"]
            if r.get("count"):
                g["count"] = r["count"]
        self.cfg = make_config(self.cfg)
        self.refresh_groups()
        new = len([r for r in rows if r["id"] not in before])
        self.update_status(f"Импорт групп: новых {new}, обновлено {len(rows) - new}"
                           + (" (список заменён)" if replace else ""))
        self.nb.select(self.tab_frames["groups"])

    # ---------------- связь с MusicAnalyzer ----------------
    LINK_PATH = os.path.join(os.path.expanduser("~"), ".ma2_fxgen_link.json")

    def write_link(self, report):
        """Список эффектов на пульте → файл, который читает MusicAnalyzer."""
        lib = self.lib()
        by_name = {}
        for k, t in lib.items():
            by_name.setdefault(str(t.get("name", k)).strip().lower(), (k, self.tpl_category(k, t)))
        looks, order = {}, []
        alts = {base: (copy_no, off) for copy_no, _g, _n, off, base in getattr(self, "phase_copies", [])}
        for no, grp, name in report:
            name = str(name).strip()
            key, cat = by_name.get(name.lower(), (None, None))
            if key is None:   # имя с приставкой группы и т.п. - ищем шаблон по вхождению
                hits = [v for n, v in by_name.items() if n and n in name.lower()]
                key, cat = max(hits, key=lambda v: len(lib[v[0]].get("name", ""))) if hits else (name, "combo")
            look = looks.get(key)
            if look is None:
                look = looks[key] = {"key": key, "name": lib.get(key, {}).get("name", name),
                                     "cat": cat, "bpm": lib.get(key, {}).get("bpm"), "effects": []}
                order.append(key)
            try:
                no = int(no)
            except (TypeError, ValueError):
                pass
            effect = {"no": no, "group": str(grp)}
            gr = next((g for g in self.cfg.get("groups", []) if str(g.get("name")) == str(grp)), None)
            if gr is not None and key in lib and hasattr(fx, "has_move_dim") and fx.has_move_dim(lib[key], gr, self.cfg, lib):
                effect["dim"] = True          # в эффекте движения свой диммер
            if no in alts:
                effect["alt"], effect["alt_phase"] = alts[no]
            look["effects"].append(effect)
        data = {"version": 1, "written": time.strftime("%Y-%m-%d %H:%M:%S"),
                "host": self.conn["host"].get().strip(),
                "speed_groups": self.cfg.get("speed_groups", {}),
                "groups": [{"id": g.get("id"), "name": g.get("name"), "caps": g.get("caps", []),
                            "count": g.get("count"),
                            "kind": "" if g.get("kind") == "-" else g.get("kind"), "fixture_type": g.get("fixture_type")}
                           for g in self.cfg.get("groups", [])],
                "looks": [looks[k] for k in order],
                "layout": {"stage": self.layout.get("stage", STAGE_DEFAULT),
                           "pt": self.layout.get("pt", {}),
                           "fix": {k: {**{kk: f.get(kk) for kk in ("id", "name", "type", "group", "x", "y", "z",
                                                                    "mount", "rot", "inv_pan", "inv_tilt")},
                                       "kind": self.type_caps(f.get("type") or "")[0],
                                       "caps": self.type_caps(f.get("type") or "")[1]}
                                   for k, f in self.layout.get("fix", {}).items()}},
                "presets": self.layout.get("made", [])}
        st = self.layout.get("stage", STAGE_DEFAULT)
        w, d = max(_f(st.get("w"), 12), 1), max(_f(st.get("d"), 8), 1)
        for g in data["groups"]:
            pts = [f for f in self.layout.get("fix", {}).values() if f.get("group") == g["id"] and f.get("x") is not None]
            if pts:
                cx = sum(_f(f["x"]) for f in pts) / len(pts)
                cy = sum(_f(f["y"]) for f in pts) / len(pts)
                # план анализатора: x 0..1 слева направо, y 0 - задник, 1 - край сцены
                g["x"] = round(min(1, max(0, cx / w + 0.5)), 3)
                g["y"] = round(min(1, max(0, 1 - cy / d)), 3)
        try:
            with open(self.LINK_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            self.log_line(f"Анализатору не передано: {e}", "err")
            return False
        n = sum(len(l["effects"]) for l in data["looks"])
        self.log_line(f"→ Анализатору: {len(order)} эффектов ({n} объектов Effects) в {self.LINK_PATH}. "
                      "В анализаторе: «🎛 grandMA2…» → «🔗 Взять эффекты генератора»", "info")
        self.update_status("Эффекты переданы анализатору")
        return True

    def link_to_analyzer(self):
        """Передать анализатору эффекты, которые уже отправлены на пульт (без повторной отправки)."""
        cmds, report, _ = self.current_build()
        if not report:
            messagebox.showinfo("Анализатор", "Нечего передавать: нет групп или отмеченных шаблонов.")
            return
        self.write_link(report)

    # ---------------- настройки приложения ----------------
    PREFS_PATH = os.path.join(os.path.expanduser("~"), ".ma2_fxgen_gui.json")

    def load_prefs(self):
        try:
            with open(self.PREFS_PATH, encoding="utf-8") as f:
                p = json.load(f)
        except (OSError, ValueError):
            p = {}
        self.prefs = {"connect_on_start": True, "import_after_connect": True, **p}
        for k in ("host", "port", "user", "password", "delay"):
            if k in self.prefs:
                self.conn[k].set(str(self.prefs[k]))
        self.antiphase.set(bool(self.prefs.get("antiphase", True)))
        self.layout.clear()
        self.layout.update(self.prefs.get("layout") or {})
        self.layout_ui.reload()
        self.copy_shift.set(str(self.prefs.get("phase_copy_shift", 500)))
        self.copy_shift.trace_add("write", lambda *_: self.save_prefs_later())
        # IP, порт, логин и пароль запоминаются сразу при вводе, а не только после подключения
        self._prefs_job = None
        for k in ("host", "port", "user", "password", "delay"):
            self.conn[k].trace_add("write", lambda *_: self.save_prefs_later())

    def save_prefs_later(self):
        if getattr(self, "_prefs_job", None):
            self.after_cancel(self._prefs_job)
        self._prefs_job = self.after(500, self.save_prefs)

    def save_prefs(self):
        self._prefs_job = None
        for k in ("host", "port", "user", "password", "delay"):
            self.prefs[k] = self.conn[k].get().strip()
        self.prefs["antiphase"] = bool(self.antiphase.get())
        self.prefs["layout"] = self.layout
        self.prefs["phase_copy_shift"] = self.copy_shift.get().strip() or "500"
        if self.cfg_path:
            self.prefs["last_config"] = self.cfg_path
        try:
            with open(self.PREFS_PATH, "w", encoding="utf-8") as f:
                json.dump(self.prefs, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def startup(self):
        last = self.prefs.get("last_config")
        if last and os.path.exists(last):
            self.open_cfg(last)
        if self.prefs.get("connect_on_start", True):
            self.open_connect_dialog(import_after=None)

    def on_close(self):
        self.stop_flag.set()
        self.layout_ui.follow_on = False
        self.save_prefs()
        if self.ma and not self.busy():
            self.ma.close(logout=True)
        self.destroy()

    # =================================================================
    #  ФАЙЛЫ / СТАТУС
    # =================================================================
    def open_cfg(self, p=None):
        p = p or filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if not p:
            return
        try:
            with open(p, encoding="utf-8") as f:
                self.cfg = make_config(json.load(f))
            lay = self.cfg.pop("layout", None)
            if isinstance(lay, dict) and lay.get("fix"):
                self.layout.clear()
                self.layout.update(lay)
                self.layout_ui.reload()
        except (OSError, ValueError) as e:
            messagebox.showerror("Открыть", str(e))
            return
        self.cfg_path = p
        self.cur_custom = None
        self.load_settings_to_ui()
        self.refresh_all()
        self.update_status(f"Открыт {p}")
        self.save_prefs()

    def save_cfg(self, as_new=False):
        if not self.apply_settings(quiet=True):
            return
        p = self.cfg_path
        if as_new or not p:
            p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
            if not p:
                return
        with open(p, "w", encoding="utf-8") as f:
            json.dump({**self.cfg, "layout": self.layout}, f, ensure_ascii=False, indent=2)
        self.cfg_path = p
        self.update_status(f"Сохранено: {p}")
        self.save_prefs()

    def export_custom(self):
        if not self.cfg["custom"]:
            messagebox.showinfo("Экспорт", "Своих шаблонов пока нет.")
            return
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")],
                                         initialfile="fx_templates.json")
        if p:
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"custom": self.cfg["custom"]}, f, ensure_ascii=False, indent=2)
            self.update_status(f"Экспортировано {len(self.cfg['custom'])} шаблонов: {p}")

    def import_custom(self):
        p = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not p:
            return
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            items = data.get("custom", data) if isinstance(data, dict) else data
            assert isinstance(items, list)
        except (OSError, ValueError, AssertionError):
            messagebox.showerror("Импорт", "Ожидается JSON со списком \"custom\".")
            return
        existing = {c["key"]: i for i, c in enumerate(self.cfg["custom"])}
        added = replaced = 0
        for c in items:
            if not isinstance(c, dict) or "key" not in c or c["key"] in fx.BUILTIN_KEYS:
                continue
            c.setdefault("name", c["key"])
            c.setdefault("layers", [])
            if c["key"] in existing:
                self.cfg["custom"][existing[c["key"]]] = c
                replaced += 1
            else:
                self.cfg["custom"].append(c)
                added += 1
        self.refresh_all()
        self.update_status(f"Импорт: добавлено {added}, заменено {replaced}")

    def on_tab(self, _e=None):
        if self.tab_is("cmd"):
            self.render_commands()
        self.t0 = time.time()

    def update_status(self, msg=None):
        if not hasattr(self, "status"):
            return
        n_on = sum(self.checked.values())
        base = (f'Групп: {len(self.cfg["groups"])} · шаблонов включено: {n_on}/{len(self.checked)} · '
                f'своих: {len(self.cfg["custom"])} · конфиг: {self.cfg_path or "не сохранён"}')
        self.status.config(text=f"{msg}   |   {base}" if msg else base)


# =====================================================================
#  LAYOUT: где висят фонари (X/Y/Z), Pan/Tilt на точку, follow, пресеты
# =====================================================================
# Сцена в метрах, вид сверху: X - вправо от центра (как видит зал), Y - вглубь
# сцены от её переднего края (зал при Y < 0), Z - высота от пола сцены.
STAGE_DEFAULT = {"w": 12.0, "d": 8.0}
MOUNTS = ("верх", "пол")
ORDERS = ("по номеру", "слева направо", "справа налево", "спереди назад", "сзади вперёд",
          "из центра", "к центру", "по кругу", "снизу вверх")
PT_DEFAULT = {"pan": 540.0, "tilt": 270.0}
POS_LOOKS = (  # готовые позиции: имя → куда светят (функция от прибора и сцены)
    ("Центр", "в центр сцены на 1,7 м"),
    ("Авансцена", "на передний край сцены"),
    ("В зал", "в зал на уровне лиц"),
    ("Вниз", "прямо под себя"),
    ("Крест", "каждый - в зеркальную точку на другой стороне"),
    ("Веер", "веером в зал"),
)


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def aim(fix, target, rng=None, prev=None):
    """Pan/Tilt (градусы от центра диапазона), чтобы прибор светил в точку target (x, y, z).
    Подвес «верх»: Tilt 0 - луч вниз; «пол»: Tilt 0 - луч вверх. Pan 0 - прибор
    смотрит в зал, поправка - rot (поворот прибора) и инверсии. Из двух решений
    (Pan, Tilt) и (Pan+180, -Tilt) берётся то, что влезает в диапазон и ближе к prev."""
    rng = rng or PT_DEFAULT
    px, py, pz = _f(fix.get("x")), _f(fix.get("y")), _f(fix.get("z"))
    dx, dy, dz = target[0] - px, target[1] - py, target[2] - pz
    h = math.hypot(dx, dy)
    hung = fix.get("mount", "верх") != "пол"
    tilt = math.degrees(math.atan2(h, -dz if hung else dz))
    if h < 1e-6:
        heading = prev[0] if prev else 0.0
    else:
        heading = math.degrees(math.atan2(dx, -dy))   # + к правому краю сцены
    return aim_dir(fix, heading, tilt, rng, prev)


def aim_dir(fix, heading, tilt, rng=None, prev=None):
    """Pan/Tilt прибора для направления луча: heading - куда по плану (0 - в зал,
    + к правому краю сцены), tilt - угол от вертикали (подвес: от «вниз», пол: от «вверх»)"""
    rng = rng or PT_DEFAULT
    pan0 = heading - _f(fix.get("rot"))
    half_p, half_t = _f(rng.get("pan"), 540) / 2, _f(rng.get("tilt"), 270) / 2
    cands = []
    for base, t in ((pan0, tilt), (pan0 + 180, -tilt)):
        if abs(t) > half_t + 1e-6:
            continue
        for k in range(-3, 4):
            p = base + 360 * k
            if abs(p) <= half_p + 1e-6:
                cands.append((p, t))
    if not cands:
        return None
    if prev:
        p, t = min(cands, key=lambda c: abs(c[0] - prev[0]) + abs(c[1] - prev[1]))
    else:
        p, t = min(cands, key=lambda c: abs(c[0]) + 0.5 * abs(c[1]))
    if fix.get("inv_pan"):
        p = -p
    if fix.get("inv_tilt"):
        t = -t
    return round(p, 1), round(t, 1)


STEP_ORDERS = ("веер из центра", "слева направо", "справа налево", "спереди назад", "сзади вперёд", "по номеру")


def step_dirs(fixes, mode, pan0, tilt0, dpan, dtilt, stage=None):
    """шаг угла: каждый следующий прибор (в порядке mode) повёрнут на dpan / dtilt.
    «веер из центра» - средний на pan0/tilt0, соседи расходятся симметрично.
    → [(прибор, heading, tilt)]"""
    items = [f for f in fixes if f.get("x") is not None]
    by_id = {int(f["id"]): f for f in items}
    order = order_ids(items, "слева направо" if mode == "веер из центра" else mode, stage)
    n = len(order)
    out = []
    for i, fid in enumerate(order):
        if mode == "веер из центра":
            k = i - (n - 1) / 2.0
            out.append((by_id[fid], _f(pan0) + k * _f(dpan), _f(tilt0) + abs(k) * _f(dtilt)))
        else:
            out.append((by_id[fid], _f(pan0) + i * _f(dpan), _f(tilt0) + i * _f(dtilt)))
    return out


def look_target(name, fix, stage):
    """точка для готовой позиции name у прибора fix"""
    w, d = _f(stage.get("w"), 12), _f(stage.get("d"), 8)
    x, y, z = _f(fix.get("x")), _f(fix.get("y")), _f(fix.get("z"))
    if name == "Центр":
        return (0.0, d / 2, 1.7)
    if name == "Авансцена":
        return (x * 0.6, 1.0, 1.7)
    if name == "В зал":
        return (x * 1.5, -8.0, 1.7)
    if name == "Вниз":
        return (x, y, 0.0 if fix.get("mount", "верх") != "пол" else z + 10)
    if name == "Крест":
        return (-x if abs(x) > 0.3 else 0.0, d / 2, 0.0)
    if name == "Веер":
        return (x * 3 if abs(x) > 0.3 else 0.0, -6.0, 3.0)
    return (0.0, d / 2, 1.7)


def name_group(fix_name, groups):
    """группа по имени прибора: «SPOT 3» → группа «SPOT», «Leg RB 2» → «Leg»"""
    n = (fix_name or "").lower()
    best, best_len = None, 0
    for g in groups:
        gn = (g.get("name") or "").lower().strip()
        if not gn:
            continue
        words = re.findall(r"[a-zа-я0-9]+", gn)
        if n.startswith(gn) or (words and all(w in n for w in words)):
            if len(gn) > best_len:
                best, best_len = g["id"], len(gn)
    return best


def merge_layout_fixtures(layout, fixtures, groups, members=None, kinds=None):
    """приборы из патча → layout["fix"]; уже расставленные не двигаются,
    новые расставляются по группам. → сколько новых"""
    members = members or {}
    kinds = kinds or {}
    fix = layout.setdefault("fix", {})
    by_member = {}
    for gid, ids in members.items():
        for i in ids or ():
            by_member.setdefault(i, gid)
    new = []
    for f in fixtures:
        key = str(f["id"])
        cur = fix.get(key)
        gid = by_member.get(f["id"])
        if gid is None:
            gid = name_group(f.get("name"), groups)
        if cur is None:
            cur = fix[key] = {"id": f["id"], "name": f.get("name", ""), "type": f.get("type", ""),
                              "group": gid, "mount": "верх", "rot": 0, "inv_pan": False, "inv_tilt": False}
            new.append(key)
        else:
            cur.update({"name": f.get("name", cur.get("name", "")), "type": f.get("type", cur.get("type", ""))})
            if cur.get("group") is None:
                cur["group"] = gid
    if new:
        auto_place(layout, groups, kinds, only=new)
        console_positions(layout, fixtures, only=new)
    return len(new)


def console_positions(layout, fixtures, only=None):
    """3D-позиции из патча MA2 → Layout. MA: x - вправо, y - вглубь (минус - к залу),
    0 - центр сцены, z - высота. В Layout y=0 - край сцены, поэтому сдвиг на d/2;
    сцена расширяется, чтобы все приборы поместились. → сколько приборов поставлено"""
    fix = layout.setdefault("fix", {})
    todo = [f for f in fixtures if f.get("pos") and str(f["id"]) in fix
            and (only is None or str(f["id"]) in only)]
    if not todo:
        return 0
    stage = layout.setdefault("stage", dict(STAGE_DEFAULT))
    w, d = _f(stage.get("w"), 12), _f(stage.get("d"), 8)
    w = max(w, math.ceil(2 * max(abs(f["pos"][0]) for f in todo) + 1))
    d = max(d, math.ceil(2 * max(f["pos"][1] for f in todo) + 1))
    stage["w"], stage["d"] = float(w), float(d)
    for f in todo:
        x, y, z = f["pos"]
        cur = fix[str(f["id"])]
        cur["x"], cur["y"], cur["z"] = round(x, 2), round(y + d / 2, 2), round(z, 2)
        cur["mount"] = "верх" if z >= 1.5 else "пол"
        cur["rot"] = round((f.get("rot") or (0, 0, 0))[2], 1)
    return len(todo)


def auto_place(layout, groups, kinds=None, only=None):
    """начальная расстановка: группа - ряд; передние - у края, задние - в глубине,
    боковые - по краям; фронтальные профили - в зале; споты и уош - сверху, пары - на полу"""
    kinds = kinds or {}
    stage = layout.setdefault("stage", dict(STAGE_DEFAULT))
    w, d = _f(stage.get("w"), 12), _f(stage.get("d"), 8)
    fix = layout.get("fix", {})
    names = {g["id"]: g.get("name", "") for g in groups}
    rows = {}
    for key, f in fix.items():
        rows.setdefault(f.get("group"), []).append(key)
    for r, (gid, keys) in enumerate(sorted(rows.items(), key=lambda kv: str(kv[0]))):
        keys.sort(key=lambda k: int(k) if str(k).isdigit() else 0)
        todo = [k for k in keys if only is None or k in only]
        if not todo:
            continue
        gname = (names.get(gid) or fix[keys[0]].get("name") or "").lower()
        ftype = (fix[keys[0]].get("type") or "").lower()
        kind = kinds.get(fix[keys[0]].get("type"), "")
        y, z, mount = d * (0.3 + 0.12 * (r % 4)), 6.0, "верх"
        if re.search(r"front|фронт|перед|аван", gname + " " + ftype):
            y, z = -6.0, 7.0
        elif re.search(r"back|задн|контр|leg", gname):
            y = d - 0.5
        if kind == "par" or re.search(r"\bpar\b|leg|side|бок|пол|floor", gname + " " + ftype):
            z, mount = 0.3, "пол"
        if kind == "-" or re.search(r"fog|haze|дым", gname + " " + ftype):
            y, z, mount = d, 0.3, "пол"
        n = len(keys)
        side = re.search(r"side|бок", gname)
        for i, k in enumerate(keys):
            if k not in todo:
                continue
            f = fix[k]
            if side:
                half = (n + 1) // 2
                f["x"] = -w / 2 if i < half else w / 2
                j = i if i < half else i - half
                f["y"] = round(d * (j + 1) / (half + 1), 2)
            else:
                f["x"] = round(-0.8 * w / 2 + (0.8 * w) * (i / (n - 1) if n > 1 else 0.5), 2)
                f["y"] = round(y, 2)
            f["z"], f["mount"] = z, mount


def order_ids(fixes, mode, stage=None):
    """номера приборов в порядке mode - так их выберет эффект, и фаза ляжет по сцене"""
    stage = stage or STAGE_DEFAULT
    cy = _f(stage.get("d"), 8) / 2
    items = [f for f in fixes if f.get("x") is not None]
    if mode == "слева направо":
        key = lambda f: (_f(f["x"]), _f(f["y"]))
    elif mode == "справа налево":
        key = lambda f: (-_f(f["x"]), _f(f["y"]))
    elif mode == "спереди назад":
        key = lambda f: (_f(f["y"]), _f(f["x"]))
    elif mode == "сзади вперёд":
        key = lambda f: (-_f(f["y"]), _f(f["x"]))
    elif mode == "из центра":
        key = lambda f: (math.hypot(_f(f["x"]), _f(f["y"]) - cy), _f(f["x"]))
    elif mode == "к центру":
        key = lambda f: (-math.hypot(_f(f["x"]), _f(f["y"]) - cy), _f(f["x"]))
    elif mode == "по кругу":
        key = lambda f: (math.atan2(_f(f["y"]) - cy, _f(f["x"])) % (2 * math.pi))
    elif mode == "снизу вверх":
        key = lambda f: (_f(f["z"]), _f(f["x"]))
    else:
        key = lambda f: int(f["id"])
    return [int(f["id"]) for f in sorted(items, key=key)]


GROUP_SEL_RE = re.compile(r"^\s*Group\s+(\d+)\s*$", re.I)


def apply_layout_order(cmds, layout, groups, default_mode):
    """выбор «Group N» в блоках эффектов → «Fixture a + b + c» в порядке по сцене.
    → (команды, сколько заменено, сводка)"""
    if not layout or not layout.get("fix"):
        return cmds, 0, "порядок по Layout: приборы не расставлены"
    own = layout.get("group_order") or {}
    by_group = {}
    for f in layout["fix"].values():
        by_group.setdefault(f.get("group"), []).append(f)
    out, n, missing = [], 0, set()
    for c in cmds:
        m = GROUP_SEL_RE.match(c)
        if m:
            gid = int(m.group(1))
            mode = own.get(str(gid)) or default_mode
            fixes = by_group.get(gid) or []
            if mode != "по номеру" and len(fixes) > 1:
                ids = order_ids(fixes, mode, layout.get("stage"))
                if ids:
                    out.append("Fixture " + " + ".join(str(i) for i in ids))
                    n += 1
                    continue
            elif mode != "по номеру" and not fixes:
                missing.add(gid)
        out.append(c)
    info = f"порядок по Layout: выбор переписан в {n} эффектах" if n else \
        "порядок по Layout: в командах нет строк «Group N» - пришли экспорт TXT"
    if missing:
        info += f"; в Layout нет приборов групп {', '.join(map(str, sorted(missing)))}"
    return out, n, info


def pt_commands(aims, attrs=None):
    """{id: (pan, tilt)} → команды программера"""
    attrs = attrs or {}
    pan, tilt = attrs.get("pan") or "PAN", attrs.get("tilt") or "TILT"
    out = []
    for fid, (p, t) in aims.items():
        out += [f"Fixture {fid}", f'Attribute "{pan}" At {fx_num(p)}', f'Attribute "{tilt}" At {fx_num(t)}']
    return out


def fx_num(v):
    v = round(float(v), 1)
    return int(v) if v.is_integer() else v


def preset_commands(pool, no, name, body):
    """тело (выбор + значения) → запись пресета. Перед Store выбираются все
    приборы тела, чтобы пресет взял значения каждого"""
    ids = []
    for c in body:
        m = re.match(r"^Fixture\s+(\d+)$", c)
        if m and m.group(1) not in ids:
            ids.append(m.group(1))
    sel = ["Fixture " + " + ".join(ids)] if len(ids) > 1 else []
    return (["ClearAll"] + list(body) + sel + [f"Store Preset {pool}.{no} /o",
                                               f'Label Preset {pool}.{no} "{name}"', "ClearAll"])


GROUP_COLORS = ("#f0a830", "#5fb3f0", "#7ccf7c", "#e06c9f", "#b48cf0", "#f07c5f", "#5fe0d0", "#d0d060",
                "#9fa8b8", "#f0c0a0")


class LayoutTab:
    """вкладка Layout: план сцены сверху, X/Y/Z приборов, follow и пресеты позиций"""
    PAD = 30

    def __init__(self, app, parent):
        self.app = app
        self.L = app.layout
        self.ensure()
        self.sel = set()
        self.target = list(self.L.get("target") or (0.0, _f(self.L["stage"].get("d"), 8) / 2, 1.7))
        self.drag = None
        self.follow_on = False
        self.dirty = False
        self.prev = {}

        left = ttk.Frame(parent)
        left.pack(side="left", fill="both", expand=True, padx=(10, 4), pady=10)
        bar = ttk.Frame(left)
        bar.pack(fill="x")
        self.mode = tk.StringVar(value="place")
        ttk.Radiobutton(bar, text="Расстановка", value="place", variable=self.mode,
                        command=self.draw).pack(side="left")
        ttk.Radiobutton(bar, text="Follow", value="follow", variable=self.mode,
                        command=self.draw).pack(side="left", padx=(6, 14))
        ttk.Label(bar, text="Сцена, м: ширина").pack(side="left")
        self.stage_w = tk.StringVar(value=str(fx_num(self.L["stage"].get("w", 12))))
        self.stage_d = tk.StringVar(value=str(fx_num(self.L["stage"].get("d", 8))))
        ttk.Entry(bar, textvariable=self.stage_w, width=5).pack(side="left", padx=3)
        ttk.Label(bar, text="глубина").pack(side="left")
        ttk.Entry(bar, textvariable=self.stage_d, width=5).pack(side="left", padx=3)
        for v in (self.stage_w, self.stage_d):
            v.trace_add("write", lambda *_: self.on_stage())
        ttk.Button(bar, text="⇩ Патч с пульта", style="Accent.TButton",
                   command=app.pull_patch).pack(side="right")
        ttk.Button(bar, text="Разложить заново", command=self.relayout).pack(side="right", padx=6)
        self.canvas = tk.Canvas(left, bg="#0f1115", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, pady=(6, 0))
        self.hint = ttk.Label(left, text="", style="Muted.TLabel")
        self.hint.pack(fill="x", pady=(4, 0))
        c = self.canvas
        c.bind("<Configure>", lambda e: self.draw())
        c.bind("<ButtonPress-1>", self.on_press)
        c.bind("<B1-Motion>", self.on_drag)
        c.bind("<ButtonRelease-1>", self.on_release)
        c.bind("<MouseWheel>", lambda e: self.on_wheel(1 if e.delta > 0 else -1))
        c.bind("<Button-4>", lambda e: self.on_wheel(1))
        c.bind("<Button-5>", lambda e: self.on_wheel(-1))

        right = ttk.Frame(parent, width=340)
        right.pack(side="left", fill="y", padx=(4, 10), pady=10)
        gbox = ttk.Labelframe(right, text="Группы - щелчок выбирает её приборы")
        gbox.pack(fill="x")
        self.glist = tk.Listbox(gbox, height=7, bg=PANEL, fg=FG, selectbackground=ACCENT,
                                relief="flat", exportselection=False)
        self.glist.pack(fill="x", padx=6, pady=4)
        self.glist.bind("<<ListboxSelect>>", self.on_group)
        row = ttk.Frame(gbox)
        row.pack(fill="x", padx=6, pady=(0, 4))
        ttk.Label(row, text="порядок в эффектах").pack(side="left")
        self.gorder = tk.StringVar(value="как везде")
        cb = ttk.Combobox(row, textvariable=self.gorder, values=("как везде",) + ORDERS, width=16, state="readonly")
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", self.on_gorder)

        fbox = ttk.Labelframe(right, text="Выбранные приборы")
        fbox.pack(fill="x", pady=(8, 0))
        self.sel_lbl = ttk.Label(fbox, text="ничего не выбрано", style="Muted.TLabel")
        self.sel_lbl.grid(row=0, column=0, columnspan=4, sticky="w", padx=6, pady=(2, 4))
        self.v = {k: tk.StringVar() for k in ("x", "y", "z", "rot", "group", "mount")}
        self.inv_pan, self.inv_tilt = tk.BooleanVar(), tk.BooleanVar()
        for i, (k, label) in enumerate((("x", "X, м"), ("y", "Y, м"), ("z", "Z (высота), м"), ("rot", "поворот°"))):
            ttk.Label(fbox, text=label).grid(row=1 + i // 2, column=(i % 2) * 2, sticky="w", padx=6, pady=2)
            ttk.Entry(fbox, textvariable=self.v[k], width=7).grid(row=1 + i // 2, column=(i % 2) * 2 + 1, sticky="w")
        ttk.Label(fbox, text="подвес").grid(row=3, column=0, sticky="w", padx=6, pady=2)
        ttk.Combobox(fbox, textvariable=self.v["mount"], values=MOUNTS, width=6,
                     state="readonly").grid(row=3, column=1, sticky="w")
        ttk.Label(fbox, text="группа").grid(row=3, column=2, sticky="w", padx=6)
        self.gcombo = ttk.Combobox(fbox, textvariable=self.v["group"], width=12, state="readonly")
        self.gcombo.grid(row=3, column=3, sticky="w")
        ttk.Checkbutton(fbox, text="инверсия Pan", variable=self.inv_pan).grid(row=4, column=0, columnspan=2,
                                                                               sticky="w", padx=6)
        ttk.Checkbutton(fbox, text="инверсия Tilt", variable=self.inv_tilt).grid(row=4, column=2, columnspan=2,
                                                                                 sticky="w", padx=6)
        ttk.Button(fbox, text="Применить к выбранным", command=self.apply_fields).grid(
            row=5, column=0, columnspan=4, sticky="w", padx=6, pady=4)

        wbox = ttk.Labelframe(right, text="Follow")
        wbox.pack(fill="x", pady=(8, 0))
        ttk.Label(wbox, text="высота точки, м").grid(row=0, column=0, sticky="w", padx=6, pady=2)
        self.t_z = tk.StringVar(value=str(fx_num(self.target[2])))
        self.t_z.trace_add("write", lambda *_: self.on_tz())
        ttk.Entry(wbox, textvariable=self.t_z, width=6).grid(row=0, column=1, sticky="w")
        ttk.Label(wbox, text="пауза, с").grid(row=0, column=2, sticky="w", padx=6)
        self.f_wait = tk.StringVar(value=str(self.L.get("follow_wait", 0.03)))
        ttk.Entry(wbox, textvariable=self.f_wait, width=5).grid(row=0, column=3, sticky="w")
        self.btn_follow = ttk.Button(wbox, text="▶ Follow", style="Accent.TButton", command=self.toggle_follow)
        self.btn_follow.grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=4)
        ttk.Button(wbox, text="Отпустить (ClearAll)", command=self.release).grid(row=1, column=2, columnspan=2,
                                                                                 sticky="w")

        sbox = ttk.Labelframe(right, text="Шаг угла: каждый следующий прибор поворачивается на шаг")
        sbox.pack(fill="x", pady=(8, 0))
        sp = self.L.get("step") or {}
        self.step_v = {k: tk.StringVar(value=str(sp.get(k, d))) for k, d in
                       (("pan0", 0), ("tilt0", 30), ("dpan", 10), ("dtilt", 0))}
        for i, (k, label) in enumerate((("pan0", "Pan старт°"), ("tilt0", "Tilt старт°"), ("dpan", "шаг Pan°"), ("dtilt", "шаг Tilt°"))):
            ttk.Label(sbox, text=label).grid(row=i // 2, column=(i % 2) * 2, sticky="w", padx=6, pady=2)
            ttk.Entry(sbox, textvariable=self.step_v[k], width=7).grid(row=i // 2, column=(i % 2) * 2 + 1, sticky="w")
        self.step_order = tk.StringVar(value=sp.get("order", STEP_ORDERS[0]))
        ttk.Combobox(sbox, textvariable=self.step_order, values=STEP_ORDERS, width=18,
                     state="readonly").grid(row=2, column=0, columnspan=4, sticky="w", padx=6, pady=2)
        row = ttk.Frame(sbox)
        row.grid(row=3, column=0, columnspan=4, sticky="w", padx=4, pady=(2, 4))
        ttk.Button(row, text="▶ На пульт", command=self.step_send).pack(side="left", padx=2)
        ttk.Button(row, text="💾 В пресет", command=self.step_store).pack(side="left", padx=2)
        ttk.Label(sbox, text="Pan 0 - в зал, + к правому краю сцены; Tilt - от вертикали.\n"
                             "Поворот и инверсии каждого прибора учтены.",
                  style="Muted.TLabel").grid(row=4, column=0, columnspan=4, sticky="w", padx=6, pady=(0, 4))

        pbox = ttk.Labelframe(right, text="Пресеты позиций (Preset 2.x)")
        pbox.pack(fill="x", pady=(8, 0))
        ttk.Label(pbox, text="номер 2.").grid(row=0, column=0, sticky="w", padx=6, pady=2)
        self.p_no = tk.StringVar(value=str(self.L.get("pos_next", 101)))
        ttk.Entry(pbox, textvariable=self.p_no, width=6).grid(row=0, column=1, sticky="w")
        ttk.Label(pbox, text="имя").grid(row=0, column=2, sticky="w", padx=6)
        self.p_name = tk.StringVar(value="Точка")
        ttk.Entry(pbox, textvariable=self.p_name, width=12).grid(row=0, column=3, sticky="w")
        ttk.Button(pbox, text="💾 Сохранить позицию (точка follow)", command=self.store_target).grid(
            row=1, column=0, columnspan=4, sticky="w", padx=6, pady=(4, 2))
        looks = ttk.Frame(pbox)
        looks.grid(row=2, column=0, columnspan=4, sticky="w", padx=4)
        for i, (name, why) in enumerate(POS_LOOKS):
            ttk.Button(looks, text=name, style="Small.TButton",
                       command=lambda n=name: self.store_looks([n])).grid(row=i // 3, column=i % 3, padx=2, pady=2)
        ttk.Button(pbox, text="Все готовые позиции", command=lambda: self.store_looks([n for n, _ in POS_LOOKS])).grid(
            row=3, column=0, columnspan=4, sticky="w", padx=6, pady=(2, 4))
        self.made_lbl = ttk.Label(pbox, text="", style="Muted.TLabel", wraplength=320, justify="left")
        self.made_lbl.grid(row=4, column=0, columnspan=4, sticky="w", padx=6, pady=(0, 4))

        obox = ttk.Labelframe(right, text="Эффекты: порядок приборов")
        obox.pack(fill="x", pady=(8, 0))
        self.order = tk.StringVar(value=self.L.get("order", "по номеру"))
        ob = ttk.Combobox(obox, textvariable=self.order, values=ORDERS, width=18, state="readonly")
        ob.pack(anchor="w", padx=6, pady=4)
        ob.bind("<<ComboboxSelected>>", lambda e: self.save())
        ttk.Label(obox, text="«Group N» в эффекте станет «Fixture …» в этом порядке:\n"
                             "Phase 0 Thru 360 пойдёт по сцене, а не по номерам",
                  style="Muted.TLabel").pack(anchor="w", padx=6, pady=(0, 4))
        self.refresh()

    # ---------------- данные ----------------
    def ensure(self):
        self.L.setdefault("stage", dict(STAGE_DEFAULT))
        self.L.setdefault("fix", {})
        self.L.setdefault("pt", {})
        self.L.setdefault("made", [])
        self.L.setdefault("group_order", {})

    def reload(self):
        """app.layout заменён (настройки, конфиг) - обновить поля и план"""
        self.ensure()
        self.sel.clear()
        self.prev.clear()
        st = self.L["stage"]
        self.stage_w.set(str(fx_num(_f(st.get("w"), 12))))
        self.stage_d.set(str(fx_num(_f(st.get("d"), 8))))
        self.p_no.set(str(self.L.get("pos_next", 101)))
        self.order.set(self.L.get("order", "по номеру"))
        self.f_wait.set(str(self.L.get("follow_wait", 0.03)))
        self.target = list(self.L.get("target") or (0.0, _f(st.get("d"), 8) / 2, 1.7))
        self.t_z.set(str(fx_num(self.target[2])))
        self.refresh()

    def fixes(self):
        return self.L["fix"]

    def groups(self):
        return self.app.cfg.get("groups", [])

    def pt_range(self, ftype):
        return {**PT_DEFAULT, **(self.L["pt"].get(ftype) or {})}

    def can_move(self, f):
        kind, caps = self.app.type_caps(f.get("type") or "")
        return "pt" in caps and kind != "-"

    def save(self):
        self.L["order"] = self.order.get()
        self.L["target"] = list(self.target)
        try:
            self.L["follow_wait"] = float(self.f_wait.get())
        except ValueError:
            pass
        self.app.save_prefs_later()

    def merge(self, fixtures, members):
        kinds = {f.get("type"): self.app.type_caps(f.get("type") or "")[0] for f in fixtures}
        n = merge_layout_fixtures(self.L, fixtures, self.groups(), members, kinds)
        self.save()
        self.refresh()
        return n

    def relayout(self):
        if self.fixes() and not messagebox.askyesno("Layout", "Расставить все приборы заново по группам?"):
            return
        kinds = {f.get("type"): self.app.type_caps(f.get("type") or "")[0] for f in self.fixes().values()}
        auto_place(self.L, self.groups(), kinds)
        self.save()
        self.draw()

    def on_stage(self):
        try:
            self.L["stage"] = {"w": max(1.0, float(self.stage_w.get())), "d": max(1.0, float(self.stage_d.get()))}
        except ValueError:
            return
        self.save()
        self.draw()

    # ---------------- координаты ----------------
    def view(self):
        c = self.canvas
        W, H = max(c.winfo_width(), 200), max(c.winfo_height(), 200)
        w, d = _f(self.L["stage"].get("w"), 12), _f(self.L["stage"].get("d"), 8)
        xs = [abs(_f(f.get("x"))) for f in self.fixes().values()] + [w / 2]
        ys = [_f(f.get("y")) for f in self.fixes().values()] + [0.0, d, self.target[1]]
        x0, x1 = -max(xs) - 1, max(xs) + 1
        y0, y1 = min(min(ys) - 1, -3), max(ys) + 1
        k = min((W - 2 * self.PAD) / (x1 - x0), (H - 2 * self.PAD) / (y1 - y0))
        ox = W / 2
        oy = self.PAD + y1 * k
        return k, ox, oy

    def to_screen(self, x, y):
        k, ox, oy = self.view()
        return ox + x * k, oy - y * k

    def to_world(self, sx, sy):
        k, ox, oy = self.view()
        return (sx - ox) / k, (oy - sy) / k

    # ---------------- рисование ----------------
    def refresh(self):
        gs = self.groups()
        self.glist.delete(0, "end")
        for g in gs:
            n = sum(1 for f in self.fixes().values() if f.get("group") == g["id"])
            self.glist.insert("end", f'{g["id"]}  {g["name"]}  ({n})')
        loose = sum(1 for f in self.fixes().values() if f.get("group") is None)
        if loose:
            self.glist.insert("end", f"без группы  ({loose})")
        self.gcombo["values"] = ["-"] + [f'{g["id"]} {g["name"]}' for g in gs]
        self.show_made()
        self.draw()

    def color(self, gid):
        ids = [g["id"] for g in self.groups()]
        return GROUP_COLORS[ids.index(gid) % len(GROUP_COLORS)] if gid in ids else "#8a909c"

    def draw(self):
        c = self.canvas
        c.delete("all")
        w, d = _f(self.L["stage"].get("w"), 12), _f(self.L["stage"].get("d"), 8)
        k, _, _ = self.view()
        x0, y0 = self.to_screen(-w / 2, d)
        x1, y1 = self.to_screen(w / 2, 0)
        c.create_rectangle(x0, y0, x1, y1, fill="#1a1d24", outline="#3a3f4a")
        for i in range(int(-w // 2), int(w // 2) + 1):
            sx, _ = self.to_screen(i, 0)
            c.create_line(sx, y0, sx, y1, fill="#22262e")
        for j in range(0, int(d) + 1):
            _, sy = self.to_screen(0, j)
            c.create_line(x0, sy, x1, sy, fill="#22262e")
        c.create_line(x0, y1, x1, y1, fill=ACCENT, width=2)
        c.create_text((x0 + x1) / 2, y0 - 10, text="задник", fill=MUTED, font=("Segoe UI", 8))
        c.create_text((x0 + x1) / 2, y1 + 12, text="край сцены · ЗАЛ ↓", fill=MUTED, font=("Segoe UI", 8))
        if not self.fixes():
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2, fill=MUTED, font=("Segoe UI", 11),
                          text="приборов нет - нажмите «⇩ Патч с пульта»")
        follow = self.mode.get() == "follow"
        if follow:
            tx, ty = self.to_screen(self.target[0], self.target[1])
            for fid in self.sel:
                f = self.fixes().get(fid)
                if f and f.get("x") is not None and self.can_move(f):
                    fx_, fy_ = self.to_screen(_f(f["x"]), _f(f["y"]))
                    c.create_line(fx_, fy_, tx, ty, fill="#5a4a20", dash=(3, 3))
        for key, f in self.fixes().items():
            if f.get("x") is None:
                continue
            sx, sy = self.to_screen(_f(f["x"]), _f(f["y"]))
            col = self.color(f.get("group"))
            on = key in self.sel
            r = 7
            shape = c.create_oval if f.get("mount", "верх") != "пол" else c.create_rectangle
            shape(sx - r, sy - r, sx + r, sy + r, fill=col if self.can_move(f) else "#2a2e36",
                  outline="#ffffff" if on else col, width=3 if on else 1, tags=("fix", key))
            c.create_text(sx, sy + 13, text=str(f.get("id")), fill=FG if on else MUTED, font=("Segoe UI", 7))
        if follow:
            tx, ty = self.to_screen(self.target[0], self.target[1])
            c.create_line(tx - 12, ty, tx + 12, ty, fill=ERR, width=2)
            c.create_line(tx, ty - 12, tx, ty + 12, fill=ERR, width=2)
            c.create_text(tx + 16, ty - 10, anchor="w", fill=ERR, font=("Segoe UI", 8),
                          text=f"{fx_num(self.target[0])}; {fx_num(self.target[1])}; h {fx_num(self.target[2])} м")
            self.hint.config(text="Follow: выберите приборы (щелчок по ним или группа справа) и ведите точку мышью; "
                                  "колесо - высота. " + ("● идёт на пульт" if self.follow_on else "▶ Follow - начать"))
        else:
            self.hint.config(text="Щелчок - выбрать, Shift - добавить, тянуть - двигать. ○ - сверху, □ - на полу; "
                                  "серые - без Pan/Tilt")

    def show_sel(self):
        n = len(self.sel)
        fs = [self.fixes()[k] for k in self.sel if k in self.fixes()]
        self.sel_lbl.config(text=("ничего не выбрано" if not n else
                                  f"{n}: " + ", ".join(str(f["id"]) for f in fs[:12]) + (" …" if n > 12 else "")))
        if fs:
            f = fs[0]
            for k in ("x", "y", "z", "rot"):
                vals = {fx_num(_f(x.get(k))) for x in fs}
                self.v[k].set(str(vals.pop()) if len(vals) == 1 else "")
            self.v["mount"].set(f.get("mount", "верх"))
            g = next((g for g in self.groups() if g["id"] == f.get("group")), None)
            self.v["group"].set(f'{g["id"]} {g["name"]}' if g else "-")
            self.inv_pan.set(bool(f.get("inv_pan")))
            self.inv_tilt.set(bool(f.get("inv_tilt")))

    # ---------------- мышь ----------------
    def hit(self, sx, sy):
        best, dist = None, 12
        for key, f in self.fixes().items():
            if f.get("x") is None:
                continue
            fx_, fy_ = self.to_screen(_f(f["x"]), _f(f["y"]))
            d_ = math.hypot(fx_ - sx, fy_ - sy)
            if d_ < dist:
                best, dist = key, d_
        return best

    def on_press(self, e):
        key = self.hit(e.x, e.y)
        shift = bool(e.state & 0x1)
        if self.mode.get() == "follow" and key is None:
            self.move_target(e)
            self.drag = ("target",)
            return
        if key is None:
            if not shift:
                self.sel.clear()
            self.drag = None
        else:
            if shift or self.mode.get() == "follow":
                self.sel.symmetric_difference_update({key})
            elif key not in self.sel:
                self.sel = {key}
            self.drag = ("fix", e.x, e.y) if self.mode.get() == "place" else None
        self.prev.clear()
        self.show_sel()
        self.draw()
        if self.follow_on:
            self.dirty = True

    def on_drag(self, e):
        if not self.drag:
            return
        if self.drag[0] == "target":
            self.move_target(e)
            return
        k, _, _ = self.view()
        dx, dy = (e.x - self.drag[1]) / k, -(e.y - self.drag[2]) / k
        for key in self.sel:
            f = self.fixes().get(key)
            if f is not None:
                f["x"] = round(_f(f.get("x")) + dx, 2)
                f["y"] = round(_f(f.get("y")) + dy, 2)
        self.drag = ("fix", e.x, e.y)
        self.draw()

    def on_release(self, _e):
        if self.drag and self.drag[0] == "fix":
            self.show_sel()
            self.save()
        elif self.drag:
            self.save()
        self.drag = None

    def move_target(self, e):
        x, y = self.to_world(e.x, e.y)
        self.target[0], self.target[1] = round(x, 2), round(y, 2)
        self.dirty = True
        self.draw()

    def on_wheel(self, step):
        if self.mode.get() != "follow":
            return
        self.target[2] = round(max(0.0, self.target[2] + 0.1 * step), 2)
        self.t_z.set(str(fx_num(self.target[2])))

    def on_tz(self):
        try:
            self.target[2] = float(self.t_z.get().replace(",", "."))
        except ValueError:
            return
        self.dirty = True
        self.draw()

    def on_group(self, _e=None):
        s = self.glist.curselection()
        if not s:
            return
        i = s[0]
        gs = self.groups()
        gid = gs[i]["id"] if i < len(gs) else None
        self.sel = {k for k, f in self.fixes().items() if f.get("group") == gid}
        self.gorder.set(self.L["group_order"].get(str(gid), "как везде") if gid is not None else "как везде")
        self.cur_gid = gid
        self.prev.clear()
        self.dirty = True
        self.show_sel()
        self.draw()

    def on_gorder(self, _e=None):
        gid = getattr(self, "cur_gid", None)
        if gid is None:
            return
        v = self.gorder.get()
        if v == "как везде":
            self.L["group_order"].pop(str(gid), None)
        else:
            self.L["group_order"][str(gid)] = v
        self.save()

    def apply_fields(self):
        fs = [self.fixes()[k] for k in self.sel if k in self.fixes()]
        if not fs:
            return
        for k in ("x", "y", "z", "rot"):
            s = self.v[k].get().strip().replace(",", ".")
            if s == "":
                continue
            try:
                val = float(s)
            except ValueError:
                messagebox.showerror("Layout", f"{k}: не число")
                return
            for f in fs:
                f[k] = val
        g = self.v["group"].get()
        gid = None if g in ("", "-") else int(g.split()[0])
        for f in fs:
            f["mount"] = self.v["mount"].get() or f.get("mount", "верх")
            f["inv_pan"], f["inv_tilt"] = bool(self.inv_pan.get()), bool(self.inv_tilt.get())
            if g != "":
                f["group"] = gid
        self.save()
        self.refresh()

    # ---------------- Pan/Tilt ----------------
    def aims(self, keys, target_of):
        out, skipped = {}, []
        for key in sorted(keys, key=lambda k: int(k) if str(k).isdigit() else 0):
            f = self.fixes().get(key)
            if not f or f.get("x") is None or not self.can_move(f):
                continue
            a = aim(f, target_of(f), self.pt_range(f.get("type")), self.prev.get(key))
            if a is None:
                skipped.append(str(f["id"]))
                continue
            self.prev[key] = a
            out[f["id"]] = a
        return out, skipped

    def movers(self):
        keys = self.sel or set(self.fixes())
        return [k for k in keys if k in self.fixes() and self.can_move(self.fixes()[k])]

    # ---------------- follow ----------------
    def toggle_follow(self):
        if self.follow_on:
            self.follow_on = False
            return
        app = self.app
        if not app.ma:
            messagebox.showinfo("Follow", "Сначала подключитесь к пульту.")
            return
        if app.busy():
            messagebox.showinfo("Follow", "Дождитесь окончания текущей операции.")
            return
        if not [k for k in self.sel if k in self.fixes() and self.can_move(self.fixes()[k])]:
            messagebox.showinfo("Follow", "Выберите приборы с Pan/Tilt: щелчком на плане или группой справа.")
            return
        self.mode.set("follow")
        try:
            self.wait_s = max(0.0, float(self.f_wait.get().replace(",", ".")))
        except ValueError:
            self.wait_s = 0.03
        self.follow_on, self.dirty = True, True
        self.btn_follow.config(text="■ Стоп follow")
        ma = app.ma
        attrs = app.cfg.get("attrs", {})

        def run():
            try:
                while self.follow_on:
                    if not self.dirty:
                        time.sleep(0.02)
                        continue
                    self.dirty = False
                    target = tuple(self.target)
                    keys = [k for k in tuple(self.sel) if k in self.fixes()]
                    aims, skipped = self.aims(keys, lambda f: target)
                    wait = self.wait_s
                    for c in pt_commands(aims, attrs):
                        if not self.follow_on:
                            break
                        ma.send(c, wait=wait)
                    if skipped:
                        app.q.put(("log", f"follow: не достают до точки {', '.join(skipped)}", "err"))
            except OSError as e:
                app.q.put(("conn_lost", str(e)))
                app.q.put(("log", f"follow остановлен: {e}", "err"))
            finally:
                self.follow_on = False
                app.q.put(("follow_off",))

        app.run_worker(run)
        self.draw()

    def follow_stopped(self):
        self.btn_follow.config(text="▶ Follow")
        self.draw()

    def release(self):
        if self.follow_on:
            self.follow_on = False
        self.send_list(["ClearAll"], "программер очищен")

    # ---------------- шаг угла ----------------
    def step_params(self):
        out = {}
        for k, v in self.step_v.items():
            try:
                out[k] = float(v.get().strip().replace(",", "."))
            except ValueError:
                messagebox.showerror("Шаг угла", f"{k}: не число")
                return None
        out["order"] = self.step_order.get() or STEP_ORDERS[0]
        self.L["step"] = out
        self.save()
        return out

    def step_aims(self):
        if not self.sel:
            messagebox.showinfo("Шаг угла", "Выберите приборы: щелчком на плане или группой справа.")
            return None
        p = self.step_params()
        if p is None:
            return None
        fixes = [self.fixes()[k] for k in self.movers()]
        aims, skipped = {}, []
        for f, heading, tilt in step_dirs(fixes, p["order"], p["pan0"], p["tilt0"], p["dpan"], p["dtilt"],
                                          self.L.get("stage")):
            a = aim_dir(f, heading, tilt, self.pt_range(f.get("type")))
            if a is None:
                skipped.append(str(f["id"]))
            else:
                aims[f["id"]] = a
        return p, aims, skipped

    def step_send(self):
        r = self.step_aims()
        if not r:
            return
        _p, aims, skipped = r
        if skipped:
            self.app.log_line(f"шаг угла: вне диапазона {', '.join(skipped)}", "err")
        if aims:
            self.send_list(pt_commands(aims, self.app.cfg.get("attrs", {})), f"шаг угла: {len(aims)} приборов")

    def step_store(self):
        r = self.step_aims()
        if not r:
            return
        p, aims, skipped = r
        self.store([(f"Шаг {fx_num(p['dpan'])}°", aims, skipped)])

    # ---------------- пресеты ----------------
    def next_no(self):
        try:
            return int(self.p_no.get())
        except ValueError:
            return int(self.L.get("pos_next", 101))

    def store_target(self):
        keys = self.movers()
        if not self.sel:
            messagebox.showinfo("Пресет", "Выберите приборы, которые светят в точку follow.")
            return
        target = tuple(self.target)
        self.prev.clear()
        aims, skipped = self.aims(keys, lambda f: target)
        self.store([(self.p_name.get().strip() or "Точка", aims, skipped)])

    def store_looks(self, names):
        keys = self.movers()
        jobs = []
        for name in names:
            self.prev.clear()
            aims, skipped = self.aims(keys, lambda f, n=name: look_target(n, f, self.L["stage"]))
            jobs.append((name, aims, skipped))
        self.store(jobs)

    def store(self, jobs):
        jobs = [j for j in jobs if j[1]]
        if not jobs:
            messagebox.showinfo("Пресет", "Нет приборов с Pan/Tilt на плане (или все вне диапазона).")
            return
        no = self.next_no()
        attrs = self.app.cfg.get("attrs", {})
        cmds, made, notes = [], [], []
        for name, aims, skipped in jobs:
            cmds += preset_commands(2, no, name, pt_commands(aims, attrs))
            made.append({"pool": 2, "no": no, "name": name, "fixtures": sorted(aims)})
            if skipped:
                notes.append(f"{name}: не достают {', '.join(skipped)}")
            no += 1
        if not messagebox.askyesno("Пресеты", f"Записать на пульт {len(made)} пресет(ов) позиций: "
                                              + ", ".join(f'2.{m["no"]} {m["name"]}' for m in made)
                                              + "?\nПресеты с этими номерами будут перезаписаны."
                                              + ("\n\n" + "\n".join(notes) if notes else "")):
            return

        def done(errors):
            if errors:
                return
            old = {(m["pool"], m["no"]): m for m in self.L["made"]}
            for m in made:
                old[(m["pool"], m["no"])] = m
            self.L["made"] = sorted(old.values(), key=lambda m: (m["pool"], m["no"]))
            self.L["pos_next"] = no
            self.p_no.set(str(no))
            self.save()
            self.show_made()

        self.send_list(cmds, f"пресеты позиций: {len(made)}", done)

    def show_made(self):
        made = [m for m in self.L.get("made", []) if m.get("pool") == 2]
        self.made_lbl.config(text=("на пульте: " + ", ".join(f'2.{m["no"]} {m["name"]}' for m in made[-12:])
                                   if made else "пресетов позиций ещё нет"))

    def send_list(self, cmds, title, on_done=None):
        app = self.app
        if not app.ma:
            messagebox.showinfo("Пульт", "Сначала подключитесь к пульту.")
            return
        if app.busy():
            if self.follow_on:
                self.follow_on = False
                app.after(300, lambda: self.send_list(cmds, title, on_done))
                return
            messagebox.showinfo("Пульт", "Дождитесь окончания текущей операции.")
            return
        ma = app.ma
        try:
            delay = float(app.conn["delay"].get())
        except ValueError:
            delay = 0.12

        def run():
            errors = 0
            try:
                for c in cmds:
                    r = ma.send(c, wait=delay)
                    r = fx.own_reply(r or "", c) if hasattr(fx, "own_reply") else r
                    if any(w in (r or "").lower() for w in ("error", "illegal", "unknown")):
                        errors += 1
                        app.q.put(("log", f"ERR {c}\n    {fx.clean_text(r).strip()[:200]}", "err"))
                    else:
                        app.q.put(("log", f"ok  {c}", "ok"))
                app.q.put(("log", f"{title}: готово, ошибок {errors}", "err" if errors else "info"))
            except OSError as e:
                errors += 1
                app.q.put(("conn_lost", str(e)))
                app.q.put(("log", f"{title}: связь потеряна ({e})", "err"))
            finally:
                if on_done:
                    app.q.put(("call", on_done, errors))

        app.log_line(f"{title} - {len(cmds)} команд", "info")
        app.run_worker(run)


# =====================================================================
#  ДИАЛОГ ГРУППЫ
# =====================================================================
class GroupDialog(tk.Toplevel):
    def __init__(self, parent, g, lib):
        super().__init__(parent)
        self.g, self.ok, self.lib = g, False, lib
        self.title("Группа")
        self.configure(bg=BG)
        self.transient(parent)
        self.resizable(False, False)
        f = ttk.Frame(scroll_box(self))
        f.pack(padx=14, pady=12)
        self.v = {k: tk.StringVar(value=str(g.get(k, ""))) for k in
                  ("id", "name", "count", "size", "shut_lo", "shut_hi", "phase_shift")}
        labels = (("id", "ID группы в MA2"), ("name", "Имя"), ("count", "Приборов (для превью)"),
                  ("size", "Амплитуда pan/tilt, °"), ("shut_lo", "Shutter low"), ("shut_hi", "Shutter high"),
                  ("phase_shift", "Сдвиг фазы, ° (пусто - авто)"))
        for r, (k, lab) in enumerate(labels):
            ttk.Label(f, text=lab).grid(row=r, column=0, sticky="w", pady=3)
            ttk.Entry(f, textvariable=self.v[k], width=22).grid(row=r, column=1, sticky="w", pady=3)
        r = len(labels)
        ttk.Label(f, text="Возможности").grid(row=r, column=0, sticky="nw", pady=6)
        cf = ttk.Frame(f)
        cf.grid(row=r, column=1, sticky="w")
        self.caps = {c: tk.BooleanVar(value=c in g["caps"]) for c in CAPS}
        for c in CAPS:
            ttk.Checkbutton(cf, text=c, variable=self.caps[c]).pack(side="left", padx=(0, 6))
        r += 1
        ttk.Label(f, text="Шаблоны (ключи через ,\nпусто = все подходящие)").grid(row=r, column=0, sticky="w", pady=6)
        self.tpl = tk.StringVar(value=", ".join(g["templates"]) if g.get("templates") else "")
        ttk.Entry(f, textvariable=self.tpl, width=44).grid(row=r, column=1, pady=6)
        b = ttk.Frame(f)
        b.grid(row=r + 1, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(b, text="Отмена", command=self.destroy).pack(side="right")
        ttk.Button(b, text="OK", style="Accent.TButton", command=self.save).pack(side="right", padx=6)
        self.bind("<Return>", lambda e: self.save())
        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()
        self.wait_window()

    def save(self):
        try:
            for k in ("id", "count"):
                self.g[k] = int(self.v[k].get())
            for k in ("size", "shut_lo", "shut_hi"):
                self.g[k] = fx.num(float(self.v[k].get()))
        except ValueError:
            messagebox.showerror("Группа", "ID, количество и значения должны быть числами", parent=self)
            return
        self.g["name"] = self.v["name"].get().strip() or f'Group {self.g["id"]}'
        ph = self.v["phase_shift"].get().strip()
        try:
            self.g["phase_shift"] = fx.num(float(ph)) if ph else ""
        except ValueError:
            messagebox.showerror("Группа", "Сдвиг фазы - число градусов или пусто", parent=self)
            return
        self.g["caps"] = [c for c in CAPS if self.caps[c].get()]
        keys = [k.strip() for k in self.tpl.get().split(",") if k.strip()]
        bad = [k for k in keys if k not in self.lib]
        if bad:
            messagebox.showerror("Группа", "Неизвестные шаблоны: " + ", ".join(bad), parent=self)
            return
        self.g["templates"] = keys or None
        self.ok = True
        self.destroy()


# =====================================================================
#  ДИАЛОГ СЛОЯ
# =====================================================================
class LayerDialog(tk.Toplevel):
    def __init__(self, parent, layer, lib, own_key, cfg):
        super().__init__(parent)
        self.L, self.ok, self.lib = layer, False, lib
        self.title("Слой")
        self.configure(bg=BG)
        self.transient(parent)
        self.resizable(False, False)
        f = ttk.Frame(scroll_box(self))
        f.pack(padx=14, pady=12)

        is_line = "line" in layer
        self.mode = tk.StringVar(value="line" if is_line else "tpl")
        src = ttk.Labelframe(f, text="Источник")
        src.grid(row=0, column=0, sticky="ew")
        ttk.Radiobutton(src, text="Шаблон", variable=self.mode, value="tpl",
                        command=self.on_mode).grid(row=0, column=0, sticky="w", padx=8, pady=4)
        keys = [k for k in fx.ordered_keys(lib) if k != own_key]
        self.tpl = ttk.Combobox(src, state="readonly", width=28, values=keys)
        self.tpl.set(layer.get("tpl") or keys[0])
        self.tpl.grid(row=0, column=1, columnspan=3, sticky="w", padx=4)
        self.tpl.bind("<<ComboboxSelected>>", lambda e: self.update_hint())
        ttk.Label(src, text="Только атрибуты").grid(row=1, column=0, sticky="w", padx=8)
        af = ttk.Frame(src)
        af.grid(row=1, column=1, columnspan=5, sticky="w")
        self.only = {a: tk.BooleanVar(value=a in (layer.get("attrs") or [])) for a in ATTRS}
        self.only_cb = {}
        for a in ATTRS:
            cb = ttk.Checkbutton(af, text=a, variable=self.only[a])
            cb.pack(side="left", padx=(0, 4))
            self.only_cb[a] = cb
        self.hint = ttk.Label(src, text="", style="Muted.TLabel")
        self.hint.grid(row=2, column=1, columnspan=5, sticky="w", padx=4)

        ttk.Radiobutton(src, text="Своя строка", variable=self.mode, value="line",
                        command=self.on_mode).grid(row=3, column=0, sticky="w", padx=8, pady=(8, 4))
        ln = layer.get("line") or ["dim", "sin", 0, 100, "0 Thru 360", 100]
        lf = ttk.Frame(src)
        lf.grid(row=3, column=1, columnspan=5, sticky="w", pady=(8, 4))
        self.l_attr = ttk.Combobox(lf, state="readonly", width=8, values=ATTRS)
        self.l_attr.set(ln[0])
        self.l_form = ttk.Combobox(lf, state="readonly", width=10, values=list(cfg["forms"]))
        self.l_form.set(ln[1])
        self.l_lo, self.l_hi = tk.StringVar(value=str(ln[2])), tk.StringVar(value=str(ln[3]))
        self.l_phase, self.l_width = tk.StringVar(value=str(ln[4])), tk.StringVar(value=str(ln[5]))
        self.line_w = []
        for lab, w in (("attr", self.l_attr), ("form", self.l_form)):
            ttk.Label(lf, text=lab).pack(side="left", padx=(0, 2))
            w.pack(side="left", padx=(0, 8))
            self.line_w.append(w)
        for lab, var, wd in (("lo", self.l_lo, 7), ("hi", self.l_hi, 7)):
            ttk.Label(lf, text=lab).pack(side="left", padx=(0, 2))
            e = ttk.Entry(lf, textvariable=var, width=wd)
            e.pack(side="left", padx=(0, 8))
            self.line_w.append(e)
        lf2 = ttk.Frame(src)
        lf2.grid(row=4, column=1, columnspan=5, sticky="w", pady=(0, 6))
        ttk.Label(lf2, text="phase").pack(side="left", padx=(0, 2))
        e = ttk.Combobox(lf2, textvariable=self.l_phase, width=14, values=PHASE_PRESETS[1:])
        e.pack(side="left", padx=(0, 8))
        self.line_w.append(e)
        ttk.Label(lf2, text="width").pack(side="left", padx=(0, 2))
        e = ttk.Entry(lf2, textvariable=self.l_width, width=6)
        e.pack(side="left")
        self.line_w.append(e)
        ttk.Label(lf2, text="  lo/hi: число или $size, -$size, $shut_lo, $shut_hi",
                  style="Muted.TLabel").pack(side="left")

        ov = ttk.Labelframe(f, text="Переопределения (пусто = как в источнике)")
        ov.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.o = {k: tk.StringVar(value=show(layer.get(k))) for k in
                  ("bpm", "speed", "phase", "width", "lo", "hi", "scale", "wings", "groups", "blocks")}
        spec = [("bpm", "BPM", 7), ("speed", "×Скорость", 7), ("width", "Width", 7),
                ("lo", "Low", 7), ("hi", "High", 7), ("scale", "Амплитуда %", 7),
                ("wings", "Wings", 5), ("groups", "Groups", 5), ("blocks", "Blocks", 5)]
        for i, (k, lab, w) in enumerate(spec):
            r, c = divmod(i, 3)
            ttk.Label(ov, text=lab).grid(row=r, column=c * 2, sticky="w", padx=(8, 4), pady=3)
            ttk.Entry(ov, textvariable=self.o[k], width=w).grid(row=r, column=c * 2 + 1, sticky="w")
        ttk.Label(ov, text="Phase").grid(row=3, column=0, sticky="w", padx=(8, 4), pady=3)
        ttk.Combobox(ov, textvariable=self.o["phase"], width=16,
                     values=PHASE_PRESETS).grid(row=3, column=1, columnspan=2, sticky="w")
        self.inv = tk.BooleanVar(value=bool(layer.get("invert")))
        ttk.Checkbutton(ov, text="Инвертировать (low ↔ high)", variable=self.inv).grid(
            row=3, column=3, columnspan=3, sticky="w", padx=8)
        ttk.Label(ov, text="×Скорость умножает BPM (0.5 = вдвое медленнее). Wings/Groups/Blocks: -1 = убрать.",
                  style="Muted.TLabel").grid(row=4, column=0, columnspan=6, sticky="w", padx=8, pady=(4, 6))

        b = ttk.Frame(f)
        b.grid(row=2, column=0, sticky="e", pady=(10, 0))
        ttk.Button(b, text="Отмена", command=self.destroy).pack(side="right")
        ttk.Button(b, text="OK", style="Accent.TButton", command=self.save).pack(side="right", padx=6)
        self.bind("<Escape>", lambda e: self.destroy())
        self.on_mode()
        self.grab_set()
        self.wait_window()

    def on_mode(self):
        tpl_on = self.mode.get() == "tpl"
        self.tpl.config(state="readonly" if tpl_on else "disabled")
        for cb in self.only_cb.values():
            cb.config(state="normal" if tpl_on else "disabled")
        for w in self.line_w:
            w.config(state=("readonly" if isinstance(w, ttk.Combobox) and w in (self.l_attr, self.l_form)
                            else "normal") if not tpl_on else "disabled")
        self.update_hint()

    def update_hint(self):
        if self.mode.get() != "tpl":
            self.hint.config(text="")
            return
        t = self.lib.get(self.tpl.get())
        try:
            attrs = [l["attr"] for l in fx.resolved_lines(t, self.lib)[0]]
        except ValueError:
            attrs = []
        self.hint.config(text="в шаблоне: " + ", ".join(attrs) + "   (ничего не отмечено = все)")

    def save(self):
        L = {}
        try:
            if self.mode.get() == "tpl":
                L["tpl"] = self.tpl.get()
                only = [a for a in ATTRS if self.only[a].get()]
                if only:
                    L["attrs"] = only
            else:
                lo, hi = parse_val(self.l_lo.get()), parse_val(self.l_hi.get())
                w = parse_val(self.l_width.get())
                if lo is None or hi is None or w is None or not self.l_phase.get().strip():
                    raise ValueError("у своей строки нужны lo, hi, phase и width")
                L["line"] = [self.l_attr.get(), self.l_form.get(), lo, hi, self.l_phase.get().strip(), w]
            for k in ("bpm", "speed", "width", "lo", "hi", "scale"):
                v = parse_val(self.o[k].get())
                if v is not None:
                    if k not in ("lo", "hi") and isinstance(v, str):
                        raise ValueError(f"{k}: нужно число")
                    L[k] = v
            for k in ("wings", "groups", "blocks"):
                s = self.o[k].get().strip()
                if s:
                    L[k] = int(s)
            ph = self.o["phase"].get().strip()
            if ph:
                fx_ok = all(p.strip().lstrip("-").replace(".", "", 1).isdigit() for p in ph.split("Thru"))
                if not fx_ok:
                    raise ValueError("phase: формат «0» или «0 Thru 360»")
                L["phase"] = ph
            if self.inv.get():
                L["invert"] = True
        except ValueError as e:
            messagebox.showerror("Слой", str(e), parent=self)
            return
        self.L.clear()
        self.L.update(L)
        self.ok = True
        self.destroy()


# =====================================================================
#  ДИАЛОГ ПОДКЛЮЧЕНИЯ (показывается при запуске)
# =====================================================================
class ConnectDialog(tk.Toplevel):
    def __init__(self, app, import_after=None):
        super().__init__(app)
        self.app = app
        self.title("Подключение к grandMA2")
        self.configure(bg=BG)
        self.transient(app)
        self.resizable(False, False)
        f = ttk.Frame(scroll_box(self))
        f.pack(padx=16, pady=14)
        ttk.Label(f, text="Подключение к grandMA2 (Telnet)", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        ttk.Label(f, text="На пульте: Setup → Console → Global Settings → Telnet = Login Enabled",
                  style="Muted.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))
        first = None
        for r, (k, lab) in enumerate((("host", "IP пульта / onPC"), ("port", "Порт"),
                                      ("user", "Пользователь"), ("password", "Пароль")), start=2):
            ttk.Label(f, text=lab).grid(row=r, column=0, sticky="w", pady=3)
            e = ttk.Entry(f, textvariable=app.conn[k], width=24, show="•" if k == "password" else "")
            e.grid(row=r, column=1, sticky="w", pady=3)
            first = first or e
        self.imp = tk.BooleanVar(value=app.prefs.get("import_after_connect", True)
                                 if import_after is None else import_after)
        self.on_start = tk.BooleanVar(value=app.prefs.get("connect_on_start", True))
        ttk.Checkbutton(f, text="После подключения импортировать группы из шоу",
                        variable=self.imp).grid(row=6, column=0, columnspan=2, sticky="w", pady=(10, 2))
        ttk.Checkbutton(f, text="Показывать это окно при запуске",
                        variable=self.on_start).grid(row=7, column=0, columnspan=2, sticky="w")
        self.status = ttk.Label(f, text="", style="Muted.TLabel", wraplength=360)
        self.status.grid(row=8, column=0, columnspan=2, sticky="w", pady=(8, 0))
        b = ttk.Frame(f)
        b.grid(row=9, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(b, text="Работать офлайн", command=self.offline).pack(side="right")
        self.btn = ttk.Button(b, text="Подключиться", style="Accent.TButton", command=self.connect)
        self.btn.pack(side="right", padx=6)
        self.bind("<Return>", lambda e: self.connect())
        self.bind("<Escape>", lambda e: self.offline())
        self.protocol("WM_DELETE_WINDOW", self.offline)
        self.update_idletasks()
        x = app.winfo_rootx() + (app.winfo_width() - self.winfo_width()) // 2
        y = app.winfo_rooty() + 80
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.grab_set()
        first.focus_set()

    def save_flags(self):
        self.app.prefs["import_after_connect"] = self.imp.get()
        self.app.prefs["connect_on_start"] = self.on_start.get()
        self.app.save_prefs()

    def connect(self):
        self.btn.config(state="disabled")
        self.status.config(text="Подключение…", style="Muted.TLabel")
        self.app.connect_async(on_ok=self.ok, on_fail=self.fail)

    def ok(self):
        self.save_flags()
        imp = self.imp.get()
        self.destroy()
        if imp:
            self.app.after(100, self.app.open_import)

    def fail(self, msg):
        if self.winfo_exists():
            self.status.config(text="Не удалось: " + msg, style="Warn.TLabel")
            self.btn.config(state="normal")

    def offline(self):
        self.save_flags()
        self.destroy()


# =====================================================================
#  ДИАЛОГ ИМПОРТА ГРУПП ИЗ ШОУ
# =====================================================================
class ImportGroupsDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app, self.rows = app, []
        app.import_dlg = self
        self.title("Импорт групп из шоу")
        self.configure(bg=BG)
        self.transient(app)
        self.geometry("920x620")
        self.minsize(420, 300)
        f = ttk.Frame(scroll_box(self))
        f.pack(fill="both", expand=True, padx=12, pady=10)

        q = ttk.Labelframe(f, text="Запрос к пульту")
        q.pack(fill="x")
        self.list_cmd = tk.StringVar(value=app.prefs.get("list_cmd", "List Group"))
        self.detail_cmd = tk.StringVar(value=app.prefs.get("detail_cmd", "List Group {id}"))
        self.counts = tk.BooleanVar(value=app.prefs.get("pull_counts", True))
        ttk.Label(q, text="Список групп").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(q, textvariable=self.list_cmd, width=22).grid(row=0, column=1, sticky="w")
        self.btn_q = ttk.Button(q, text="Запросить снова", style="Accent.TButton", command=self.query)
        self.btn_q.grid(row=0, column=2, padx=8, sticky="w")
        ttk.Checkbutton(q, text="Кол-во приборов", variable=self.counts).grid(
            row=1, column=0, sticky="w", padx=8)
        ttk.Entry(q, textvariable=self.detail_cmd, width=22).grid(row=1, column=1, sticky="w")
        ttk.Label(q, text="{id} — номер группы", style="Muted.TLabel").grid(row=1, column=2, sticky="w", padx=8)
        self.prog = ttk.Label(q, text="", style="Muted.TLabel", wraplength=860)
        self.prog.grid(row=2, column=0, columnspan=3, sticky="w", padx=8, pady=(2, 4))

        cols = ("on", "id", "name", "count", "caps", "status")
        heads = ("✓", "ID", "Имя", "Приборов", "Возможности (угаданы)", "Статус")
        widths = (34, 45, 180, 70, 150, 300)
        tf = ttk.Frame(f)
        tf.pack(fill="both", expand=True, pady=(8, 0))
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", selectmode="extended")
        for c, h, w in zip(cols, heads, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="center" if c in ("on", "id", "count") else "w",
                             stretch=c == "status")
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.tree.tag_configure("off", foreground="#6b707a")
        self.tree.tag_configure("new", foreground="#7ccf7c")
        self.tree.bind("<Button-1>", self.on_click)
        self.tree.bind("<Double-1>", self.on_double)

        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=6)
        ttk.Button(bar, text="Все", style="Small.TButton", command=lambda: self.set_all(True)).pack(side="left")
        ttk.Button(bar, text="Ничего", style="Small.TButton", command=lambda: self.set_all(False)).pack(side="left", padx=4)
        ttk.Button(bar, text="Изменить…", style="Small.TButton", command=self.edit_row).pack(side="left", padx=(12, 0))
        ttk.Label(bar, text="Двойной клик — поправить",
                  style="Muted.TLabel").pack(side="left", padx=10)
        self.btn_raw = ttk.Button(bar, text="Ответ пульта ▸", style="Small.TButton", command=self.toggle_raw)
        self.btn_raw.pack(side="right")

        self.raw = tk.Text(f, bg="#0c0d10", fg=MUTED, font=("Consolas", 9), relief="flat", height=8)
        self.raw_shown = False

        bottom = ttk.Frame(f)
        bottom.pack(fill="x", side="bottom", pady=(6, 0))
        self.mode = tk.StringVar(value="merge")
        ttk.Radiobutton(bottom, text="Добавить / обновить",
                        variable=self.mode, value="merge").pack(side="left")
        ttk.Radiobutton(bottom, text="Заменить все группы", variable=self.mode,
                        value="replace").pack(side="left", padx=12)
        ttk.Button(bottom, text="Закрыть", command=self.destroy).pack(side="right")
        self.btn_imp = ttk.Button(bottom, text="Импортировать", style="Accent.TButton",
                                  command=self.do_import, state="disabled")
        self.btn_imp.pack(side="right", padx=6)
        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()
        self.after(100, self.query)

    # ---------------- запрос ----------------
    def query(self):
        p = self.app.prefs
        p["list_cmd"], p["detail_cmd"], p["pull_counts"] = \
            self.list_cmd.get().strip(), self.detail_cmd.get().strip(), self.counts.get()
        if not self.app.ma:
            self.prog.config(text="Нет подключения к пульту.", style="Warn.TLabel")
            return
        self.btn_q.config(state="disabled")
        self.btn_imp.config(state="disabled")
        self.prog.config(text=f"Запрос «{p['list_cmd']}»…", style="Muted.TLabel")
        self.app.pull_async(p["list_cmd"], p["detail_cmd"] if p["pull_counts"] else "",
                            p["pull_counts"], self.on_pulled)

    def set_progress(self, i, n):
        self.prog.config(text=f"Читаю состав групп: {i} / {n}")

    def on_pulled(self, groups, raw, error):
        if not self.winfo_exists():
            return
        self.btn_q.config(state="normal")
        self.raw.delete("1.0", "end")
        self.raw.insert("1.0", raw or "")
        if error:
            self.prog.config(text="Ошибка: " + error, style="Warn.TLabel")
            return
        if not groups:
            self.prog.config(text="Не удалось разобрать список групп. Открой «Ответ пульта» и проверь "
                                  "команду; пришли этот ответ — подстрою разбор.", style="Warn.TLabel")
            if not self.raw_shown:
                self.toggle_raw()
            return
        existing = {g["id"]: g for g in self.app.cfg["groups"]}
        self.rows = []
        for g in groups:
            ex = existing.get(g["id"])
            a, b = (ex["name"].lower() if ex else ""), g["name"].lower()
            same = ex and (a == b or a in b or b in a)
            row = {"id": g["id"], "name": g["name"], "count": g.get("count"), "on": True,
                   "caps": list(ex["caps"]) if same else g["caps"]}
            if ex and not same:
                row["status"] = f'ID занят «{ex["name"]}» — заменится, возможности угаданы заново'
                row["new"] = True
            elif ex:
                parts = []
                if ex["name"] != g["name"]:
                    parts.append(f'имя «{ex["name"]}» → «{g["name"]}»')
                if g.get("count") and g.get("count") != ex.get("count"):
                    parts.append(f'приборов {ex.get("count", "?")} → {g["count"]}')
                row["status"] = "есть: " + ("; ".join(parts) if parts else "без изменений")
                row["new"] = False
            else:
                row["status"], row["new"] = "новая", True
            self.rows.append(row)
        n_cnt = sum(1 for r in self.rows if r["count"])
        self.prog.config(text=f"Найдено групп: {len(self.rows)}"
                              + (f", кол-во приборов определено у {n_cnt}" if self.counts.get() else "")
                              + ". Возможности новых групп угаданы по имени — проверь.", style="Muted.TLabel")
        self.refresh()
        self.btn_imp.config(state="normal")

    # ---------------- таблица ----------------
    def refresh(self):
        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self.rows):
            tags = [] if r["on"] else ["off"]
            if r.get("new") and r["on"]:
                tags.append("new")
            self.tree.insert("", "end", iid=str(i), tags=tags, values=(
                ON if r["on"] else OFF, r["id"], r["name"], r["count"] or "?",
                " ".join(r["caps"]), r["status"]))
        keep = [s for s in sel if self.tree.exists(s)]
        if keep:
            self.tree.selection_set(keep)

    def on_click(self, e):
        row = self.tree.identify_row(e.y)
        if row and self.tree.identify_column(e.x) == "#1":
            r = self.rows[int(row)]
            r["on"] = not r["on"]
            self.refresh()
            return "break"

    def on_double(self, e):
        row = self.tree.identify_row(e.y)
        if row and self.tree.identify_column(e.x) != "#1":
            self.tree.selection_set(row)
            self.edit_row()

    def set_all(self, v):
        for r in self.rows:
            r["on"] = v
        self.refresh()

    def edit_row(self):
        s = self.tree.selection()
        if not s:
            return
        r = self.rows[int(s[0])]
        tmp = {"id": r["id"], "name": r["name"], "count": r["count"] or 6, "caps": list(r["caps"]),
               "size": 20, "shut_lo": 0, "shut_hi": 100, "templates": None}
        if GroupDialog(self, tmp, self.app.lib()).ok:
            r.update({"name": tmp["name"], "count": tmp["count"], "caps": tmp["caps"]})
            self.refresh()

    def toggle_raw(self):
        if self.raw_shown:
            self.raw.pack_forget()
            self.btn_raw.config(text="Ответ пульта ▸")
        else:
            self.raw.pack(fill="x", pady=(0, 4))
            self.btn_raw.config(text="Ответ пульта ▾")
        self.raw_shown = not self.raw_shown

    def do_import(self):
        rows = [{"id": r["id"], "name": r["name"], "count": r["count"], "caps": r["caps"]}
                for r in self.rows if r["on"]]
        if not rows:
            messagebox.showinfo("Импорт", "Ничего не отмечено.", parent=self)
            return
        replace = self.mode.get() == "replace"
        if replace and not messagebox.askyesno(
                "Импорт", f"Заменить все группы конфига ({len(self.app.cfg['groups'])}) "
                          f"на {len(rows)} из шоу?\nНастройки удалённых групп пропадут.", parent=self):
            return
        self.app.save_prefs()
        self.destroy()
        self.app.apply_imported(rows, replace)




class PatchDialog(tk.Toplevel):
    """патч с пульта: тип прибора → вид и возможности; группа → тип её приборов"""

    def __init__(self, app, fixtures, members, raw, console=None, sizes=None):
        super().__init__(app)
        self.app, self.fixtures, self.raw = app, fixtures, raw
        self.members, self.console, self.sizes = members, console or [], sizes or {}
        self.title("Патч с пульта")
        self.configure(bg=BG)
        self.transient(app)
        self.geometry("1100x680")
        f = ttk.Frame(scroll_box(self))
        f.pack(fill="both", expand=True, padx=12, pady=10)
        counts = {}
        for fx_ in fixtures:
            counts[fx_["type"] or "?"] = counts.get(fx_["type"] or "?", 0) + 1
        self.types = sorted(counts)
        tl = ttk.Labelframe(f, text="Типы приборов в патче - поправь, если угадано неверно (запоминается)")
        tl.pack(fill="x")
        self.kind_vars, self.cap_vars = {}, {}
        ttk.Label(tl, text="тип прибора").grid(row=0, column=0, sticky="w", padx=6)
        ttk.Label(tl, text="шт").grid(row=0, column=1)
        ttk.Label(tl, text="вид").grid(row=0, column=2)
        for j, c in enumerate(CAPS):
            ttk.Label(tl, text=c).grid(row=0, column=3 + j, padx=2)
        ttk.Label(tl, text="Pan°").grid(row=0, column=3 + len(CAPS), padx=(8, 2))
        ttk.Label(tl, text="Tilt°").grid(row=0, column=4 + len(CAPS), padx=2)
        self.pt_vars = {}
        if not fixtures:
            ttk.Label(tl, text="приборы не разобраны - ответ пульта ниже; пришли его, подстрою разбор",
                      foreground=ERR).grid(row=1, column=0, columnspan=8, sticky="w", padx=6, pady=4)
        for i, t in enumerate(self.types, start=1):
            kind, caps = app.type_caps(t)
            ttk.Label(tl, text=t[:40]).grid(row=i, column=0, sticky="w", padx=6)
            ttk.Label(tl, text=str(counts[t])).grid(row=i, column=1)
            kv = tk.StringVar(value=kind)
            ttk.Combobox(tl, textvariable=kv, values=KINDS, width=6, state="readonly").grid(row=i, column=2, padx=4)
            self.kind_vars[t] = kv
            self.cap_vars[t] = {}
            for j, c in enumerate(CAPS):
                v = tk.BooleanVar(value=c in caps)
                ttk.Checkbutton(tl, variable=v).grid(row=i, column=3 + j)
                self.cap_vars[t][c] = v
            rng = {**PT_DEFAULT, **(app.layout.get("pt", {}).get(t) or {})}
            pv, tv = tk.StringVar(value=str(fx_num(rng["pan"]))), tk.StringVar(value=str(fx_num(rng["tilt"])))
            ttk.Entry(tl, textvariable=pv, width=5).grid(row=i, column=3 + len(CAPS), padx=(8, 2))
            ttk.Entry(tl, textvariable=tv, width=5).grid(row=i, column=4 + len(CAPS), padx=2)
            self.pt_vars[t] = (pv, tv)
        gl = ttk.Labelframe(f, text="Группы генератора")
        gl.pack(fill="x", pady=(10, 0))
        matched = match_group_types(app.cfg["groups"], fixtures, members)
        self.group_vars = {}
        choices = ["-"] + self.types
        for i, g in enumerate(app.cfg["groups"]):
            m = matched.get(g["id"], {})
            ttk.Label(gl, text=f'{g["id"]}  {g["name"]}').grid(row=i, column=0, sticky="w", padx=6, pady=1)
            v = tk.StringVar(value=m.get("type") or g.get("fixture_type") or "-")
            ttk.Combobox(gl, textvariable=v, values=choices, width=34, state="readonly").grid(row=i, column=1, padx=6)
            note = m.get("how", "не найдено") + (" · ⚠ разные приборы в группе" if m.get("mixed") else "")
            ttk.Label(gl, text=note, style="Muted.TLabel").grid(row=i, column=2, sticky="w")
            self.group_vars[g["id"]] = (v, self.sizes.get(g["id"]) or m.get("count"))
        if self.console:
            cl = ttk.Labelframe(f, text="Группы на пульте")
            cl.pack(fill="x", pady=(10, 0))
            self.console_types = match_group_types(self.console, fixtures, members)
            mine = {g["id"] for g in app.cfg["groups"]}
            self.console_vars = {}
            for i, g in enumerate(self.console):
                m = self.console_types.get(g["id"], {})
                v = tk.BooleanVar(value=g["id"] not in mine)
                self.console_vars[g["id"]] = v
                ttk.Checkbutton(cl, variable=v, text=f'{g["id"]}  {g["name"][:30]}').grid(
                    row=i // 2, column=(i % 2) * 2, sticky="w", padx=6, pady=1)
                n = g.get("count") or m.get("count")
                note = (f"{n} шт · " if n else "") + (m.get("type") or "тип не найден")[:24] + \
                       (" · уже есть" if g["id"] in mine else "")
                ttk.Label(cl, text=note, style="Muted.TLabel").grid(row=i // 2, column=(i % 2) * 2 + 1,
                                                                    sticky="w", padx=(0, 16))
            ttk.Button(cl, text="➕ Взять отмеченные группы в генератор", command=self.take_console).grid(
                row=(len(self.console) + 1) // 2, column=0, columnspan=2, sticky="w", padx=6, pady=(4, 2))
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=8)
        ttk.Button(bar, text="Применить к группам", style="Accent.TButton", command=self.apply).pack(side="left")
        if any(fx_.get("pos") for fx_ in fixtures):
            ttk.Button(bar, text="📐 Позиции 3D пульта → Layout", command=self.take_positions).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Закрыть", command=self.destroy).pack(side="left", padx=6)
        ttk.Label(bar, text="Шаблоны, которые приборы группы не умеют, генератор пропустит "
                            "(нет P/T - без движения, нет RGB - цвет даёт колесо в анализаторе)",
                  style="Muted.TLabel").pack(side="left", padx=10)
        txt = tk.Text(f, bg="#0c0d10", fg=MUTED, font=("Consolas", 9), relief="flat", height=10)
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", raw)

    def apply(self):
        app = self.app
        tc = app.prefs.setdefault("type_caps", {})
        pt = app.layout.setdefault("pt", {})
        for t in self.types:
            tc[t] = {"kind": self.kind_vars[t].get(), "caps": [c for c in CAPS if self.cap_vars[t][c].get()]}
            try:
                pt[t] = {"pan": float(self.pt_vars[t][0].get()), "tilt": float(self.pt_vars[t][1].get())}
            except ValueError:
                pass
        changed = 0
        for g in app.cfg["groups"]:
            v, count = self.group_vars.get(g["id"], (None, None))
            t = v.get() if v else "-"
            if t == "-" or t not in tc:
                continue
            g["fixture_type"], g["kind"], g["caps"] = t, tc[t]["kind"], list(tc[t]["caps"])
            if count:
                g["count"] = count
            changed += 1
        app.save_prefs()
        app.refresh_groups()
        app.layout_ui.refresh()
        app.update_status(f"Патч применён: групп {changed}")
        self.destroy()

    def save_types(self):
        tc = self.app.prefs.setdefault("type_caps", {})
        for t in self.types:
            tc[t] = {"kind": self.kind_vars[t].get(), "caps": [c for c in CAPS if self.cap_vars[t][c].get()]}
        return tc

    def take_console(self):
        """группы пульта → группы генератора: имя, число приборов (с инстансами), тип и возможности"""
        app, tc = self.app, self.save_types()
        rows = []
        for g in self.console:
            if not self.console_vars[g["id"]].get():
                continue
            t = self.console_types.get(g["id"], {}).get("type")
            kind, caps = (tc[t]["kind"], list(tc[t]["caps"])) if t in tc else app.type_caps(t or g["name"])
            rows.append({"id": g["id"], "name": g["name"], "caps": caps, "type": t, "kind": kind,
                         "count": g.get("count") or self.console_types.get(g["id"], {}).get("count")})
        if not rows:
            messagebox.showinfo("Патч", "Отметь группы пульта, которые взять.", parent=self)
            return
        app.apply_imported(rows, False)
        by_id = {g["id"]: g for g in app.cfg["groups"]}
        for r in rows:
            if r["type"] and r["id"] in by_id:
                by_id[r["id"]]["fixture_type"], by_id[r["id"]]["kind"] = r["type"], r["kind"]
        app.save_prefs()
        app.refresh_groups()
        app.layout_ui.merge(self.fixtures, self.members)
        self.destroy()
        PatchDialog(app, self.fixtures, self.members, self.raw, self.console, self.sizes)

    def take_positions(self):
        if not messagebox.askyesno("Layout", "Поставить все приборы на вкладке Layout по 3D-позициям из шоу?",
                                   parent=self):
            return
        lay = self.app.layout_ui
        n = console_positions(lay.L, self.fixtures)
        lay.save()
        lay.refresh()
        self.app.update_status(f"Layout: по позициям пульта поставлено {n} приборов")

# «LightDancer_app.exe --fxgen --capture» - сразу окно переноса в Capture
import sys as _sys
if "--capture" in _sys.argv[1:]:
    try:
        import ma2_capture as _cap
        App = _cap.make_app
    except ImportError:
        pass

if __name__ == "__main__":
    App().mainloop()
