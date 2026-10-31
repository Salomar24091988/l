"""Цвет по кругу Иттена: гармонии от тональности, цвет - по типу фонаря.

- Круг для RGB: 24 оттенка без жёлтого (вместо него янтарь и оранжевый),
  у каждого 3 вида: насыщенный, глубокий, светлый = 72 пресета Color 4.101-4.172.
  Споты с колесом берут ближайший из своих слотов (пресеты 4.181+).
- Тоника трека → базовый оттенок (минор - соседний оттенок), от него гармония:
  моно, аналоговая, комплементарная, расщеплённая, триада, квадрат, прямоугольник.
- Фонари одного типа - одного цвета, разные типы - разные цвета гармонии.
  На пике / в быстром темпе / на искрах тип делится надвое (половины по сцене
  или через один) и берёт два цвета.
- Смена - на сильную долю, волной по Layout (из центра, по кругу, слева направо…):
  RGB плавно за четверть доли, споты с колесом - через темноту (провал мастера
  их экзекьютора диммера), чтобы не было видно прокрутки колеса.
- На новой фразе цвета переходят между типами по кругу и меняется направление
  волны; нажим (пик / минимум ударов) разворачивает волну.
"""
import colorsys
import math
import re
import threading
import time

DEFAULTS = {
    "pal_on": True,             # палитра Иттена вместо цветовых эффектов генератора
    "pal_over_gen": False,      # палитра и при эффектах генератора (пишет в программер - перекрывает их)
    "pal_start": 101,           # RGB: 24 оттенка × 3 вида = 4.101-4.172
    "pal_wheel_start": 181,     # споты с колесом: 4.181+
    "pal_created": False,
    "pal_wheel": [],            # [{name, hue, preset}] - что записано для колеса
    "pal_fade": 0.25,           # переход RGB, доля удара
    "pal_wheel_dark": True,     # колесо - через темноту
    "pal_fade_cmd": " Fade {t}",
    "pal_dip_down": "Executor {ex} At 0 Fade {t}",
    "pal_dip_up": "Executor {ex} At 100 Fade {t}",
    "pal_rgb_attrs": "COLORRGB1, COLORRGB2, COLORRGB3",
    "pal_migrated": False,
}

N = 24
GAP = (50.0, 85.0)              # жёлтый и жёлто-зелёный вырезаны из круга
HUE_NAMES = ("красный", "алый", "оранжевый", "янтарный", "весенний", "зелёный", "изумрудный", "нефрит",
             "мятный", "бирюзовый", "аква", "голубой", "небесный", "лазурный", "синий", "королевский",
             "индиго", "ультрафиолет", "фиолетовый", "пурпур", "орхидея", "маджента", "фуксия", "малиновый")
SHADES = (("", 1.0, 1.0), ("глубокий", 1.0, 0.62), ("светлый", 0.42, 1.0))
HARMONIES = {
    "моно": ((0, 0), (0, 1), (0, 2)),
    "аналоговая": ((0, 0), (-2, 0), (2, 0)),
    "комплементарная": ((0, 0), (12, 0)),
    "расщеплённая": ((0, 0), (10, 0), (14, 0)),
    "триада": ((0, 0), (8, 0), (16, 0)),
    "квадрат": ((0, 0), (6, 0), (12, 0), (18, 0)),
    "прямоугольник": ((0, 0), (4, 0), (12, 0), (16, 0)),
}
MOODS = {
    "calm": ("моно", "аналоговая"),
    "пульс": ("комплементарная", "расщеплённая"),
    "бег": ("триада", "расщеплённая"),
    "поток": ("расщеплённая", "аналоговая", "триада"),
    "искры": ("квадрат", "прямоугольник"),
    "peak": ("квадрат", "прямоугольник"),
    "fast": ("прямоугольник", "квадрат", "триада"),
}
MOOD_NAMES = {"calm": "спокойно", "peak": "пик", "fast": "быстро"}
SPLIT_MOODS = ("peak", "fast", "искры")
WAVES = ("из центра", "по кругу", "слева направо", "к центру", "справа налево", "спереди назад")
STEPS = 6                       # волна - не больше 6 отправок на смену


