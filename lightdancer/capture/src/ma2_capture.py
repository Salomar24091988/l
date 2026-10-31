"""Перенос патча grandMA2 в визуализатор Capture.

Ярлык «Перенос MA2 → Capture» (или в генераторе «Файл → Перенос в Capture…»):
- открыть XML слоя патча из MA2 (Setup → Patch & Fixture Schedule → Export Layer,
  стиль Only XML) и, по желанию, XML групп (Export Group 1 Thru 9999 "capture_groups");
- проверить таблицу: номера, типы, адреса, позиции, повороты, группы;
- «Сохранить CSV для Capture» - файл для Capture: File → Import Fixture Data.
В Capture переносится риг и патч. Кью, эффекты и пресеты остаются в MA2 и
управляют Capture вживую по Art-Net / sACN.
"""
import csv
import glob
import math
import os
import re
import sys
import uuid
import xml.etree.ElementTree as ET
import zipfile

TITLE = "Перенос MA2 → Capture"
FLAG = "--capture"
COLS = ("Fixture ID", "Channel", "Name", "Fixture Type", "Layer", "Universe", "Address", "DMX",
        "Position X", "Position Y", "Position Z", "Rotation X", "Rotation Y", "Rotation Z", "Groups")
AXES = {"same": "как в MA2 (Z - высота, Y - вглубь)",
        "yup": "поменять Y и Z (если приборы легли набок)"}
SEPS = {",": "запятая", ";": "точка с запятой"}
STEPS = ("Проще всего: впишите IP пульта и нажмите «Взять патч с пульта» (номера, типы, адреса, позиции).\n"
         "1. Или файлом из MA2: Setup → Patch & Fixture Schedule → выбрать слой → Export Layer → Only XML.\n"
         "   Группы: в командной строке  Export Group 1 Thru 9999 \"capture_groups\"  (их видно только в CSV)\n"
         "   onPC на этом ПК: «Открыть XML / CSV…» сразу открывает его папку importexport. Подходит и ma2_patch_diag.txt.\n"
         "   CSV с позициями (PosX/PosY/PosZ, Position X…, X/Y/Z): можно открыть после патча с пульта - позиции допишутся по номеру прибора.\n"
         "2. Здесь: «Открыть XML / CSV…», проверить таблицу, «Сохранить MVR для Capture…».\n"
         "3. Capture: Файл → Импорт → MVR. Capture попросит один раз сопоставить каждый тип прибора\n"
         "   со своей библиотекой - после этого приборы встают с адресами и позициями.\n"
         "4. Связь: Art-Net или sACN на пульте и в Capture, те же universe.")


def local(tag):
    return tag.rsplit("}", 1)[-1]


def attr(el, *names):
    for n in names:
        v = el.get(n)
        if v not in (None, ""):
            return v
    return ""


