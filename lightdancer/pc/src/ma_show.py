"""Сценарий света поверх дорожек ma_rig.

Веер лучей по музыке. Приборы с Pan/Tilt из Layout генератора расходятся
веером: ширина - от громкости, высота (Tilt) - от яркости звука (верха - лучи
в зал, бас - в пол), направление - вместе с «нажимом». Автопилот сам решает,
когда включить веер: нарастание, поток, пик; выключает на «беге», в быстром
темпе и в тишине. Пока веер включён, эффекты движения этих групп отдыхают.

Сценарий трека из базы. Для трека, который уже играл, по всем его
проигрываниям (music_patterns.db: такты, полосы, секции, паттерны) заранее
размечается, где нарастание, пик, спокойные места и смены секций. Веер
раскрывается к пику заранее, цвет и движение меняются на границах секций,
стробо - только на настоящих пиках. Живой счёт тактов сверяется с паттернами
сценария; если сбился - работает живой автопилот.

Журнал и «Сохранить». Что стояло на каждой дорожке в каждой секции трека,
пишется в базу (таблицы ma2_*). «💾 Сохранить» запоминает текущую секцию
трека (дроп, середина, брейк) - в следующий раз в ней будет ровно это.
Несохранённое в следующий раз пробуется другим вариантом.
"""
import json
import math
import threading
import time
from datetime import datetime