def hue_of(i):
    step = (360.0 - (GAP[1] - GAP[0])) / N
    h = (i % N) * step
    if h >= GAP[0]:
        h += GAP[1] - GAP[0]
    return h % 360


def rgb_of(i, shade=0):
    _, s, v = SHADES[shade % 3]
    r, g, b = colorsys.hsv_to_rgb(hue_of(i) / 360.0, s, v)
    return round(r * 100), round(g * 100), round(b * 100)


def color_name(i, shade=0):
    tag = SHADES[shade % 3][0]
    return (HUE_NAMES[i % N] + (" " + tag if tag else "")).strip()


def preset_no(start, i, shade=0):
    return int(start) + (i % N) * 3 + shade % 3


def nearest_index(hue):
    return min(range(N), key=lambda i: min(abs(hue_of(i) - hue), 360 - abs(hue_of(i) - hue)))


def base_index(position, mode, key_palette):
    """тоника → оттенок круга: цвет тональности из старой палитры, минор - соседний"""
    rgb = key_palette[int(position) % 12][1]
    r, g, b = (max(0, min(100, v)) / 100.0 for v in rgb)
    h = colorsys.rgb_to_hsv(r, g, b)[0] * 360
    i = nearest_index(h)
    return (i + 1) % N if mode == "minor" else i


def harmony_colors(base, name, variant=0):
    """[(оттенок, вид)]: база - насыщенная, остальные цвета меняют вид от варианта"""
    out = []
    for k, (off, shade) in enumerate(HARMONIES[name]):
        if name != "моно" and k:
            shade = (variant + k) % 3 if variant % 2 else 0
        out.append(((base + off) % N, shade))
    return out


def sel_cmd(ids):
    """[401..410, 501] → «Fixture 401 Thru 410 + 501»"""
    ids = sorted({int(i) for i in ids})
    parts, i = [], 0
    while i < len(ids):
        j = i
        while j + 1 < len(ids) and ids[j + 1] == ids[j] + 1:
            j += 1
        parts.append(str(ids[i]) if i == j else f"{ids[i]} Thru {ids[j]}")
        i = j + 1
    return "Fixture " + " + ".join(parts) if parts else ""


def units_of(s):
    """фонари с цветом: из Layout генератора (по одному), иначе - группы целиком.
    → [{key, sel, ids, type, x, y, rgb, wheel, group}]"""
    out = []
    layout = s.get("fxgen_layout") or {}
    for f in (layout.get("fix") or {}).values():
        caps = f.get("caps") or []
        rgb, wheel = "rgb" in caps, "wheel" in caps and "rgb" not in caps
        if not (rgb or wheel) or f.get("x") is None:
            continue
        out.append({"key": f"f{f['id']}", "ids": [int(f["id"])], "type": f.get("type") or "?",
                    "x": float(f.get("x") or 0), "y": float(f.get("y") or 0), "rgb": rgb, "wheel": wheel,
                    "group": f.get("group"), "z": float(f.get("z") or 0)})
    if out:
        return out, layout.get("stage") or {"w": 12, "d": 8}
    for gr in s.get("rig_groups") or []:
        caps = gr.get("caps") or []
        rgb, wheel = "rgb" in caps, "wheel" in caps and "rgb" not in caps
        if gr.get("id") is None or not (rgb or wheel):
            continue
        out.append({"key": f"g{gr['id']}", "sel": f"Group {gr['id']}", "type": gr.get("fixture_type") or gr.get("type") or "?",
                    "x": (float(gr.get("x", 0.5)) - 0.5) * 12, "y": (1 - float(gr.get("y", 0.5))) * 8,
                    "rgb": rgb, "wheel": wheel, "group": gr.get("id"), "z": 0.0})
    return out, {"w": 12, "d": 8}


def type_order(units):
    counts = {}
    for u in units:
        counts[u["type"]] = counts.get(u["type"], 0) + 1
    return sorted(counts, key=lambda t: (-counts[t], str(t)))


