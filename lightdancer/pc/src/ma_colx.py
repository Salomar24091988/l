"""Цвета анализатора как в ColorExec: группы EV / ODD, пресеты из Gel.

Встраивается в собранный анализатор поверх grandma2 / music_gui (после ma_wheel):
- пресеты 4."red", 4."blue"… пишутся так же, как в плагине ColorExec:
  «Group EV At Gel "ma colors".N» → Store Preset 4."имя" /m (и то же для ODD);
- 12 цветовых кью тональностей (page.16-27): обе группы - цвет тональности
  (12 цветов «ma colors» по кругу оттенков, один к одному), 12 пар (page.31-42):
  EV - цвет тональности, ODD - антагонист;
- по желанию - экзекьютор COLOR (page.50) со всеми парами, как делает
  ColorExec: Goto, Fade 2, Off 2 с, цвет кнопки по кью, без сине-жёлтых пар;
- группы EV / ODD вводятся в окне «🎛 grandMA2…» и меняются во время работы:
  «🎨 Пересоздать цвета» перестраивает всё сразу;
- включённый режим выключает палитру Иттена (цвет ведут эти кью).
Пустая группа EV - цвета строятся как раньше.
"""
import colorsys

GELS = (
    ('"ma colors"."1"', "white"), ('"ma colors"."2"', "red"), ('"ma colors"."3"', "orange"),
    ('"ma colors"."4"', "yellow"), ('"ma colors"."5"', "ferngreen"), ('"ma colors"."6"', "green"),
    ('"ma colors"."7"', "seagreen"), ('"ma colors"."8"', "cyan"), ('"ma colors"."9"', "lavander"),
    ('"ma colors"."10"', "blue"), ('"ma colors"."11"', "violet"), ('"ma colors"."12"', "magenta"),
    ('"ma colors"."13"', "pink"), ('"lee"."201"', "ctb"), ('"lee"."205"', "cto"),
)
RGB = {
    "white": (60, 60, 60), "cto": (60, 55, 30), "red": (60, 0, 0), "green": (0, 60, 0),
    "blue": (0, 0, 60), "cyan": (0, 60, 60), "magenta": (60, 0, 60), "yellow": (60, 60, 0),
    "orange": (60, 35, 0), "pink": (80, 0, 30), "seagreen": (0, 60, 30), "ferngreen": (30, 60, 0),
    "lavander": (0, 30, 60), "violet": (30, 0, 60), "ctb": (45, 60, 60),
}
HUES = ("red", "orange", "yellow", "ferngreen", "green", "seagreen", "cyan", "lavander",
        "blue", "violet", "magenta", "pink")
# пары экзекьютора COLOR - как в ColorExec
BASE = ("red", "green", "blue", "cyan", "magenta", "yellow")
SECOND = ("cto", "red", "green", "blue", "cyan", "magenta", "yellow", "orange", "seagreen", "pink", "ctb")
WARM, COLD = ("yellow", "orange"), ("blue", "cyan")

DEFAULTS = {
    "colx_on": False,
    "colx_ev": "",
    "colx_odd": "",
    "colx_presets": True,
    "colx_exec": True,
    "colx_no_by": True,
}


def hue_of(rgb):
    r, g, b = (max(0.0, float(x)) for x in rgb)
    m = max(r, g, b) or 1.0
    return colorsys.rgb_to_hsv(r / m, g / m, b / m)[0] * 360.0


def nearest(rgb):
    """ближайший по оттенку цвет из 12 «ma colors»"""
    h = hue_of(rgb)
    return min(HUES, key=lambda n: min(abs(hue_of(RGB[n]) - h), 360 - abs(hue_of(RGB[n]) - h)))


def key_colors(key_rgb):
    """12 тональностей → 12 цветов «ma colors» один к одному: по порядку оттенков,
    со сдвигом, при котором оттенки ближе всего"""
    order = sorted(range(12), key=lambda p: hue_of(key_rgb(p)))

    def dist(a, b):
        d = abs(a - b) % 360
        return min(d, 360 - d)

    best = min(range(12), key=lambda k: sum(dist(hue_of(key_rgb(p)), hue_of(RGB[HUES[(i + k) % 12]]))
                                             for i, p in enumerate(order)))
    out = [None] * 12
    for i, p in enumerate(order):
        out[p] = HUES[(i + best) % 12]
    return out


