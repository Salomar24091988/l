"""Режимы BPM: свой темп в каждый speed master.

Встраивается в собранный анализатор поверх grandma2 / music_gui:
- темп трека (BPM / bpm_div) уходит не в один speed master, а в четыре -
  по категориям эффектов генератора: Dimmer, Position, Color, Strobe
  (номера мастеров как у генератора, 1-4), у каждого свой множитель
  (¼, ½, ×1, ×2, ×4). Комбо-эффекты идут за мастером Position;
- режим поверх множителей:
    по такту  - множители как выставлены;
    по секции - брейк вдвое медленнее, дроп вдвое быстрее;
    по энергии - множитель плавно от ×½ до ×2 по громкости/плотности;
    ручной    - свой BPM (поле или Tap), темп трека не трогает пульт;
    стоп в брейке - в брейке все мастера в 0, иначе как по такту;
- в окне «🎛 grandMA2…» панель «BPM: РЕЖИМЫ» и строка, что ушло в мастера.
"""
import time

CATS = ("dimmer", "position", "color", "strobe")
CAT_NAMES = {"dimmer": "Dimmer", "position": "Position", "color": "Color", "strobe": "Strobe"}
MULTS = (0.25, 0.5, 1.0, 2.0, 4.0)
MULT_TEXT = {0.25: "¼", 0.5: "½", 1.0: "×1", 2.0: "×2", 4.0: "×4"}
MODES = (("beat", "по такту"), ("section", "по секции"), ("energy", "по энергии"),
         ("manual", "ручной"), ("stop", "стоп в брейке"))
SECTION_FACTOR = {"B": 0.5, "M": 1.0, "D": 2.0}
REFRESH = 8.0          # раз в столько секунд мастера шлются повторно, даже без изменений

DEFAULTS = {
    "bpm_multi": True,
    "bpm_mode": "beat",
    "bpm_sm_dimmer": 1, "bpm_sm_position": 2, "bpm_sm_color": 3, "bpm_sm_strobe": 4,
    "bpm_x_dimmer": 1.0, "bpm_x_position": 0.5, "bpm_x_color": 0.25, "bpm_x_strobe": 2.0,
    "bpm_manual": 120.0,
}


def section_code(sec):
    """D / M / B из того, что прислал анализатор (буква или слово)"""
    if not sec:
        return None
    t = str(sec).strip().lower()
    if t in ("d", "дроп", "drop") or t.startswith("дроп"):
        return "D"
    if t in ("b", "брейк", "break") or t.startswith("брейк"):
        return "B"
    if t in ("m", "середина", "mid", "middle") or t.startswith("серед"):
        return "M"
    return None


def feat(features, key):
    if isinstance(features, dict):
        return features.get(key)
    return getattr(features, key, None)


class Norm:
    """0..1 по тому, что уже звучало в треке (медленно забывает края)"""

    def __init__(self):
        self.lo = self.hi = None
        self.n = 0

    def add(self, v):
        if v is None:
            return None
        v = float(v)
        self.n += 1
        if self.lo is None:
            self.lo = self.hi = v
        self.lo = min(v, self.lo + (v - self.lo) * 0.02)
        self.hi = max(v, self.hi + (v - self.hi) * 0.02)
        if self.n < 4 or self.hi - self.lo < 1e-6:
            return 0.5
        return max(0.0, min(1.0, (v - self.lo) / (self.hi - self.lo)))


class State:
    def __init__(self):
        self.track = None          # BPM трека (до деления)
        self.section = None        # D / M / B
        self.norm = Norm()
        self.energy = None         # сглаженная 0..1
        self.out, self.out_t = {}, {}
        self.why = ""
        self.taps = []


def state(ctl):
    st = ctl.__dict__.get("_bpm")
    if st is None:
        st = ctl._bpm = State()
    return st


def masters(s):
    """[(категория, номер мастера)] без повторов мастера (первая категория побеждает)"""
    out, seen = [], set()
    for c in CATS:
        try:
            m = int(s.get(f"bpm_sm_{c}", DEFAULTS[f"bpm_sm_{c}"]))
        except (TypeError, ValueError):
            continue
        if m < 1 or m in seen:
            continue
        seen.add(m)
        out.append((c, m))
    return out


