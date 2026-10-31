"""Связь MusicAnalyzer ↔ ma2_fxgen (генератор эффектов grandMA2).

Генератор после отправки на пульт пишет ~/.ma2_fxgen_link.json: какие
эффекты (шаблоны) он создал и в каких объектах Effects они лежат по группам.
Анализатор:
- кнопкой «🔗 Взять эффекты генератора» ставит эти Effects на экзекьюторы
  страниц 11-15 (Dimmer, Position, Color, Strobe, Комбо; один шаблон = подряд
  идущие экзекьюторы, по одному на группу),
  подписывает и привязывает к speed master своей категории (ma_bpm);
- автопилот вместо своих эффектов 10.1-10.12 включает эффекты генератора:
  пульс ← Dimmer, бег ← Position / Комбо, поток ← Color, искры ← Strobe
  (если какой-то категории нет - берёт ближайшую). Включает «Go Executor
  11.1 Thru 11.3», прежний гасит «Off Executor …». Круг, заливка, цвет по
  тональности и позиции работают как раньше.
"""
import json
import os
import re
import sys
import threading
import time

LINK_NAME = ".ma2_fxgen_link.json"
DEFAULTS = {"fxgen_on": True, "fxgen_page": 11, "fxgen_assigned": [], "fxgen_groups": [], "fxgen_mtime": 0.0,
            "fxgen_layout": {}}

# какие категории генератора подходят каждой группе автопилота (по порядку)
PREFER = {
    "пульс": ("dimmer", "combo", "strobe", "custom"),
    "бег": ("position", "combo", "dimmer", "custom"),
    "поток": ("color", "position", "combo", "custom"),
    "искры": ("strobe", "dimmer", "combo", "custom"),
}
RANGE = re.compile(r"^\s*(\d+\.\d+)\s*(?:-|thru)\s*(\d+\.\d+)\s*$", re.I)

_local = threading.local()


BUSY_NAME = ".ma2_fxgen_busy"
BUSY_STALE = 15.0
_busy = {"t": 0.0, "on": False}


def fxgen_busy():
    """генератор сейчас пишет на пульт (метка ~/.ma2_fxgen_busy свежая)"""
    now = time.time()
    if now - _busy["t"] < 0.3:
        return _busy["on"]
    try:
        age = now - os.path.getmtime(os.path.join(os.path.expanduser("~"), BUSY_NAME))
        on = age < BUSY_STALE
    except OSError:
        on = False
    _busy["t"], _busy["on"] = now, on
    return on


def link_paths(g):
    yield os.path.join(os.path.expanduser("~"), LINK_NAME)
    yield os.path.join(os.path.dirname(os.path.abspath(g.SETTINGS_FILE)), "fxgen_link.json")


def read_link(g):
    """→ (данные, путь) или (None, причина)"""
    found = [p for p in link_paths(g) if os.path.exists(p)]
    if not found:
        return None, "генератор ещё ничего не передал (нет " + LINK_NAME + ")"
    path = max(found, key=os.path.getmtime)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        return None, f"не читается {path}: {e}"
    looks = [l for l in data.get("looks") or [] if l.get("effects")]
    if not looks:
        return None, "в файле генератора нет эффектов"
    data["looks"] = looks
    data["_path"] = path
    data["_mtime"] = os.path.getmtime(path)
    return data, path


# 5 страниц экзекьюторов: по одной на категорию генератора
PAGE_CATS = (("dimmer",), ("position",), ("color",), ("strobe",), ("combo", "custom"))
PAGE_TITLES = ("Dimmer", "Position", "Color", "Strobe", "Комбо")


def page_of(cat, first_page):
    cat = (cat or "combo").lower()
    for i, cats in enumerate(PAGE_CATS):
        if cat in cats:
            return int(first_page) + i
    return int(first_page) + len(PAGE_CATS) - 1