def assign(units, colors, variant=0, split=False):
    """фонари одного типа - один цвет; разные типы - разные цвета гармонии.
    split: тип делится надвое (чётные варианты - половины слева/справа, нечётные - через один)"""
    n = len(colors)
    out = {}
    for ti, typ in enumerate(type_order(units)):
        mine = sorted([u for u in units if u["type"] == typ], key=lambda u: (u["x"], u["y"]))
        c1 = colors[(ti + variant) % n]
        c2 = colors[(ti + variant + 1) % n] if n > 1 else (c1[0], (c1[1] + 1) % 3)
        for k, u in enumerate(mine):
            second = split and len(mine) > 1 and (
                (k >= len(mine) / 2) if variant % 2 == 0 else (k % 2 == 1))
            out[u["key"]] = c2 if second else c1
    return out


def wave_params(units, direction, stage, reverse=False):
    """0..1 для каждого фонаря: когда до него дойдёт волна"""
    if not units:
        return {}
    cy = float(stage.get("d", 8)) / 2
    raw = {}
    for u in units:
        x, y = u["x"], u["y"]
        if direction == "из центра":
            v = math.hypot(x, y - cy)
        elif direction == "к центру":
            v = -math.hypot(x, y - cy)
        elif direction == "по кругу":
            v = math.atan2(y - cy, x) % (2 * math.pi)
        elif direction == "слева направо":
            v = x
        elif direction == "справа налево":
            v = -x
        else:
            v = y
        raw[u["key"]] = v
    lo, hi = min(raw.values()), max(raw.values())
    span = (hi - lo) or 1.0
    out = {k: (v - lo) / span for k, v in raw.items()}
    if reverse:
        out = {k: 1 - v for k, v in out.items()}
    return out


def wheel_slots(s, parse_slots):
    slots, _ = parse_slots(s.get("wheel_slots", ""))
    return [sl for sl in slots if sl[1] is not None]


def wheel_value(slot_index, s, parse_slots):
    """что слать колесу: свой пресет (если создан), иначе значение слота"""
    made = s.get("pal_wheel") or []
    if slot_index < len(made) and made[slot_index].get("preset"):
        return "At Preset " + made[slot_index]["preset"]
    slots = wheel_slots(s, parse_slots)
    if slot_index >= len(slots):
        return None
    value = slots[slot_index][2]
    if value.startswith("Preset"):
        return "At " + value
    attr = (s.get("wheel_attr") or "COLOR1").strip().strip('"') or "COLOR1"
    return f'Attribute "{attr}" At {value}'


def nearest_slot_index(hue, slots):
    if not slots:
        return None
    return min(range(len(slots)), key=lambda j: min(abs(slots[j][1] - hue), 360 - abs(slots[j][1] - hue)))


def num(v):
    v = round(float(v), 3)
    return int(v) if v.is_integer() else v