def master_of(s, cat):
    """номер мастера для категории эффекта генератора (комбо и прочее - как Position)"""
    cat = (cat or "").lower()
    if cat not in CATS:
        cat = "position"
    try:
        return int(s.get(f"bpm_sm_{cat}", DEFAULTS[f"bpm_sm_{cat}"]))
    except (TypeError, ValueError):
        return int(s.get("speed_master", 1) or 1)


def mode_factor(s, st):
    mode = s.get("bpm_mode", "beat")
    if mode == "section":
        return SECTION_FACTOR.get(st.section, 1.0), f"секция {st.section or '?'}"
    if mode == "energy":
        e = 0.5 if st.energy is None else st.energy
        f = 2 ** (2 * e - 1)                      # 0 → ×½, 0.5 → ×1, 1 → ×2
        f = round(f * 4) / 4                      # ступеньки по ¼, чтобы не дёргать пульт
        return max(0.5, min(2.0, f)), f"энергия {e:.2f}"
    if mode == "stop" and st.section == "B":
        return 0.0, "брейк - стоп"
    return 1.0, ""


def targets(ctl):
    """{мастер: BPM} и пояснение"""
    s, st = ctl.settings, state(ctl)
    if s.get("bpm_mode") == "manual":
        try:
            base = float(s.get("bpm_manual", 120) or 120)
        except (TypeError, ValueError):
            base = 120.0
        note = "ручной"
        factor = 1.0
    else:
        if not st.track:
            return {}, ""
        try:
            div = max(1, int(s.get("bpm_div", 1) or 1))
        except (TypeError, ValueError):
            div = 1
        base = st.track / div
        factor, note = mode_factor(s, st)
    out = {}
    for c, m in masters(s):
        try:
            x = float(s.get(f"bpm_x_{c}", DEFAULTS[f"bpm_x_{c}"]))
        except (TypeError, ValueError):
            x = 1.0
        v = base * x * factor
        out[m] = round(v, 1) if v else 0
    return out, note


def push(ctl, force=False):
    """отправить на пульт мастера, у которых темп заметно сменился"""
    import grandma2 as g
    s, st = ctl.settings, state(ctl)
    if not (ctl.enabled and s.get("bpm_on") and s.get("bpm_multi", True)):
        return
    tg, note = targets(ctl)
    if not tg:
        return
    now = time.time()
    step = getattr(g, "BPM_STEP", 0.5)
    interval = getattr(g, "BPM_INTERVAL", 1.0)
    parts = []
    for c, m in masters(s):
        v = tg.get(m)
        if v is None:
            continue
        parts.append(f"{CAT_NAMES[c][:3]} {m}: {num(v)}")
        prev, t = st.out.get(m), st.out_t.get(m, 0)
        if not force and prev is not None:
            if now - t < REFRESH and (abs(v - prev) < step or now - t < interval):
                continue
        integer = bool(s.get("bpm_integer")) and abs(v - round(v)) < 1e-9
        ctl.send(g.bpm_command(m, v, integer), key=f"bpm{m}")
        st.out[m], st.out_t[m] = v, now
    st.why = " · ".join(parts) + (f"  ({note})" if note else "")


def num(v):
    v = float(v)
    return str(int(v)) if v == int(v) else f"{v:.1f}"


