"""Позиции голов как в PosExec: группа задаётся во время работы.

Встраивается в собранный анализатор поверх grandma2 / music_gui:
- вместо 8 своих позиций (каждому прибору свои pan / tilt по роли «середина»)
  экзекьютор позиций (page.30) строится как плагин PosExec: 9 позиций
  45, UP, DOWN, VEER, CENTER, X OPEN, X CLOSE, VEER UP, X UP;
- позиции пишутся пресетами 2."имя" (/m - дописываются для выбранной группы),
  кью - «Group N At Preset 2."имя"», так что одна раскладка работает на
  любую группу;
- группа (1, «1 + 3», «1 Thru 4») вводится в окне «🎛 grandMA2…», кнопка
  «🎯 Пересоздать позиции» перестраивает экзекьютор сразу, без перезапуска;
- пусто в поле группы - приборы роли «середина», как раньше.
Автопилот листает кью как прежде (Go+ по долям), их стало 9.
"""

POSITIONS = ("45", "UP", "DOWN", "VEER", "CENTER", "X OPEN", "X CLOSE", "VEER UP", "X UP")

DEFAULTS = {
    "pos_group": "",
    "pos_presets": True,
    "pos_spread": 40,
    "pos_tilt": 45,
}


def num(v):
    v = round(float(v), 2)
    return str(int(v)) if v == int(v) else str(v)


def position_cmds(name, spread=40, tilt=45):
    """команды программера для позиции (те же, что SetPosition в PosExec)"""
    sp, t = num(spread), num(tilt)
    base = {"45": [f'Attribute "pan" At 0', f'Attribute "tilt" At -{t}'],
            "UP": ['Attribute "pan" At 0', 'Attribute "tilt" At -90'],
            "DOWN": ['Attribute "pan" At 0', 'Attribute "tilt" At 0']}
    if name in base:
        return list(base[name])
    fan = f'Attribute "pan" At -{sp} Thru {sp}'
    rev = f'Attribute "pan" At {sp} Thru -{sp}'
    return {
        "VEER": base["45"] + [fan],
        "CENTER": base["45"] + [rev],
        "X OPEN": base["45"] + ["MAtricksGroups 2", fan],
        "X CLOSE": base["45"] + ["MAtricksGroups 2", rev],
        "VEER UP": base["UP"] + [fan],
        "X UP": base["UP"] + ["MAtricksGroups 2", fan],
    }.get(name, list(base["45"]))


def selection(s, roles, g):
    """«Group 3» из настройки или приборы роли «середина» (как раньше)"""
    grp = str(s.get("pos_group") or "").strip()
    if grp:
        return f"Group {grp}", f"группа {grp}"
    roles = {**getattr(g, "FX_ROLE_DEFAULTS", {}), **(roles or {})}
    try:
        kind, a, b = g.parse_selection(roles.get("mid") or "")
    except Exception:
        kind = None
    if kind is None or b - a > 64:
        return None, None
    return (f"{kind} {a}" if a == b else f"{kind} {a} Thru {b}"), f"{kind} {a}-{b}"


def make_script(g, settings):
    def position_script(page, roles=None):
        s = settings()
        sel, _ = selection(s, roles, g)
        if not sel:
            return []
        ex = g.pos_exec(page)
        spread, tilt = s.get("pos_spread", 40), s.get("pos_tilt", 45)
        out = [(f"Store Page {int(page)}", None)]
        if s.get("pos_presets", True):
            for name in POSITIONS:
                out += [("ClearAll", None), (sel, None)]
                out += [(c, None) for c in position_cmds(name, spread, tilt)]
                out += [(f'Store Preset 2."{name}" /m', None), ("MAtricksReset", None)]
            out.append(("ClearAll", None))
        for k, name in enumerate(POSITIONS, 1):
            out.append(("ClearAll", None))
            if s.get("pos_presets", True):
                out.append((f'{sel} At Preset 2."{name}"', None))
            else:
                out.append((sel, None))
                out += [(c, None) for c in position_cmds(name, spread, tilt)]
            out += [("MAtricksReset", None)] if not s.get("pos_presets", True) else []
            out += [(f"Store Executor {ex} Cue {k} /o", f"Store Cue {k} Executor {ex} /o"),
                    (f'Label Executor {ex} Cue {k} "{name}"', None),
                    (f"Assign Executor {ex} Cue {k} /fade=0.3", f"Assign Cue {k} Executor {ex} /fade=0.3")]
        out += [(f"Delete Executor {ex} Cue {len(POSITIONS) + 1} Thru 99 /noconfirm", None),
                (f'Label Executor {ex} "позиции по ударам"', None), ("ClearAll", None)]
        return out

    return position_script


