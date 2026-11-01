package com.yan.malight.core;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Автопилот grandMA2, как в анализаторе на компьютере (grandma2.py + ma_bpm.py):
 * раз в такт - группа эффектов (пульс / бег / поток / искры / круг) и вариант,
 * на долях - Go+ позиций голов, на событиях - цвет, темп - в speed-мастера.
 * Раскладка - та, что анализатор создаёт на пульте:
 *   page.1-12 эффекты (группа × 3 варианта), page.13-14 круг, page.15 заливка,
 *   page.16-27 цвета, page.30 позиции, page.31-42 пары цветов.
 */
public final class Director implements Analyzer.Listener {

    public static final String[] GROUPS = {"пульс", "бег", "поток", "искры"};
    static final String[][] VARIANTS = {
            {"все вместе", "через один", "строб"},
            {"волна", "чейз", "пила"},
            {"дыхание", "медленная волна", "перелив"},
            {"случайно", "мерцание", "вспышки"},
    };
    static final String[] CHASE = {"круг", "круг ×2"};
    static final int AUTO_HOLD = 2, AUTO_PHRASE = 8, AUTO_BURST_BARS = 2, AUTO_BUILD_MAX = 16, AUTO_BUILD_FAST = 2;
    static final String[] COLOR_CYCLE = {"основной", "пара", "антагонист", "пара"};
    static final double COLOR_MIN_GAP = 6, COLOR_PHRASE_GAP = 14, COLOR_FORCE = 26;
    static final double BPM_STEP = 0.5, BPM_INTERVAL = 1.0, BPM_REFRESH = 8.0;

    private final Settings s;
    private final Ma2Client ma;
    private final Analyzer an;

    // то, что показывает экран
    public volatile String autoWhy = "", colorLast = "", posLast = "", bpmLast = "";
    public volatile String autoCmd;

    // автопилот
    private String group;
    private int bars, seed, burst, build;
    private String candGroup;
    private int candCount;
    private String lastSection;
    private final List<Double> dens = new ArrayList<>(), energies = new ArrayList<>();
    private boolean[][] prevGrid;

    // цвет
    private String colorCmd;
    private int colorPos = -1, colorStep, colorBars;
    private double colorSince;
    private String colorEvent, colorSec;

    // BPM
    private final Map<Integer, Double> bpmSent = new HashMap<>();
    private final Map<Integer, Double> bpmTime = new HashMap<>();
    private double energyNorm = 0.5, normLo = Double.NaN, normHi = Double.NaN;
    private int normN;
    private double bpmCandidate;

    // заливка
    private double fillLevel, fillFlashUntil, fillTime;
    private int fillSent = -1;
    private boolean fillGo, quiet = true;

    public Director(Settings settings, Ma2Client client, Analyzer analyzer) {
        s = settings;
        ma = client;
        an = analyzer;
    }

    private double now() { return an.streamTime(); }

    private boolean on() { return s.enabled; }

    private void send(String cmd) { ma.send(cmd, null); }

    // ------------------------------------------------------------------ раскладка
    String ex(int n) { return s.page + "." + n; }

    // эффекты генератора
    private String poolsSrc;
    private Map<String, List<Map<String, Object>>> pools = new HashMap<>();
    private String lookName;
    public volatile boolean usingGen;

    /** пулы эффектов генератора по группам автопилота; пусто - генератор не подключён */
    @SuppressWarnings("unchecked")
    public synchronized Map<String, List<Map<String, Object>>> genPools() {
        String js = s.fxgenAssigned;
        if (js == null) js = "";
        if (!js.equals(poolsSrc)) {
            poolsSrc = js;
            Map<String, List<Map<String, Object>>> p = new HashMap<>();
            try {
                if (!js.trim().isEmpty()) {
                    Object o = Json.parse(js);
                    if (o instanceof List && !((List<Object>) o).isEmpty()) p = FxLink.pools((List<Object>) o);
                }
            } catch (RuntimeException ignored) {
            }
            pools = p;
        }
        return pools;
    }

    public boolean genActive() { return s.fxgenOn && !genPools().isEmpty(); }

    String fxExec(String g, int variant) {
        lookName = null;
        if (g.equals("круг")) return ex(13 + variant);
        if (genActive()) {
            List<Map<String, Object>> pool = genPools().get(g);
            if (pool != null && !pool.isEmpty()) {
                Map<String, Object> look = pool.get((variant + seed * 3) % pool.size());
                lookName = String.valueOf(look.get("name"));
                return String.valueOf(look.get("exec"));
            }
        }
        int gi = indexOf(GROUPS, g);
        String own = new String[]{s.execPulse, s.execRun, s.execFlow, s.execSpark}[gi].trim();
        if (!own.isEmpty()) {
            String[] list = own.split("[\\s,;]+");
            return list[variant % list.length];
        }
        return ex(gi * 3 + variant + 1);
    }

