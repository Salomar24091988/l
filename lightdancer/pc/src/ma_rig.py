"""Группы приборов, их тип (спот / wash / par) и план сцены сверху.

- «⇩ Группы с пульта»: анализатор шлёт в MA2 «List Group» и разбирает ответ;
  добавляются и группы, которые передал генератор эффектов (с возможностями
  dim / pt / rgb). Тип угадывается по имени и возможностям, его можно сменить.
- План сверху: каждая группа - метка на сцене, её можно перетащить.
  Внизу плана - зрители (перед сценой), вверху - задник.
- Для каждого типа можно отметить, какие эффекты генератора ему подходят.
- Автопилот: у каждого типа свой эффект из подходящих, все эффекты идут по
  кругу (а не только первые три). Новый эффект включается волной по сцене:
  бег - слева направо, поток - от зрителей к заднику, пульс - от центра,
  искры - вразброс. Каждая группа включается своим экзекьютором.
"""
import math
import random
import re
import threading
import time

TYPES = ("spot", "wash", "par")
TYPE_NAMES = {"spot": "спот", "wash": "wash", "par": "par", "": "-"}
TYPE_COLORS = {"spot": "#f0a830", "wash": "#4aa3ff", "par": "#c46cff", "": "#6b707a"}
TOKEN = "fx:"
DEFAULTS = {"gen_main": True,   # генератор главный: анализатор не перекрывает его эффекты
            "rig_groups": [], "rig_allowed": {}, "rig_on": True, "rig_push": True, "rig_anti": True,
            "rig_beam_on": True, "rig_beam_attrs": {}, "rig_beam_looks": [], "rig_beam_assigned": [],
            "rig_beam_page": 0, "rig_beam_presets": True, "rig_preset_start": 101}
DIM_CAT = "dimmer"
# противофаза группа к группе - на бег и поток; пульс и искры бьют вместе
ANTI_RHYTHMS = ("бег", "поток")

# какие категории эффектов генератора подходят группе автопилота
PREFER = {
    "пульс": ("dimmer", "combo", "strobe", "custom"),
    "бег": ("position", "combo", "dimmer", "custom"),
    "поток": ("color", "position", "combo", "custom"),
    "искры": ("strobe", "dimmer", "combo", "custom"),
}


# дорожки: диммер снизу горит всегда; движение, цвет, шаттер и луч идут
# одновременно поверх, у каждой свой повод
TRACKS = ("dim", "move", "color", "shutter", "beam")
TRACK_CATS = {"dim": ("dimmer",), "move": ("position", "combo", "custom"), "color": ("color",),
              "shutter": ("strobe",), "beam": ("beam",)}
TRACK_NAMES = {"dim": "диммер", "move": "движ.", "color": "цвет", "shutter": "шаттер", "beam": "луч"}
ANTI_TRACKS = ("dim", "move", "color")       # шаттер всегда бьёт вместе
BEAM_PEAK_BARS = 4                           # сколько тактов держится призма после пика

# функции луча: ключ → имя атрибута MA2 (меняется в окне «Луч»)
BEAM_ATTRS = {"zoom": "ZOOM", "focus": "FOCUS", "iris": "IRIS", "frost": "FROST1",
              "prism": "PRISMA1", "prism_rot": "PRISMA1_POS", "gobo": "GOBO1", "gobo_rot": "GOBO1_POS",
              "anim": "ANIMATIONWHEEL1", "cto": "CTO"}
BEAM_NAMES = {"zoom": "зум", "focus": "фокус", "iris": "ирис", "frost": "фрост", "prism": "призма",
              "prism_rot": "вращение призмы", "gobo": "гобо", "gobo_rot": "вращение гобо",
              "anim": "анимация", "cto": "CTO"}
# какая возможность прибора нужна функции
BEAM_CAPS = {"zoom": "zoom", "focus": "focus", "iris": "iris", "frost": "frost", "prism": "prism",
             "prism_rot": "prism", "gobo": "gobo", "gobo_rot": "gobo", "anim": "anim", "cto": "cto"}
# если патч не прочитан - что обычно умеет тип прибора
TYPE_BEAM_CAPS = {"spot": ("zoom", "focus", "iris", "frost", "prism", "gobo"), "wash": ("zoom", "frost"), "par": ()}
BEAM_WHEN = {"peak": "пик ударов", "fast": "быстрый темп", "phrase": "новая фраза", "calm": "спокойно"}
BEAM_LOOKS = [
    {"key": "prism", "name": "Призма", "when": "peak", "recipe": "prism=60, prism_rot=75, zoom=35, focus=50"},
    {"key": "prism_zoom", "name": "Призма + зум", "when": "peak", "recipe": "prism=60, prism_rot=30, zoom~Sin 10-60"},
    {"key": "narrow", "name": "Узкий луч", "when": "fast", "recipe": "zoom=0, iris=35, focus=60, frost=0, prism=0"},
    {"key": "zoom_pulse", "name": "Зум-пульс", "when": "fast", "recipe": "zoom~Sin 0-60, focus=55, prism=0"},
    {"key": "gobo", "name": "Гобо", "when": "phrase", "recipe": "gobo=20, gobo_rot=65, focus=70, zoom=30, prism=0"},
    {"key": "gobo_focus", "name": "Гобо + фокус", "when": "phrase", "recipe": "gobo=40, gobo_rot=35, focus~Sin 40-80 x0.5"},
    {"key": "soft", "name": "Мягкий", "when": "calm", "recipe": "frost=70, zoom=100, iris=100, prism=0, gobo=0"},
    {"key": "iris_breath", "name": "Ирис-дыхание", "when": "calm", "recipe": "iris~Sin 20-100 x0.5, zoom=60, prism=0"},
]
RECIPE_ITEM = re.compile(r"^\s*([a-z_]+)\s*(=|~)\s*(.+?)\s*$", re.I)


def parse_recipe(text):
    """«zoom=40, prism=60, iris~Sin 20-100 x0.5» → [(ключ, ("at", 40) | ("fx", форма, lo, hi, множитель))]"""
    out, bad = [], []
    for part in re.split(r"[,;\n]+", text or ""):
        if not part.strip():
            continue
        m = RECIPE_ITEM.match(part)
        key = m.group(1).lower() if m else ""
        if not m or key not in BEAM_ATTRS:
            bad.append(part.strip())
            continue
        if m.group(2) == "=":
            try:
                out.append((key, ("at", float(m.group(3).replace(",", ".")))))
            except ValueError:
                bad.append(part.strip())
            continue
        f = re.match(r"([A-Za-z]+)\s+(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)(?:\s*x\s*(\d+(?:\.\d+)?))?", m.group(3))
        if not f:
            bad.append(part.strip())
            continue
        out.append((key, ("fx", f.group(1).capitalize(), float(f.group(2)), float(f.group(3)),
                          float(f.group(4) or 1))))
    return out, bad


def num(v):
    v = float(v)
    return str(int(v)) if v.is_integer() else f"{v:g}"


def group_beam_caps(gr):
    caps = set(gr.get("caps") or [])
    beam = {c for c in caps if c in set(BEAM_CAPS.values())}
    return beam or set(TYPE_BEAM_CAPS.get(gr.get("type") or "", ()))


# статика луча → пул пресетов MA2: 3 Gobo, 4 Color, 5 Beam, 6 Focus
PRESET_POOL = {"zoom": 6, "focus": 6, "iris": 5, "frost": 5, "prism": 5, "prism_rot": 5,
               "gobo": 3, "gobo_rot": 3, "anim": 3, "cto": 4}
POOL_NAMES = {3: "гобо", 4: "цвет", 5: "луч", 6: "фокус"}
# 4.101-4.172 - палитра RGB, 4.181+ - колесо, поэтому CTO луча - с 4.201
POOL_SHIFT = {4: 100}