def plan_change(s, units, stage, targets, current, direction, reverse, beat, parse_slots, dim_execs):
    """→ [(через сколько секунд, команда)] для смены цвета волной"""
    start = s.get("pal_start", 101)
    fade = max(0.05, float(s.get("pal_fade", 0.25)) * beat)
    wave = beat
    fade_cmd = s.get("pal_fade_cmd", " Fade {t}") or ""
    changed = [u for u in units if targets.get(u["key"]) != current.get(u["key"])]
    if not changed:
        return []
    params = wave_params(changed, direction, stage, reverse)
    slots = wheel_slots(s, parse_slots)
    rgb_buckets, wheel_buckets = {}, {}
    for u in changed:
        step = min(STEPS - 1, int(params[u["key"]] * STEPS))
        hue_i, shade = targets[u["key"]]
        if u["rgb"]:
            rgb_buckets.setdefault((step, preset_no(start, hue_i, shade)), []).append(u)
        else:
            j = nearest_slot_index(hue_of(hue_i), slots)
            cur = current.get(u["key"])
            if j is None or (cur and nearest_slot_index(hue_of(cur[0]), slots) == j):
                continue    # колесо и так на этом слоте
            wheel_buckets.setdefault((step, j), []).append(u)
    events = []

    def selection(us):
        ids = [i for u in us for i in u.get("ids") or []]
        if ids:
            return sel_cmd(ids)
        return " + ".join(u["sel"] for u in us)

    for (step, no), us in sorted(rgb_buckets.items()):
        t = step * wave / STEPS
        events.append((t, f"{selection(us)} At Preset 4.{no}" + fade_cmd.format(t=num(fade))))
    dark = bool(s.get("pal_wheel_dark", True))
    dip = min(0.12, beat / 4)
    # колесо: группа с экзекьютором диммера гаснет целиком один раз (по первому
    # своему фонарю в волне), в темноте все её фонари встают на новые слоты
    by_dip, plain = {}, []
    for (step, j), us in sorted(wheel_buckets.items()):
        for u in us:
            execs = tuple(dim_execs.get(u.get("group"), [])) if dark else ()
            if execs:
                d = by_dip.setdefault(execs, {"step": step, "slots": {}})
                d["step"] = min(d["step"], step)
                d["slots"].setdefault(j, []).append(u)
            else:
                plain.append((step, j, u))
    for execs, d in by_dip.items():
        t = d["step"] * wave / STEPS
        events += [(t, s.get("pal_dip_down", DEFAULTS["pal_dip_down"]).format(ex=ex, t=num(dip))) for ex in execs]
        for j, us in sorted(d["slots"].items()):
            value = wheel_value(j, s, parse_slots)
            if value:
                events.append((t + dip, f"{selection(us)} {value}"))
        events += [(t + dip + 0.04, s.get("pal_dip_up", DEFAULTS["pal_dip_up"]).format(ex=ex, t=num(dip * 1.5)))
                   for ex in execs]
    grouped = {}
    for step, j, u in plain:
        grouped.setdefault((step, j), []).append(u)
    for (step, j), us in sorted(grouped.items()):
        value = wheel_value(j, s, parse_slots)
        if value:
            events.append((step * wave / STEPS, f"{selection(us)} {value}"))
    return sorted(events, key=lambda e: e[0])


def create_script(s, units, parse_slots):
    """пресеты палитры: 72 RGB + слоты колеса → [(команда, None)], [слоты колеса]"""
    attrs = [a.strip().strip('"') for a in re.split(r"[,;]", s.get("pal_rgb_attrs") or "") if a.strip()][:3]
    attrs = attrs if len(attrs) == 3 else ["COLORRGB1", "COLORRGB2", "COLORRGB3"]
    start = int(s.get("pal_start", 101))
    rgb_units = [u for u in units if u["rgb"]]
    wheel_units = [u for u in units if u["wheel"]]

    def selection(us):
        ids = [i for u in us for i in u.get("ids") or []]
        return [sel_cmd(ids)] if ids else [u["sel"] for u in us]

    out = []
    if rgb_units:
        sel = selection(rgb_units)
        for i in range(N):
            for shade in range(3):
                no = preset_no(start, i, shade)
                out.append(("ClearAll", None))
                out += [(c, None) for c in sel]
                out += [(f'Attribute "{a}" At {v}', None) for a, v in zip(attrs, rgb_of(i, shade))]
                out += [(f"Store Preset 4.{no} /o", None), (f'Label Preset 4.{no} "{color_name(i, shade)}"', None)]
    made = []
    if wheel_units:
        sel = selection(wheel_units)
        attr = (s.get("wheel_attr") or "COLOR1").strip().strip('"') or "COLOR1"
        no = int(s.get("pal_wheel_start", 181))
        for name, hue, value in wheel_slots(s, parse_slots):
            if value.startswith("Preset"):
                made.append({"name": name, "hue": hue, "preset": value.split()[-1]})
                continue
            out.append(("ClearAll", None))
            out += [(c, None) for c in sel]
            out += [(f'Attribute "{attr}" At {value}', None), (f"Store Preset 4.{no} /o", None),
                    (f'Label Preset 4.{no} "колесо {name}"', None)]
            made.append({"name": name, "hue": hue, "preset": f"4.{no}"})
            no += 1
    out.append(("ClearAll", None))
    return out, made


class Palette:
    """состояние палитры одного MA2Control"""

    def __init__(self):
        self.key = None          # (position, mode)
        self.mood = None
        self.harmony = None
        self.variant = 0
        self.wave = 0
        self.current = {}        # unit key → (оттенок, вид)
        self.gen = 0
        self.text = ""

    def reset(self):
        self.mood = self.harmony = None
        self.current = {}
        self.gen += 1