def num(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def children(el, name):
    return [c for c in el if local(c.tag) == name]


def descendants(el, name):
    return [c for c in el.iter() if c is not el and local(c.tag) == name]


def parse_addr(text):
    """«513» (абсолютный) или «2.001» → (universe, address)."""
    t = str(text or "").strip()
    m = re.match(r"^(\d+)\s*[./:]\s*(\d+)$", t)
    if m:
        return int(m.group(1)), int(m.group(2))
    if t.isdigit() and int(t) > 0:
        n = int(t)
        return (n - 1) // 512 + 1, (n - 1) % 512 + 1
    return None


def vec(el, name):
    found = descendants(el, name) if el is not None else []
    if not found:
        return None
    e = found[0]
    return tuple(num(e.get(k, 0)) for k in ("x", "y", "z"))


def parse_fixtures(root):
    """Приборы из XML слоя патча MA2."""
    out = []
    parents = {c: p for p in root.iter() for c in p}
    for fx in root.iter():
        if local(fx.tag) != "Fixture":
            continue
        parent = parents.get(fx)
        if parent is not None and local(parent.tag) == "Fixture":
            continue
        fid = attr(fx, "fixture_id", "fix_id", "FixID", "fixid")
        cid = attr(fx, "channel_id", "cha_id", "ChaID", "chaid")
        if not fid and not cid:
            continue
        ft = (children(fx, "FixtureType") or descendants(fx, "FixtureType") or [None])[0]
        ftype = attr(ft, "name") if ft is not None else attr(fx, "fixture_type", "type")
        ftype = re.sub(r"^\d+\s+", "", ftype)       # «3 Mac Quantum Profile Basic» → без номера типа
        layer = attr(parent, "name", "index") if parent is not None and local(parent.tag) == "Layer" else ""
        subs = descendants(fx, "SubFixture") or [fx]
        best, pos, rot = None, None, None
        for s in subs:
            patch = (descendants(s, "Patch") or [None])[0]
            a = None
            if patch is not None:
                ad = (descendants(patch, "Address") or [None])[0]
                a = parse_addr(ad.text if ad is not None else attr(patch, "address", "Address"))
            if a and (best is None or a < best):
                best = a
            ap = (descendants(s, "AbsolutePosition") or [s])[0]
            pos = pos or vec(ap, "Location")
            rot = rot or vec(ap, "Rotation")
        out.append({"fid": fid, "cid": cid, "name": attr(fx, "name"), "type": ftype, "layer": layer,
                    "addr": best, "pos": pos or (0.0, 0.0, 0.0), "rot": rot or (0.0, 0.0, 0.0),
                    "has_pos": pos is not None})
    return out


def parse_groups(root):
    """Группы из XML групп MA2: {"F1": ["EV", …], "C101": […]}."""
    groups = {}
    for gr in root.iter():
        if local(gr.tag) != "Group":
            continue
        name = attr(gr, "name") or "Group " + attr(gr, "index")
        seen = set()
        for e in gr.iter():
            f, c = attr(e, "fix_id", "fixture_id"), attr(e, "cha_id", "channel_id")
            key = "F" + f if f else ("C" + c if c else "")
            if key and key not in seen:
                seen.add(key)
                groups.setdefault(key, []).append(name)
    return groups


LIST_ROW = re.compile(
    r"^\s*(?:Fixture|Channel)\s+\d+\s+(?P<name>.*?)\s{2,}(?P<fid>\d+|-)\s+(?P<cid>\d+|-)\s+"
    r"(?P<type>\d+\s+.+?)\s{2,}(?P<patch>\S+)\s+(?:Yes|No)\s+"
    r"(?P<px>-?[\d.]+)\s+(?P<py>-?[\d.]+)\s+(?P<pz>-?[\d.]+)\s+"
    r"(?P<rx>-?[\d.]+)\s+(?P<ry>-?[\d.]+)\s+(?P<rz>-?[\d.]+)")


def parse_list(text):
    """Приборы из ответа пульта «List Fixture» / «List Channel» (или из ma2_patch_diag.txt)."""
    out, seen = [], set()
    for line in text.splitlines():
        m = LIST_ROW.match(line)
        if not m or (m["fid"] == "-" and m["cid"] == "-"):
            continue
        fid, cid = m["fid"].replace("-", ""), m["cid"].replace("-", "")
        if (fid, cid) in seen:
            continue
        seen.add((fid, cid))
        pos = tuple(num(m[k]) for k in ("px", "py", "pz"))
        out.append({"fid": fid, "cid": cid, "name": m["name"].strip(), "type": re.sub(r"^\d+\s+", "", m["type"]),
                    "layer": "", "addr": parse_addr(m["patch"]), "pos": pos,
                    "rot": tuple(num(m[k]) for k in ("rx", "ry", "rz")), "has_pos": any(pos)})
    return out


ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def telnet_lists(host, user="remote", password="1234", port=30000, timeout=6.0):
    """Telnet к grandMA2: «List Fixture» и «List Channel» → текст ответов."""
    import socket
    import time

    def read(sock, idle=0.8, limit=timeout):
        buf, t0, last = b"", time.time(), time.time()
        sock.settimeout(0.2)
        while time.time() - t0 < limit:
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                if buf and time.time() - last > idle:
                    break
                continue
            if not chunk:
                break
            buf, last = buf + chunk, time.time()
        return ANSI.sub("", buf.decode("utf-8", "replace"))

    with socket.create_connection((host, int(port)), timeout=timeout) as sock:
        read(sock, limit=2.0)
        eol = "\r\n"

        def ask(cmd, limit=timeout):
            nonlocal eol
            sock.sendall((cmd + eol).encode("utf-8"))
            reply = read(sock, limit=limit)
            if "ILLEGAL CHARACTER" in reply.upper() and eol == "\r\n":
                eol = "\r"
                sock.sendall((cmd + eol).encode("utf-8"))
                reply = read(sock, limit=limit)
            return reply

        login = ask(f'Login "{user}" "{password}"', 3.0)
        if "Logged in" not in login and "logged in" not in login.lower():
            if "ERROR" in login.upper() or "denied" in login.lower():
                raise RuntimeError("Пульт не пустил: проверьте пользователя и пароль.\n" + login.strip()[-300:])
        return ask("List Fixture", 20.0) + "\n" + ask("List Channel", 20.0)


# колонки CSV: ключ → возможные заголовки (без регистра, пробелов и знаков)
CSV_COLS = {
    "fid": ("fixid", "fixtureid", "fixture", "fixtureno", "fixturenumber", "fix", "id", "unitnumber", "unit"),
    "cid": ("chaid", "chid", "channelid", "channel", "chan", "ch", "channelno"),
    "layer": ("layer", "layername"),
    "name": ("name", "fixturename", "label", "instrumentname"),
    "type": ("fixturetype", "type", "instrumenttype", "model", "fixturemodel", "gdtfspec", "profile"),
    "patch": ("patch", "dmx", "dmxaddress", "absoluteaddress", "address", "addr", "startaddress"),
    "universe": ("universe", "univ", "uni", "dmxuniverse", "line"),
    "px": ("posx", "positionx", "x", "xpos", "locationx", "xlocation", "xposition", "positionxm", "posxm"),
    "py": ("posy", "positiony", "y", "ypos", "locationy", "ylocation", "yposition", "positionym", "posym"),
    "pz": ("posz", "positionz", "z", "zpos", "locationz", "zlocation", "zposition", "height", "positionzm", "poszm"),
    "rx": ("rotx", "rotationx", "rx", "xrotation", "rotationxdeg"),
    "ry": ("roty", "rotationy", "ry", "yrotation", "rotationydeg"),
    "rz": ("rotz", "rotationz", "rz", "zrotation", "rotationzdeg"),
}


def _norm(h):
    return re.sub(r"[^a-zа-я0-9]", "", (h or "").lower().replace("позиция", "position").replace("вращение", "rotation"))


def parse_csv(text):
    """Приборы из CSV (MA2, Capture, Excel, Vectorworks…). Колонки узнаются по заголовкам;
    позиции в миллиметрах (заголовок с «mm») переводятся в метры. → (приборы, найденные колонки)"""
    text = text.lstrip("\ufeff")
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return [], {}
    try:
        dialect = csv.Sniffer().sniff("\n".join(lines[:20]), delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(lines, dialect))
    head = [re.sub(r"(mm|cm|m|deg)$", "", _norm(h)) if re.search(r"(position|pos|rotation|rot|location)[xyz]", _norm(h))
            else _norm(h) for h in rows[0]]
    cols = {}
    for key, names in CSV_COLS.items():
        for n in names:                       # сначала точные имена в порядке важности
            if n in head and head.index(n) not in cols.values():
                cols[key] = head.index(n)
                break
    scale = {k: (0.001 if "mm" in rows[0][i].lower() else 1.0) for k, i in cols.items() if k in ("px", "py", "pz")}

    def cell(row, key):
        i = cols.get(key)
        return row[i].strip() if i is not None and i < len(row) else ""

    out = []
    for row in rows[1:]:
        fid, cid = cell(row, "fid"), cell(row, "cid")
        fid = fid.split(".")[0] if re.fullmatch(r"\d+(\.\d+)?", fid) else ""     # 401.1 (инстанс) → 401
        cid = cid if re.fullmatch(r"\d+", cid) else ""
        if not fid and not cid:
            continue
        addr = parse_addr(cell(row, "patch"))
        uni = cell(row, "universe")
        if uni.isdigit() and cell(row, "patch").isdigit() and int(cell(row, "patch")) <= 512:
            addr = (int(uni), int(cell(row, "patch")))
        has = [cell(row, k) for k in ("px", "py", "pz")]
        pos = tuple(num(cell(row, k)) * scale.get(k, 1.0) for k in ("px", "py", "pz"))
        out.append({"fid": fid, "cid": cid, "name": cell(row, "name"),
                    "type": re.sub(r"\s*\(\d+\)$", "", re.sub(r"^\d+\s+", "", cell(row, "type"))), "layer": cell(row, "layer"), "addr": addr, "pos": pos,
                    "rot": tuple(num(cell(row, k)) for k in ("rx", "ry", "rz")),
                    "has_pos": any(h != "" for h in has)})
    return out, cols


class Rig:
    def __init__(self):
        self.fixtures, self.groups, self.sources = [], {}, []

    def add(self, fx, source):
        """Новые приборы добавляются; у уже загруженных дополняются позиции, адрес, тип."""
        by_fid = {f["fid"]: f for f in self.fixtures if f["fid"]}
        by_cid = {f["cid"]: f for f in self.fixtures if f["cid"]}
        new, upd = 0, 0
        for f in fx:
            old = by_fid.get(f["fid"]) if f["fid"] else by_cid.get(f["cid"])
            if old is None:
                self.fixtures.append(f)
                new += 1
                continue
            if f["has_pos"] and (not old["has_pos"] or not any(old["pos"])):
                old["pos"], old["rot"], old["has_pos"] = f["pos"], f["rot"], True
                upd += 1
            for k in ("addr", "type", "name", "cid", "fid"):
                if f.get(k) and not old.get(k):
                    old[k] = f[k]
        self.sources.append(f"{source}: приборов {new}" + (f", позиции у {upd}" if upd else ""))

    def load(self, path):
        name = os.path.basename(path)
        if path.lower().endswith(".csv"):
            try:
                with open(path, encoding="utf-8-sig", errors="replace") as f:
                    fx, cols = parse_csv(f.read())
            except OSError as e:
                self.sources.append(f"{name}: не прочитан ({e})")
                return
            self.add(fx, name)
            if not fx:
                self.sources[-1] += " (не нашёл колонки номера прибора)"
            elif not any(k in cols for k in ("px", "py", "pz")):
                self.sources[-1] += " (в CSV нет позиций: в CSV из MA2 их нет, откройте XML того же слоя)"
            return
        if not path.lower().endswith(".xml"):
            try:
                with open(path, encoding="utf-8-sig", errors="replace") as f:
                    self.add(parse_list(f.read()), name)
            except OSError as e:
                self.sources.append(f"{name}: не прочитан ({e})")
            return
        try:
            root = ET.parse(path).getroot()
        except (ET.ParseError, OSError) as e:
            self.sources.append(f"{name}: не прочитан ({e})")
            return
        fx, gr = parse_fixtures(root), parse_groups(root)
        self.add(fx, name)
        for k, v in gr.items():
            self.groups.setdefault(k, []).extend(v)
        if gr:
            self.sources[-1] += f", в группах {len(gr)}"

    def rows(self, axes="same"):
        def m(v):
            return (v[0], -v[2], v[1]) if axes == "yup" else v

        def r(n):
            return f"{round(n, 3) + 0.0:g}"

        def key(f):
            return int(f["fid"] or f["cid"] or 0) if (f["fid"] or f["cid"] or "0").isdigit() else 0

        out = []
        for f in sorted(self.fixtures, key=key):
            p, o = m(f["pos"]), m(f["rot"])
            g = self.groups.get("F" + f["fid"], []) + (self.groups.get("C" + f["cid"], []) if f["cid"] else [])
            u, a = f["addr"] or ("", "")
            out.append({"Fixture ID": f["fid"], "Channel": f["cid"], "Name": f["name"], "Fixture Type": f["type"],
                        "Layer": f["layer"], "Universe": u, "Address": a,
                        "DMX": f"{u}.{a:03d}" if f["addr"] else "",
                        "Position X": r(p[0]), "Position Y": r(p[1]), "Position Z": r(p[2]),
                        "Rotation X": r(o[0]), "Rotation Y": r(o[1]), "Rotation Z": r(o[2]),
                        "Groups": " | ".join(dict.fromkeys(g))})
        return out

    def stats(self):
        types = {f["type"] or "?" for f in self.fixtures}
        unp = sum(1 for f in self.fixtures if not f["addr"])
        nopos = sum(1 for f in self.fixtures if not f["has_pos"])
        return (f"Приборов: {len(self.fixtures)}   Типов: {len(types)}   "
                + (f"Без адреса: {unp}   " if unp else "Все с адресом   ")
                + (f"Без позиции: {nopos}   " if nopos else "Позиции есть у всех   ")
                + (f"В группах: {len(self.groups)}" if self.groups else "Группы не загружены"))


def rot_matrix(rx, ry, rz):
    """Повороты MA2 (градусы, X→Y→Z) → базис u, v, w для Matrix в MVR."""
    a, b, c = (math.radians(v) for v in (rx, ry, rz))
    ca, sa, cb, sb, cc, sc = math.cos(a), math.sin(a), math.cos(b), math.sin(b), math.cos(c), math.sin(c)
    m = [[cb * cc, sa * sb * cc - ca * sc, ca * sb * cc + sa * sc],
         [cb * sc, sa * sb * sc + ca * cc, ca * sb * sc - sa * cc],
         [-sb, sa * cb, ca * cb]]                 # Rz · Ry · Rx
    return [[m[0][i], m[1][i], m[2][i]] for i in range(3)]   # столбцы = оси прибора


def mvr_xml(fixtures):
    """GeneralSceneDescription.xml: MVR 1.5. MA2 и MVR: x - вправо, y - вглубь, z - высота;
    метры MA2 → миллиметры MVR. Тип прибора - GDTFSpec по имени типа MA2:
    Capture при импорте попросит сопоставить каждый тип со своей библиотекой."""
    def fmt(v):
        return f"{round(v, 6) + 0.0:g}"

    root = ET.Element("GeneralSceneDescription", verMajor="1", verMinor="5",
                      provider="MusicAnalyzer", providerVersion="ma2_capture")
    layers = ET.SubElement(ET.SubElement(root, "Scene"), "Layers")
    by_layer = {}
    for f in fixtures:
        by_layer.setdefault(f["layer"] or "MA2", []).append(f)
    for lname, items in by_layer.items():
        kids = ET.SubElement(ET.SubElement(layers, "Layer", name=lname, uuid=str(uuid.uuid4()).upper()), "ChildList")
        for f in items:
            fe = ET.SubElement(kids, "Fixture", name=f["name"] or f"Fixture {f['fid'] or f['cid']}",
                               uuid=str(uuid.uuid4()).upper())
            u, v, w = rot_matrix(*f["rot"])
            o = [c * 1000.0 for c in f["pos"]]
            ET.SubElement(fe, "Matrix").text = "".join("{" + ",".join(fmt(c) for c in vec) + "}"
                                                       for vec in (u, v, w, o))
            ET.SubElement(fe, "GDTFSpec").text = (f["type"] or "Unknown") + ".gdtf"
            ET.SubElement(fe, "GDTFMode").text = f["type"] or "Default"
            if f["addr"]:
                adr = ET.SubElement(fe, "Addresses")
                ET.SubElement(adr, "Address", attrib={"break": "0"}).text = str((f["addr"][0] - 1) * 512 + f["addr"][1])
            num_id = f["fid"] or f["cid"] or "0"
            ET.SubElement(fe, "FixtureID").text = num_id
            ET.SubElement(fe, "FixtureIDNumeric").text = num_id if num_id.isdigit() else "0"
            ET.SubElement(fe, "UnitNumber").text = f["cid"] if (f["cid"] or "").isdigit() else "0"
    ET.indent(root)
    return b'<?xml version="1.0" encoding="UTF-8" standalone="no" ?>\n' + ET.tostring(root, encoding="utf-8")


def write_mvr(path, fixtures):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("GeneralSceneDescription.xml", mvr_xml(fixtures))


def write_csv(path, rows, sep=","):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter=sep)
        w.writeheader()
        w.writerows(rows)


