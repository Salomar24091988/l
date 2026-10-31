"""Споты с цветовым колесом + пульт на 10.0.0.12.

Встраивается в собранный анализатор поверх grandma2 / music_gui:
- цветовые кью 10.16-10.27 и пары 10.31-10.42 задают цвет не только через
  COLORRGB1-3 (смешение), но и через колесо (COLOR1) у спотов. Каждой из
  12 тональностей достаётся ближайший по оттенку слот колеса, антагонисту -
  свой ближайший слот;
- слот можно задать числом (Attribute "COLOR1" At 15) или пресетом
  (At Preset 4.3) - тогда MA2 сам знает, где на колесе этот цвет;
- в окне «🎛 grandMA2…» панель «КОЛЕСО ЦВЕТА (СПОТЫ)»: приборы с колесом,
  атрибут, слоты, и что получилось по тональностям;
- адрес пульта по умолчанию 10.0.0.12 (логин тот же, remote / 1234); старый
  адрес в grandma2.json заменяется один раз.
"""
import colorsys
import re
import sys

HOST = "10.0.0.12"
OLD_HOSTS = ("192.168.2.105", "127.0.0.1", "")

WHEEL_DEFAULTS = {
    "wheel_on": True,
    # пусто - колесо получают все приборы баса и середины (у кого нет
    # колеса, MA2 строку пропустит); иначе - только эти приборы
    "wheel_fixtures": "",
    "wheel_attr": "COLOR1",
    "wheel_slots": "белый 0, красный 8, оранжевый 15, зелёный 29, "
                   "голубой 36, синий 43, пурпурный 50",
    "wheel_no_yellow": False,
    # цвета тональностей - пресетами Color 4.N (N = с этого номера, 12 подряд);
    # кью только ссылаются на них: поправили пресет на пульте - цвет меняется везде
    "color_presets": True,
    "color_preset_start": 101,
}

# цвет тональности (COLORRGB1-3, %), по квинтовому кругу C G D A E B F# Db Ab Eb Bb F.
# Без жёлтого: вместо него оранжевый. Соседние тональности - соседние оттенки,
# антагонист (через 6) - контрастный: рубин ↔ небесный, оранжевый ↔ индиго
KEY_PALETTE = (
    ("рубиновый", (100, 0, 10)),       # C
    ("алый", (100, 10, 0)),            # G
    ("оранжевый", (100, 30, 0)),       # D  (был жёлтый)
    ("зелёный", (10, 100, 5)),         # A  (был лаймовый)
    ("изумрудный", (0, 100, 45)),      # E
    ("бирюзовый", (0, 100, 85)),       # B
    ("небесный", (0, 60, 100)),        # F#
    ("королевский синий", (0, 20, 100)),  # Db
    ("индиго", (30, 0, 100)),          # Ab
    ("фиолетовый", (65, 0, 100)),      # Eb
    ("маджента", (100, 0, 75)),        # Bb
    ("фуксия", (100, 0, 35)),          # F
)


def key_rgb(position):
    return KEY_PALETTE[int(position) % 12][1]


# оттенок (градусы) по названию цвета; None - белый / без оттенка
HUES = (
    (("бел", "white", "open", "откр"), None),
    (("розов", "pink"), 330),
    (("малин", "crimson"), 345),
    (("крас", "red"), 0),
    (("оранж", "orange", "амбер", "amber"), 30),
    (("жёлт", "желт", "yellow"), 55),
    (("салат", "lime", "лайм"), 90),
    (("зел", "green"), 120),
    (("бирюз", "cyan", "циан", "teal"), 175),
    (("голуб", "light blue", "lightblue", "sky"), 200),
    (("синий", "син", "blue"), 235),
    (("фиол", "violet", "uv", "лаванд", "lavender"), 270),
    (("пурпур", "magenta", "маджент", "purple"), 300),
)


def hue_of(name):
    name = (name or "").strip().lower()
    for stems, hue in HUES:
        if any(name.startswith(s) for s in stems):
            return True, hue
    return False, None