def install_grandma2(g):
    if getattr(g, "_palette_installed", False):
        return g
    g._palette_installed = True
    for k, v in DEFAULTS.items():
        g.DEFAULTS.setdefault(k, v)
    C = g.MA2Control

    original_load = g.load_settings

    def load_settings():
        s = original_load()
        for k, v in DEFAULTS.items():
            s.setdefault(k, v)
        if not s.get("pal_migrated"):
            # 4.101-4.172 теперь палитра: цвета тональностей (старые кью) - на 4.221
            if int(s.get("color_preset_start", 101) or 101) == 101:
                s["color_preset_start"] = 221
            s["pal_migrated"] = True
            try:
                g.save_settings(s)
            except Exception:
                pass
        return s

    g.load_settings = load_settings

    def pal(self):
        p = self.__dict__.get("_palette")
        if p is None:
            p = self._palette = Palette()
        return p

    def active(self):
        s = self.settings
        if getattr(g, "gen_main", None) and g.gen_main(self) and not s.get("pal_over_gen", False):
            return False        # генератор главный: палитра не пишет в программер
        return bool(s.get("pal_on", True) and s.get("pal_created")) and bool(units_of(s)[0])

    g.palette_active = active

    original_on_key = C.on_key

    def on_key(self, tonic, mode, *args, **kwargs):
        try:
            pal(self).key = (g.key_position(tonic, mode), mode)
        except Exception:
            pass
        return original_on_key(self, tonic, mode, *args, **kwargs)

    C.on_key = on_key

    original_color_apply = C.color_apply

    def color_apply(self, *args, **kwargs):
        # цвет ведёт палитра - старые кью тональности не включаем
        cmd = getattr(self, "auto_cmd", None)
        if active(self) and isinstance(cmd, str) and cmd.startswith("fx:"):
            return None
        return original_color_apply(self, *args, **kwargs)

    C.color_apply = color_apply

    def palette_bar(self, rig, features, phrase, turned):
        """раз в такт (сильная доля) из дорожек ma_rig"""
        if not active(self):
            return
        p, s = pal(self), self.settings
        units, stage = units_of(s)
        if p.key is None:
            p.key = (0, "major")
        if rig.get("peak_hold", 0) > 0:
            mood = "peak"
        elif rig.get("fast"):
            mood = "fast"
        elif rig.get("script_mood"):
            mood = rig["script_mood"]          # настроение такта из сценария трека
        elif getattr(rig.get("tempo"), "calm", False):
            mood = "calm"
        else:
            mood = rig.get("rhythm") or "бег"
        if mood not in MOODS:
            mood = "бег"
        key_new = rig.get("pal_key") != p.key
        rig["pal_key"] = p.key
        script = bool(rig.get("script"))
        # по сценарию цвет меняется в его точках (секция, смена после пика), без него - по фразам
        step = rig.pop("script_color", False) if script else phrase
        force = (rig.get("force") or {}).get("palette") or {}
        if step:
            p.variant += 1
            p.wave += 1
        if not (key_new or step or mood != p.mood or not p.current or (force and force != rig.get("applied_palette"))):
            return
        names = MOODS[mood]
        tried = (rig.get("avoid") or {}).get("palette") or {}
        if force.get("harmony"):
            harmony = force["harmony"]                       # 💾 сохранено для этой секции
            p.variant = int(force.get("variant", p.variant) or 0)
            p.wave = int(force.get("wave", p.wave) or 0)
        else:
            ring = [names[(p.variant + i) % len(names)] for i in range(len(names))]
            harmony = min(ring, key=lambda h: int(tried.get(h, 0) or 0)) if tried else ring[0]
        rig["applied_palette"] = {"harmony": harmony, "variant": p.variant, "wave": p.wave}
        base = base_index(p.key[0], p.key[1], g.KEY_PALETTE)
        colors = harmony_colors(base, harmony, p.variant)
        targets = assign(units, colors, p.variant, mood in SPLIT_MOODS)
        get = (lambda k: features.get(k)) if isinstance(features, dict) else (lambda k: getattr(features, k, None))
        try:
            bpm = float(get("bpm") or getattr(self, "bpm_sent", 0) or 120)
        except (TypeError, ValueError):
            bpm = 120.0
        beat = 60.0 / max(40.0, min(220.0, bpm))
        if mood in ("fast", "peak"):
            beat /= 2
        direction = WAVES[p.wave % len(WAVES)]
        reverse = rig.get("dir", 1) < 0
        events = plan_change(s, units, stage, targets, p.current, direction, reverse, beat,
                             g.parse_slots, rig.get("dim_by_group") or {})
        p.mood, p.harmony, p.current = mood, harmony, targets
        p.text = (f"{harmony} от «{color_name(base)}» · " + MOOD_NAMES.get(mood, mood)
                  + (" · типы делятся" if mood in SPLIT_MOODS else "") + f" · волна {direction}")
        if events:
            run_events(self, events)
            self.add_log(f"🎨 {p.text} ({len(events)} команд)")

    g.palette_bar = palette_bar

    def palette_resend(self):
        """послать текущие цвета заново и сразу (после очистки программера), без затемнения"""
        if not active(self):
            return 0
        p = pal(self)
        if not p.current:
            return 0
        s = dict(self.settings, pal_wheel_dark=False)
        units, stage = units_of(s)
        events = plan_change(s, units, stage, p.current, {}, WAVES[0], False, 0.05,
                             g.parse_slots, {})
        for _t, cmd in events:
            self.send(cmd)
        return len(events)

    g.palette_resend = palette_resend

    def palette_text(self):
        return pal(self).text if active(self) else ""

    g.palette_text = palette_text

    def palette_reset(self):
        pal(self).reset()

    g.palette_reset = palette_reset

    def run_events(self, events):
        p = pal(self)
        p.gen += 1
        gen = p.gen
        t0 = time.time()

        def run():
            for t, cmd in events:
                if p.gen != gen:
                    return
                wait = t0 + t - time.time()
                if wait > 0:
                    time.sleep(wait)
                self.send(cmd)

        threading.Thread(target=run, daemon=True).start()

    def palette_create(self, done=None):
        """записать пресеты палитры на пульт"""
        s = self.settings
        if not (self.enabled and self.client.connected) or self.fx_busy:
            if done:
                done(["нет связи с MA2" if not self.fx_busy else "пульт занят"])
            return False
        units, _ = units_of(s)
        if not units:
            if done:
                done(["нет фонарей с цветом: в генераторе нужен Layout (⇩ Патч с пульта) и «→ Анализатору»"])
            return False
        script, made = create_script(s, units, g.parse_slots)
        self.fx_busy = True

        def run():
            errors = []
            try:
                self.add_log(f"🎨 палитра: {len(script)} команд…")
                for command, _ in script:
                    if not self.client.connected:
                        errors.append("связь пропала")
                        break
                    if self.run_checked(command):
                        errors.append(command)
                if self.client.connected:
                    s["pal_created"], s["pal_wheel"] = True, made
                    g.save_settings(s)
                    pal(self).reset()
                    self.add_log(f"🎨 палитра готова: 72 цвета RGB с 4.{s.get('pal_start', 101)}"
                                 + (f", колесо {len(made)} слотов" if made else "")
                                 + (f"; ошибок {len(errors)}" if errors else ""))
            finally:
                self.fx_busy = False
                if done:
                    done(errors)

        threading.Thread(target=run, daemon=True).start()
        return True

    C.palette_create = palette_create
    return g