def assign_script(data, page, master):
    """команды для пульта и список «эффект → экзекьюторы»; страницы page…page+4"""
    page = int(page)
    pages = [page + i for i in range(len(PAGE_CATS))]
    out, assigned, used = [(f"Store Page {p}", None) for p in pages], [], {p: 0 for p in pages}
    for look in data["looks"]:
        cat = (look.get("cat") or "combo").lower()
        p = page_of(cat, page)
        sm = master(cat) if callable(master) else master
        first = used[p] + 1
        for e in look["effects"]:
            used[p] += 1
            ex = f"{p}.{used[p]}"
            label = f'{look.get("name", look.get("key"))} · {e.get("group", "")}'.replace('"', "'")
            out += [(f"Assign Effect {e['no']} At Executor {ex}", None),
                    (f'Label Executor {ex} "{label[:30]}"', None),
                    (f'Assign SpecialMaster "speedmaster".{int(sm)} At Effect {e['no']}', None)]
        last = used[p]
        ex = f"{p}.{first}" if last == first else f"{p}.{first}-{p}.{last}"
        execs = [{"group": e.get("group", ""), "exec": f"{p}.{first + i}", **({"dim": True} if e.get("dim") else {})}
                 for i, e in enumerate(look["effects"])]
        # копии со сдвигом фазы (противофаза) - следом за обычными, в общий диапазон не входят
        for e, entry in zip(look["effects"], execs):
            if e.get("alt") is None:
                continue
            used[p] += 1
            alt = f"{p}.{used[p]}"
            label = f'{look.get("name", look.get("key"))} · {e.get("group", "")} ±{e.get("alt_phase", 180)}'
            out += [(f"Assign Effect {e['alt']} At Executor {alt}", None),
                    (f'Label Executor {alt} "{label.replace(chr(34), chr(39))[:30]}"', None),
                    (f'Assign SpecialMaster "speedmaster".{int(sm)} At Effect {e['alt']}', None)]
            entry["alt"] = alt
        assigned.append({"key": look.get("key"), "name": look.get("name", look.get("key")),
                         "cat": cat, "exec": ex, "execs": execs})
    for i, p in enumerate(pages):
        out.append((f'Label Page {p} "FX {PAGE_TITLES[i]}"', None))
    return out, assigned


def pools(assigned):
    by_cat = {}
    for a in assigned:
        by_cat.setdefault(a["cat"], []).append(a)
    result = {}
    for group, cats in PREFER.items():
        pool = []
        for c in cats:
            pool += by_cat.get(c, [])
        result[group] = pool or list(assigned)
    return result