def beam_script(s, page, master, bpm=120):
    """эффекты луча → кью на экзекьюторах страницы page: каждый эффект - свой
    экзекьютор, в нём все группы, которые это умеют (статика + эффект-строки).
    Статика сначала пишется в пресеты (Gobo/Color/Beam/Focus), кью ссылается на них"""
    attrs = {**BEAM_ATTRS, **(s.get("rig_beam_attrs") or {})}
    groups = [gr for gr in s.get("rig_groups") or [] if gr.get("type") in TYPES and gr.get("id") is not None]
    use_presets = bool(s.get("rig_beam_presets", True))
    try:
        start = int(s.get("rig_preset_start", 101))
    except (TypeError, ValueError):
        start = 101
    next_no = {}
    out, presets = [], []
    cues, assigned, n = [(f"Store Page {page}", None)], [], 0
    for look in s.get("rig_beam_looks") or BEAM_LOOKS:
        items, _bad = parse_recipe(look.get("recipe"))
        per_group = []
        for gr in groups:
            caps = group_beam_caps(gr)
            mine = [(k, v) for k, v in items if BEAM_CAPS[k] in caps]
            if mine:
                per_group.append((gr, mine))
        if not per_group:
            continue
        refs = {}   # группа → [пресеты]
        if use_presets:
            pools = sorted({PRESET_POOL.get(k, 5) for _, mine in per_group for k, v in mine if v[0] == "at"})
            for pool in pools:
                no = next_no.get(pool, start + POOL_SHIFT.get(pool, 0))
                next_no[pool] = no + 1
                body = []
                for gr, mine in per_group:
                    vals = [(k, v) for k, v in mine if v[0] == "at" and PRESET_POOL.get(k, 5) == pool]
                    if not vals:
                        continue
                    body.append((f"Group {gr['id']}", None))
                    body += [(f'Attribute "{attrs.get(k) or BEAM_ATTRS[k]}" At {num(v[1])}', None) for k, v in vals]
                    refs.setdefault(gr["id"], []).append(f"{pool}.{no}")
                label = f'{look["name"]} - {POOL_NAMES.get(pool, "")}'.strip(" -")
                out += [("ClearAll", None)] + body + [(f"Store Preset {pool}.{no} /o", None),
                                                      (f'Label Preset {pool}.{no} "{label}"', None)]
                presets.append({"pool": pool, "no": no, "name": label})
        lines = []
        for gr, mine in per_group:
            lines.append((f"Group {gr['id']}", None))
            lines += [(f"At Preset {ref}", None) for ref in refs.get(gr["id"], [])]
            for k, v in mine:
                name = attrs.get(k) or BEAM_ATTRS[k]
                if v[0] == "at":
                    if not use_presets:
                        lines.append((f'Attribute "{name}" At {num(v[1])}', None))
                else:
                    _, form, lo, hi, mult = v
                    lines += [(f'Attribute "{name}"', None), (f'At Form "{form}"', None),
                              (f"EffectLow {num(lo)}", None), (f"EffectHigh {num(hi)}", None),
                              (f"EffectBPM {num(round(bpm * mult))}", None)]
        n += 1
        ex = f"{page}.{n}"
        cues += [("ClearAll", None)] + lines + [
            (f"Store Executor {ex} /o", None),
            (f'Label Executor {ex} "луч {look["name"]}"', None),
            (f"Assign Executor {ex} /speedmaster=speed{int(master)}", None)]
        assigned.append({"key": look["key"], "name": look["name"], "when": look.get("when"), "exec": ex})
    out += cues + [("ClearAll", None), (f'Label Page {page} "FX Луч"', None)]
    beam_script.presets = presets
    return out, assigned


class Melody:
    """мелодия по хроме анализатора: хрома тональности - это сумма нот с
    затуханием, поэтому ноты такта = сейчас - затухшее прошлое. Если ноты
    такта заметно не похожи на последние такты - новая фраза."""

    def __init__(self, similar=0.8, min_bars=2):
        self.similar, self.min_bars = similar, min_bars
        self.prev, self.prev_t = None, None
        self.history = []
        self.since = 99
        self.present = False
        self.fresh = False

    def update(self, chroma, now, memory=20.0):
        self.fresh = False
        if chroma is None:
            return False
        try:
            cur = [float(x) for x in chroma]
        except TypeError:
            return False
        if len(cur) != 12:
            return False
        prev, prev_t = self.prev, self.prev_t
        self.prev, self.prev_t = cur, now
        if prev is None:
            return False
        decay = math.exp(-max(now - prev_t, 0.0) / max(memory, 0.5))
        bar = [max(0.0, c - decay * p) for c, p in zip(cur, prev)]
        total = sum(bar)
        self.present = total > 1e-6 * max(1.0, sum(cur))
        self.since += 1
        if not self.present:
            return False
        vec = [x / total for x in bar]
        new = False
        if len(self.history) >= 2 and self.since >= self.min_bars:
            mean = [sum(h[i] for h in self.history) / len(self.history) for i in range(12)]
            dot = sum(a * b for a, b in zip(vec, mean))
            na = math.sqrt(sum(a * a for a in vec)) or 1.0
            nb = math.sqrt(sum(b * b for b in mean)) or 1.0
            if dot / (na * nb) < self.similar:
                new = True
                self.since = 0
                self.history = []
        self.history = (self.history + [vec])[-4:]
        self.fresh = new
        return new


class Tempo:
    """быстрый темп: удары в секунду заметно выше среднего по треку.
    Включение и выключение на разных порогах - шаттер не мигает на границе."""

    def __init__(self, up=1.3, down=1.1, floor=4.0):
        self.up, self.down, self.floor = up, down, floor
        self.mean = None
        self.fast = False
        self.calm = False
        self.value = None

    def update(self, rate):
        if rate is None or rate <= 0:
            return self.fast
        self.value = rate
        self.mean = rate if self.mean is None else 0.9 * self.mean + 0.1 * rate
        if self.fast:
            self.fast = rate >= self.mean * self.down and rate >= self.floor * 0.85
        else:
            self.fast = rate >= max(self.floor, self.mean * self.up)
        self.calm = not self.fast and rate <= self.mean * 0.7
        return self.fast


def hit_rate(features):
    """ударов в секунду за такт: по среднему промежутку, иначе по числу ударов"""
    get = (lambda k: features.get(k)) if isinstance(features, dict) else (lambda k: getattr(features, k, None))
    interval = get("interval_ms")
    try:
        if interval and float(interval) > 1:
            return 1000.0 / float(interval)
    except (TypeError, ValueError):
        pass
    try:
        hits = float(sum(get("hits") or []))
        bpm = float(get("bpm") or 120) or 120
        return hits / (4 * 60.0 / bpm)
    except (TypeError, ValueError):
        return None


class Push:
    """ищет экстремумы частоты ударов: разгон → пик → торможение → минимум.
    Поворот засчитывается, когда частота ушла от экстремума на 12% (и хотя бы
    на 0.3 удара/с) - мелкое дрожание не разворачивает волну."""

    def __init__(self, share=0.12, floor=0.3):
        self.share, self.floor = share, floor
        self.value = None       # сглаженная частота
        self.rising = None
        self.extreme = None
        self.last = None

    def update(self, rate):
        if rate is None or rate <= 0:
            return False
        self.value = rate if self.value is None else 0.5 * self.value + 0.5 * rate
        v = self.value
        if self.extreme is None:
            self.extreme = v
            return False
        gap = max(self.floor, self.share * max(self.extreme, 0.1))
        if self.rising is None:
            if abs(v - self.extreme) >= gap:
                self.rising, self.extreme = v > self.extreme, v
            return False
        if self.rising:
            if v >= self.extreme:
                self.extreme = v
            elif self.extreme - v >= gap:
                self.rising, self.extreme, self.last = False, v, "peak"
                return True
        else:
            if v <= self.extreme:
                self.extreme = v
            elif v - self.extreme >= gap:
                self.rising, self.extreme, self.last = True, v, "min"
                return True
        return False


def guess_type(name, caps=None):
    n = (name or "").lower()
    caps = set(caps or [])
    if re.search(r"wash|уош|вош|вош|заливк", n):
        return "wash"
    if re.search(r"spot|спот|beam|бим|head|голов|\bts\b|moving|mh\b|profile|профил", n):
        return "spot"
    if re.search(r"par|пар|led|лед|rgb|cyc|циклор|bar|бар", n):
        return "par"
    if "pt" in caps and caps & {"wheel", "gobo", "prism"}:
        return "spot"
    if "pt" in caps and "rgb" in caps:
        return "wash"
    if "pt" in caps:
        return "spot"
    if "rgb" in caps or "dim" in caps:
        return "par"
    return ""


def guess_place(name, i, n):
    """начальное место на плане: по словам в имени, иначе в ряд"""
    t = (name or "").lower()
    x = 0.15 + 0.7 * (i + 0.5) / max(1, n)
    y = 0.5
    if re.search(r"front|фронт|перед|передн|аван", t):
        y = 0.85
    elif re.search(r"back|задн|контр|back ?light|top|верх|toplight", t):
        y = 0.15
    if re.search(r"\bleft\b|\bl\b|лев", t):
        x = 0.12
    elif re.search(r"right|\br\b|прав", t):
        x = 0.88
    elif re.search(r"center|centre|центр|mid", t):
        x = 0.5
    return round(x, 3), round(y, 3)


GROUP_LINE = re.compile(r'^\s*(?:group\s+)?(\d{1,4})\s+(?:name\s*=?\s*)?"?([^"\t]*?[^\s"\d][^"\t]*?)"?\s*(?:\s{2,}.*)?$', re.I)
SKIP = re.compile(r"executing|^\[|^no\.?\s|^id\s|^name|pool|^\s*$|error|syntax|ok\s*$|^\d+\s*$", re.I)