def install_gui(mg):
    if getattr(mg, "_palette_installed", False):
        return mg
    mg._palette_installed = True
    mg.PaletteWindow = PaletteWindow
    return mg


class PaletteWindow:
    """окно палитры: круг 24 × 3, состояние, кнопка записи на пульт"""

    def __init__(self, rig):
        import music_gui as mg
        import grandma2 as g
        tk = mg.tk
        self.rig, self.mg, self.g = rig, mg, g
        self.ma = rig.owner.ma
        s = self.ma.settings
        self.win = (getattr(mg, "scroll_toplevel", None) or tk.Toplevel)(rig.win)
        self.win.title("Палитра Иттена")
        self.win.configure(bg=mg.BG)
        self.body = self.win
        top = tk.Frame(self.body, bg=mg.BG)
        top.pack(fill="x", padx=12, pady=(10, 4))
        self.on = tk.BooleanVar(value=bool(s.get("pal_on", True)))
        self.dark = tk.BooleanVar(value=bool(s.get("pal_wheel_dark", True)))
        self.over = tk.BooleanVar(value=bool(s.get("pal_over_gen", False)))
        for text, var, key in (("палитра Иттена ведёт цвет", self.on, "pal_on"),
                               ("колесо - через темноту", self.dark, "pal_wheel_dark"),
                               ("и поверх эффектов генератора", self.over, "pal_over_gen")):
            tk.Checkbutton(top, text=text, variable=var, command=lambda k=key, v=var: self.ma.set(**{k: bool(v.get())}),
                           bg=mg.BG, fg=mg.TEXT, activebackground=mg.BG, activeforeground=mg.TEXT,
                           selectcolor=mg.OFF, font=("Segoe UI", 9), highlightthickness=0).pack(side="left", padx=(0, 10))
        mg.flat_button(top, "🎨 Записать палитру на пульт", self.create, mg.ACCENT).pack(side="right")
        self.status = tk.Label(self.body, text="", bg=mg.BG, fg=mg.DIM, font=("Segoe UI", 9),
                               anchor="w", justify="left", wraplength=760)
        self.status.pack(fill="x", padx=12)
        self.canvas = tk.Canvas(self.body, width=760, height=150, bg=mg.PANEL, highlightthickness=0)
        self.canvas.pack(padx=12, pady=6)
        tk.Label(self.body, text="RGB: 24 оттенка × (насыщенный, глубокий, светлый) = пресеты 4.101-4.172. "
                                "Споты с колесом - свои слоты (4.181+). Фонари одного типа - одного цвета, "
                                "на пике и в быстром темпе тип делится на два цвета. Смена - на сильную долю, "
                                "волной по Layout генератора.",
                 bg=mg.BG, fg=mg.DIM, font=("Segoe UI", 8), anchor="w", justify="left",
                 wraplength=760).pack(fill="x", padx=12, pady=(0, 10))
        self.draw()
        self.tick()

    def draw(self):
        c = self.canvas
        c.delete("all")
        w = 760 / N
        for i in range(N):
            for shade in range(3):
                r, g_, b = rgb_of(i, shade)
                col = "#%02x%02x%02x" % (int(r * 2.55), int(g_ * 2.55), int(b * 2.55))
                c.create_rectangle(i * w + 1, 6 + shade * 34, (i + 1) * w - 1, 36 + shade * 34, fill=col, outline="")
            c.create_text(i * w + w / 2, 120, text=str(preset_no(self.ma.settings.get("pal_start", 101), i)),
                          fill=self.mg.DIM, font=("Segoe UI", 7))
        p = self.ma.__dict__.get("_palette")
        if p and p.current:
            used = {h for h, _ in p.current.values()}
            for i in used:
                c.create_rectangle(i * w + 1, 2, (i + 1) * w - 1, 108, outline="#ffffff", width=2)

    def tick(self):
        try:
            if not self.win.winfo_exists():
                return
        except Exception:
            return
        s = self.ma.settings
        units, _ = units_of(s)
        rgb = sum(1 for u in units if u["rgb"])
        wheel = sum(1 for u in units if u["wheel"])
        types = type_order(units)
        text = (f"фонарей с цветом: RGB {rgb}, колесо {wheel}; типов {len(types)}"
                + (": " + ", ".join(types[:5]) if types else " - нужен Layout генератора (→ Анализатору)")
                + ("" if s.get("pal_created") else " · пресеты ещё не записаны"))
        now = self.g.palette_text(self.ma) if hasattr(self.g, "palette_text") else ""
        self.status.config(text=text + ("\nсейчас: " + now if now else ""))
        self.draw()
        self.win.after(1000, self.tick)

    def create(self):
        def done(errors):
            try:
                self.win.after(0, lambda: self.status.config(
                    text=("ошибки: " + "; ".join(errors[:3])) if errors else "палитра записана"))
            except Exception:
                pass

        if not self.ma.palette_create(done):
            pass


def install():
    import ma_wheel
    ma_wheel.register("grandma2", install_grandma2)
    ma_wheel.register("music_gui", install_gui)