def exec_pairs(no_by=True):
    """список пар экзекьютора COLOR (как в ColorExec)"""
    out = [(c, c) for c in ("white", "cto", "red", "green", "blue", "cyan", "magenta", "yellow", "orange", "seagreen")]
    for a in BASE:
        out += [(a, b) for b in SECOND if b != a]
    out += [(c, "white") for c in ("red", "green", "blue", "cyan", "magenta", "yellow", "orange", "seagreen", "pink")]
    out.append(("cto", "ctb"))
    if no_by:
        out = [(a, b) for a, b in out if not ((a in WARM and b in COLD) or (a in COLD and b in WARM))]
    return out


def groups(s):
    ev = str(s.get("colx_ev") or "").strip()
    odd = str(s.get("colx_odd") or "").strip() or ev
    return ev, odd


def at(grp, name):
    return f'Group {grp} At Preset 4."{name}"'


def script(g, s, page):
    ev, odd = groups(s)
    out = []
    if s.get("colx_presets", True):
        out.append(("ClearAll", None))
        for gel, name in GELS:
            for grp in dict.fromkeys((ev, odd)):
                out += [(f"Group {grp} At Gel {gel}", None), (f'Store Preset 4."{name}" /m', None),
                        ("ClearAll", None)]
    out.append((f"Store Page {int(page)}", None))
    kc = key_colors(g.key_rgb)
    for position in range(12):
        ex = g.color_exec(page, position)
        c = kc[position]
        out += [("ClearAll", None), (at(ev, c), None)]
        if odd != ev:
            out.append((at(odd, c), None))
        out += [(f"Store Executor {ex} /o", None),
                (f'Label Executor {ex} "цвет {g.FIFTHS[position]} {c}"', None)]
    for position in range(12):
        ex = g.pair_exec(page, position)
        q = g.antagonist(position)
        a, b = kc[position], kc[q]
        out += [("ClearAll", None), (at(ev, a), None), (at(odd, b), None),
                (f"Store Executor {ex} /o", None),
                (f'Label Executor {ex} "пара {g.FIFTHS[position]} {a}-{b}"', None)]
    if s.get("colx_exec", True):
        ex = f"{int(page)}.50"
        for i, (a, b) in enumerate(exec_pairs(s.get("colx_no_by", True)), 1):
            r, gg, bb = RGB[a]
            name = a if a == b else f"{a}-{b}"
            out += [("ClearAll", None), (at(ev, a), None), (at(odd, b), None),
                    (f"Store Executor {ex} Cue {i} /o", f"Store Cue {i} Executor {ex} /o"),
                    (f'Label Executor {ex} Cue {i} "{name}"', None),
                    (f"Appearance Executor {ex} Cue {i} /red={r} /green={gg} /blue={bb}", None)]
        out += [("ClearAll", None), (f"Assign Goto Executor {ex}", None),
                (f'Label Executor {ex} "COLOR"', None),
                (f"Assign Fade 2 Cue 1 Thru Executor {ex}", None),
                (f"Assign Executor {ex} /offtime=2 /ooo=off", None)]
    out.append(("ClearAll", None))
    return out


def install_grandma2(g):
    if getattr(g, "_colx_installed", False):
        return g
    g._colx_installed = True
    for k, v in DEFAULTS.items():
        g.DEFAULTS.setdefault(k, v)
    holder = {"ctl": None}
    C = g.MA2Control
    original_init = C.__init__

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        holder["ctl"] = self

    C.__init__ = init
    original_script = g.color_script

    def color_script(page, roles=None):
        ctl = holder["ctl"]
        s = ctl.settings if ctl is not None else dict(g.DEFAULTS)
        if s.get("colx_on") and groups(s)[0]:
            return script(g, s, page)
        return original_script(page, roles)

    g.color_script = color_script
    g.colx_script = lambda s, page: script(g, s, page)
    return g