def parse_groups(lines):
    """строки ответа MA2 на «List Group» → [{"id", "name"}]"""
    out, seen = [], set()
    for line in lines:
        line = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", line).rstrip()
        line = re.sub(r"^\d\d:\d\d:\d\d\s+", "", line)      # время из журнала
        line = re.sub(r"^\s*\d+h\d+m[\d.]+s\s*:\s?", "", line)  # время из Command Line Feedback
        line = re.sub(r"^\s*Group\s+\d+\s+(?=\d)", "", line, flags=re.I)  # «Group 1 1  SPOT»
        if line.startswith("›") or SKIP.search(line.strip()[:12]):
            continue
        m = GROUP_LINE.match(line)
        if not m:
            continue
        gid, name = int(m.group(1)), m.group(2).strip()
        name = re.split(r"\s{2,}|\t", name)[0].strip()
        if not name or gid in seen or len(name) > 40:
            continue
        seen.add(gid)
        out.append({"id": gid, "name": name})
    return out


def merge_groups(old, found, source=None):
    """добавить найденные группы, не теряя тип и место уже настроенных"""
    by_name = {(g.get("name") or "").lower(): g for g in old}
    by_id = {g.get("id"): g for g in old if g.get("id") is not None}
    out = [dict(g) for g in old]
    index = {id(g): i for i, g in enumerate(old)}
    added = 0
    for f in found:
        g = by_name.get((f.get("name") or "").lower()) or by_id.get(f.get("id"))
        if g is not None:
            i = index[id(g)]
            out[i].update({k: v for k, v in f.items() if v not in (None, "", [])
                           and k in ("id", "caps", "count", "fixture_type")})
            if f.get("x") is not None and f.get("y") is not None:
                # место группы с Layout генератора - главнее угаданного
                out[i]["x"], out[i]["y"] = f["x"], f["y"]
            if f.get("kind") and not out[i].get("type"):
                out[i]["type"] = f["kind"]
            if not out[i].get("name"):
                out[i]["name"] = f.get("name")
            continue
        new = {"id": f.get("id"), "name": f.get("name"), "caps": f.get("caps") or [],
               "count": f.get("count"), "type": f.get("kind") or guess_type(f.get("name"), f.get("caps")),
               "from": source}
        if f.get("x") is not None and f.get("y") is not None:
            new["x"], new["y"] = f["x"], f["y"]
        out.append(new)
        added += 1
    n = len(out)
    for i, g in enumerate(out):
        if g.get("x") is None or g.get("y") is None:
            g["x"], g["y"] = guess_place(g.get("name"), i, n)
    return out, added