def install_grandma2(g):
    if getattr(g, "_bpm_installed", False):
        return g
    g._bpm_installed = True
    for k, v in DEFAULTS.items():
        g.DEFAULTS.setdefault(k, v)
    C = g.MA2Control
    g.bpm_state, g.bpm_push, g.bpm_master_of = state, push, master_of

    original_on_bpm = C.on_bpm

    def on_bpm(self, bpm):
        s = self.settings
        if not s.get("bpm_multi", True):
            return original_on_bpm(self, bpm)
        if not (self.enabled and s.get("bpm_on")):
            return
        if s.get("bpm_mode") == "manual":
            return push(self)
        if not bpm or bpm < 40 or bpm > 300:
            return
        value = round(bpm) if s.get("bpm_integer") else round(bpm, 1)
        candidate, self.bpm_candidate = self.bpm_candidate, value
        if candidate is None or abs(candidate - value) > 1:
            return
        self.bpm_sent, self.bpm_time = value, time.time()
        state(self).track = value
        push(self)

    C.on_bpm = on_bpm

    original_on_bar = C.on_bar

    def on_bar(self, features, *args, **kwargs):
        result = original_on_bar(self, features, *args, **kwargs)
        try:
            st = state(self)
            a = getattr(self, "a", None)
            sec = section_code(kwargs.get("section") or feat(features, "section")
                               or getattr(self, "section", None) or getattr(a, "section", None))
            if sec:
                st.section = sec
            e = st.norm.add(feat(features, "energy"))
            if e is not None:
                st.energy = e if st.energy is None else st.energy + (e - st.energy) * 0.25
            push(self)
        except Exception as e:
            try:
                self.add_log(f"⚠ bpm: {e}")
            except Exception:
                pass
        return result

    C.on_bar = on_bar

    original_on_section = C.on_section

    def on_section(self, section):
        result = original_on_section(self, section)
        sec = section_code(section)
        if sec:
            state(self).section = sec
            try:
                push(self)
            except Exception:
                pass
        return result

    C.on_section = on_section

    original_new_track = C.new_track

    def new_track(self, *args, **kwargs):
        st = state(self)
        st.norm, st.energy, st.section = Norm(), None, None
        return original_new_track(self, *args, **kwargs)

    C.new_track = new_track

    def bpm_tap(self):
        """Tap: средний интервал последних ударов → ручной BPM"""
        st, now = state(self), time.time()
        st.taps = [t for t in st.taps if now - t < 3.0][-7:] + [now]
        if len(st.taps) < 2:
            return None
        gaps = [b - a for a, b in zip(st.taps, st.taps[1:])]
        bpm = round(60.0 / (sum(gaps) / len(gaps)), 1)
        if 30 <= bpm <= 300:
            self.set(bpm_manual=bpm)
            push(self, force=True)
            return bpm
        return None

    C.bpm_tap = bpm_tap
    return g