def install_grandma2(g):
    if getattr(g, "_fxlink_installed", False):
        return g
    g._fxlink_installed = True
    for k, v in DEFAULTS.items():
        g.DEFAULTS.setdefault(k, v)

    def ctl():
        return getattr(g, "_fxlink_ctl", None)

    def active(c=None):
        c = c or ctl()
        s = getattr(c, "settings", None) or {}
        return bool(s.get("fxgen_on", True) and s.get("fxgen_assigned"))

    # --- запуск / гашение диапазона экзекьюторов «11.1-11.3» ---
    original_go, original_off = g.go_command, g.off_command

    def go_command(text):
        m = RANGE.match(text or "")
        if m:
            return f"Go Executor {m.group(1)} Thru {m.group(2)}"
        return original_go(text)

    def off_command(text):
        m = RANGE.match(text or "")
        if m:
            return f"Off Executor {m.group(1)} Thru {m.group(2)}"
        return original_off(text)

    g.go_command, g.off_command = go_command, off_command

    # --- автопилот берёт эффекты генератора ---
    original_fx_exec = g.fx_exec

    def fx_exec(page, group, variant):
        c = ctl()
        if group != "круг" and not getattr(_local, "creating", False) and active(c):
            pool = pools(c.settings["fxgen_assigned"]).get(group)
            if pool:
                seed = 0
                try:
                    seed = int((c.auto_state or {}).get("seed", 0))
                except Exception:
                    pass
                look = pool[(int(variant) + seed * 3) % len(pool)]
                c._fxlink_name = look["name"]
                return look["exec"]
        return original_fx_exec(page, group, variant)

    g.fx_exec = fx_exec

    original_fx_script = g.fx_script

    def fx_script(*args, **kwargs):
        # свои эффекты анализатора создаются на своих экзекьюторах, как раньше
        _local.creating = True
        try:
            return original_fx_script(*args, **kwargs)
        finally:
            _local.creating = False

    g.fx_script = fx_script

    C = g.MA2Control
    original_init = C.__init__

    def init(self, *args, **kwargs):
        g._fxlink_ctl = self
        original_init(self, *args, **kwargs)
        for k, v in DEFAULTS.items():
            self.settings.setdefault(k, v)

    C.__init__ = init

    # --- пока генератор пишет на пульт, анализатор молчит: пользователь тот же,
    # программер и выбор приборов общие - чужая команда сбила бы эффект ---
    # пауза - на уровне Telnet: через него идут и send, и run_checked, и фейдеры
    paused = {"on": False}

    def gate():
        """True - команду не слать"""
        c = ctl()
        if fxgen_busy():
            if not paused["on"]:
                paused["on"] = True
                try:
                    c.add_log("⏸ генератор пишет на пульт - анализатор ждёт")
                except Exception:
                    pass
            return True
        if paused["on"]:
            paused["on"] = False
            if c is not None:
                threading.Thread(target=resume, args=(c,), daemon=True).start()
        return False

    def original_send(self, cmd, *args, **kwargs):
        client = getattr(self, "client", None)
        return client.send(cmd) if client is not None else None

    def resume(self):
        """генератор закончил: вернуть пульту то, что анализатор держит сейчас"""
        try:
            self.add_log("▶ генератор закончил - анализатор снова управляет пультом")
            sh = self.__dict__.get("_show")
            if sh is not None:
                sh.fan["sent"] = {}
            for ex in list(getattr(self, "_rig_active", None) or []):
                original_send(self, f"Go Executor {ex}")
            if getattr(g, "palette_resend", None):
                g.palette_resend(self)
        except Exception as e:
            try:
                self.add_log(f"⚠ возврат после генератора: {e}")
            except Exception:
                pass


    # --- конец строки Telnet: часть пультов / onPC на «\r\n» отвечают
    # «Error #3: ILLEGAL CHARACTER» после каждой команды - переходим на «\r» ---
    T = getattr(g, "Telnet", None)
    if T is not None and not getattr(T, "_eol_patched", False):
        T._eol_patched = True
        original_tinit = T.__init__

        def tinit(self, log, *args, **kwargs):
            def watch(line, *a, **k):
                try:
                    if "illegal character" in str(line).lower():
                        eol = self.__dict__.get("eol", b"\r\n")
                        nxt = {b"\r\n": b"\r", b"\r": b"\n"}.get(eol)
                        # ответы на уже отправленные строки ещё идут - 3 с не переключаем дальше
                        if nxt and self.__dict__.get("eol_bad", 0) < 2 \
                                and time.time() - self.__dict__.get("eol_at", 0) > 3.0:
                            self.eol_bad = self.__dict__.get("eol_bad", 0) + 1
                            self.eol_at = time.time()
                            self.eol = nxt
                            log("пульт не принимает конец строки " + repr(eol) + " - перехожу на " + repr(nxt))
                except Exception:
                    pass
                return log(line, *a, **k)

            original_tinit(self, watch, *args, **kwargs)

        original_tsend = T.send

        def tsend(self, command, *args, **kwargs):
            if gate():
                return None
            return original_tsend(self, command, *args, **kwargs)

        T.send = tsend

        def write(self, command):
            self.sock.sendall(command.encode("utf-8", "replace") + self.__dict__.get("eol", b"\r\n"))
            self.sent += 1

        T.__init__ = tinit
        T.write = write

    original_autopilot = C.__dict__.get("autopilot")

    def autopilot(self):
        s = self.settings
        if active(self):
            return bool(self.enabled and s.get("autopilot"))
        return original_autopilot.fget(self) if isinstance(original_autopilot, property) else bool(
            self.enabled and s.get("autopilot") and s.get("fx_created"))

    C.autopilot = property(autopilot)

    original_on_bar = C.on_bar

    def on_bar(self, *args, **kwargs):
        self._fxlink_name = None
        result = original_on_bar(self, *args, **kwargs)
        name = getattr(self, "_fxlink_name", None)
        if name and self.auto_why and " (" in self.auto_why:
            # в строке автопилота - имя эффекта генератора, а не своего рецепта
            head, tail = self.auto_why.split(" (", 1)
            group = head.split(" · ", 1)[0]
            self.auto_why = f"{group} · {name} (" + tail
        return result

    C.on_bar = on_bar

    def fxgen_link(self, done=None):
        """прочитать файл генератора и поставить его эффекты на экзекьюторы"""
        data, why = read_link(g)
        if not data:
            self.add_log("🔗 " + why)
            if done:
                done([why])
            return False
        if not (self.enabled and self.client.connected) or self.fx_busy:
            if done:
                done(["нет связи с MA2" if not self.fx_busy else "уже создаю…"])
            return False
        self.fx_busy = True
        page = int(self.settings.get("fxgen_page", 11) or 11)
        master = self.settings.get("speed_master", 1)
        if self.settings.get("bpm_multi", True) and hasattr(g, "bpm_master_of"):
            master = lambda cat, s=self.settings: g.bpm_master_of(s, cat)
        script, assigned = assign_script(data, page, master)

        def run():
            errors = []
            try:
                self.add_log(f"🔗 ставлю {len(assigned)} эффектов генератора на страницы {page}-{page + 4} "
                             f"({len(script)} команд)…")
                for command, _ in script:
                    if not self.client.connected:
                        errors.append("связь пропала")
                        break
                    if self.run_checked(command):
                        errors.append(command)
                if not self.client.connected:
                    return
                old = self.auto_cmd
                self.settings["fxgen_assigned"] = assigned
                if data.get("groups"):
                    self.settings["fxgen_groups"] = data["groups"]
                if data.get("layout"):
                    self.settings["fxgen_layout"] = data["layout"]
                self.settings["fxgen_mtime"] = data["_mtime"]
                self.settings["fxgen_on"] = True
                g.save_settings(self.settings)
                if old:
                    off = g.off_command(old)
                    if off:
                        self.send(off)
                    self.auto_cmd = None
                self.add_log("🔗 эффекты генератора готовы: "
                             + ", ".join(f"{a['name']} {a['exec']}" for a in assigned[:6])
                             + (" …" if len(assigned) > 6 else "")
                             + (f"; ошибки MA2 на: {', '.join(errors[:4])}" if errors else ""))
            finally:
                self.fx_busy = False
                if done:
                    done(errors)

        threading.Thread(target=run, daemon=True).start()
        return True

    C.fxgen_link = fxgen_link

    def fxgen_summary(s):
        data, why = read_link(g)
        assigned = s.get("fxgen_assigned") or []
        lines = []
        if data:
            fresh = data["_mtime"] > float(s.get("fxgen_mtime") or 0) + 1
            lines.append(f"генератор передал {len(data['looks'])} эффектов ({data.get('written', '')})"
                         + (" - новые, нажмите «🔗 Взять эффекты генератора»" if fresh and assigned else ""))
        else:
            lines.append(why)
        if assigned:
            p = pools(assigned)
            lines.append("на пульте: " + " · ".join(f"{a['name']} {a['exec']}" for a in assigned[:8])
                         + (" …" if len(assigned) > 8 else ""))
            lines.append("автопилот: " + " · ".join(
                f"{grp} ← {', '.join(a['name'] for a in pool[:3])}" for grp, pool in p.items()))
        return "\n".join(lines), bool(data) and not assigned

    g.fxgen_summary = fxgen_summary
    return g