def install_grandma2(g):
    if getattr(g, "_rig_installed", False):
        return g
    g._rig_installed = True
    import ma_fxlink
    for k, v in DEFAULTS.items():
        g.DEFAULTS.setdefault(k, v)

    C = g.MA2Control

    def ctl():
        return getattr(g, "_fxlink_ctl", None)

    def rig_active(c):
        s = getattr(c, "settings", None) or {}
        if not (s.get("rig_on", True) and s.get("fxgen_on", True) and s.get("fxgen_assigned")):
            return False
        return any(gr.get("type") and look_execs(s, gr.get("name"))
                   for gr in s.get("rig_groups") or [])

    def look_execs(s, group_name, look=None, anti=False):
        """экзекьюторы группы в эффекте (или во всех эффектах) генератора;
        anti - копия со сдвигом фазы, если генератор её сделал"""
        name = (group_name or "").lower()
        looks = [look] if look else (s.get("fxgen_assigned") or [])
        return [(e.get("alt") if anti and e.get("alt") else e["exec"]) for lk in looks for e in lk.get("execs") or []
                if (e.get("group") or "").lower() == name]

    def allowed(s, typ):
        chosen = (s.get("rig_allowed") or {}).get(typ)
        looks = s.get("fxgen_assigned") or []
        if chosen is None:
            return list(looks)
        keys = set(chosen)
        return [lk for lk in looks if lk.get("key") in keys]

    # --- автопилот: вместо одного экзекьютора - «fx:бег:1», раскладка в switch ---
    previous_fx_exec = g.fx_exec

    def fx_exec(page, group, variant):
        c = ctl()
        if group in PREFER and not getattr(ma_fxlink._local, "creating", False) and rig_active(c):
            return f"{TOKEN}{group}:{int(variant)}"
        if group not in PREFER and not getattr(ma_fxlink._local, "creating", False) and gen_main(c):
            return f"{TOKEN}бег:{int(variant)}"      # свой круговой chase анализатора - эффектами генератора
        return previous_fx_exec(page, group, variant)

    g.fx_exec = fx_exec

    # --- «генератор главный»: свои кью анализатора не перекрывают эффекты генератора ---
    def gen_main(c):
        s = getattr(c, "settings", None) or {}
        return bool(s.get("gen_main", True)) and rig_active(c)

    g.gen_main = gen_main

    def own_gate(self):
        """True - свои кью анализатора (цвет по тону, позиции, заливка) сейчас не шлём;
        при входе в режим один раз гасим то, что они успели включить"""
        on = gen_main(self)
        if on and not self.__dict__.get("_gen_main_on"):
            self.__dict__["_gen_main_on"] = True
            try:
                page = int(self.settings.get("fx_page", 10) or 10)
                execs = [g.pos_exec(page), g.fill_exec(page), g.chase_exec(page, 0), g.chase_exec(page, 1)]
                for ex in dict.fromkeys(execs):
                    self.send(f"Off Executor {ex}")
                if getattr(self, "color_cmd", None):
                    off = g.off_command(self.color_cmd)
                    if off:
                        self.send(off)
                    self.color_cmd = None
                self.add_log("🎛 генератор главный: свои цвета, позиции и заливка анализатора выключены")
            except Exception as e:
                self.add_log(f"⚠ генератор главный: {e}")
        elif not on:
            self.__dict__["_gen_main_on"] = False
        return on

    for name in ("color_apply", "fill_tick", "on_beat"):
        original = getattr(C, name, None)
        if original is None:
            continue

        def make(original):
            def gated(self, *args, **kwargs):
                if own_gate(self):
                    return None
                return original(self, *args, **kwargs)
            return gated

        setattr(C, name, make(original))

    # «fx:…» - не экзекьютор: Go делает switch, Off гасит всё, что включила раскладка
    previous_go, previous_off = g.go_command, g.off_command

    def go_command(cmd):
        if isinstance(cmd, str) and cmd.startswith(TOKEN):
            return None
        return previous_go(cmd)

    def off_command(cmd):
        if isinstance(cmd, str) and cmd.startswith(TOKEN):
            c = ctl()
            if c is not None:
                for ex in getattr(c, "_rig_active", []) or []:
                    c.send(f"Off Executor {ex}")
                c._rig_active, c._rig_active_set = [], set()
            return None
        return previous_off(cmd)

    g.go_command, g.off_command = go_command, off_command

    def pick(counters, key, fit, tried=None, name="key"):
        """все подходящие эффекты по очереди: свой счётчик на дорожку / тип.
        tried - {вариант: сколько раз показан и не сохранён}: такие - реже"""
        counters[key] = counters.get(key, -1) + 1
        start = counters[key] % len(fit)
        if not tried:
            return fit[start]
        ring = fit[start:] + fit[:start]
        best = min(ring, key=lambda lk: int(tried.get(str(lk.get(name)), 0) or 0))
        counters[key] = (start + ring.index(best)) % len(fit)
        return best

    def fan_ids(self):
        fan = getattr(g, "show_fan_groups", None)
        try:
            return {str(x) for x in fan(self)} if fan else set()
        except Exception:
            return set()

    def order(picks, rhythm, direction=1):
        """порядок волны по плану; direction -1 - в обратную сторону"""
        if rhythm == "бег":
            out = sorted(picks, key=lambda p: (p[1], p[2]))
        elif rhythm == "поток":
            out = sorted(picks, key=lambda p: (-p[2], p[1]))   # от зрителей (низ плана) к заднику
        elif rhythm == "пульс":
            out = sorted(picks, key=lambda p: (p[1] - 0.5) ** 2 + (p[2] - 0.5) ** 2)
        else:
            out = list(picks)
            random.Random(len(out)).shuffle(out)
        return out[::-1] if direction < 0 else out

    def fire(self, execs, spread=None):
        """включить волной: вся раскладка укладывается в полдоли"""
        if not execs:
            return
        if spread is None:
            bpm = float(self.bpm_sent or 120) or 120
            spread = min(0.4, 30.0 / max(60.0, bpm))
        if not spread:
            for ex in execs:
                self.send(f"Go Executor {ex}")
            return
        n = len(execs)
        positions = [(spread * i / (n - 1) if n > 1 else 0, ex) for i, ex in enumerate(execs)]
        start = time.time()
        wave = self.__dict__["_rig_wave"] = self.__dict__.get("_rig_wave", 0) + 1

        def run():
            for delay, ex in positions:
                wait = start + delay - time.time()
                if wait > 0:
                    time.sleep(wait)
                if self._rig_wave != wave:
                    return       # уже пошла новая волна
                if ex not in (getattr(self, "_rig_active_set", None) or ()):
                    continue     # уже переключились на другое
                self.send(f"Go Executor {ex}")

        threading.Thread(target=run, daemon=True).start()

    def unique(picks):
        out = []
        for ex, *_ in picks:
            if ex not in out:
                out.append(ex)
        return out

    def state(self):
        st = self.__dict__.get("_rig")
        if st is None:
            st = self._rig = {"layers": {t: [] for t in TRACKS}, "picks": {t: [] for t in TRACKS},
                              "sel": {}, "turn": {}, "why": {}, "rhythm": None, "anti": None,
                              "melody": Melody(), "tempo": Tempo(), "push": Push(),
                              "key_new": False, "fast": False, "beam": None, "peak_hold": 0,
                              "phrase": False}
        return st

    def track_looks(s, track, typ, names):
        cats = TRACK_CATS[track]
        return [lk for lk in allowed(s, typ) if lk.get("cat") in cats
                and any((e.get("group") or "").lower() in names for e in lk.get("execs") or [])]

    def set_layer(self, track, picks, how="together"):
        """включить новое, погасить старое; диммер - сначала новый, потом гасим старый"""
        st = state(self)
        new, old = unique(picks), list(st["layers"][track])
        st["layers"][track], st["picks"][track] = new, picks
        active = []
        for t in TRACKS:
            active += [ex for ex in st["layers"][t] if ex not in active]
        self._rig_active, self._rig_active_set = active, set(active)
        go = [ex for ex in new if ex not in old]
        if how == "dim":
            for ex in go:
                self.send(f"Go Executor {ex}")
        for ex in old:
            if ex not in self._rig_active_set:
                self.send(f"Off Executor {ex}")
        if how == "wave":
            fire(self, go)
        elif how != "dim":
            fire(self, go, spread=0)

    def refresh(self, triggers=(), restart=False):
        """разложить все дорожки по группам: диммер, движение, цвет, шаттер.
        triggers - какие дорожки берут следующий эффект"""
        s, st = self.settings, state(self)
        rhythm = st["rhythm"] or "бег"
        anti = bool(st["anti"])
        groups = [gr for gr in s.get("rig_groups") or [] if gr.get("type") in TYPES]
        fan = fan_ids(self)
        force, avoid = st.get("force") or {}, st.get("avoid") or {}
        why = {}
        shown, used = st.setdefault("shown", {}), st.setdefault("used", set())
        own_dim = set()          # группы, у которых диммер идёт внутри эффекта движения
        # движение - первым: от него зависит, нужен ли группе отдельный диммер
        for track in ("move", "dim", "color", "shutter"):
            picks = []
            for typ in TYPES:
                members = [gr for gr in groups if gr["type"] == typ and look_execs(s, gr.get("name"))]
                if track == "move" and fan:
                    # группы веера держат Pan/Tilt сами - эффекты движения им не включаем
                    members = [gr for gr in members if str(gr.get("id")) not in fan]
                if track == "dim" and own_dim:
                    members = [gr for gr in members if (gr.get("name") or "").lower() not in own_dim]
                names = {(gr.get("name") or "").lower() for gr in members}
                pool = track_looks(s, track, typ, names) if members else []
                on = bool(pool) and (track != "shutter" or st["fast"] or st.get("strobe_force")
                                     or st.get("peak_hold", 0) > 0)
                if track == "color" and getattr(g, "palette_active", None) and g.palette_active(self):
                    on = False      # цвет ведёт палитра Иттена
                if not on:
                    st["sel"].pop((track, typ), None)
                    if track == "dim" and members:
                        why.setdefault(typ, []).append("⚠ без диммера")
                    continue
                keys = [lk.get("key") for lk in pool]
                cur = st["sel"].get((track, typ))
                slot = f"{track}|{typ}"
                if force.get(slot) in keys:
                    cur = st["sel"][(track, typ)] = force[slot]      # 💾 сохранено для этой секции
                elif cur not in keys or track in triggers:
                    # сначала то, что ещё не показывали (все эффекты генератора по кругу),
                    # среди равных - реже сохранённое
                    seen = shown.setdefault((track, typ), {})
                    av = avoid.get(slot) or {}
                    rank = {str(k): int(seen.get(k, 0)) * 1000 + int(av.get(str(k), 0) or 0) for k in keys}
                    cur = st["sel"][(track, typ)] = pick(st["turn"], (track, typ), pool, rank).get("key")
                    seen[cur] = seen.get(cur, 0) + 1
                used.add(cur)
                look = pool[keys.index(cur)]
                why.setdefault(typ, []).append(TRACK_NAMES[track] + " " + look["name"])
                use_alt = anti and track in ANTI_TRACKS
                for gr in members:
                    execs = look_execs(s, gr.get("name"), look, use_alt)
                    if track == "move" and any(e.get("dim") for e in look.get("execs") or []
                                               if (e.get("group") or "").lower() == (gr.get("name") or "").lower()):
                        own_dim.add((gr.get("name") or "").lower())
                    if track == "dim":
                        st.setdefault("dim_by_group", {})[gr.get("id")] = list(execs)
                    for ex in execs:
                        picks.append((ex, float(gr.get("x", 0.5)), float(gr.get("y", 0.5)), typ))
            if track == "move":
                picks = order(picks, rhythm, st.get("dir", 1))
            set_layer(self, track, picks, "dim" if track == "dim" else ("wave" if track == "move" else "together"))
        if restart:
            # фаза сменилась: все слои стартуют разом на первую долю, без волны -
            # иначе задержка волны сдвинула бы фазу
            fire(self, list(self._rig_active), spread=0)
        st["why"] = why
        beam = (" · луч " + st["beam_name"]) if st.get("beam_name") else ""
        total = len(s.get("fxgen_assigned") or [])
        count = f" · показано {len(used)}/{total}" if total else ""
        if total and len(used) >= total and not st.get("all_shown"):
            st["all_shown"] = True
            self.add_log(f"🎛 все {total} эффектов генератора уже были в работе - дальше по второму кругу")
        self._rig_why = " · ".join(f"{TYPE_NAMES[t]}: " + ", ".join(v) for t, v in why.items()) \
            + (" · противофаза" if anti else "") + beam + count

    def all_off(self):
        st = state(self)
        for ex in getattr(self, "_rig_active", []) or []:
            self.send(f"Off Executor {ex}")
        self._rig_active, self._rig_active_set = [], set()
        for t in TRACKS:
            st["layers"][t], st["picks"][t] = [], []
        st["sel"].clear()
        st["rhythm"] = st["anti"] = st["beam"] = None
        st["beam_name"] = ""
        if getattr(g, "show_reset", None):
            try:
                g.show_reset(self)
            except Exception as e:
                self.add_log(f"⚠ сценарий: {e}")
        if getattr(g, "palette_reset", None):
            g.palette_reset(self)

    g.rig_all_off = all_off

    original_switch = C.switch

    def switch(self, new, old, off_prev):
        """автопилот выбрал характер ритма (fx:бег:1): от него - порядок волны,
        противофаза и смена диммера; эффекты дорожек меняет on_bar"""
        is_new = isinstance(new, str) and new.startswith(TOKEN)
        is_old = isinstance(old, str) and old.startswith(TOKEN)
        if not (is_new or is_old):
            return original_switch(self, new, old, off_prev)
        if new == old:
            return None
        if not is_new:
            all_off(self)
            command = g.go_command(new) if new else None
            if command:
                self.send(command)
            return None
        if old and not is_old and off_prev:
            off = g.off_command(old)
            if off:
                self.send(off)
        st = state(self)
        rhythm = new[len(TOKEN):].split(":")[0]
        anti = rhythm in ANTI_RHYTHMS and bool(self.settings.get("rig_anti", True))
        first = st["rhythm"] is None
        triggers = {"dim"} if rhythm != st["rhythm"] else set()
        restart = st["anti"] is not None and anti != st["anti"]
        st["rhythm"], st["anti"] = rhythm, anti
        refresh(self, triggers if not first else (), restart)
        return None

    C.switch = switch

    original_on_key = C.on_key

    def on_key(self, *args, **kwargs):
        state(self)["key_new"] = True
        return original_on_key(self, *args, **kwargs)

    C.on_key = on_key

    original_on_bar = C.on_bar

    def on_bar(self, features, *args, **kwargs):
        result = original_on_bar(self, features, *args, **kwargs)
        cmd = self.auto_cmd
        if isinstance(cmd, str) and cmd.startswith(TOKEN) and state(self)["rhythm"]:
            tracks_bar(self, features)
            if self.auto_why:
                why = getattr(self, "_rig_why", "") or "эффекты генератора"
                self.auto_why = re.sub(r"·\s.*?\(" + re.escape(cmd) + r"\)", "· " + why, self.auto_why, count=1)
        return result

    C.on_bar = on_bar

    def tracks_bar(self, features):
        """раз в такт, на первую долю: у каждой дорожки свой повод"""
        s, st = self.settings, state(self)
        triggers, notes = set(), []
        # движение - по мелодии: новая фраза → следующий эффект движения
        a = getattr(self, "a", None)
        phrase = st["melody"].update(getattr(a, "key_chroma", None), time.time(), melody_memory())
        st["phrase"] = st["melody"].present
        if phrase:
            triggers.add("move")
            if gen_main(self):
                triggers.add("color")     # без палитры цвет генератора тоже меняется по фразам
            notes.append("новая фраза")
        # цвет - по тону: сменилась тональность → следующий цветовой эффект
        if st["key_new"]:
            st["key_new"] = False
            triggers.add("color")
            notes.append("новый тон")
        # шаттер - в быстром темпе
        rate = hit_rate(features)
        fast = st["tempo"].update(rate)
        if fast != st["fast"]:
            st["fast"] = fast
            if fast:
                triggers.add("shutter")
            notes.append("быстрый темп - шаттер" if fast else "темп спал - шаттер выкл")
        # нажим - разворот волны движения в пике и минимуме частоты ударов
        turned = s.get("rig_push", True) and st["push"].update(rate)
        if turned:
            st["dir"] = -st.get("dir", 1)
            notes.append(("пик" if st["push"].last == "peak" else "минимум") + " ударов - волна "
                         + ("→" if st["dir"] > 0 else "←"))
            if st["push"].last == "peak":
                st["peak_hold"] = BEAM_PEAK_BARS
        # сценарий трека из базы и веер: свои поводы дорожкам
        if getattr(g, "show_bar", None):
            try:
                add, drop = g.show_bar(self, st, features, bool(phrase), bool(turned))
                triggers = (triggers | set(add)) - set(drop)
                strobe = bool(st.get("strobe_force"))
                if strobe != bool(st.get("strobe_was")):
                    st["strobe_was"] = strobe
                    if not st["fast"]:
                        triggers.add("shutter")
                        notes.append("сценарий: строб" if strobe else "строб выкл")
            except Exception as e:
                self.add_log(f"⚠ сценарий: {e}")
        beam_bar(self, st)
        peak = st.get("peak_hold", 0) > 0
        if peak != bool(st.get("peak_was")):
            st["peak_was"] = peak
            if not st["fast"]:
                triggers.add("shutter")
                notes.append("пик - строб" if peak else "строб после пика выкл")
        if getattr(g, "palette_bar", None):
            try:
                g.palette_bar(self, st, features, bool(phrase), bool(turned))
            except Exception as e:
                self.add_log(f"⚠ палитра: {e}")
        if triggers or turned or st.get("beam_changed"):
            refresh(self, triggers)
            if turned and "move" not in triggers:
                picks = order(st["picks"]["move"], st["rhythm"] or "", 1)
                picks = picks[::-1] if st.get("dir", 1) < 0 else picks
                st["picks"]["move"] = picks
                fire(self, unique(picks))
        if notes:
            self.add_log("🎚 " + "; ".join(notes))

    def melody_memory():
        import sys
        try:
            return float(getattr(sys.modules.get("music_analyzer"), "KEY_MEMORY", 20.0))
        except (TypeError, ValueError):
            return 20.0

    def beam_bar(self, st):
        """луч: призма в пике ударов, узкий луч в быстром темпе, гобо на фразе,
        мягкий свет в спокойных местах"""
        s = self.settings
        st["beam_changed"] = False
        looks = s.get("rig_beam_assigned") or []
        if not (s.get("rig_beam_on", True) and looks):
            return
        if st["peak_hold"] > 0:
            st["peak_hold"] -= 1
            mode = "peak"
        elif st["fast"]:
            mode = "fast"
        elif st["tempo"].calm:
            mode = "calm"
        elif st["phrase"]:
            mode = "phrase"
        else:
            mode = None
        phrase_new = mode == "phrase" and st["melody"].fresh
        if mode == st["beam"] and not phrase_new:
            return
        pool = [lk for lk in looks if lk.get("when") == mode]
        st["beam"] = mode
        forced = (st.get("force") or {}).get(f"beam|{mode}")
        if not pool:
            st["beam_name"] = ""
            set_layer(self, "beam", [])
        else:
            same = [lk for lk in pool if lk.get("name") == forced]
            look = same[0] if same else pick(st["turn"], ("beam", mode), pool,
                                              (st.get("avoid") or {}).get(f"beam|{mode}"), "name")
            st["beam_name"] = look["name"]
            set_layer(self, "beam", [(look["exec"], 0.5, 0.5, "spot")])
        st["beam_changed"] = True

    original_on_lull = C.on_lull

    def on_lull(self, *args, **kwargs):
        cmd = self.auto_cmd
        if isinstance(cmd, str) and cmd.startswith(TOKEN) and self.autopilot:
            all_off(self)
            st = state(self)
            st["push"], st["tempo"], st["melody"] = Push(), Tempo(), Melody()
            st["fast"], st["peak_hold"] = False, 0
            self.auto_cmd = None
            self.auto_state = {}
            self.auto_why = "тишина"
            self.add_log("🤖 тишина - эффекты генератора выключены")
        return original_on_lull(self, *args, **kwargs)

    C.on_lull = on_lull

    def rig_query(self, done=None, command="List Group"):
        """спросить у MA2 список групп; ответ разбирается из журнала Telnet"""
        if not (self.enabled and self.client.connected):
            if done:
                done(None, "нет связи с MA2")
            return False
        start = time.time()

        def run():
            self.client.send(command)
            last, seen = time.time(), 0
            while time.time() - start < 6:
                time.sleep(0.1)
                lines = [t for when, t in list(self.log_lines) if when >= start]
                if len(lines) != seen:
                    seen, last = len(lines), time.time()
                elif seen and time.time() - last > 0.8:
                    break
            lines = [t for when, t in list(self.log_lines) if when >= start]
            found = parse_groups(lines)
            s = self.settings
            linked = [dict(gr) for gr in s.get("fxgen_groups") or []]
            merged, added = merge_groups(s.get("rig_groups") or [], linked, "генератор")
            merged, added2 = merge_groups(merged, found, "пульт")
            s["rig_groups"] = merged
            g.save_settings(s)
            msg = (f"с пульта: {len(found)} групп" if found else "пульт не прислал список групп (ответ в журнале)") \
                + (f", из генератора: {len(linked)}" if linked else "") + f"; новых {added + added2}"
            self.add_log("🗺 " + msg)
            if done:
                done(found, msg)

        threading.Thread(target=run, daemon=True).start()
        return True

    C.rig_query = rig_query

    def ask(self, command, done):
        """послать команду и собрать ответ из журнала Telnet → done(строки)"""
        start = time.time()

        def run():
            self.client.send(command)
            last, seen = time.time(), 0
            while time.time() - start < 6:
                time.sleep(0.1)
                lines = [t for when, t in list(self.log_lines) if when >= start]
                if len(lines) != seen:
                    seen, last = len(lines), time.time()
                elif seen and time.time() - last > 0.8:
                    break
            done([t for when, t in list(self.log_lines) if when >= start])

        threading.Thread(target=run, daemon=True).start()

    def rig_attr_query(self, done):
        """какие атрибуты луча есть в шоу (List Attribute)"""
        if not (self.enabled and self.client.connected):
            done(None, "нет связи с MA2")
            return False

        def got(lines):
            text = " ".join(lines).upper()
            names = {**BEAM_ATTRS, **(self.settings.get("rig_beam_attrs") or {})}
            found = {k: bool(re.search(r"(?<![A-Z0-9_])" + re.escape(v.upper()) + r"(?![A-Z0-9_])", text))
                     for k, v in names.items()}
            ok = [BEAM_NAMES[k] for k, v in found.items() if v]
            miss = [f"{BEAM_NAMES[k]} ({names[k]})" for k, v in found.items() if not v]
            msg = ("есть: " + ", ".join(ok) if ok else "атрибуты луча не найдены") + \
                  ("; нет: " + ", ".join(miss) if miss else "")
            self.add_log("🔆 List Attribute - " + msg)
            done(found, msg)

        ask(self, "List Attribute", got)
        return True

    C.rig_attr_query = rig_attr_query

    def rig_beam_create(self, done=None):
        """создать эффекты луча на пульте: страница после 5 страниц генератора"""
        s = self.settings
        if not (self.enabled and self.client.connected) or self.fx_busy:
            if done:
                done(["нет связи с MA2" if not self.fx_busy else "пульт занят"])
            return False
        page = int(s.get("rig_beam_page") or 0) or int(s.get("fxgen_page", 11) or 11) + 5
        script, assigned = beam_script(s, page, s.get("speed_master", 1), float(self.bpm_sent or 120) or 120)
        if not assigned:
            if done:
                done(["нет групп с id, которые умеют зум / фокус / призму / гобо - проверьте типы и патч"])
            return False
        self.fx_busy = True

        def run():
            errors = []
            try:
                self.add_log(f"🔆 луч: {len(assigned)} эффектов на страницу {page} ({len(script)} команд)…")
                for command, _ in script:
                    if not self.client.connected:
                        errors.append("связь пропала")
                        break
                    if self.run_checked(command):
                        errors.append(command)
                if self.client.connected:
                    s["rig_beam_assigned"] = assigned
                    g.save_settings(s)
                    self.add_log("🔆 луч готов: " + ", ".join(f"{a['name']} {a['exec']}" for a in assigned))
            finally:
                self.fx_busy = False
                if done:
                    done(errors)

        threading.Thread(target=run, daemon=True).start()
        return True

    C.rig_beam_create = rig_beam_create

    def rig_sync(s):
        """добавить группы генератора без запроса к пульту"""
        linked = [dict(gr) for gr in s.get("fxgen_groups") or []]
        names = {(e.get("group") or "") for lk in s.get("fxgen_assigned") or [] for e in lk.get("execs") or []}
        known = {(gr.get("name") or "").lower() for gr in linked}
        linked += [{"name": n} for n in sorted(names) if n and n.lower() not in known]
        merged, added = merge_groups(s.get("rig_groups") or [], linked, "генератор")
        s["rig_groups"] = merged
        return added

    g.rig_sync = rig_sync
    g.rig_active = rig_active
    g.rig_look_execs = look_execs
    return g