def install_gui(mg):
    if getattr(mg, "_bpm_installed", False):
        return mg
    mg._bpm_installed = True
    tk = mg.tk
    W = mg.MA2Window
    original_build = W.build

    def build(self, *args, **kwargs):
        result = original_build(self, *args, **kwargs)
        try:
            bpm_panel(self)
        except Exception as e:
            try:
                self.ma.add_log(f"⚠ панель BPM: {e}")
            except Exception:
                pass
        return result

    W.build = build

    def label(parent, text, bg=None):
        return tk.Label(parent, text=text, bg=bg or mg.PANEL, fg=mg.DIM, font=("Segoe UI", 8))

    def bpm_panel(self):
        import grandma2 as g2
        ma = self.ma
        s = ma.settings
        box = self.panel("BPM: РЕЖИМЫ", self.body)
        top = tk.Frame(box, bg=mg.PANEL)
        top.pack(fill="x")
        self.check(top, "свой темп в каждый speed master", "bpm_multi", 0, mg.PANEL)
        label(top, "режим").pack(side="left", padx=(12, 4))
        mode = tk.StringVar(value=s.get("bpm_mode", "beat"))

        def set_mode():
            ma.set(bpm_mode=mode.get())
            g2.bpm_push(ma, force=True)

        for key, text in MODES:
            tk.Radiobutton(top, text=text, value=key, variable=mode, command=set_mode,
                           bg=mg.PANEL, fg=mg.TEXT, activebackground=mg.PANEL, activeforeground=mg.TEXT,
                           selectcolor=mg.OFF, font=("Segoe UI", 9), highlightthickness=0).pack(side="left", padx=(0, 6))

        grid = tk.Frame(box, bg=mg.PANEL)
        grid.pack(fill="x", pady=(4, 0))
        label(grid, "категория").grid(row=0, column=0, sticky="w")
        label(grid, "мастер").grid(row=0, column=1, sticky="w", padx=(8, 0))
        label(grid, "множитель").grid(row=0, column=2, sticky="w", padx=(8, 0))
        entries = {}

        def save_master(c, e):
            try:
                v = max(1, int(e.get().strip()))
            except ValueError:
                return
            if v != ma.settings.get(f"bpm_sm_{c}"):
                ma.set(**{f"bpm_sm_{c}": v})
                g2.bpm_push(ma, force=True)

        for r, c in enumerate(CATS, start=1):
            tk.Label(grid, text=CAT_NAMES[c], bg=mg.PANEL, fg=mg.TEXT,
                     font=("Segoe UI", 9)).grid(row=r, column=0, sticky="w")
            e = entries[c] = self.entry(grid, str(s.get(f"bpm_sm_{c}", DEFAULTS[f"bpm_sm_{c}"])), 4)
            e.grid(row=r, column=1, sticky="w", padx=(8, 0))
            e.bind("<Return>", lambda _e, c=c, e=e: save_master(c, e))
            e.bind("<FocusOut>", lambda _e, c=c, e=e: save_master(c, e))
            row = tk.Frame(grid, bg=mg.PANEL)
            row.grid(row=r, column=2, sticky="w", padx=(8, 0))
            try:
                cur = float(s.get(f"bpm_x_{c}", DEFAULTS[f"bpm_x_{c}"]))
            except (TypeError, ValueError):
                cur = 1.0
            var = tk.DoubleVar(value=cur)

            def set_x(c=c, var=var):
                ma.set(**{f"bpm_x_{c}": float(var.get())})
                g2.bpm_push(ma, force=True)

            for x in MULTS:
                tk.Radiobutton(row, text=MULT_TEXT[x], value=x, variable=var, command=set_x,
                               bg=mg.PANEL, fg=mg.TEXT, activebackground=mg.PANEL, activeforeground=mg.TEXT,
                               selectcolor=mg.OFF, font=("Segoe UI", 9), highlightthickness=0).pack(side="left", padx=(0, 4))

        man = tk.Frame(box, bg=mg.PANEL)
        man.pack(fill="x", pady=(4, 0))
        label(man, "ручной BPM").pack(side="left")
        manual = self.entry(man, num(s.get("bpm_manual", 120)), 6)
        manual.pack(side="left", padx=(4, 6))

        def save_manual(_e=None):
            try:
                v = float(manual.get().strip().replace(",", "."))
            except ValueError:
                return
            if 1 <= v <= 400 and v != ma.settings.get("bpm_manual"):
                ma.set(bpm_manual=v)
                g2.bpm_push(ma, force=True)

        manual.bind("<Return>", save_manual)
        manual.bind("<FocusOut>", save_manual)

        def tap():
            bpm = ma.bpm_tap()
            if bpm:
                manual.delete(0, "end")
                manual.insert(0, num(bpm))

        mg.flat_button(man, "👆 Tap", tap, mg.ACCENT).pack(side="left")
        label(man, "(Tap ставит ручной BPM; в режиме «ручной» темп трека на пульт не идёт)").pack(side="left", padx=(8, 0))

        status = tk.Label(box, text="", bg=mg.PANEL, fg=mg.TEXT, font=("Segoe UI", 9), anchor="w")
        status.pack(fill="x", pady=(4, 0))
        tk.Label(box, text="Мастера - те же Speed-группы, что ставит генератор (Dimmer 1, Position 2, Color 3, Strobe 4; "
                           "комбо - за Position). Темп = BPM трека / «делитель BPM» × множитель × режим. "
                           "По секции: брейк ×½, дроп ×2. По энергии: от ×½ до ×2.",
                 bg=mg.PANEL, fg=mg.DIM, font=("Segoe UI", 8), anchor="w", justify="left",
                 wraplength=860).pack(fill="x", pady=(2, 0))

        def tick():
            try:
                if not status.winfo_exists():
                    return
                st = g2.bpm_state(ma)
                if ma.settings.get("bpm_mode") == "manual":
                    g2.bpm_push(ma)          # без музыки on_bpm не зовётся - держим ручной темп сами
                if not ma.settings.get("bpm_multi", True):
                    text = "выключено - темп идёт в один speed master, как раньше"
                else:
                    text = ("→ " + st.why) if st.why else "темп ещё не отправлялся"
                status.configure(text=text)
                status.after(500, tick)
            except Exception:
                pass

        tick()

    return mg


def install():
    import ma_wheel
    ma_wheel.register("grandma2", install_grandma2)
    ma_wheel.register("music_gui", install_gui)