    static int indexOf(String[] a, String v) {
        for (int i = 0; i < a.length; i++) if (a[i].equals(v)) return i;
        return 0;
    }

    static boolean isExec(String t) { return t != null && t.trim().matches("\\d+(\\.\\d+)?(\\s*-\\s*\\d+\\.\\d+)?"); }

    /** «11.1-11.3» → «11.1 Thru 11.3» */
    static String execList(String v) {
        String[] ab = v.trim().split("\\s*-\\s*");
        return ab.length == 2 ? ab[0] + " Thru " + ab[1] : v.trim();
    }

    void go(String v) {
        if (v == null) return;
        send(isExec(v) ? "Go Executor " + execList(v) : v);
    }

    void off(String v) {
        if (isExec(v)) send("Off Executor " + execList(v));
    }

    void switchTo(String now, String old) {
        if (now != null && now.equals(old)) return;
        if (old != null) off(old);
        go(now);
    }

    // ------------------------------------------------------------------ события анализа
    @Override
    public synchronized void onBeat(int beat, double period, String section) {
        quiet = false;
        if (!on() || !s.autopilot || !s.fxMove) return;
        int every = "D".equals(section) ? 1 : "B".equals(section) ? 4 : 2;
        if (every == 4 && beat != 1) return;
        if (every == 2 && beat != 1 && beat != 3) return;
        String e = ex(30);
        double fade = Math.round(Math.max(0.05, Math.min(4.0, s.posSmooth * period * every)) * 100) / 100.0;
        send(fade < 0.06 ? "Go+ Executor " + e : "Go+ Executor " + e + " Fade " + num(fade));
        posLast = e + " · " + (every == 1 ? "каждая доля" : every == 2 ? "через долю" : "раз в такт") + " · фейд " + num(fade) + " с";
    }

    @Override
    public synchronized void onBar(Analyzer.Bar b) {
        quiet = false;
        // секция для цвета и BPM
        if (b.section != null && !b.section.equals(colorSec)) {
            if (colorSec != null) colorEvent = b.section;
            colorSec = b.section;
        }
        energyNorm = norm(b.energy);
        if (b.burst) fillFlash();
        pushBpm(false);
        if (!on()) return;
        colorTick(b);
        if (!s.autopilot) return;
        String[] choice = choose(b);
        String g = choice[0];
        int variant = Integer.parseInt(choice[1]);
        String v = fxExec(g, variant);
        String name = lookName != null ? lookName : g.equals("круг") ? CHASE[variant] : VARIANTS[indexOf(GROUPS, g)][variant];
        usingGen = lookName != null;
        autoWhy = g + " · " + name + " (" + v + ") - " + choice[2];
        if (!v.equals(autoCmd)) {
            switchTo(v, autoCmd);
            autoCmd = v;
        }
    }

    @Override
    public synchronized void onLull() {
        quiet = true;
        fillTick();
        if (on() && s.autopilot && autoCmd != null) {
            off(autoCmd);
            autoCmd = null;
            group = null;
            autoWhy = "тишина - эффект выключен";
        }
    }

    /** характер ритма по рисунку такта (как rhythm_group) */
    static String rhythmGroup(boolean[][] grid) {
        if (grid == null) return "бег";
        int[] c = new int[3];
        for (int z = 0; z < 3; z++) for (boolean x : grid[z]) if (x) c[z]++;
        int low = c[0], mid = c[1], high = c[2], total = low + mid + high;
        if (total < 4) return "поток";
        if (high >= 8 && high >= low + mid) return "искры";
        if (low >= 3 && total <= 8) return "пульс";
        if (total <= 5) return "поток";
        return "бег";
    }

