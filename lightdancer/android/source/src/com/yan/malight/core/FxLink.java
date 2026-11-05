package com.yan.malight.core;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Анализатор + генератор, как ma_fxlink.py на ПК.
 * После «Создать на пульте» генератор знает, какие объекты Effects он сделал (looks).
 * assignScript ставит их на экзекьюторы страниц page…page+4 (Dimmer, Position, Color, Strobe, Комбо),
 * подписывает и привязывает к speed-мастеру категории. Автопилот (Director) потом включает
 * их вместо page.1-12: пульс ← Dimmer, бег ← Position, поток ← Color, искры ← Strobe.
 */
@SuppressWarnings("unchecked")
public final class FxLink {

    private FxLink() { }

    public static final String[][] PAGE_CATS = {{"dimmer"}, {"position"}, {"color"}, {"strobe"}, {"combo", "custom"}};
    public static final String[] PAGE_TITLES = {"Dimmer", "Position", "Color", "Strobe", "Комбо"};
    public static final String[] GROUPS = {"пульс", "бег", "поток", "искры"};
    static final String[][] PREFER = {
            {"dimmer", "combo", "strobe", "custom"},
            {"position", "combo", "dimmer", "custom"},
            {"color", "position", "combo", "custom"},
            {"strobe", "dimmer", "combo", "custom"},
    };

    /** отчёт генератора → looks [{key, name, cat, effects: [{no, group, alt?, alt_phase?}]}] */
    public static List<Object> looks(FxGen.Result r) {
        Map<String, Map<String, Object>> lib = FxGen.library(FxGen.defaultConfig());
        Map<String, Map<String, Object>> byKey = new LinkedHashMap<>();
        for (FxGen.Made m : r.report) {
            Map<String, Object> look = byKey.get(m.key);
            if (look == null) {
                look = new LinkedHashMap<>();
                Map<String, Object> t = lib.get(m.key);
                look.put("key", m.key);
                look.put("name", m.name);
                look.put("cat", t != null && t.get("cat") != null ? String.valueOf(t.get("cat")) : "combo");
                if (t != null && t.get("bpm") != null) look.put("bpm", t.get("bpm"));
                look.put("effects", new ArrayList<Object>());
                byKey.put(m.key, look);
            }
            Map<String, Object> e = new LinkedHashMap<>();
            e.put("no", m.effect);
            e.put("group", m.group);
            long[] alt = r.alts.get(m.effect);
            if (alt != null) {
                e.put("alt", alt[0]);
                e.put("alt_phase", alt[1]);
            }
            ((List<Object>) look.get("effects")).add(e);
        }
        return new ArrayList<Object>(byKey.values());
    }

    public static int pageOf(String cat, int first) {
        String c = cat == null ? "combo" : cat.toLowerCase();
        for (int i = 0; i < PAGE_CATS.length; i++)
            for (String x : PAGE_CATS[i]) if (x.equals(c)) return first + i;
        return first + PAGE_CATS.length - 1;
    }

    /** speed-мастер категории (комбо и прочее - как Position, как master_of на ПК) */
    public static int masterOf(Settings s, String cat) {
        String c = cat == null ? "" : cat.toLowerCase();
        if (c.equals("dimmer")) return s.smDimmer;
        if (c.equals("color")) return s.smColor;
        if (c.equals("strobe")) return s.smStrobe;
        return s.smPosition;
    }

    public static final class Script {
        public final List<String> cmds = new ArrayList<>();
        public final List<Object> assigned = new ArrayList<>();
    }