def install_grandma2(g):
    if getattr(g, "_pos_installed", False):
        return g
    g._pos_installed = True
    for k, v in DEFAULTS.items():
        g.DEFAULTS.setdefault(k, v)
    holder = {"ctl": None}
    C = g.MA2Control
    original_init = C.__init__

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        holder["ctl"] = self

    C.__init__ = init

    def settings():
        ctl = holder["ctl"]
        return ctl.settings if ctl is not None else dict(g.DEFAULTS)

    g.position_script = make_script(g, settings)
    # pos_done сравнивает число ошибок с числом позиций
    g.FX_POSITIONS = [(name, lambda x, i: (0, 0)) for name in POSITIONS]
    return g


def install_gui(mg):
    if getattr(mg, "_pos_installed", False):
        return mg
    mg._pos_installed = True
    tk = mg.tk
    W = mg.MA2Window
    original_build = W.build

    def build(self, *args, **kwargs):
        result = original_build(self, *args, **kwargs)
        try:
            pos_panel(self)
        except Exception as e:
            try:
                self.ma.add_log(f"⚠ панель позиций: {e}")
            except Exception:
                pass
        return result

    W.build = build

    def pos_panel(self):
        import grandma2 as g2
        ma = self.ma
        s = ma.settings
        box = self.panel("ПОЗИЦИИ ГОЛОВ (как PosExec)", self.body)
        line = tk.Frame(box, bg=mg.PANEL)
        line.pack(fill="x")
        tk.Label(line, text="группа", bg=mg.PANEL, fg=mg.DIM, font=("Segoe UI", 8)).pack(side="left")
        grp = self.entry(line, str(s.get("pos_group", "") or ""), 12)
        grp.pack(side="left", padx=(4, 10))
        nums = {}
        for text, key in (("веер ±°", "pos_spread"), ("наклон 45 → °", "pos_tilt")):
            tk.Label(line, text=text, bg=mg.PANEL, fg=mg.DIM, font=("Segoe UI", 8)).pack(side="left")
            e = nums[key] = self.entry(line, num(s.get(key, DEFAULTS[key])), 4)
            e.pack(side="left", padx=(4, 10))
        self.check(line, "пресеты 2.x", "pos_presets", 0, mg.PANEL)
        info = tk.Label(box, text="", bg=mg.PANEL, fg=mg.DIM, font=("Segoe UI", 8), anchor="w")

        def save(_e=None):
            vals = {"pos_group": grp.get().strip()}
            for key, e in nums.items():
                try:
                    vals[key] = float(e.get().strip().replace(",", "."))
                except ValueError:
                    pass
            changed = {k: v for k, v in vals.items() if ma.settings.get(k) != v}
            if changed:
                ma.set(**changed)
            show()

        def show():
            sel, text = selection(ma.settings, ma.settings.get("fx_roles"), g2)
            ex = g2.pos_exec(int(ma.settings.get("fx_page", 10) or 10))
            info.configure(text=(f"Executor {ex}: {len(POSITIONS)} позиций для «{sel}»" if sel
                                 else "нет выборки: впишите группу или приборы роли «середина»"),
                           fg=mg.DIM if sel else mg.WARN)

        def rebuild():
            save()

            def done(*_a):
                try:
                    self.win.after(0, show)
                except Exception:
                    pass

            if not ma.create_effects(done, part="positions"):
                ma.add_log("🎯 позиции не пересозданы: нет связи с пультом или идёт другая операция")

        for e in [grp] + list(nums.values()):
            e.bind("<Return>", save)
            e.bind("<FocusOut>", save)
        mg.flat_button(line, "🎯 Пересоздать позиции", rebuild, mg.ACCENT).pack(side="left", padx=(10, 0))
        info.pack(fill="x", pady=(3, 0))
        tk.Label(box, text="Позиции: " + ", ".join(POSITIONS) + ". Группу можно менять во время работы - "
                           "впишите и нажмите «Пересоздать»: пресеты 2.x допишутся для неё (/m), кью - "
                           "«Group N At Preset 2.\"имя\"». Пусто - приборы роли «середина».",
                 bg=mg.PANEL, fg=mg.DIM, font=("Segoe UI", 8), anchor="w", justify="left",
                 wraplength=860).pack(fill="x", pady=(2, 0))
        show()

    return mg


def install():
    import ma_wheel
    ma_wheel.register("grandma2", install_grandma2)
    ma_wheel.register("music_gui", install_gui)