def install_gui(mg):
    if getattr(mg, "_fxlink_installed", False):
        return mg
    mg._fxlink_installed = True
    tk = mg.tk
    W = mg.MA2Window
    original_build = W.build

    def build(self, *args, **kwargs):
        result = original_build(self, *args, **kwargs)
        try:
            fxgen_panel(self)
        except Exception as e:
            try:
                self.ma.add_log(f"⚠ панель генератора: {e}")
            except Exception:
                pass
        return result

    W.build = build

    def fxgen_panel(self):
        import grandma2 as g2
        s = self.ma.settings
        box = self.panel("FX-ГЕНЕРАТОР (ma2_fxgen)", self.body)
        line = tk.Frame(box, bg=mg.PANEL)
        line.pack(fill="x")
        self.check(line, "автопилот берёт эффекты генератора", "fxgen_on", 0, mg.PANEL)
        tk.Label(line, text="страницы с", bg=mg.PANEL, fg=mg.DIM,
                 font=("Segoe UI", 8)).pack(side="left", padx=(10, 3))
        page = self.entry(line, str(s.get("fxgen_page", 11)), 4)
        page.pack(side="left")
        info = tk.Label(box, text="", bg=mg.PANEL, fg=mg.DIM, font=("Segoe UI", 8),
                        anchor="w", justify="left", wraplength=860)

        def show():
            text, todo = g2.fxgen_summary(self.ma.settings)
            info.configure(text=text, fg=mg.WARN if todo else mg.DIM)

        def save_page(_e=None):
            try:
                value = max(1, int(page.get().strip()))
            except ValueError:
                return
            if value != self.ma.settings.get("fxgen_page"):
                self.ma.set(fxgen_page=value)

        page.bind("<Return>", save_page)
        page.bind("<FocusOut>", save_page)

        def take():
            save_page()

            def done(errors):
                try:
                    self.win.after(0, show)
                except Exception:
                    pass

            if not self.ma.fxgen_link(done):
                show()

        mg.flat_button(line, "🔗 Взять эффекты генератора", take, mg.ACCENT).pack(side="left", padx=(12, 0))

        def open_gen():
            try:
                import ma_fxgen_app
                ma_fxgen_app.launch()
                self.ma.add_log("генератор эффектов открывается…")
            except Exception as e:
                self.ma.add_log(f"⚠ генератор не открылся: {e}")

        mg.flat_button(line, "🎛 Открыть генератор", open_gen, mg.ACCENT).pack(side="left", padx=(6, 0))
        info.pack(fill="x", pady=(3, 0))
        tk.Label(box, text="В генераторе: «Отправить на пульт» или «→ Анализатору». Тогда здесь «🔗 Взять…»: "
                           "эффекты встанут на 5 страниц подряд с этой (Dimmer, Position, Color, Strobe, Комбо), скорость - от speed master своей категории (см. «BPM: режимы»)."
                           " Dimmer → пульс, Position → бег, Color → поток, Strobe → искры",
                 bg=mg.PANEL, fg=mg.DIM, font=("Segoe UI", 8), anchor="w", justify="left",
                 wraplength=860).pack(fill="x", pady=(2, 0))
        show()

    return mg


def install():
    import ma_wheel
    ma_wheel.register("grandma2", install_grandma2)
    ma_wheel.register("music_gui", install_gui)