def parse_slots(text):
    """«красный 8, синий 43; белый 0, зелёный=Preset 4.5» →
    [(название, оттенок или None, «8» / «Preset 4.5»)], [непонятые куски]"""
    slots, bad = [], []
    for part in re.split(r"[,;\n]+", text or ""):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(.+?)\s*[=:]?\s*((?:preset|пресет|p)\s*\d+(?:\.\d+)?|-?\d+(?:[.,]\d+)?)", part, re.I)
        if not m:
            bad.append(part)
            continue
        name, value = m.group(1).strip(" =:"), m.group(2).strip()
        known, hue = hue_of(name)
        if not known:
            bad.append(part)
            continue
        p = re.fullmatch(r"(?:preset|пресет|p)\s*(\d+(?:\.\d+)?)", value, re.I)
        if p:
            value = "Preset " + (p.group(1) if "." in p.group(1) else "4." + p.group(1))
        else:
            value = value.replace(",", ".")
        slots.append((name, hue, value))
    return slots, bad


def rgb_hue(rgb):
    r, g, b = (max(0, min(100, v)) / 100 for v in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return None if s < 0.2 else h * 360


def nearest_slot(rgb, slots):
    # ближайший по кругу оттенков цветной слот; белый - только если цветных нет
    hue = rgb_hue(rgb)
    colored = [s for s in slots if s[1] is not None]
    if hue is None or not colored:
        white = [s for s in slots if s[1] is None]
        return (white or colored or [None])[0]
    return min(colored, key=lambda s: min(abs(s[1] - hue), 360 - abs(s[1] - hue)))


def wheel_command(attr, value):
    if value.startswith("Preset"):
        return f"At {value}"
    return f'Attribute "{attr}" At {value}'


def install_grandma2(g):
    if getattr(g, "_wheel_installed", False):
        return g
    g._wheel_installed = True
    g.DEFAULTS["host"] = HOST
    g.key_rgb = key_rgb
    g.KEY_PALETTE = KEY_PALETTE
    for k, v in WHEEL_DEFAULTS.items():
        g.DEFAULTS.setdefault(k, v)

    original_load = g.load_settings

    def load_settings():
        settings = original_load()
        for k, v in WHEEL_DEFAULTS.items():
            settings.setdefault(k, v)
        if not settings.get("wheel_no_yellow"):
            # жёлтого больше нет: убрать его слот из сохранённого колеса (один раз)
            parts = [p for p in str(settings.get("wheel_slots") or "").split(",")
                     if not re.match(r"\s*(жёлт|желт|yellow)", p, re.I)]
            settings["wheel_slots"] = ",".join(parts).strip(" ,")
            settings["wheel_no_yellow"] = True
            try:
                g.save_settings(settings)
            except Exception:
                pass
        if not settings.get("host_10_0_0_12"):
            # пульт переехал на 10.0.0.12 - старый адрес меняется один раз,
            # дальше IP в окне можно ставить любой
            if (settings.get("host") or "").strip() in OLD_HOSTS:
                settings["host"] = HOST
            settings["host_10_0_0_12"] = True
            try:
                g.save_settings(settings)
            except Exception:
                pass
        return settings

    g.load_settings = load_settings

    def wheel_settings():
        # MA2Control держит настройки у себя; color_script их не получает,
        # поэтому берём их у последнего созданного MA2Control
        ctl = getattr(g, "_wheel_ctl", None)
        s = getattr(ctl, "settings", None) or load_settings()
        return s

    def split_wheel(selection, wheel_sel):
        """(выборка для RGB, выборка для колеса) из выборки роли"""
        sel = g.clean_selection(selection)
        if not wheel_sel:
            return sel, sel
        kind, ids = g.selection_ids(selection)
        wkind, wids = g.selection_ids(wheel_sel)
        if kind != "Fixture" or not ids or wkind != "Fixture" or not wids:
            return sel, None
        wset = set(wids)
        rgb = [i for i in ids if i not in wset]
        whl = [i for i in ids if i in wset]
        return (g.selection_command("Fixture", rgb) if rgb else None,
                g.selection_command("Fixture", whl) if whl else None)

    def color_lines(selection, position, wheel):
        rgb_sel, wheel_sel = selection
        out = []
        if rgb_sel:
            out.append((rgb_sel, None))
            for attribute, value in zip(("COLORRGB1", "COLORRGB2", "COLORRGB3"), g.key_rgb(position)):
                out.append((f'Attribute "{attribute}" At {value}', None))
        if wheel and wheel_sel:
            slot = nearest_slot(g.key_rgb(position), wheel["slots"])
            if slot:
                out.append((wheel_sel, None))
                out.append((wheel_command(wheel["attr"], slot[2]), None))
        return out

    def wheel_config(s):
        if not s.get("wheel_on", True):
            return None
        slots, _ = parse_slots(s.get("wheel_slots", ""))
        if not slots:
            return None
        attr = (s.get("wheel_attr") or "COLOR1").strip().strip('"') or "COLOR1"
        return {"slots": slots, "attr": attr}

    def color_script(page, roles=None):
        # как раньше (12 кью по тональности + 12 пар), плюс колесо у спотов
        roles = {**g.FX_ROLE_DEFAULTS, **(roles or {})}
        s = wheel_settings()
        wheel = wheel_config(s)
        wheel_sel = (s.get("wheel_fixtures") or "").strip() if wheel else ""
        if wheel_sel:
            wheel_sel = g.clean_selection(wheel_sel)
        selections = [split_wheel(roles.get(r), wheel_sel)
                      for r in ("bass", "mid") if (roles.get(r) or "").strip()]
        # приборы с колесом, которых нет ни в басе, ни в середине - цвет середины
        spare = None
        if wheel_sel:
            wkind, wids = g.selection_ids(wheel_sel)
            used = set()
            covered = True
            for r in ("bass", "mid"):
                kind, ids = g.selection_ids(roles.get(r) or "")
                if kind == "Fixture" and ids:
                    used.update(ids)
                elif (roles.get(r) or "").strip():
                    covered = False
            if wkind == "Fixture" and wids:
                rest = [i for i in wids if i not in used]
                if rest:
                    spare = (None, g.selection_command("Fixture", rest))
            elif not any(w for _, w in selections):
                spare = (None, wheel_sel)
        groups_ = selections + ([spare] if spare else [])
        out = []
        use_presets = bool(s.get("color_presets", True))
        try:
            start = int(s.get("color_preset_start", 101))
        except (TypeError, ValueError):
            start = 101
        if use_presets:
            for position in range(12):
                no = start + position
                out.append(("ClearAll", None))
                for selection in groups_:
                    out += color_lines(selection, position, wheel)
                out += [(f"Store Preset 4.{no} /o", None),
                        (f'Label Preset 4.{no} "{g.FIFTHS[position]} {KEY_PALETTE[position][0]}"', None)]

        def lines(selection, position):
            if not use_presets:
                return color_lines(selection, position, wheel)
            rgb_sel, w_sel = selection
            res = []
            for sel in (rgb_sel, w_sel if wheel and w_sel != rgb_sel else None):
                if sel:
                    res += [(sel, None), (f"At Preset 4.{start + position % 12}", None)]
            return res

        out.append((f"Store Page {int(page)}", None))
        for position in range(12):
            ex = g.color_exec(page, position)
            out.append(("ClearAll", None))
            for selection in groups_:
                out += lines(selection, position)
            out += [(f"Store Executor {ex} /o", None),
                    (f'Label Executor {ex} "цвет {g.FIFTHS[position]} / {g.MINORS[position]}"', None)]
        # пары: бас - основной цвет, середина (и лишние споты) - антагонист
        if len(selections) == 2:
            for position in range(12):
                ex = g.pair_exec(page, position)
                q = g.antagonist(position)
                out.append(("ClearAll", None))
                for selection, p in zip(groups_, (position, q, q)):
                    out += lines(selection, p)
                out += [(f"Store Executor {ex} /o", None),
                        (f'Label Executor {ex} "пара {g.FIFTHS[position]} + {g.FIFTHS[q]}"', None)]
        out.append(("ClearAll", None))
        return out

    g.color_script = color_script

    original_init = g.MA2Control.__init__

    def init(self, *args, **kwargs):
        g._wheel_ctl = self
        original_init(self, *args, **kwargs)

    g.MA2Control.__init__ = init

    def wheel_summary(s):
        """строка для окна: что получат споты по тональностям"""
        if not s.get("wheel_on", True):
            return "колесо выключено - споты цвет не получают", False
        slots, bad = parse_slots(s.get("wheel_slots", ""))
        if not slots:
            return "⚠ не понял слоты - пример: красный 8, синий 43, зелёный Preset 4.5", True
        parts = []
        for position in range(12):
            slot = nearest_slot(g.key_rgb(position), slots)
            parts.append(f"{g.FIFTHS[position]}→{slot[0]}" if slot else f"{g.FIFTHS[position]}→?")
        text = " · ".join(parts)
        if bad:
            text = "⚠ пропущено: " + ", ".join(bad) + "   " + text
        return text, bool(bad)

    g.wheel_summary = wheel_summary
    g.parse_slots = parse_slots
    return g



# =====================================================================
#  ПРОКРУТКА ОКОН: содержимое больше окна - появляются ползунки
# =====================================================================
_SCROLL_AREAS = []          # [(canvas, inner)]
_SCROLL_SKIP = ("Text", "Listbox", "Treeview", "Canvas", "Spinbox", "TCombobox", "Scale", "TScale")


def _on_wheel(event):
    """колесо мыши: крутит ближайшую область прокрутки под курсором"""
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
        if getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        else:
            step = -1 if event.delta > 0 else 1
        if event.state & 0x1:      # Shift - вбок
            target.xview_scroll(step * 3, "units")
        else:
            target.yview_scroll(step * 3, "units")
    except Exception:
        pass


def scroll_box(parent, bg=None, scrollbar=None, inner_cls=None, inner_kw=None):
    """холст с ползунками во весь parent; возвращает внутренний фрейм -
    в него кладётся содержимое. Ползунки видны, только когда не влезает."""
    import tkinter as tk
    canvas = tk.Canvas(parent, highlightthickness=0, bd=0)
    if bg:
        canvas.configure(bg=bg)
    sb = scrollbar or tk.Scrollbar
    vs = sb(parent, orient="vertical", command=canvas.yview)
    hs = sb(parent, orient="horizontal", command=canvas.xview)
    canvas.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
    canvas.grid(row=0, column=0, sticky="nsew")
    parent.rowconfigure(0, weight=1)
    parent.columnconfigure(0, weight=1)
    inner = (inner_cls or tk.Frame)(canvas, **(inner_kw or {}))
    if bg and not inner_kw:
        try:
            inner.configure(bg=bg)
        except Exception:
            pass
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
        except Exception:
            pass

    def poll():
        try:
            if not canvas.winfo_exists():
                return
        except Exception:
            return
        fit()
        canvas.after(400, poll)

    canvas.bind("<Configure>", fit, add="+")
    top = parent.winfo_toplevel()
    if not getattr(top, "_ma_wheel_bound", False):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            top.bind_all(seq, _on_wheel, add="+")
        top._ma_wheel_bound = True
    canvas.after(30, poll)
    return inner


def _make_scroll_inner():
    import tkinter as tk
    wm_names = [n for n in dir(tk.Wm) if not n.startswith("_") and n not in ("grid", "forget", "frame")]

    class ScrollInner(tk.Frame):
        """внутренность окна с прокруткой: для кода окна это и есть окно -
        title/geometry/protocol/bind и пр. уходят настоящему Toplevel"""

        def destroy(self):
            top = self.__dict__.get("_top")
            if top is not None and not self.__dict__.get("_dying"):
                self._dying = True
                try:
                    top.destroy()
                    return
                except Exception:
                    pass
            tk.Frame.destroy(self)

        def configure(self, cnf=None, **kw):
            bg = kw.get("bg", kw.get("background"))
            if isinstance(cnf, dict):
                bg = cnf.get("bg", cnf.get("background", bg))
            top = self.__dict__.get("_top")
            if bg and top is not None:
                for w in (top, self.master):
                    try:
                        w.configure(bg=bg)
                    except Exception:
                        pass
            return tk.Frame.configure(self, cnf, **kw)

        config = configure

    def delegate(name):
        def call(self, *args, **kwargs):
            args = [a._top if isinstance(a, ScrollInner) else a for a in args]
            return getattr(self._top, name)(*args, **kwargs)
        call.__name__ = name
        return call

    for n in wm_names + ["bind", "unbind", "lift", "tkraise", "lower", "focus_force", "grab_set", "grab_release"]:
        setattr(ScrollInner, n, delegate(n))
    return ScrollInner


_SCROLL_INNER = None


def scroll_toplevel(*args, **kwargs):
    """как tk.Toplevel, но содержимое прокручивается"""
    import tkinter as tk
    global _SCROLL_INNER
    if _SCROLL_INNER is None:
        _SCROLL_INNER = _make_scroll_inner()
    args = [a._top if isinstance(a, _SCROLL_INNER) else a for a in args]
    if isinstance(kwargs.get("master"), _SCROLL_INNER):
        kwargs["master"] = kwargs["master"]._top
    top = _REAL_TOPLEVEL[0](*args, **kwargs)
    bg = kwargs.get("bg") or kwargs.get("background") or top.cget("bg")
    inner = scroll_box(top, bg, inner_cls=_SCROLL_INNER, inner_kw={"bg": bg})
    inner._top = top
    try:
        top.minsize(320, 200)    # окно можно сделать меньше содержимого - для этого ползунки
    except Exception:
        pass
    return inner


_REAL_TOPLEVEL = []


def scrolled_init(original):
    """__init__ окна анализатора: на время создания tk.Toplevel даёт окно с прокруткой"""
    def init(self, *args, **kwargs):
        import tkinter as tk
        if not _REAL_TOPLEVEL:
            _REAL_TOPLEVEL.append(tk.Toplevel)
        real = _REAL_TOPLEVEL[0]
        tk.Toplevel = scroll_toplevel
        try:
            return original(self, *args, **kwargs)
        finally:
            tk.Toplevel = real
    return init


def install_gui(mg):
    if getattr(mg, "_wheel_installed", False):
        return mg
    mg._wheel_installed = True
    tk = mg.tk
    W = mg.MA2Window
    import tkinter
    if not _REAL_TOPLEVEL:
        _REAL_TOPLEVEL.append(tkinter.Toplevel)
    mg.scroll_toplevel = scroll_toplevel
    mg.scroll_box = scroll_box
    # окна анализатора: всё содержимое - с ползунками
    for cls_name in ("MA2Window", "LooksWindow", "StatsWindow"):
        cls = getattr(mg, cls_name, None)
        if cls is not None:
            cls.__init__ = scrolled_init(cls.__init__)
    original_build = W.build

    def build(self, *args, **kwargs):
        result = original_build(self, *args, **kwargs)
        try:
            wheel_panel(self)
        except Exception as e:  # окно не должно падать из-за панели
            try:
                self.ma.add_log(f"⚠ панель колеса: {e}")
            except Exception:
                pass
        return result

    W.build = build

    original_init = W.__init__

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            remember_connection(self)
        except Exception as e:
            try:
                self.ma.add_log(f"⚠ сохранение IP: {e}")
            except Exception:
                pass

    W.__init__ = init

    def remember_connection(self):
        # IP, порт, логин и пароль сохраняются в grandma2.json сразу при вводе
        # (Enter или переход в другое поле), без кнопки «Применить»
        import grandma2 as g2
        fields = getattr(self, "fields", None) or {}

        def save(_event=None):
            s = self.ma.settings
            values = {}
            for key, entry in fields.items():
                value = entry.get().strip() if key != "password" else entry.get()
                if key == "port":
                    try:
                        value = int(value)
                    except ValueError:
                        continue
                if key == "host" and not value:
                    continue
                values[key] = value
            if any(s.get(k) != v for k, v in values.items()):
                s.update(values)
                s["host_10_0_0_12"] = True
                g2.save_settings(s)
                self.ma.add_log(f"💾 сохранено: {s.get('host')}:{s.get('port')} ({s.get('user')})")

        for entry in fields.values():
            entry.bind("<Return>", save, add="+")
            entry.bind("<FocusOut>", save, add="+")

    def wheel_panel(self):
        import grandma2 as g2
        s = self.ma.settings
        for k, v in WHEEL_DEFAULTS.items():
            s.setdefault(k, v)
        box = self.panel("КОЛЕСО ЦВЕТА (СПОТЫ)", self.body)
        line = tk.Frame(box, bg=mg.PANEL)
        line.pack(fill="x")
        self.check(line, "цвет колесом", "wheel_on", 0, mg.PANEL)
        info = tk.Label(box, text="", bg=mg.PANEL, fg=mg.DIM, font=("Segoe UI", 8),
                        anchor="w", justify="left", wraplength=860)

        def show():
            text, bad = g2.wheel_summary(self.ma.settings)
            sel = (self.ma.settings.get("wheel_fixtures") or "").strip()
            who = ("приборы: " + g2.describe_selection(sel)) if sel else "приборы: все из баса и середины"
            info.configure(text=who + "\n" + text, fg=mg.WARN if bad else mg.DIM)

        def field(parent, label, key, width):
            tk.Label(parent, text=label, bg=mg.PANEL, fg=mg.DIM,
                     font=("Segoe UI", 8)).pack(side="left", padx=(10, 3))
            entry = self.entry(parent, str(self.ma.settings.get(key, "")), width)
            entry.pack(side="left")

            def save(_event=None):
                value = entry.get().strip()
                if value != str(self.ma.settings.get(key, "")):
                    self.ma.set(**{key: value})
                show()

            entry.bind("<Return>", save)
            entry.bind("<FocusOut>", save)
            return entry

        field(line, "приборы с колесом", "wheel_fixtures", 22)
        field(line, "атрибут", "wheel_attr", 9)
        line2 = tk.Frame(box, bg=mg.PANEL)
        line2.pack(fill="x", pady=(3, 0))
        field(line2, "слоты", "wheel_slots", 92)
        info.pack(fill="x", pady=(3, 0))
        tk.Label(box, text="Слот - число (Attribute \"COLOR1\" At 15) или пресет («зелёный Preset 4.5»). "
                           "Пусто в «приборы с колесом» - колесо получают все из баса и середины. "
                           "После правки нажмите «🎨 Пересоздать цвета»",
                 bg=mg.PANEL, fg=mg.DIM, font=("Segoe UI", 8), anchor="w", justify="left",
                 wraplength=860).pack(fill="x", pady=(2, 0))
        show()

    return mg


class _AfterImport:
    """Ставит заплатку на модуль сразу после его загрузки."""

    def __init__(self, patches):
        self.patches = patches

    def find_spec(self, name, path=None, target=None):
        if name not in self.patches:
            return None
        for finder in sys.meta_path:
            if finder is self or not hasattr(finder, "find_spec"):
                continue
            spec = finder.find_spec(name, path, target)
            if spec is not None:
                break
        else:
            return None
        loader = spec.loader
        exec_module = loader.exec_module
        patch = _apply

        class Loader:
            def create_module(self, spec):
                return loader.create_module(spec) if hasattr(loader, "create_module") else None

            def exec_module(self, module):
                exec_module(module)
                patch(module)

            def __getattr__(self, attr):
                return getattr(loader, attr)

        spec.loader = Loader()
        return spec


_PATCHES = {}
_HOOK = None


def register(name, patch):
    """ещё одна заплатка на модуль (применяется сразу, если модуль уже загружен)"""
    _PATCHES.setdefault(name, []).append(patch)
    if name in sys.modules:
        patch(sys.modules[name])


def _apply(module):
    for patch in _PATCHES.get(module.__name__, []):
        patch(module)


def install():
    global _HOOK
    if _HOOK is None:
        _HOOK = _AfterImport(_PATCHES)
        sys.meta_path.insert(0, _HOOK)
    register("grandma2", install_grandma2)
    register("music_gui", install_gui)