    /** решение автопилота на такт (как autopilot_choice) → {группа, вариант, причина} */
    String[] choose(Analyzer.Bar b) {
        double low = b.hits[0], mid = b.hits[1], high = b.hits[2];
        String section = b.section;
        // характер ритма - по двум последним тактам, чтобы один сбитый такт не дёргал
        String rg = rhythmGroup(b.grid);
        if (prevGrid != null && !rhythmGroup(prevGrid).equals(rg)) rg = group != null ? group : rg;
        prevGrid = b.grid;
        dens.add(mid + high);
        while (dens.size() > 6) dens.remove(0);
        energies.add((double) b.energy);
        while (energies.size() > 6) energies.remove(0);

        String h = s.hold.trim();
        if (java.util.Arrays.asList(GROUPS).contains(h)) {
            if (!h.equals(group)) {
                group = h;
                bars = 0;
            }
            bars++;
            return new String[]{h, String.valueOf(((bars - 1) / AUTO_PHRASE + seed) % 3), "вручную"};
        }

        if (b.burst && !"B".equals(section)) burst = AUTO_BURST_BARS;
        if (burst > 0) {
            burst--;
            group = "пульс";
            bars = 0;
            lastSection = section;
            build = 0;
            fillFlash();
            return new String[]{"пульс", "2", "всплеск → строб"};
        }
        if (s.chaseOn && !"D".equals(section)) {
            if (build > 0) {
                int n = dens.size();
                boolean going = n >= 2 && dens.get(n - 1) >= 0.9 * dens.get(n - 2) && build < AUTO_BUILD_MAX;
                build = going ? build + 1 : 0;
            } else if (buildRising()) build = 1;
        } else build = 0;
        if (build > 0) {
            lastSection = section;
            int v = build > AUTO_BUILD_FAST ? 1 : 0;
            return new String[]{"круг", String.valueOf(v), "разгон ритма (" + build + " такт) → " + CHASE[v]};
        }
        String want, why;
        if ("B".equals(section)) {
            want = "поток";
            why = "брейк";
        } else if ("D".equals(section)) {
            if (high >= 8 && high > 2 * low) { want = "искры"; why = "дроп, много верхов"; }
            else if (low >= 3) { want = "пульс"; why = "дроп, бочка"; }
            else { want = rg; why = "дроп, ритм «" + rg + "»"; }
        } else {
            want = rg;
            why = "ритм «" + rg + "»";
        }
        if (!want.equals(group)) {
            if (group == null || (section != null && !section.equals(lastSection))) {
                group = want;
                bars = 0;
                candGroup = null;
                candCount = 0;
            } else {
                candCount = want.equals(candGroup) ? candCount + 1 : 1;
                candGroup = want;
                if (candCount >= AUTO_HOLD) {
                    group = want;
                    bars = 0;
                    candGroup = null;
                    candCount = 0;
                } else why += " (ждём " + candCount + "/" + AUTO_HOLD + ")";
            }
        } else {
            candGroup = null;
            candCount = 0;
        }
        lastSection = section;
        bars++;
        if (bars == 1) seed = (seed + 1) % 3;
        int variant = ((bars - 1) / AUTO_PHRASE + seed) % 3;
        return new String[]{group, String.valueOf(variant), why};
    }

    private boolean buildRising() {
        // плотность ударов растёт 4 такта подряд, громкость не падает
        int n = dens.size();
        if (n < 4) return false;
        for (int i = n - 3; i < n; i++) if (dens.get(i) <= dens.get(i - 1)) return false;
        return energies.get(energies.size() - 1) >= 0.95 * energies.get(energies.size() - 4) && dens.get(n - 1) >= 4;
    }

    // ------------------------------------------------------------------ цвет
    private void colorTick(Analyzer.Bar b) {
        if (!s.fxColor || !s.autopilot) return;
        if (colorCmd == null) {
            colorPos = 0;
            colorStep = 0;
            colorApply("старт");
            return;
        }
        colorBars++;
        double since = now() - colorSince;
        String why = null;
        if (b.burst && since >= COLOR_MIN_GAP) why = "всплеск";
        else if (colorEvent != null && since >= COLOR_MIN_GAP) {
            why = "секция " + colorEvent;
            colorPos = (colorPos + 7) % 12;          // новая секция - новый основной цвет (шаг по кругу квинт)
            colorStep = -1;
        } else if (colorBars % 8 == 1 && colorBars > 1 && since >= COLOR_PHRASE_GAP) why = "новая фраза";
        else if (since >= COLOR_FORCE) why = (int) since + " с без событий";
        if (why != null) {
            colorEvent = null;
            colorStep++;
            colorApply(why);
        }
    }

    private void colorApply(String why) {
        String state = COLOR_CYCLE[colorStep % COLOR_CYCLE.length];
        int p = colorPos, q = (colorPos + 6) % 12;
        String v = state.equals("антагонист") ? ex(16 + q) : state.equals("пара") && s.colorPair ? ex(31 + p) : ex(16 + p);
        colorSince = now();
        colorLast = state + " · " + v + " · " + why;
        if (!v.equals(colorCmd)) {
            switchTo(v, colorCmd);
            colorCmd = v;
        }
    }

    // ------------------------------------------------------------------ заливка page.15
    private void fillFlash() { fillFlashUntil = now() + 1.1 * 4 * (an.bpm > 0 ? 60 / an.bpm : 0.5); }