def install_gui(mg):
    if getattr(mg, "_rig_installed", False):
        return mg
    mg._rig_installed = True
    tk = mg.tk
    W = mg.MA2Window
    original_build = W.build

    def build(self, *args, **kwargs):
        result = original_build(self, *args, **kwargs)
        try:
            # кнопка плана - в панель генератора (последняя добавленная панель)
            panels = [w for w in self.body.winfo_children() if isinstance(w, tk.Frame)]
            box = panels[-1] if panels else self.body
            line = tk.Frame(box, bg=mg.PANEL)
            line.pack(fill="x", pady=(4, 0))
            mg.flat_button(line, "🗺 Группы, типы и план сверху…", lambda: RigWindow(self), mg.ACCENT).pack(side="left")
            import grandma2 as g2
            s = self.ma.settings
            groups = s.get("rig_groups") or []
            typed = {t: [gr["name"] for gr in groups if gr.get("type") == t] for t in TYPES}
            text = "  ".join(f"{TYPE_NAMES[t]}: {', '.join(v[:4])}{' …' if len(v) > 4 else ''}"
                             for t, v in typed.items() if v) or "групп пока нет - откройте план и запросите с пульта"
            if groups and not g2.rig_active(self.ma):
                text += "   ⚠ автопилот пока по-старому: нет групп с типом, у которых есть эффекты генератора"
            tk.Label(line, text=text, bg=mg.PANEL, fg=mg.DIM, font=("Segoe UI", 8),
                     anchor="w").pack(side="left", padx=(10, 0))
        except Exception as e:
            try:
                self.ma.add_log(f"⚠ план: {e}")
            except Exception:
                pass
        return result

    W.build = build

    class RigWindow:
        MAP_W, MAP_H = 520, 360

        def __init__(self, owner):
            import grandma2 as g2
            self.g2, self.owner, self.ma = g2, owner, owner.ma
            old = getattr(owner, "_rig_window", None)
            if old is not None:
                try:
                    old.win.lift()
                    return
                except Exception:
                    pass
            owner._rig_window = self
            s = self.ma.settings
            if g2.rig_sync(s):
                g2.save_settings(s)
            self.win = (getattr(mg, "scroll_toplevel", None) or tk.Toplevel)(owner.win)
            self.win.title("Группы, типы и план сверху")
            self.win.configure(bg=mg.BG)
            self.body = self.win
            self.win.protocol("WM_DELETE_WINDOW", self.close)
            top = tk.Frame(self.body, bg=mg.BG)
            top.pack(fill="x", padx=12, pady=(10, 4))
            mg.flat_button(top, "⇩ Группы с пульта", self.query, mg.ACCENT).pack(side="left")
            mg.flat_button(top, "🔆 Луч…", lambda: BeamWindow(self), mg.ACCENT).pack(side="left", padx=(6, 0))
            if getattr(mg, "PaletteWindow", None):
                mg.flat_button(top, "🎨 Палитра…", lambda: mg.PaletteWindow(self),
                               mg.ACCENT).pack(side="left", padx=(6, 0))
            if getattr(mg, "ShowWindow", None):
                mg.flat_button(top, "🎬 Сценарий…", lambda: mg.ShowWindow(self),
                               mg.ACCENT).pack(side="left", padx=(6, 0))
            self.push_var = tk.BooleanVar(value=bool(self.ma.settings.get("rig_push", True)))
            tk.Checkbutton(top, text="нажим (разворот волны в пике и минимуме ударов)",
                           variable=self.push_var, command=self.set_push, bg=mg.BG, fg=mg.TEXT,
                           activebackground=mg.BG, activeforeground=mg.TEXT, selectcolor=mg.OFF,
                           font=("Segoe UI", 9), highlightthickness=0).pack(side="left", padx=(12, 0))
            self.anti_var = tk.BooleanVar(value=bool(self.ma.settings.get("rig_anti", True)))
            tk.Checkbutton(top, text="противофаза на бег и поток", variable=self.anti_var, command=self.set_anti,
                           bg=mg.BG, fg=mg.TEXT, activebackground=mg.BG, activeforeground=mg.TEXT,
                           selectcolor=mg.OFF, font=("Segoe UI", 9), highlightthickness=0).pack(side="left", padx=(8, 0))
            self.main_var = tk.BooleanVar(value=bool(self.ma.settings.get("gen_main", True)))
            tk.Checkbutton(top, text="генератор главный (свои цвета, позиции, палитра и веер не перекрывают его)",
                           variable=self.main_var, command=self.set_main,
                           bg=mg.BG, fg=mg.TEXT, activebackground=mg.BG, activeforeground=mg.TEXT,
                           selectcolor=mg.OFF, font=("Segoe UI", 9), highlightthickness=0).pack(side="left", padx=(8, 0))
            self.status = tk.Label(top, text="", bg=mg.BG, fg=mg.DIM, font=("Segoe UI", 9))
            self.status.pack(side="left", padx=10)
            mid = tk.Frame(self.body, bg=mg.BG)
            mid.pack(fill="both", expand=True, padx=12)
            self.list = tk.Frame(mid, bg=mg.PANEL, padx=8, pady=6)
            self.list.pack(side="left", fill="y")
            right = tk.Frame(mid, bg=mg.BG)
            right.pack(side="left", fill="both", expand=True, padx=(10, 0))
            tk.Label(right, text="ПЛАН СВЕРХУ - перетащите группы туда, где они висят", bg=mg.BG,
                     fg=mg.DIM, font=("Segoe UI", 8, "bold")).pack(anchor="w")
            self.map = tk.Canvas(right, width=self.MAP_W, height=self.MAP_H, bg=mg.PANEL,
                                 highlightthickness=0)
            self.map.pack(anchor="w")
            self.map.bind("<ButtonPress-1>", self.grab)
            self.map.bind("<B1-Motion>", self.drag)
            self.map.bind("<ButtonRelease-1>", self.drop)
            self.dragging = None
            tk.Label(self.body, text="ЭФФЕКТЫ ГЕНЕРАТОРА ПО ТИПАМ - снимите галочку, чтобы тип этот эффект не брал. "
                                    "Dimmer горит всегда; Position - по мелодии, Color - по тону, Strobe - в быстром темпе",
                     bg=mg.BG, fg=mg.DIM, font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=12, pady=(8, 0))
            self.matrix = tk.Frame(self.body, bg=mg.PANEL, padx=8, pady=6)
            self.matrix.pack(fill="x", padx=12, pady=(2, 12))
            self.redraw()

        def close(self):
            self.owner._rig_window = None
            try:
                self.win.destroy()
            except Exception:
                pass
            try:
                self.owner.build(self.owner.families())
            except Exception:
                pass

        def save(self):
            self.g2.save_settings(self.ma.settings)

        def set_anti(self):
            self.ma.settings["rig_anti"] = bool(self.anti_var.get())
            self.save()

        def set_main(self):
            self.ma.settings["gen_main"] = bool(self.main_var.get())
            self.save()

        def set_push(self):
            self.ma.settings["rig_push"] = bool(self.push_var.get())
            self.save()

        def query(self):
            self.status.configure(text="спрашиваю у пульта List Group…", fg=mg.DIM)

            def done(found, msg):
                try:
                    self.win.after(0, lambda: (self.status.configure(
                        text=msg, fg=mg.DIM if found else mg.WARN), self.redraw()))
                except Exception:
                    pass

            if not self.ma.rig_query(done):
                self.status.configure(text="нет связи с MA2 - группы взяты из генератора", fg=mg.WARN)

        # --- список групп с типами ---
        def redraw(self):
            s = self.ma.settings
            for w in self.list.winfo_children():
                w.destroy()
            tk.Label(self.list, text="ГРУППА", bg=mg.PANEL, fg=mg.DIM,
                     font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w")
            tk.Label(self.list, text="ТИП", bg=mg.PANEL, fg=mg.DIM,
                     font=("Segoe UI", 8, "bold")).grid(row=0, column=1, sticky="w")
            tk.Label(self.list, text="эффектов", bg=mg.PANEL, fg=mg.DIM,
                     font=("Segoe UI", 8, "bold")).grid(row=0, column=2, sticky="w", padx=(6, 0))
            groups = s.get("rig_groups") or []
            if not groups:
                tk.Label(self.list, text="групп нет - нажмите «⇩ Группы с пульта»\n"
                                         "или передайте эффекты из генератора",
                         bg=mg.PANEL, fg=mg.WARN, font=("Segoe UI", 9), justify="left").grid(
                    row=1, column=0, columnspan=3, sticky="w", pady=4)
            for r, gr in enumerate(groups, start=1):
                label = (f"{gr.get('id')}  " if gr.get("id") is not None else "") + str(gr.get("name"))
                tk.Label(self.list, text=label, bg=mg.PANEL, fg=mg.TEXT,
                         font=("Segoe UI", 9)).grid(row=r, column=0, sticky="w", pady=1)
                var = tk.StringVar(value=TYPE_NAMES.get(gr.get("type") or "", "-"))
                menu = tk.OptionMenu(self.list, var, *[TYPE_NAMES[t] for t in TYPES], "-",
                                     command=lambda v, gr=gr: self.set_type(gr, v))
                menu.configure(bg=mg.OFF, fg=TYPE_COLORS.get(gr.get("type") or ""), highlightthickness=0,
                               relief="flat", font=("Segoe UI", 9), width=6, activebackground=mg.OFF)
                menu.grid(row=r, column=1, sticky="w", pady=1)
                n = len(self.g2.rig_look_execs(s, gr.get("name")))
                tk.Label(self.list, text=str(n) if n else "нет", bg=mg.PANEL,
                         fg=mg.DIM if n else mg.WARN, font=("Segoe UI", 8)).grid(
                    row=r, column=2, sticky="w", padx=(6, 0))
            self.draw_map()
            self.draw_matrix()

        def set_type(self, gr, value):
            back = {v: k for k, v in TYPE_NAMES.items()}
            gr["type"] = back.get(value, "")
            self.save()
            self.redraw()

        # --- план сверху ---
        def to_xy(self, gr):
            m = 28
            return (m + gr.get("x", 0.5) * (self.MAP_W - 2 * m),
                    m + gr.get("y", 0.5) * (self.MAP_H - 2 * m))

        def draw_map(self):
            c, W_, H = self.map, self.MAP_W, self.MAP_H
            c.delete("all")
            c.create_rectangle(20, 20, W_ - 20, H - 20, outline="#3a3f4a", dash=(3, 3))
            c.create_text(W_ / 2, 10, text="задник", fill=mg.DIM, font=("Segoe UI", 8))
            c.create_text(W_ / 2, H - 9, text="▼ зрители ▼", fill=mg.DIM, font=("Segoe UI", 8))
            c.create_text(10, H / 2, text="Л", fill=mg.DIM, font=("Segoe UI", 8))
            c.create_text(W_ - 10, H / 2, text="П", fill=mg.DIM, font=("Segoe UI", 8))
            for i, gr in enumerate(self.ma.settings.get("rig_groups") or []):
                x, y = self.to_xy(gr)
                color = TYPE_COLORS.get(gr.get("type") or "", "#6b707a")
                tag = f"g{i}"
                c.create_oval(x - 9, y - 9, x + 9, y + 9, fill=color, outline="", tags=(tag, "grp"))
                c.create_text(x, y + 17, text=str(gr.get("name"))[:18], fill=mg.TEXT,
                              font=("Segoe UI", 8), tags=(tag, "grp"))

        def grab(self, e):
            hit = self.map.find_closest(e.x, e.y)
            if not hit:
                return
            tags = [t for t in self.map.gettags(hit[0]) if t.startswith("g") and t[1:].isdigit()]
            if tags:
                self.dragging = int(tags[0][1:])

        def drag(self, e):
            if self.dragging is None:
                return
            gr = self.ma.settings["rig_groups"][self.dragging]
            m = 28
            gr["x"] = round(min(1, max(0, (e.x - m) / (self.MAP_W - 2 * m))), 3)
            gr["y"] = round(min(1, max(0, (e.y - m) / (self.MAP_H - 2 * m))), 3)
            self.draw_map()

        def drop(self, _e):
            if self.dragging is not None:
                self.dragging = None
                self.save()

        # --- эффекты × типы ---
        def draw_matrix(self):
            s = self.ma.settings
            for w in self.matrix.winfo_children():
                w.destroy()
            looks = s.get("fxgen_assigned") or []
            if not looks:
                tk.Label(self.matrix, text="эффектов генератора ещё нет - «🔗 Взять эффекты генератора»",
                         bg=mg.PANEL, fg=mg.WARN, font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w")
                return
            allowed = s.setdefault("rig_allowed", {})
            tk.Label(self.matrix, text="эффект", bg=mg.PANEL, fg=mg.DIM,
                     font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w")
            for j, t in enumerate(TYPES):
                tk.Label(self.matrix, text=TYPE_NAMES[t], bg=mg.PANEL, fg=TYPE_COLORS[t],
                         font=("Segoe UI", 8, "bold")).grid(row=0, column=1 + j, padx=8)
            for i, lk in enumerate(looks, start=1):
                tk.Label(self.matrix, text=f"{lk['name']}  ({lk.get('cat')})", bg=mg.PANEL, fg=mg.TEXT,
                         font=("Segoe UI", 9)).grid(row=i, column=0, sticky="w")
                for j, t in enumerate(TYPES):
                    chosen = allowed.get(t)
                    on = chosen is None or lk.get("key") in chosen
                    var = tk.BooleanVar(value=on)

                    def toggle(t=t, key=lk.get("key"), var=var):
                        cur = allowed.get(t)
                        if cur is None:
                            cur = [x.get("key") for x in looks]
                        cur = [k for k in cur if k != key] + ([key] if var.get() else [])
                        allowed[t] = cur
                        self.save()

                    tk.Checkbutton(self.matrix, variable=var, command=lambda f=toggle: (f(), self.draw_warn()),
                                   bg=mg.PANEL, activebackground=mg.PANEL, selectcolor=mg.OFF, bd=0,
                                   highlightthickness=0).grid(row=i, column=1 + j)
            self.warn = tk.Label(self.matrix, text="", bg=mg.PANEL, fg=mg.WARN, font=("Segoe UI", 9),
                                 justify="left")
            self.warn.grid(row=len(looks) + 1, column=0, columnspan=1 + len(TYPES), sticky="w", pady=(6, 0))
            self.draw_warn()

        def draw_warn(self):
            """типы, у которых в работе есть группы, но нет ни одного диммерного эффекта"""
            s = self.ma.settings
            looks = s.get("fxgen_assigned") or []
            bad = []
            for t in TYPES:
                names = {(gr.get("name") or "").lower() for gr in s.get("rig_groups") or [] if gr.get("type") == t}
                if not names:
                    continue
                chosen = (s.get("rig_allowed") or {}).get(t)
                ok = [lk for lk in looks if lk.get("cat") == DIM_CAT
                      and (chosen is None or lk.get("key") in chosen)
                      and any((e.get("group") or "").lower() in names for e in lk.get("execs") or [])]
                if not ok:
                    bad.append(TYPE_NAMES[t])
            self.warn.configure(text=("⚠ нет диммерного эффекта для: " + ", ".join(bad)
                                      + " - эти приборы останутся в темноте. Сделайте в генераторе Dimmer-эффект "
                                        "для их групп") if bad else "")

    class BeamWindow:
        """функции луча: имена атрибутов, рецепты эффектов и когда они включаются"""

        def __init__(self, rig):
            self.rig, self.ma, self.g2 = rig, rig.ma, rig.g2
            s = self.ma.settings
            if not s.get("rig_beam_looks"):
                s["rig_beam_looks"] = [dict(lk) for lk in BEAM_LOOKS]
            self.win = (getattr(mg, "scroll_toplevel", None) or tk.Toplevel)(rig.win)
            self.win.title("Луч: призма, гобо, зум, фокус, ирис, фрост")
            self.win.configure(bg=mg.BG)
            self.body = self.win
            top = tk.Frame(self.body, bg=mg.BG)
            top.pack(fill="x", padx=12, pady=(10, 4))
            self.on = tk.BooleanVar(value=bool(s.get("rig_beam_on", True)))
            tk.Checkbutton(top, text="автопилот включает луч", variable=self.on, command=self.save_on,
                           bg=mg.BG, fg=mg.TEXT, activebackground=mg.BG, activeforeground=mg.TEXT,
                           selectcolor=mg.OFF, font=("Segoe UI", 9), highlightthickness=0).pack(side="left")
            mg.flat_button(top, "⇩ Атрибуты с пульта", self.query, mg.ACCENT).pack(side="left", padx=(12, 0))
            mg.flat_button(top, "🔆 Создать луч на пульте", self.create, mg.ACCENT).pack(side="left", padx=(6, 0))
            self.status = tk.Label(self.body, text=self.summary(), bg=mg.BG, fg=mg.DIM, font=("Segoe UI", 9),
                                   anchor="w", justify="left", wraplength=900)
            self.status.pack(fill="x", padx=12)
            box = tk.Frame(self.body, bg=mg.PANEL, padx=8, pady=6)
            box.pack(fill="x", padx=12, pady=(6, 0))
            tk.Label(box, text="ИМЕНА АТРИБУТОВ В MA2", bg=mg.PANEL, fg=mg.DIM,
                     font=("Segoe UI", 8, "bold")).grid(row=0, column=0, columnspan=10, sticky="w")
            self.attrs, self.attr_labels = {}, {}
            names = {**BEAM_ATTRS, **(s.get("rig_beam_attrs") or {})}
            for i, k in enumerate(BEAM_ATTRS):
                r, c = 1 + i // 5, (i % 5) * 2
                self.attr_labels[k] = tk.Label(box, text=BEAM_NAMES[k], bg=mg.PANEL, fg=mg.TEXT, font=("Segoe UI", 9))
                self.attr_labels[k].grid(row=r, column=c, sticky="e", padx=(8, 2), pady=2)
                e = self.rig.owner.entry(box, names[k], 14)
                e.grid(row=r, column=c + 1, sticky="w", pady=2)
                e.bind("<FocusOut>", lambda _e: self.save_attrs())
                e.bind("<Return>", lambda _e: self.save_attrs())
                self.attrs[k] = e
            looks = tk.Frame(self.body, bg=mg.PANEL, padx=8, pady=6)
            looks.pack(fill="x", padx=12, pady=(6, 0))
            self.looks_box = looks
            self.draw_looks()
            tk.Label(self.body, text="Рецепт: «ключ=значение» - статика в процентах, «ключ~Sin 10-60 x0.5» - "
                                    "эффект от 10 до 60 со скоростью ×0.5 от BPM. Ключи: "
                                    + ", ".join(BEAM_ATTRS) + ". Пустой рецепт - эффект не создаётся. "
                                    "Группы берутся из плана (нужен id группы); что умеет группа - из патча "
                                    "генератора, иначе по типу (спот: всё, wash: зум и фрост, par: ничего).",
                     bg=mg.BG, fg=mg.DIM, font=("Segoe UI", 8), wraplength=900, justify="left",
                     anchor="w").pack(fill="x", padx=12, pady=(6, 12))

        def summary(self):
            a = self.ma.settings.get("rig_beam_assigned") or []
            return ("на пульте: " + ", ".join(f"{x['name']} {x['exec']} ({BEAM_WHEN.get(x.get('when'), '-')})"
                                              for x in a)) if a else "луч на пульте ещё не создан"

        def draw_looks(self):
            box = self.looks_box
            for w in box.winfo_children():
                w.destroy()
            for j, h in enumerate(("ЭФФЕКТ", "КОГДА", "РЕЦЕПТ")):
                tk.Label(box, text=h, bg=mg.PANEL, fg=mg.DIM, font=("Segoe UI", 8, "bold")).grid(
                    row=0, column=j, sticky="w", padx=(0, 8))
            when_names = list(BEAM_WHEN.values())
            back = {v: k for k, v in BEAM_WHEN.items()}
            for i, lk in enumerate(self.ma.settings["rig_beam_looks"], start=1):
                name = self.rig.owner.entry(box, lk.get("name", ""), 16)
                name.grid(row=i, column=0, sticky="w", pady=1, padx=(0, 8))
                var = tk.StringVar(value=BEAM_WHEN.get(lk.get("when"), when_names[0]))
                menu = tk.OptionMenu(box, var, *when_names,
                                     command=lambda v, lk=lk: (lk.__setitem__("when", back[v]), self.save()))
                menu.configure(bg=mg.OFF, fg=mg.TEXT, highlightthickness=0, relief="flat",
                               font=("Segoe UI", 9), width=12, activebackground=mg.OFF)
                menu.grid(row=i, column=1, sticky="w", padx=(0, 8))
                recipe = self.rig.owner.entry(box, lk.get("recipe", ""), 70)
                recipe.grid(row=i, column=2, sticky="w", pady=1)
                bad = tk.Label(box, text="", bg=mg.PANEL, fg=mg.WARN, font=("Segoe UI", 8))
                bad.grid(row=i, column=3, sticky="w", padx=6)

                def store(_e=None, lk=lk, name=name, recipe=recipe, bad=bad):
                    lk["name"] = name.get().strip() or lk.get("name") or "луч"
                    lk["recipe"] = recipe.get().strip()
                    wrong = parse_recipe(lk["recipe"])[1]
                    bad.configure(text=("не понял: " + ", ".join(wrong)) if wrong else "")
                    self.save()

                for w in (name, recipe):
                    w.bind("<FocusOut>", store)
                    w.bind("<Return>", store)
                store()
            mg.flat_button(box, "+ эффект", self.add, mg.OFF).grid(row=len(self.ma.settings["rig_beam_looks"]) + 1,
                                                                    column=0, sticky="w", pady=(6, 0))
            mg.flat_button(box, "↺ как было", self.reset, mg.OFF).grid(row=len(self.ma.settings["rig_beam_looks"]) + 1,
                                                                        column=1, sticky="w", pady=(6, 0))

        def add(self):
            looks = self.ma.settings["rig_beam_looks"]
            looks.append({"key": f"beam_{len(looks) + 1}", "name": "Свой", "when": "phrase", "recipe": ""})
            self.save()
            self.draw_looks()

        def reset(self):
            self.ma.settings["rig_beam_looks"] = [dict(lk) for lk in BEAM_LOOKS]
            self.save()
            self.draw_looks()

        def save(self):
            self.g2.save_settings(self.ma.settings)

        def save_on(self):
            self.ma.settings["rig_beam_on"] = bool(self.on.get())
            self.save()

        def save_attrs(self):
            self.ma.settings["rig_beam_attrs"] = {k: e.get().strip() or BEAM_ATTRS[k] for k, e in self.attrs.items()}
            self.save()

        def say(self, text, warn=False):
            try:
                self.win.after(0, lambda: self.status.configure(text=text, fg=mg.WARN if warn else mg.DIM))
            except Exception:
                pass

        def query(self):
            self.save_attrs()

            def done(found, msg):
                self.say(msg, not found or not any(found.values()))
                if found:
                    def paint():
                        for k, ok in found.items():
                            self.attr_labels[k].configure(fg=mg.TEXT if ok else mg.WARN)
                    try:
                        self.win.after(0, paint)
                    except Exception:
                        pass

            if not self.ma.rig_attr_query(done):
                self.say("нет связи с MA2", True)

        def create(self):
            self.save_attrs()
            self.say("создаю эффекты луча на пульте…")

            def done(errors):
                self.say(self.summary() + (("   ⚠ ошибки: " + "; ".join(errors[:3])) if errors else ""), bool(errors))

            self.ma.rig_beam_create(done)

    mg.RigWindow = RigWindow
    mg.BeamWindow = BeamWindow
    return mg


def install():
    import ma_wheel
    ma_wheel.register("grandma2", install_grandma2)
    ma_wheel.register("music_gui", install_gui)