DEFAULTS = {
    "show_on": True,          # сценарий из базы для знакомых треков
    "fan_auto": True,         # автопилот сам включает веер
    "fan_always": False,      # веер всегда (вручную)
    "fan_over_gen": False,    # веер и при эффектах генератора (Pan/Tilt в программере перекрывает их)
    "fan_groups": None,       # None - все группы с Pan/Tilt на Layout; иначе список ID групп
    "fan_width": 12.0,        # шаг Pan между соседними приборами на полном раскрытии, °
    "fan_tilt_lo": 15.0,      # Tilt от вертикали, когда в звуке бас
    "fan_tilt_hi": 60.0,      # … когда в звуке верха
    "fan_fade": 0.5,          # переход - доля удара
    "fan_release": "ClearAll",   # вернуть Pan/Tilt эффектам (палитра потом пересылается)
}
PT_DEFAULT = {"pan": 540.0, "tilt": 270.0}
PHRASE = 8
FAN_MIN_BARS = 8          # держится минимум фразу
FAN_MAX_BARS = 16         # не дольше двух фраз подряд
FAN_COOLDOWN = 8          # после выключения - фраза без веера
BUILD_BARS = 8            # нарастание к пику
PEAK_BARS = 4
SECTION_NAMES = {"D": "дроп", "M": "середина", "B": "брейк"}
MOOD_NAMES = {"build": "нарастание", "peak": "пик", "flow": "поток", "calm": "спокойно", "drive": "драйв"}
PALETTE_MOOD = {"build": "бег", "peak": "peak", "flow": "поток", "calm": "calm"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS ma2_script (
    track_id  INTEGER PRIMARY KEY,
    src_bars  INTEGER,      -- сколько тактов базы было при расчёте
    data      TEXT,         -- JSON: разметка по тактам
    built_at  TEXT
);
CREATE TABLE IF NOT EXISTS ma2_looks (
    key       TEXT PRIMARY KEY,   -- track:<id>:<секция> или section:<секция>
    track_id  INTEGER,
    section   TEXT,
    data      TEXT,               -- JSON: что стоит на дорожках
    updated   TEXT
);
CREATE TABLE IF NOT EXISTS ma2_log (
    id        INTEGER PRIMARY KEY,
    play_id   INTEGER,
    track_id  INTEGER,
    bar_from  INTEGER,
    bar_to    INTEGER,
    section   TEXT,
    look_key  TEXT,
    saved     INTEGER,
    data      TEXT,
    at        TEXT
);
CREATE TABLE IF NOT EXISTS ma2_tried (
    key       TEXT,      -- ключ образа (трек + секция)
    slot      TEXT,      -- дорожка|тип
    value     TEXT,      -- что стояло
    n         INTEGER DEFAULT 0,
    PRIMARY KEY (key, slot, value)
);
"""


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def num(v):
    v = round(float(v), 1)
    return int(v) if v.is_integer() else v


# =====================================================================
#  ГЕОМЕТРИЯ (как в генераторе: aim_dir)
# =====================================================================
def aim_dir(fix, heading, tilt, rng=None, prev=None):
    """Pan/Tilt прибора для направления луча: heading - по плану (0 - в зал,
    + к правому краю сцены), tilt - от вертикали. Поворот и инверсии учтены."""
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


def fan_groups(s):
    """{ID группы: [приборы с Pan/Tilt слева направо]} из Layout генератора"""
    lay = s.get("fxgen_layout") or {}
    allowed = s.get("fan_groups")
    out = {}
    for f in (lay.get("fix") or {}).values():
        gid = f.get("group")
        if gid is None or f.get("x") is None or "pt" not in (f.get("caps") or []):
            continue
        if allowed is not None and gid not in allowed:
            continue
        out.setdefault(gid, []).append(f)
    for gid in out:
        out[gid].sort(key=lambda f: (_f(f.get("x")), _f(f.get("y")), int(f.get("id") or 0)))
    return out


def fan_aims(s, width, tilt, direction=1, prev=None):
    """веер: средний прибор группы смотрит в зал, соседи расходятся на шаг.
    width, tilt - 0..1 → {id: (pan, tilt)}"""
    lay = s.get("fxgen_layout") or {}
    pts = lay.get("pt") or {}
    step = _f(s.get("fan_width"), 12.0) * max(0.0, min(1.0, width))
    lo, hi = _f(s.get("fan_tilt_lo"), 15.0), _f(s.get("fan_tilt_hi"), 60.0)
    t_deg = lo + (hi - lo) * max(0.0, min(1.0, tilt))
    prev = prev or {}
    out = {}
    for _gid, fixes in fan_groups(s).items():
        n = len(fixes)
        for i, f in enumerate(fixes):
            k = i - (n - 1) / 2.0
            rng = {**PT_DEFAULT, **(pts.get(f.get("type")) or {})}
            a = aim_dir(f, direction * k * step, t_deg, rng, prev.get(f.get("id")))
            if a is not None:
                out[f.get("id")] = a
    return out


# =====================================================================
#  ЗВУК
# =====================================================================
def feat(features, key):
    if isinstance(features, dict):
        return features.get(key)
    return getattr(features, key, None)


def brightness(features):
    """доля верхов в ударах такта: 0 - один бас, 1 - одни верха"""
    hits, strength = feat(features, "hits"), feat(features, "strength")
    try:
        h = [float(x or 0) for x in list(hits)[:3]]
        s = [float(x or 0) for x in list(strength)[:3]] if strength is not None else [1.0, 1.0, 1.0]
        lo, mid, hi = (h[0] * max(s[0], 0.1), h[1] * max(s[1], 0.1), h[2] * max(s[2], 0.1))
        total = lo + mid + hi
        return (hi + 0.5 * mid) / total if total > 0 else None
    except (TypeError, ValueError, IndexError):
        return None


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


# =====================================================================
#  СЦЕНАРИЙ ТРЕКА ИЗ БАЗЫ
# =====================================================================
def percentile(vals, q):
    v = sorted(vals)
    if not v:
        return 0.0
    i = max(0, min(len(v) - 1, int(round(q * (len(v) - 1)))))
    return v[i]


def mode_of(items):
    best, cnt = None, 0
    seen = {}
    for x in items:
        seen[x] = seen.get(x, 0) + 1
        if seen[x] > cnt:
            best, cnt = x, seen[x]
    return best


def bars_of(conn, track_id):
    """такты всех проигрываний трека → {номер такта: собранное}, всего строк"""
    rows = conn.execute("SELECT b.bar, b.bands, b.section, b.pattern FROM bars b JOIN plays p ON b.play_id = p.id "
                        "WHERE p.track_id = ? AND b.bar IS NOT NULL", (track_id,)).fetchall()
    per = {}
    for bar, bands, sec, pat in rows:
        try:
            bl = [float(x) for x in json.loads(bands)] if bands else None
        except (TypeError, ValueError):
            bl = None
        d = per.setdefault(int(bar), {"e": [], "t": [], "s": [], "p": []})
        if bl:
            total = sum(bl)
            d["e"].append(total / len(bl))
            if total > 0 and len(bl) >= 5:
                d["t"].append(sum(bl[4:]) / total)
        if sec:
            d["s"].append(sec)
        if pat and pat not in ("?", "-"):
            d["p"].append(pat)
    return per, len(rows)


def plan_track(per):
    """разметка трека по тактам: настроение, веер, события"""
    if not per:
        return None
    n = max(per)
    if n < 16:
        return None
    E, T, S, P = [], [], [], []
    for b in range(1, n + 1):
        d = per.get(b) or {}
        E.append(sum(d["e"]) / len(d["e"]) if d.get("e") else None)
        T.append(sum(d["t"]) / len(d["t"]) if d.get("t") else None)
        S.append(mode_of(d.get("s") or []))
        P.append(mode_of(d.get("p") or []))
    for arr, dflt in ((E, 0.0), (T, 0.3), (S, "M")):
        last = next((x for x in arr if x is not None), dflt)
        for i, x in enumerate(arr):
            if x is None:
                arr[i] = last
            else:
                last = x
    Es = [sum(E[max(0, i - 1):i + 2]) / len(E[max(0, i - 1):i + 2]) for i in range(n)]
    lo, hi = percentile(Es, 0.1), percentile(Es, 0.95)
    En = [max(0.0, min(1.0, (e - lo) / (hi - lo))) if hi > lo else 0.5 for e in Es]
    tlo, thi = percentile(T, 0.1), percentile(T, 0.9)
    Tn = [max(0.0, min(1.0, (t - tlo) / (thi - tlo))) if thi > tlo else 0.5 for t in T]
    # секции: короткие куски (1 такт) приклеиваются к соседу
    for i in range(1, n - 1):
        if S[i] != S[i - 1] and S[i] != S[i + 1]:
            S[i] = S[i - 1]
    segments, start = [], 0
    for i in range(1, n + 1):
        if i == n or S[i] != S[start]:
            segments.append((start + 1, i, S[start]))
            start = i
    # пики: начало дропа после не-дропа или резкий скачок громкости
    cands = []
    for k, (a, _b, sec) in enumerate(segments):
        if sec == "D" and (k == 0 or segments[k - 1][2] != "D") and a > 1:
            cands.append(a)
    for i in range(4, n):
        before = sum(En[i - 4:i]) / 4
        if En[i] - before >= 0.3 and En[i] >= 0.65:
            cands.append(i + 1)
    peaks = []
    for p in sorted(set(cands)):
        if not peaks or p - peaks[-1] >= 8:
            peaks.append(p)
    builds = {}
    prev = 0
    for p in peaks:
        a = max(1, p - BUILD_BARS, prev + PEAK_BARS)
        if p - 1 >= a and En[p - 2] - En[a - 1] < 0.05:
            a = max(a, p - 4)
        for b in range(a, p):
            builds[b] = (b - a + 1) / max(1, p - a)
        prev = p
    seg_len = {}
    for a, b, sec in segments:
        for i in range(a, b + 1):
            seg_len[i] = b - a + 1
    peak_bars = {b for p in peaks for b in range(p, min(n, p + PEAK_BARS - 1) + 1)}
    moods = []
    for b in range(1, n + 1):
        e, sec = En[b - 1], S[b - 1]
        if b in peak_bars and sec != "B":
            m = "peak"
        elif b in builds:
            m = "build"
        elif e < 0.25 or sec == "B":
            m = "calm"
        elif e < 0.6:
            m = "flow"
        else:
            m = "drive"
        moods.append(m)
    # веер: нарастание и пик всегда, поток - если секция длинная; ограничения по длине
    fan = [0.0] * n
    on, since, off_at = False, 0, -FAN_COOLDOWN
    for b in range(1, n + 1):
        m = moods[b - 1]
        want = m in ("build", "peak") or (m == "flow" and seg_len.get(b, 0) >= 8)
        if b > n - 4:
            want = False
        if on:
            run = b - since
            if (not want and run >= FAN_MIN_BARS) or (run >= FAN_MAX_BARS and m != "peak") or b > n - 4:
                on, off_at = False, b
        elif want and (b - off_at >= FAN_COOLDOWN or m in ("build", "peak")):
            on, since = True, b
        if on:
            if m == "peak":
                w = 1.0
            elif m == "build":
                w = 0.25 + 0.7 * builds.get(b, 0.5)
            else:
                w = 0.3 + 0.4 * En[b - 1]
            fan[b - 1] = round(w, 2)
    bars = []
    seg_starts = {a for a, _b, _s in segments}
    for b in range(1, n + 1):
        ev = []
        if b in seg_starts:
            ev += ["seg", "color"]
        if b in peaks:
            ev += ["peak"] + ([] if "color" in ev else ["color"])
            if En[b - 1] >= 0.8 and S[b - 1] == "D":
                ev.append("strobe")
        if b - 1 in peaks and En[b - 1] >= 0.8 and S[b - 1] == "D":
            ev.append("strobe")
        bars.append({"e": round(En[b - 1], 2), "t": round(Tn[b - 1], 2), "s": S[b - 1], "p": P[b - 1],
                     "m": moods[b - 1], "fan": fan[b - 1], "ev": ev})
    return {"n": n, "bars": bars, "peaks": peaks, "segments": segments}


class ShowDB:
    """свои таблицы в базе анализатора (music_patterns.db). Старые таблицы не трогаем"""

    def __init__(self, pdb):
        self.pdb = pdb
        self.conn = getattr(pdb, "db", None)
        self.lock = getattr(pdb, "lock", None) or threading.Lock()
        self.ok = self.conn is not None
        if self.ok:
            with self.lock:
                self.conn.executescript(SCHEMA)
                self.conn.commit()

    def script(self, track_id, rebuild=False):
        """сценарий трека: из кэша или пересчитать, если в базе прибавилось тактов"""
        if not (self.ok and track_id):
            return None
        with self.lock:
            per, total = bars_of(self.conn, track_id)
            row = self.conn.execute("SELECT src_bars, data FROM ma2_script WHERE track_id = ?", (track_id,)).fetchone()
        if row and row[0] == total and not rebuild:
            try:
                return json.loads(row[1])
            except (TypeError, ValueError):
                pass
        plan = plan_track(per)
        if plan is None:
            return None
        plan["track_id"] = track_id
        with self.lock:
            self.conn.execute("INSERT OR REPLACE INTO ma2_script(track_id, src_bars, data, built_at) VALUES (?, ?, ?, ?)",
                              (track_id, total, json.dumps(plan, ensure_ascii=False),
                               datetime.now().isoformat(timespec="seconds")))
            self.conn.commit()
        return plan

    def build_all(self, progress=None):
        if not self.ok:
            return 0, 0
        with self.lock:
            ids = [r[0] for r in self.conn.execute(
                "SELECT DISTINCT track_id FROM plays WHERE bars > 0 AND track_id IS NOT NULL").fetchall()]
        made = 0
        for i, tid in enumerate(ids):
            if self.script(tid):
                made += 1
            if progress:
                progress(i + 1, len(ids))
        return made, len(ids)

    def look(self, key):
        if not self.ok:
            return None
        with self.lock:
            row = self.conn.execute("SELECT data FROM ma2_looks WHERE key = ?", (key,)).fetchone()
        try:
            return json.loads(row[0]) if row else None
        except (TypeError, ValueError):
            return None

    def save_look(self, key, track_id, section, data):
        if not self.ok:
            return False
        with self.lock:
            self.conn.execute("INSERT OR REPLACE INTO ma2_looks(key, track_id, section, data, updated) "
                              "VALUES (?, ?, ?, ?, ?)", (key, track_id, section, json.dumps(data, ensure_ascii=False),
                                                         datetime.now().isoformat(timespec="seconds")))
            self.conn.commit()
        return True

    def drop_look(self, key):
        if not self.ok:
            return False
        with self.lock:
            self.conn.execute("DELETE FROM ma2_looks WHERE key = ?", (key,))
            self.conn.commit()
        return True

    def saved_keys(self, track_id):
        if not self.ok:
            return {}
        with self.lock:
            rows = self.conn.execute("SELECT key, section FROM ma2_looks WHERE track_id = ?", (track_id,)).fetchall()
        return {sec: key for key, sec in rows}

    def tried(self, key):
        if not self.ok:
            return {}
        with self.lock:
            rows = self.conn.execute("SELECT slot, value, n FROM ma2_tried WHERE key = ?", (key,)).fetchall()
        out = {}
        for slot, value, n in rows:
            out.setdefault(slot, {})[value] = n
        return out

    def log(self, play_id, track_id, bar_from, bar_to, section, key, saved, data):
        if not self.ok:
            return
        with self.lock:
            self.conn.execute("INSERT INTO ma2_log(play_id, track_id, bar_from, bar_to, section, look_key, saved, data, at) "
                              "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                              (play_id, track_id, bar_from, bar_to, section, key, int(bool(saved)),
                               json.dumps(data, ensure_ascii=False), datetime.now().isoformat(timespec="seconds")))
            if not saved:
                for slot, value in slots_of(data):
                    self.conn.execute("INSERT INTO ma2_tried(key, slot, value, n) VALUES (?, ?, ?, 1) "
                                      "ON CONFLICT(key, slot, value) DO UPDATE SET n = n + 1", (key, slot, value))
            self.conn.commit()


def slots_of(data):
    """что стояло на дорожках → [(слот, значение)] для учёта показанного"""
    out = [(slot, str(v)) for slot, v in (data.get("sel") or {}).items() if v]
    pal = data.get("palette") or {}
    if pal.get("harmony"):
        out.append(("palette", pal["harmony"]))
    for mode, name in (data.get("beam") or {}).items():
        if name:
            out.append((f"beam|{mode}", str(name)))
    return out


def force_of(data):
    """сохранённый образ → что навязать дорожкам"""
    force = dict(data.get("sel") or {})
    if data.get("palette"):
        force["palette"] = data["palette"]
    for mode, name in (data.get("beam") or {}).items():
        force[f"beam|{mode}"] = name
    if "fan" in data:
        force["fan"] = bool(data["fan"])
    if data.get("dir"):
        force["dir"] = data["dir"]
    return force


def avoid_of(tried):
    """показанные и не сохранённые варианты - реже"""
    out = {}
    for slot, vals in (tried or {}).items():
        out[slot] = dict(vals)
    return out


# =====================================================================
#  СОСТОЯНИЕ НА ПУЛЬТЕ
# =====================================================================
class Show:
    def __init__(self):
        self.track_key = None
        self.track = {}
        self.counter = 0
        self.offset = 0
        self.lost = 0
        self.script = None
        self.script_track = None
        self.live = []                  # [(такт, буква паттерна)]
        self.e_norm, self.b_norm = Norm(), Norm()
        self.en_hist = []
        self.fan = {"on": False, "since": 0, "off_at": -FAN_COOLDOWN, "width": 0.0, "tilt": 0.5,
                    "dir": 1, "why": "", "sent": {}, "src": ""}
        self.seg = None
        self.text = ""
        self.building = set()
        self.db = None

    def plan_at(self, idx):
        """разметка такта idx с учётом сдвига, найденного по паттернам"""
        sc = self.script
        if not sc:
            return None
        self.align()
        b = idx + self.offset
        if self.lost >= 16 or b < 1 or b > sc["n"]:
            return None
        return sc["bars"][b - 1]

    def align(self):
        """сверить последние 8 тактов с паттернами сценария (сдвиг -4…+4)"""
        sc = self.script
        recent = [(i, p) for i, p in self.live[-8:] if p and p not in ("?", "-")]
        if not sc or len(recent) < 4:
            return
        best, best_score = self.offset, -1
        for off in sorted(range(-4, 5), key=lambda o: abs(o - self.offset)):
            score = 0
            for i, p in recent:
                b = i + off
                if 1 <= b <= sc["n"] and sc["bars"][b - 1].get("p") == p:
                    score += 1
            if score > best_score:
                best, best_score = off, score
        if best_score >= max(3, len(recent) * 0.6):
            self.offset, self.lost = best, 0
        elif not any(sc["bars"][i - 1 + self.offset].get("p") for i, _ in recent if 1 <= i + self.offset <= sc["n"]):
            pass                        # в сценарии нет паттернов - сверять не с чем, идём по счёту
        else:
            self.lost += 1


def look_key(track, section):
    tid = (track or {}).get("track_id")
    if tid and (track or {}).get("title"):
        return f"track:{tid}:{section}"
    return f"section:{section}"


# =====================================================================
#  УСТАНОВКА В grandma2
# =====================================================================
def install_grandma2(g):
    if getattr(g, "_show_installed", False):
        return g
    g._show_installed = True
    for k, v in DEFAULTS.items():
        g.DEFAULTS.setdefault(k, v)
    C = g.MA2Control

    def show(self):
        sh = self.__dict__.get("_show")
        if sh is None:
            sh = self._show = Show()
        return sh

    g.show_state = show

    def db_of(self, sh):
        if sh.db is None:
            pdb = getattr(getattr(self, "a", None), "db", None)
            if pdb is not None and getattr(pdb, "db", None) is not None:
                try:
                    sh.db = ShowDB(pdb)
                except Exception as e:
                    self.add_log(f"⚠ сценарий: база недоступна ({e})")
                    sh.db = False
        return sh.db or None

    # --- на каком баре и с какой буквой паттерна мы сейчас ---
    original_on_bar = C.on_bar

    def on_bar(self, features, *args, **kwargs):
        self.__dict__["_show_family"] = args[0] if args else kwargs.get("shown")
        return original_on_bar(self, features, *args, **kwargs)

    C.on_bar = on_bar

    def load_script(self, sh, tid):
        db = db_of(self, sh)
        if not db or not tid or tid in sh.building:
            return
        sh.building.add(tid)

        def run():
            try:
                sc = db.script(tid)
            except Exception as e:
                sc = None
                self.add_log(f"⚠ сценарий трека: {e}")
            finally:
                sh.building.discard(tid)
            if sh.track.get("track_id") == tid:
                sh.script, sh.script_track = sc, tid
                if sc:
                    self.add_log(f"🎬 сценарий трека: {sc['n']} тактов, пиков {len(sc['peaks'])}, "
                                 f"секций {len(sc['segments'])}")

        threading.Thread(target=run, daemon=True).start()

    def rebuild_later(self, sh, tid):
        """трек доиграл - пересчитать его сценарий с новыми тактами"""
        db = db_of(self, sh)
        if not db or not tid:
            return

        def run():
            try:
                db.script(tid)
            except Exception:
                pass

        threading.Thread(target=run, daemon=True).start()

    def new_track(self, sh, st, track):
        close_segment(self, sh, st)
        old = sh.track.get("track_id")
        if old:
            rebuild_later(self, sh, old)
        if sh.fan["on"]:
            fan_off(self, sh)
        sh.track = dict(track or {})
        sh.track_key = (sh.track.get("track_id"), sh.track.get("play_id"))
        try:
            sh.counter = int(sh.track.get("bars") or 0)
        except (TypeError, ValueError):
            sh.counter = 0
        sh.offset, sh.lost, sh.live = 0, 0, []
        sh.script = None
        sh.e_norm, sh.b_norm, sh.en_hist = Norm(), Norm(), []
        sh.fan["off_at"] = -FAN_COOLDOWN
        sh.seg = None
        st["force"], st["avoid"] = {}, {}
        if self.settings.get("show_on", True) and sh.track.get("track_id"):
            load_script(self, sh, sh.track.get("track_id"))

    # --- секции: журнал, сохранённое, показанное ---
    def snapshot(self, sh, st):
        seg = sh.seg
        if seg is None:
            return
        snap = seg["snap"]
        for (track, typ), key in (st.get("sel") or {}).items():
            snap.setdefault("sel", {})[f"{track}|{typ}"] = key
        if st.get("beam") and st.get("beam_name"):
            snap.setdefault("beam", {})[st["beam"]] = st["beam_name"]
        if st.get("applied_palette"):
            snap["palette"] = dict(st["applied_palette"])
        snap["fan"] = bool(sh.fan["on"])     # как сейчас: «Сохранить» запоминает то, что видно
        snap["dir"] = st.get("dir", 1)

    def open_segment(self, sh, st, section):
        key = look_key(sh.track, section)
        db = db_of(self, sh)
        saved = db.look(key) if db else None
        sh.seg = {"sec": section, "key": key, "start": sh.counter, "saved": bool(saved), "snap": {}}
        st["force"] = force_of(saved) if saved else {}
        st["avoid"] = {} if saved else avoid_of(db.tried(key) if db else {})
        if saved and saved.get("dir"):
            st["dir"] = saved["dir"]
        self.add_log(f"🎬 секция {SECTION_NAMES.get(section, section)}"
                     + (" - 🔒 сохранённый свет" if saved else ""))

    def close_segment(self, sh, st):
        seg = sh.seg
        if seg is None:
            return
        snapshot(self, sh, st)
        db = db_of(self, sh)
        if db and seg["snap"]:
            try:
                db.log(sh.track.get("play_id"), sh.track.get("track_id"), seg["start"], sh.counter,
                       seg["sec"], seg["key"], seg["saved"], seg["snap"])
            except Exception as e:
                self.add_log(f"⚠ журнал света: {e}")
        sh.seg = None

    def show_save(self):
        """💾 текущая секция трека: в следующий раз - ровно это"""
        sh = show(self)
        st = getattr(self, "_rig", None) or {}
        seg = sh.seg
        if seg is None:
            return "секция ещё не определилась - подождите такт-другой"
        snapshot(self, sh, st)
        db = db_of(self, sh)
        if not db:
            return "базы нет - сохранить негде"
        db.save_look(seg["key"], sh.track.get("track_id"), seg["sec"], seg["snap"])
        seg["saved"] = True
        st["force"] = force_of(seg["snap"])
        name = SECTION_NAMES.get(seg["sec"], seg["sec"])
        title = sh.track.get("title") or "трек без названия"
        msg = f"🔒 сохранено: {title} · {name}"
        self.add_log(msg)
        return msg

    C.show_save = show_save

    def show_unsave(self, key=None):
        sh = show(self)
        key = key or (sh.seg or {}).get("key")
        db = db_of(self, sh)
        if not (db and key):
            return False
        db.drop_look(key)
        if sh.seg and sh.seg["key"] == key:
            sh.seg["saved"] = False
            st = getattr(self, "_rig", None) or {}
            st["force"] = {}
        self.add_log(f"🔓 снято сохранение: {key}")
        return True

    C.show_unsave = show_unsave

    def show_build_all(self, done=None):
        sh = show(self)
        db = db_of(self, sh)
        if not db:
            if done:
                done("базы нет (анализатор без music_patterns.db)")
            return False

        def run():
            try:
                made, total = db.build_all()
                msg = f"🎬 рассчитано треков: {made} из {total}"
                tid = sh.track.get("track_id")
                if tid:
                    sh.script = db.script(tid)
            except Exception as e:
                msg = f"⚠ расчёт треков: {e}"
            self.add_log(msg)
            if done:
                done(msg)

        threading.Thread(target=run, daemon=True).start()
        return True

    C.show_build_all = show_build_all

    # --- веер ---
    def fade_suffix(self, beat):
        s = self.settings
        fmt = s.get("pal_fade_cmd", " Fade {t}") or ""
        t = max(0.0, beat * _f(s.get("fan_fade"), 0.5))
        return fmt.format(t=num(t)) if fmt and t > 0 else ""

    def send_fan(self, sh, st, beat, start=False):
        s = self.settings
        f = sh.fan
        aims = fan_aims(s, f["width"], f["tilt"], f["dir"], f["sent"] if not start else None)
        pan_a = (s.get("attrs") or {}).get("pan", "PAN") if isinstance(s.get("attrs"), dict) else "PAN"
        tilt_a = (s.get("attrs") or {}).get("tilt", "TILT") if isinstance(s.get("attrs"), dict) else "TILT"
        fade = fade_suffix(self, beat)
        n = 0
        for fid, (p, t) in aims.items():
            old = f["sent"].get(fid)
            if old and abs(old[0] - p) < 1 and abs(old[1] - t) < 1:
                continue
            # одной строкой: выбор и значения не перемешаются с командами палитры из другого потока
            self.send(f'Fixture {fid} Attribute "{pan_a}" At {num(p)}{fade}')
            self.send(f'Fixture {fid} Attribute "{tilt_a}" At {num(t)}{fade}')
            f["sent"][fid] = (p, t)
            n += 1
        return n

    def fan_off(self, sh):
        f = sh.fan
        if f["sent"]:
            cmd = self.settings.get("fan_release", "ClearAll") or "ClearAll"
            for c in str(cmd).split(";"):
                if c.strip():
                    self.send(c.strip())
            if getattr(g, "palette_resend", None):
                try:
                    g.palette_resend(self)
                except Exception:
                    pass
        f["on"], f["sent"], f["off_at"] = False, {}, sh.counter
        f["why"] = ""

    def show_fan_groups(self):
        sh = self.__dict__.get("_show")
        if not (sh and sh.fan["on"]):
            return set()
        return set(fan_groups(self.settings))

    g.show_fan_groups = show_fan_groups

    def decide_fan(self, sh, st, plan, en, tn, phrase):
        s, f = self.settings, sh.fan
        idx = sh.counter
        forced = (st.get("force") or {}).get("fan")
        peak = st.get("peak_hold", 0) > 0
        if not fan_groups(s):
            return False, "", 0.0
        if getattr(g, "gen_main", None) and g.gen_main(self) and not s.get("fan_over_gen", False):
            return False, "", 0.0       # генератор главный: веер не пишет Pan/Tilt в программер
        if s.get("fan_always"):
            want, why = True, "всегда"
        elif forced is not None:
            want, why = bool(forced), "сохранено"
        elif not s.get("fan_auto", True):
            return False, "", 0.0
        elif plan is not None:
            want = plan.get("fan", 0) > 0
            why = "сценарий: " + MOOD_NAMES.get(plan.get("m"), plan.get("m") or "")
        else:
            hist = sh.en_hist
            rising = len(hist) >= 4 and hist[-1] - sum(hist[-4:-1]) / 3 > 0.12 and hist[-1] >= hist[-2]
            flow = st.get("rhythm") == "поток" and not st.get("fast")
            stop = bool(st.get("fast")) or bool(getattr(st.get("tempo"), "calm", False)) \
                or (st.get("rhythm") == "бег" and not peak)
            phrase_start = phrase or (idx - 1) % PHRASE == 0
            if f["on"]:
                run = idx - f["since"]
                want = True
                if run >= FAN_MIN_BARS and (stop or not (rising or peak or flow)):
                    want = False
                if run >= FAN_MAX_BARS and not peak:
                    want = False
            else:
                cool = idx - f["off_at"] >= FAN_COOLDOWN
                want = cool and phrase_start and (rising or peak or flow) and not stop
            why = "нарастание" if rising else "пик" if peak else "поток" if flow else f.get("why", "")
        if plan is not None and plan.get("fan", 0) > 0:
            width = plan["fan"]
        elif peak:
            width = 1.0
        else:
            width = 0.25 + 0.75 * (en if en is not None else 0.5)
        return want, why, width

    def show_bar(self, st, features, phrase=False, turned=False):
        """раз в такт из дорожек ma_rig → (добавить поводы, убрать поводы)"""
        s = self.settings
        sh = show(self)
        a = getattr(self, "a", None)
        track = getattr(a, "track", None) or {}
        key = (track.get("track_id"), track.get("play_id"))
        if key != sh.track_key:
            new_track(self, sh, st, track)
        else:
            sh.track = dict(track) if track else sh.track
        sh.counter += 1
        add, drop = set(), set()
        fam = self.__dict__.get("_show_family")
        sh.live.append((sh.counter, fam))
        sh.live = sh.live[-32:]
        en = sh.e_norm.add(feat(features, "energy"))
        tn = sh.b_norm.add(brightness(features))
        if en is not None:
            sh.en_hist = (sh.en_hist + [en])[-16:]
        plan = sh.plan_at(sh.counter) if s.get("show_on", True) else None
        section = feat(features, "section") or getattr(a, "section", None)
        if section and (sh.seg is None or section != sh.seg["sec"]):
            first = sh.seg is None
            close_segment(self, sh, st)
            open_segment(self, sh, st, section)
            if not first:
                add |= {"dim", "move"}
            st["script_color"] = True
        st["script"] = plan is not None
        st["strobe_force"] = bool(plan and "strobe" in plan.get("ev", []))
        if plan is not None:
            ev = plan.get("ev", [])
            if phrase:
                drop.add("move")          # движение меняет сценарий, а не каждая фраза
            if "peak" in ev:
                st["peak_hold"] = max(st.get("peak_hold", 0), PEAK_BARS)
                add.add("move")
            if "color" in ev:
                st["script_color"] = True
            st["script_mood"] = PALETTE_MOOD.get(plan.get("m"))
        else:
            st["script_mood"] = None
        # веер
        try:
            bpm = float(feat(features, "bpm") or getattr(self, "bpm_sent", 0) or 120)
        except (TypeError, ValueError):
            bpm = 120.0
        beat = 60.0 / max(40.0, min(220.0, bpm))
        want, why, width = decide_fan(self, sh, st, plan, en, tn, phrase)
        f = sh.fan
        f["dir"] = (st.get("force") or {}).get("dir") or st.get("dir", 1)
        tilt = plan["t"] if plan is not None else (tn if tn is not None else 0.5)
        if want and not f["on"]:
            f.update(on=True, since=sh.counter, why=why, width=width, tilt=tilt,
                     src="сценарий" if plan is not None else "живой")
            n = send_fan(self, sh, st, beat, start=True)
            add.add("move")                  # группы веера выходят из эффектов движения
            self.add_log(f"🪭 веер вкл: {why} ({n} приборов)")
        elif f["on"] and not want:
            fan_off(self, sh)
            add.add("move")
            self.add_log("🪭 веер выкл - движение снова у эффектов")
        elif f["on"]:
            changed = abs(width - f["width"]) >= 0.08 or abs(tilt - f["tilt"]) >= 0.08 or turned
            f["why"] = why or f["why"]
            if changed:
                f["width"], f["tilt"] = width, tilt
                send_fan(self, sh, st, beat)
        snapshot(self, sh, st)
        sh.text = status_text(sh, plan)
        return add, drop

    g.show_bar = show_bar

    def status_text(sh, plan):
        parts = []
        tr = sh.track or {}
        if sh.script:
            n = sh.script["n"]
            b = sh.counter + sh.offset
            parts.append(f"сценарий: такт {b}/{n}" + (f" (сдвиг {sh.offset:+d})" if sh.offset else "")
                         + (" · сбился - живой режим" if plan is None and sh.lost >= 16 else ""))
        elif tr.get("track_id"):
            parts.append("трек новый или короткий - живой режим")
        if sh.seg:
            parts.append(f"секция {SECTION_NAMES.get(sh.seg['sec'], sh.seg['sec'])}"
                         + (" 🔒" if sh.seg["saved"] else ""))
        f = sh.fan
        if f["on"]:
            parts.append(f"веер: {f['why'] or 'вкл'} · раскрытие {int(f['width'] * 100)}%")
        if plan is not None:
            parts.append(MOOD_NAMES.get(plan.get("m"), ""))
        return " · ".join(p for p in parts if p)

    def show_text(self):
        sh = self.__dict__.get("_show")
        return sh.text if sh else ""

    g.show_text = show_text

    def show_reset(self):
        sh = self.__dict__.get("_show")
        if sh is None:
            return
        st = getattr(self, "_rig", None) or {}
        close_segment(self, sh, st)
        if sh.fan["on"]:
            fan_off(self, sh)
        sh.seg = None

    g.show_reset = show_reset
    return g


# =====================================================================
#  ОКНО «СЦЕНАРИЙ ТРЕКА»
# =====================================================================
def install_gui(mg):
    if getattr(mg, "_show_installed", False):
        return mg
    mg._show_installed = True
    mg.ShowWindow = ShowWindow
    return mg


MOOD_COLORS = {"peak": "#ff4d6d", "build": "#f0a830", "flow": "#4aa3ff", "calm": "#3a5a7a", "drive": "#c46cff"}
SECTION_COLORS = {"D": "#7a2a3a", "M": "#2a3f5a", "B": "#24433a"}


class ShowWindow:
    """сценарий текущего трека: громкость, секции, веер, события, сохранённое"""

    def __init__(self, rig):
        import music_gui as mg
        import grandma2 as g
        tk = mg.tk
        self.rig, self.mg, self.g = rig, mg, g
        self.ma = rig.owner.ma
        s = self.ma.settings
        self.win = (getattr(mg, "scroll_toplevel", None) or tk.Toplevel)(rig.win)
        self.win.title("Сценарий трека")
        self.win.configure(bg=mg.BG)
        self.body = self.win
        top = tk.Frame(self.body, bg=mg.BG)
        top.pack(fill="x", padx=12, pady=(10, 4))
        self.vars = {}
        for text, key in (("сценарий из базы", "show_on"), ("веер: автопилот", "fan_auto"),
                          ("веер всегда", "fan_always"), ("веер поверх эффектов генератора", "fan_over_gen")):
            v = self.vars[key] = tk.BooleanVar(value=bool(s.get(key, DEFAULTS[key])))
            tk.Checkbutton(top, text=text, variable=v, command=lambda k=key, v=v: self.ma.set(**{k: bool(v.get())}),
                           bg=mg.BG, fg=mg.TEXT, activebackground=mg.BG, activeforeground=mg.TEXT,
                           selectcolor=mg.OFF, font=("Segoe UI", 9), highlightthickness=0).pack(side="left", padx=(0, 10))
        mg.flat_button(top, "💾 Сохранить свет секции", self.save, mg.ACCENT).pack(side="right")
        mg.flat_button(top, "🔓 Снять", self.unsave, mg.ACCENT).pack(side="right", padx=(0, 6))
        mg.flat_button(top, "🎬 Рассчитать треки базы", self.build, mg.ACCENT).pack(side="right", padx=(0, 6))
        row = tk.Frame(self.body, bg=mg.BG)
        row.pack(fill="x", padx=12, pady=(0, 4))
        self.nums = {}
        for text, key in (("веер: шаг Pan°", "fan_width"), ("Tilt° бас", "fan_tilt_lo"), ("Tilt° верха", "fan_tilt_hi")):
            tk.Label(row, text=text, bg=mg.BG, fg=mg.DIM, font=("Segoe UI", 9)).pack(side="left")
            v = self.nums[key] = tk.StringVar(value=str(num(s.get(key, DEFAULTS[key]))))
            e = tk.Entry(row, textvariable=v, width=5, bg=mg.PANEL, fg=mg.TEXT, insertbackground=mg.TEXT,
                         relief="flat", font=("Segoe UI", 9))
            e.pack(side="left", padx=(4, 12))
            e.bind("<Return>", lambda _e: self.apply_nums())
            e.bind("<FocusOut>", lambda _e: self.apply_nums())
        self.status = tk.Label(self.body, text="", bg=mg.BG, fg=mg.TEXT, font=("Segoe UI", 9),
                               anchor="w", justify="left", wraplength=900)
        self.status.pack(fill="x", padx=12)
        self.canvas = tk.Canvas(self.body, width=900, height=200, bg=mg.PANEL, highlightthickness=0)
        self.canvas.pack(padx=12, pady=6)
        self.note = tk.Label(self.body, text="", bg=mg.BG, fg=mg.DIM, font=("Segoe UI", 9), anchor="w")
        self.note.pack(fill="x", padx=12)
        tk.Label(self.body, text="Полосы: секции (дроп / середина / брейк), линия - громкость, ниже - настроение, "
                                "веер (высота - раскрытие), ▲ пик, ◆ смена цвета, ⚡ стробо, 🔒 сохранённая секция. "
                                "Белая черта - где мы сейчас. «Сохранить» запоминает свет текущей секции трека.",
                 bg=mg.BG, fg=mg.DIM, font=("Segoe UI", 8), anchor="w", justify="left",
                 wraplength=900).pack(fill="x", padx=12, pady=(0, 10))
        self.tick()

    def apply_nums(self):
        vals = {}
        for k, v in self.nums.items():
            try:
                vals[k] = float(v.get().replace(",", "."))
            except ValueError:
                continue
        if vals:
            self.ma.set(**vals)

    def save(self):
        msg = self.ma.show_save()
        self.note.config(text=msg or "")

    def unsave(self):
        ok = self.ma.show_unsave()
        self.note.config(text="сохранение снято" if ok else "в этой секции нечего снимать")

    def build(self):
        self.note.config(text="считаю…")

        def done(msg):
            try:
                self.win.after(0, lambda: self.note.config(text=msg))
            except Exception:
                pass

        self.ma.show_build_all(done)

    def draw(self, sh):
        c = self.canvas
        c.delete("all")
        W, H = 900, 200
        sc = sh.script if sh else None
        if not sc:
            c.create_text(W / 2, H / 2, fill=self.mg.DIM, font=("Segoe UI", 10),
                          text="для этого трека сценария нет: трек новый или не опознан.\n"
                               "Работает живой автопилот; после проигрывания трек рассчитается сам.")
            return
        n = sc["n"]
        k = (W - 20) / n
        x0 = 10
        saved = {}
        db = sh.db or None
        if db and sh.track.get("track_id"):
            try:
                saved = db.saved_keys(sh.track.get("track_id"))
            except Exception:
                saved = {}
        for a, b, sec in sc["segments"]:
            c.create_rectangle(x0 + (a - 1) * k, 10, x0 + b * k, 110, fill=SECTION_COLORS.get(sec, "#333"), outline="")
            c.create_text(x0 + (a - 1) * k + 3, 14, anchor="nw", fill=self.mg.TEXT, font=("Segoe UI", 7),
                          text=SECTION_NAMES.get(sec, sec) + (" 🔒" if sec in saved else ""))
        pts = []
        for i, bar in enumerate(sc["bars"]):
            pts += [x0 + (i + 0.5) * k, 108 - bar["e"] * 90]
        if len(pts) >= 4:
            c.create_line(*pts, fill="#e8e8e8", width=1)
        for i, bar in enumerate(sc["bars"]):
            xa, xb = x0 + i * k, x0 + (i + 1) * k
            c.create_rectangle(xa, 116, xb, 128, fill=MOOD_COLORS.get(bar["m"], "#444"), outline="")
            if bar["fan"]:
                c.create_rectangle(xa, 160 - bar["fan"] * 26, xb, 160, fill="#f0a830", outline="")
            for e_, mark, y in (("peak", "▲", 172), ("color", "◆", 184), ("strobe", "⚡", 196)):
                if e_ in bar["ev"]:
                    c.create_text((xa + xb) / 2, y, text=mark, fill=MOOD_COLORS["peak"] if e_ != "color" else "#4aa3ff",
                                  font=("Segoe UI", 7))
        cur = sh.counter + sh.offset
        if 1 <= cur <= n:
            x = x0 + (cur - 0.5) * k
            c.create_line(x, 6, x, 198, fill="#ffffff", width=2)

    def tick(self):
        try:
            if not self.win.winfo_exists():
                return
        except Exception:
            return
        sh = self.ma.__dict__.get("_show")
        tr = (sh.track if sh else {}) or {}
        title = tr.get("title") or ("трек без названия" if tr.get("track_id") else "трек ещё не начался")
        text = title + ((" · " + sh.text) if sh and sh.text else "")
        self.status.config(text=text)
        self.draw(sh)
        self.win.after(1000, self.tick)


def install():
    import ma_wheel
    ma_wheel.register("grandma2", install_grandma2)
    ma_wheel.register("music_gui", install_gui)