    /** раз в ~50 мс из движка */
    public synchronized void fillTick() {
        if (!on() || !s.fillOn || !s.autopilot) return;
        double t = now();
        double target = quiet ? 0 : (t < fillFlashUntil ? s.fillPeak : s.fillBase);
        double dt = Math.max(0, t - fillTime);
        fillTime = t;
        double tau = target > fillLevel ? 0.25 : 1.5;
        fillLevel += (target - fillLevel) * (1 - Math.exp(-dt / tau));
        if (Math.abs(target - fillLevel) < 0.5) fillLevel = target;
        int v = (int) Math.round(fillLevel);
        if (v == fillSent) return;
        String e = ex(15);
        ma.send("Executor " + e + " At " + v, "fill");
        if (v > 0 && !fillGo) { send("Go Executor " + e); fillGo = true; }
        else if (v == 0 && fillGo) { send("Off Executor " + e); fillGo = false; }
        fillSent = v;
    }

    // ------------------------------------------------------------------ BPM → SpecialMaster 3.N
    private double norm(double v) {
        normN++;
        if (Double.isNaN(normLo)) normLo = normHi = v;
        normLo = Math.min(v, normLo + (v - normLo) * 0.02);
        normHi = Math.max(v, normHi + (v - normHi) * 0.02);
        if (normN < 4 || normHi - normLo < 1e-6) return 0.5;
        double e = Math.max(0, Math.min(1, (v - normLo) / (normHi - normLo)));
        return energyNorm * 0.7 + e * 0.3;
    }

    /** {мастер → темп} */
    public Map<Integer, Double> bpmTargets() {
        Map<Integer, Double> out = new java.util.LinkedHashMap<>();
        double base, factor = 1;
        if (s.bpmMode.equals("manual")) base = s.bpmManual;
        else {
            double b = an.bpm;
            if (b < 40 || b > 300) return out;
            base = b / Math.max(1, s.bpmDiv);
            String sec = an.section;
            if (s.bpmMode.equals("section")) factor = "B".equals(sec) ? 0.5 : "D".equals(sec) ? 2 : 1;
            else if (s.bpmMode.equals("energy")) factor = Math.max(0.5, Math.min(2, Math.round(Math.pow(2, 2 * energyNorm - 1) * 4) / 4.0));
            else if (s.bpmMode.equals("stop") && "B".equals(sec)) factor = 0;
        }
        int[] m = {s.smDimmer, s.smPosition, s.smColor, s.smStrobe};
        double[] x = {s.xDimmer, s.xPosition, s.xColor, s.xStrobe};
        for (int i = 0; i < 4; i++) {
            if (m[i] < 1 || out.containsKey(m[i])) continue;
            out.put(m[i], Math.round(base * x[i] * factor * 10) / 10.0);
        }
        return out;
    }

    /** из движка раз в 0.5 с и на каждом такте */
    public synchronized void pushBpm(boolean force) {
        if (!on() || !s.bpmOn) return;
        if (!s.bpmMode.equals("manual")) {
            // темп ещё ищется - ждём, пока два замера подряд совпадут
            double b = Math.round(an.bpm);
            double c = bpmCandidate;
            bpmCandidate = b;
            if (!force && Math.abs(c - b) > 1) return;
        }
        double t = now();
        StringBuilder sb = new StringBuilder();
        for (Map.Entry<Integer, Double> e : bpmTargets().entrySet()) {
            int m = e.getKey();
            double v = e.getValue();
            Double last = bpmSent.get(m), lt = bpmTime.get(m);
            boolean due = force || last == null || (Math.abs(v - last) >= BPM_STEP && t - lt >= BPM_INTERVAL)
                    || t - lt >= BPM_REFRESH;
            if (due) {
                ma.send("SpecialMaster 3." + m + " At " + num(v), "bpm" + m);
                bpmSent.put(m, v);
                bpmTime.put(m, t);
            }
            sb.append(sb.length() > 0 ? "  " : "").append("SM3.").append(m).append("=").append(num(v));
        }
        bpmLast = sb.toString();
    }

    public synchronized void resetSent() {
        bpmSent.clear();
        bpmTime.clear();
        fillSent = -1;
        fillGo = false;
    }

    // ------------------------------------------------------------------ кнопки
    /** все эффекты автопилота выключить (page.1-50) */
    public synchronized void stopAll() {
        send("Off Executor " + ex(1) + " Thru " + ex(50));
        if (!genPools().isEmpty())
            for (int i = 0; i < FxLink.PAGE_CATS.length; i++)
                send("Off Executor " + (s.fxgenPage + i) + ".1 Thru " + (s.fxgenPage + i) + ".100");
        autoCmd = null;
        colorCmd = null;
        group = null;
        fillGo = false;
        fillSent = -1;
        autoWhy = "всё выключено";
    }

    public synchronized void forgetState() {
        autoCmd = null;
        colorCmd = null;
        group = null;
    }

    static String num(double v) {
        double r = Math.round(v * 100) / 100.0;
        return r == Math.rint(r) ? String.valueOf((long) r) : String.valueOf(r);
    }
}