    /** команды для пульта и список «эффект → экзекьюторы» (assign_script) */
    public static Script assignScript(List<Object> looks, int page, Settings s) {
        Script out = new Script();
        int[] used = new int[PAGE_CATS.length];
        for (int i = 0; i < PAGE_CATS.length; i++) out.cmds.add("Store Page " + (page + i));
        for (Object lo : looks) {
            Map<String, Object> look = (Map<String, Object>) lo;
            List<Object> effects = (List<Object>) look.get("effects");
            if (effects == null || effects.isEmpty()) continue;
            String cat = look.get("cat") == null ? "combo" : String.valueOf(look.get("cat")).toLowerCase();
            int p = pageOf(cat, page), pi = p - page;
            int sm = masterOf(s, cat);
            String name = look.get("name") != null ? String.valueOf(look.get("name")) : String.valueOf(look.get("key"));
            int first = used[pi] + 1;
            List<Object> execs = new ArrayList<>();
            for (Object eo : effects) {
                Map<String, Object> e = (Map<String, Object>) eo;
                used[pi]++;
                String ex = p + "." + used[pi];
                String label = cut((name + " · " + str(e.get("group"))).replace('"', '\''), 30);
                out.cmds.add("Assign Effect " + str(e.get("no")) + " At Executor " + ex);
                out.cmds.add("Label Executor " + ex + " \"" + label + "\"");
                out.cmds.add("Assign SpecialMaster \"speedmaster\"." + sm + " At Effect " + str(e.get("no")));
                Map<String, Object> en = new LinkedHashMap<>();
                en.put("group", str(e.get("group")));
                en.put("exec", ex);
                execs.add(en);
            }
            int last = used[pi];
            String range = last == first ? p + "." + first : p + "." + first + "-" + p + "." + last;
            // копии со сдвигом фазы - следом за обычными, в общий диапазон не входят
            for (int i = 0; i < effects.size(); i++) {
                Map<String, Object> e = (Map<String, Object>) effects.get(i);
                if (e.get("alt") == null) continue;
                used[pi]++;
                String alt = p + "." + used[pi];
                Object ph = e.get("alt_phase") == null ? 180L : e.get("alt_phase");
                String label = cut((name + " · " + str(e.get("group")) + " ±" + str(ph)).replace('"', '\''), 30);
                out.cmds.add("Assign Effect " + str(e.get("alt")) + " At Executor " + alt);
                out.cmds.add("Label Executor " + alt + " \"" + label + "\"");
                out.cmds.add("Assign SpecialMaster \"speedmaster\"." + sm + " At Effect " + str(e.get("alt")));
                ((Map<String, Object>) execs.get(i)).put("alt", alt);
            }
            Map<String, Object> a = new LinkedHashMap<>();
            a.put("key", look.get("key"));
            a.put("name", name);
            a.put("cat", cat);
            a.put("exec", range);
            a.put("execs", execs);
            out.assigned.add(a);
        }
        for (int i = 0; i < PAGE_CATS.length; i++)
            out.cmds.add("Label Page " + (page + i) + " \"FX " + PAGE_TITLES[i] + "\"");
        return out;
    }

    /** {группа автопилота → подходящие эффекты} */
    public static Map<String, List<Map<String, Object>>> pools(List<Object> assigned) {
        Map<String, List<Map<String, Object>>> byCat = new LinkedHashMap<>();
        List<Map<String, Object>> all = new ArrayList<>();
        for (Object o : assigned) {
            Map<String, Object> a = (Map<String, Object>) o;
            String c = String.valueOf(a.get("cat"));
            if (!byCat.containsKey(c)) byCat.put(c, new ArrayList<Map<String, Object>>());
            byCat.get(c).add(a);
            all.add(a);
        }
        Map<String, List<Map<String, Object>>> out = new LinkedHashMap<>();
        for (int g = 0; g < GROUPS.length; g++) {
            List<Map<String, Object>> pool = new ArrayList<>();
            for (String c : PREFER[g]) if (byCat.containsKey(c)) pool.addAll(byCat.get(c));
            out.put(GROUPS[g], pool.isEmpty() ? all : pool);
        }
        return out;
    }

    /** сколько экзекьюторов занято на каждой из 5 страниц */
    public static int[] usedPerPage(List<Object> assigned, int page) {
        int[] n = new int[PAGE_CATS.length];
        for (Object o : assigned) {
            Map<String, Object> a = (Map<String, Object>) o;
            for (Object eo : (List<Object>) a.get("execs")) {
                Map<String, Object> e = (Map<String, Object>) eo;
                count(n, str(e.get("exec")), page);
                if (e.get("alt") != null) count(n, str(e.get("alt")), page);
            }
        }
        return n;
    }

    private static void count(int[] n, String ex, int page) {
        try {
            String[] pq = ex.split("\\.");
            int p = Integer.parseInt(pq[0]) - page, q = Integer.parseInt(pq[1]);
            if (p >= 0 && p < n.length) n[p] = Math.max(n[p], q);
        } catch (RuntimeException ignored) {
        }
    }

    static String str(Object o) { return o == null ? "" : Py.str(o); }

    static String cut(String s, int n) { return s.length() > n ? s.substring(0, n) : s; }
}