CFG = os.path.join(os.path.expanduser("~"), ".ma2_capture.json")


def load_cfg():
    import json
    try:
        with open(CFG, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_cfg(data):
    import json
    try:
        with open(CFG, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


def importexport_dir():
    """Папка importexport grandMA2 onPC (самая новая версия), если есть."""
    base = os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "MA Lighting Technologies", "grandma")
    found = sorted(glob.glob(os.path.join(base, "gma2_V_*", "importexport")))
    return found[-1] if found else (base if os.path.isdir(base) else os.path.expanduser("~"))


def build(win, rig=None, fetch=None):
    """Окно переноса в win (Tk или Toplevel). fetch() → пути XML с пульта (из генератора)."""
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    rig = rig or Rig()
    win.title(TITLE)
    win.geometry("1180x620")
    top = ttk.Frame(win, padding=8)
    top.pack(fill="x")
    ttk.Button(top, text="Открыть XML / CSV…", command=lambda: open_xml()).pack(side="left")
    if fetch:
        ttk.Button(top, text="Взять с пульта (onPC)", command=lambda: pull()).pack(side="left", padx=(6, 0))
    ttk.Button(top, text="Очистить", command=lambda: clear()).pack(side="left", padx=6)
    ttk.Label(top, text="Оси:").pack(side="left", padx=(12, 2))
    axes = tk.StringVar(value=AXES["same"])
    cb = ttk.Combobox(top, textvariable=axes, values=list(AXES.values()), state="readonly", width=38)
    cb.pack(side="left")
    ttk.Label(top, text="Разделитель:").pack(side="left", padx=(12, 2))
    sep = tk.StringVar(value=SEPS[","])
    cs = ttk.Combobox(top, textvariable=sep, values=list(SEPS.values()), state="readonly", width=16)
    cs.pack(side="left")
    net = ttk.Frame(win, padding=(8, 0, 8, 6))
    net.pack(fill="x")
    cfg = load_cfg()
    host, user, pwd = (tk.StringVar(value=cfg.get(k, d)) for k, d in
                       (("host", "10.0.0.8"), ("user", "remote"), ("password", "1234")))
    ttk.Label(net, text="Пульт по сети (Telnet):").pack(side="left")
    ttk.Entry(net, textvariable=host, width=14).pack(side="left", padx=(6, 0))
    ttk.Label(net, text="пользователь").pack(side="left", padx=(8, 2))
    ttk.Entry(net, textvariable=user, width=10).pack(side="left")
    ttk.Label(net, text="пароль").pack(side="left", padx=(8, 2))
    ttk.Entry(net, textvariable=pwd, width=8, show="•").pack(side="left")
    ttk.Button(net, text="Взять патч с пульта", command=lambda: pull_net()).pack(side="left", padx=8)
    bar = ttk.Frame(win, padding=(8, 0, 8, 6))
    bar.pack(fill="x")
    ttk.Button(bar, text="Сохранить MVR для Capture…", command=lambda: save_mvr()).pack(side="left")
    ttk.Button(bar, text="Сохранить CSV…", command=lambda: save()).pack(side="left", padx=6)

    stats = tk.StringVar()
    ttk.Label(win, textvariable=stats, padding=(8, 0)).pack(fill="x")
    src = tk.StringVar()
    ttk.Label(win, textvariable=src, padding=(8, 0), foreground="#666").pack(fill="x")

    box = ttk.Frame(win, padding=8)
    box.pack(fill="both", expand=True)
    tree = ttk.Treeview(box, columns=COLS, show="headings")
    for c in COLS:
        tree.heading(c, text=c)
        tree.column(c, width=150 if c in ("Name", "Fixture Type", "Groups") else 72, stretch=c == "Groups")
    ys = ttk.Scrollbar(box, orient="vertical", command=tree.yview)
    xs = ttk.Scrollbar(box, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
    tree.grid(row=0, column=0, sticky="nsew")
    ys.grid(row=0, column=1, sticky="ns")
    xs.grid(row=1, column=0, sticky="ew")
    box.rowconfigure(0, weight=1)
    box.columnconfigure(0, weight=1)
    ttk.Label(win, text=STEPS, padding=8, justify="left").pack(fill="x")

    def axes_key():
        return next(k for k, v in AXES.items() if v == axes.get())

    def sep_key():
        return next(k for k, v in SEPS.items() if v == sep.get())

    def refresh(*_):
        tree.delete(*tree.get_children())
        for row in rig.rows(axes_key()):
            tree.insert("", "end", values=[row[c] for c in COLS])
        stats.set(rig.stats() if rig.fixtures or rig.groups else "Откройте XML слоя патча из MA2 (и XML групп)")
        src.set("  ·  ".join(rig.sources))

    def open_xml():
        paths = filedialog.askopenfilenames(parent=win, title="XML из grandMA2 (слой патча, группы)",
                                            initialdir=importexport_dir(),
                                            filetypes=[("MA2 XML, CSV или список", "*.xml *.csv *.txt"), ("Все файлы", "*.*")])
        for p in paths:
            rig.load(p)
        refresh()
        if paths and not rig.fixtures:
            messagebox.showwarning(TITLE, "В файлах не нашлось приборов.\n\nНужен XML слоя патча: "
                                   "Setup → Patch & Fixture Schedule → Export Layer → Only XML.", parent=win)

    def pull():
        import threading
        stats.set("Выгружаю патч и группы с пульта…")

        def run():
            try:
                paths, err = fetch(), None
            except Exception as e:
                paths, err = [], str(e)
            win.after(0, lambda: done(paths, err))

        def done(paths, err):
            if err:
                refresh()
                messagebox.showwarning(TITLE, err, parent=win)
                return
            rig.__init__()
            for p in paths:
                rig.load(p)
            refresh()

        threading.Thread(target=run, daemon=True).start()

    def pull_net():
        import threading
        h, u, pw = host.get().strip(), user.get().strip(), pwd.get()
        save_cfg({"host": h, "user": u, "password": pw})
        stats.set(f"Читаю патч с пульта {h}…")

        def run():
            try:
                fx, err = parse_list(telnet_lists(h, u, pw)), None
            except Exception as e:
                fx, err = [], f"Не удалось взять патч с {h}:\n{e}\n\nНа пульте: Setup → Console → Global Settings → Telnet = Login Enabled."
            win.after(0, lambda: done(fx, err))

        def done(fx, err):
            if err or not fx:
                refresh()
                messagebox.showwarning(TITLE, err or "Пульт ответил, но приборов в ответе нет.", parent=win)
                return
            rig.__init__()
            rig.add(fx, f"пульт {h}")
            refresh()

        threading.Thread(target=run, daemon=True).start()

    def clear():
        rig.__init__()
        refresh()

    def save_mvr():
        if not rig.fixtures:
            messagebox.showinfo(TITLE, "Сначала откройте XML слоя патча.", parent=win)
            return
        p = filedialog.asksaveasfilename(parent=win, title="MVR для Capture", defaultextension=".mvr",
                                         initialfile="capture_rig.mvr", filetypes=[("MVR", "*.mvr")])
        if not p:
            return
        try:
            write_mvr(p, sorted(rig.fixtures, key=lambda f: int(f["fid"] or f["cid"] or 0)
                                if (f["fid"] or f["cid"] or "0").isdigit() else 0))
        except OSError as e:
            messagebox.showerror(TITLE, f"Не удалось сохранить:\n{e}", parent=win)
            return
        types = len({f["type"] for f in rig.fixtures})
        messagebox.showinfo(TITLE, f"Сохранено приборов: {len(rig.fixtures)}\n{p}\n\n"
                            f"В Capture: Файл → Импорт → MVR. Capture попросит один раз сопоставить "
                            f"{types} тип(ов) приборов со своей библиотекой.", parent=win)

    def save():
        if not rig.fixtures:
            messagebox.showinfo(TITLE, "Сначала откройте XML слоя патча.", parent=win)
            return
        p = filedialog.asksaveasfilename(parent=win, title="CSV для Capture", defaultextension=".csv",
                                         initialfile="capture_rig.csv", filetypes=[("CSV", "*.csv")])
        if not p:
            return
        try:
            write_csv(p, rig.rows(axes_key()), sep_key())
        except OSError as e:
            messagebox.showerror(TITLE, f"Не удалось сохранить:\n{e}", parent=win)
            return
        messagebox.showinfo(TITLE, f"Сохранено приборов: {len(rig.fixtures)}\n{p}\n\n"
                            "В Capture: File → Import Fixture Data.", parent=win)

    cb.bind("<<ComboboxSelected>>", refresh)
    cs.bind("<<ComboboxSelected>>", refresh)
    refresh()
    return rig


def open_window(master, fetch=None):
    """Окно переноса поверх генератора."""
    import tkinter as tk
    w = tk.Toplevel(master)
    build(w, fetch=fetch)
    return w


def make_app():
    """Отдельное окно: MusicAnalyzer_app.exe --fxgen --capture."""
    import tkinter as tk
    root = tk.Tk()
    build(root)
    return root


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--mvr":
        r = Rig()
        for p in sys.argv[3:]:
            r.load(p)
        write_mvr(sys.argv[2], r.fixtures)
        print(r.stats())
    elif len(sys.argv) > 2 and sys.argv[1] == "--csv":
        r = Rig()
        for p in sys.argv[3:]:
            r.load(p)
        write_csv(sys.argv[2], r.rows())
        print(r.stats())
    else:
        make_app().mainloop()