def install_gui(mg):
    if getattr(mg, "_colx_installed", False):
        return mg
    mg._colx_installed = True
    tk = mg.tk
    W = mg.MA2Window
    original_build = W.build

    def build(self, *args, **kwargs):
        result = original_build(self, *args, **kwargs)
        try:
            colx_panel(self)
        except Exception as e:
            try:
                self.ma.add_log(f"⚠ панель цветов: {e}")
            except Exception:
                pass
        return result

    W.build = build

    def colx_panel(self):
        ma = self.ma
        s = ma.settings
        box = self.panel("ЦВЕТА (как ColorExec)", self.body)
        line = tk.Frame(box, bg=mg.PANEL)
        line.pack(fill="x")
        on = tk.BooleanVar(value=bool(s.get("colx_on")))

        def toggle():
            vals = {"colx_on": bool(on.get())}
            if on.get() and ma.settings.get("pal_on", True):
                vals["pal_on"] = False
                ma.add_log("🎨 цвета как ColorExec - палитра Иттена выключена (вернуть можно в её окне)")
            ma.set(**vals)
            show()

        tk.Checkbutton(line, text="цвета по группам EV / ODD", variable=on, command=toggle,
                       bg=mg.PANEL, fg=mg.TEXT, activebackground=mg.PANEL, activeforeground=mg.TEXT,
                       selectcolor=mg.OFF, font=("Segoe UI", 9), highlightthickness=0).pack(side="left")
        fields = {}
        for text, key in (("EV группа", "colx_ev"), ("ODD группа", "colx_odd")):
            tk.Label(line, text=text, bg=mg.PANEL, fg=mg.DIM, font=("Segoe UI", 8)).pack(side="left", padx=(10, 3))
            e = fields[key] = self.entry(line, str(s.get(key, "") or ""), 10)
            e.pack(side="left")
        line2 = tk.Frame(box, bg=mg.PANEL)
        line2.pack(fill="x", pady=(3, 0))
        self.check(line2, "пресеты 4.x из Gel", "colx_presets", 0, mg.PANEL)
        self.check(line2, "экзекьютор COLOR со всеми парами", "colx_exec", 0, mg.PANEL)
        self.check(line2, "без сине-жёлтых пар", "colx_no_by", 0, mg.PANEL)
        info = tk.Label(box, text="", bg=mg.PANEL, fg=mg.DIM, font=("Segoe UI", 8), anchor="w")

        def save(_e=None):
            vals = {k: e.get().strip() for k, e in fields.items()}
            changed = {k: v for k, v in vals.items() if ma.settings.get(k) != v}
            if changed:
                ma.set(**changed)
            show()

        def show():
            st = ma.settings
            ev, odd = groups(st)
            page = int(st.get("fx_page", 10) or 10)
            if not st.get("colx_on"):
                text, warn = "выключено - цвета строятся как раньше", False
            elif not ev:
                text, warn = "впишите группу EV (ODD можно оставить пустой - тогда та же)", True
            else:
                text = (f"EV «{ev}», ODD «{odd}»: кью тональностей {page}.16-{page}.27, пары {page}.31-{page}.42"
                        + (f", COLOR {page}.50 ({len(exec_pairs(st.get('colx_no_by', True)))} кью)"
                           if st.get("colx_exec", True) else ""))
                warn = False
            info.configure(text=text, fg=mg.WARN if warn else mg.DIM)

        def rebuild():
            save()

            def done(*_a):
                try:
                    self.win.after(0, show)
                except Exception:
                    pass

            if not ma.create_effects(done, part="colors"):
                ma.add_log("🎨 цвета не пересозданы: нет связи с пультом или идёт другая операция")

        for e in fields.values():
            e.bind("<Return>", save)
            e.bind("<FocusOut>", save)
        mg.flat_button(line, "🎨 Пересоздать цвета", rebuild, mg.ACCENT).pack(side="left", padx=(10, 0))
        info.pack(fill="x", pady=(3, 0))
        tk.Label(box, text="Как плагин ColorExec: пресеты 4.\"red\"… из Gel (\"ma colors\", lee 201 / 205) для обеих "
                           "групп (/m), кью - «Group EV At Preset 4.\"цвет\"; Group ODD At Preset 4.\"цвет\"». "
                           "Тональности → 12 цветов по кругу оттенков, пара - антагонист на ODD. Группы можно менять "
                           "во время работы - впишите и нажмите «Пересоздать цвета».",
                 bg=mg.PANEL, fg=mg.DIM, font=("Segoe UI", 8), anchor="w", justify="left",
                 wraplength=860).pack(fill="x", pady=(2, 0))
        show()

    return mg


def install():
    import ma_wheel
    ma_wheel.register("grandma2", install_grandma2)
    ma_wheel.register("music_gui", install_gui)
