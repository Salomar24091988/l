package com.yan.malight.core;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Генератор эффектов grandMA2 - перенос ma2_fxgen.py (ядро) строка в строку:
 * команды выходят те же, что у генератора на ПК (проверяется тестом против Python).
 * Шаблон, строка, группа, конфиг - Map / List, как dict / list в Python.
 */
@SuppressWarnings("unchecked")
public final class FxGen {

    public static final List<String> LINE_FIELDS = Arrays.asList("attr", "form", "lo", "hi", "phase", "width");
    public static final List<String> LINE_EXTRAS = Arrays.asList("groups", "wings", "blocks");
    public static final List<String> LINE_ORDER = Arrays.asList("dim", "shutter", "pan", "tilt", "r", "g", "b");
    public static final List<String> CATEGORIES = Arrays.asList("dimmer", "position", "color", "strobe", "combo");
    static final Map<String, String> ATTR_CAP = new HashMap<>(), ATTR_CAT = new HashMap<>();

    static {
        String[][] a = {{"dim", "dim", "dimmer"}, {"shutter", "shutter", "strobe"}, {"pan", "pt", "position"},
                {"tilt", "pt", "position"}, {"r", "rgb", "color"}, {"g", "rgb", "color"}, {"b", "rgb", "color"}};
        for (String[] r : a) {
            ATTR_CAP.put(r[0], r[1]);
            ATTR_CAT.put(r[0], r[2]);
        }
    }

    private static List<Map<String, Object>> builtin;
    private static Map<String, Object> defaults;

    static synchronized void load() {
        if (builtin != null) return;
        Map<String, Object> j = (Map<String, Object>) Json.parse(FxLibrary.JSON);
        builtin = (List<Map<String, Object>>) j.get("templates");
        defaults = (Map<String, Object>) j.get("defaults");
    }

    /** встроенные шаблоны и комбо по порядку библиотеки */
    public static List<Map<String, Object>> templates() {
        load();
        return builtin;
    }

    /** конфиг как DEFAULTS в Python (свежая копия) + группы */
    public static Map<String, Object> defaultConfig() {
        load();
        Map<String, Object> cfg = (Map<String, Object>) Json.parse(Json.write(defaults));
        cfg.put("groups", new ArrayList<Object>());
        cfg.put("custom", new ArrayList<Object>());
        return cfg;
    }

    /** library(cfg): встроенные + свои из конфига (свои перекрывают по ключу) */
    public static Map<String, Map<String, Object>> library(Map<String, Object> cfg) {
        Map<String, Map<String, Object>> lib = new LinkedHashMap<>();
        for (Map<String, Object> t : templates()) lib.put((String) t.get("key"), t);
        Object custom = cfg == null ? null : cfg.get("custom");
        if (custom instanceof List) for (Object c : (List<Object>) custom) {
            Map<String, Object> m = (Map<String, Object>) c;
            lib.put((String) m.get("key"), m);
        }
        return lib;
    }

    public static List<String> orderedKeys(Map<String, Map<String, Object>> lib) {
        List<String> keys = new ArrayList<>();
        for (Map<String, Object> t : templates()) keys.add((String) t.get("key"));
        for (String k : lib.keySet()) if (!keys.contains(k)) keys.add(k);
        return keys;
    }

    // ------------------------------------------------------------------ развёртка
    static Map<String, Object> normLine(Object line, Object tplBpm, Map<String, Object> opts, Object cat) {
        Map<String, Object> d;
        if (line instanceof Map) d = new LinkedHashMap<>((Map<String, Object>) line);
        else {
            List<Object> l = (List<Object>) line;
            d = new LinkedHashMap<>();
            for (int i = 0; i < Math.min(6, l.size()); i++) d.put(LINE_FIELDS.get(i), l.get(i));
            if (l.size() > 6) d.putAll((Map<String, Object>) l.get(6));
        }
        if (!d.containsKey("bpm")) d.put("bpm", tplBpm);
        if (!d.containsKey("scale")) d.put("scale", 100L);
        for (String k : LINE_EXTRAS) if (opts.containsKey(k) && !d.containsKey(k)) d.put(k, opts.get(k));
        d.put("cat", cat != null && ATTR_CAT.containsValue(cat) ? cat
                : (ATTR_CAT.containsKey(d.get("attr")) ? ATTR_CAT.get(d.get("attr")) : "dimmer"));
        return d;
    }

    static Map<String, Object> applyLayer(Map<String, Object> line, Map<String, Object> layer) {
        Map<String, Object> d = new LinkedHashMap<>(line);
        if (Py.given(layer.get("bpm"))) d.put("bpm", layer.get("bpm"));
        Object sp = layer.get("speed");
        if (Py.given(sp) && !Py.eq(sp, 1L)) d.put("bpm", Py.toDouble(d.get("bpm")) * Py.toDouble(sp));
        for (String k : new String[]{"phase", "width", "lo", "hi"}) if (Py.given(layer.get(k))) d.put(k, layer.get(k));
        Object sc = layer.get("scale");
        if (Py.given(sc) && !Py.eq(sc, 100L)) {
            Object cur = d.containsKey("scale") ? d.get("scale") : 100L;
            d.put("scale", Py.toDouble(cur) * Py.toDouble(sc) / 100.0);
        }
        if (Py.truthy(layer.get("invert"))) {
            Object lo = d.get("lo");
            d.put("lo", d.get("hi"));
            d.put("hi", lo);
        }
        for (String k : LINE_EXTRAS) {
            if (Py.given(layer.get(k))) {
                long v = Py.toLong(layer.get(k));
                if (v < 0) d.remove(k);
                else d.put(k, v);
            }
        }
        return d;
    }

    static List<Map<String, Object>> expand(Map<String, Object> tpl, Map<String, Map<String, Object>> lib, int depth) {
        if (depth > 6) throw new IllegalArgumentException("Слишком глубокая вложенность в '" + tpl.get("key") + "'");
        Object bpm = tpl.containsKey("bpm") ? tpl.get("bpm") : (Object) 60L;
        Object o = tpl.get("opts");
        Map<String, Object> opts = o instanceof Map ? (Map<String, Object>) o : new HashMap<String, Object>();
        List<Map<String, Object>> out = new ArrayList<>();
        Object lines = tpl.get("lines");
        if (lines instanceof List) for (Object l : (List<Object>) lines) out.add(normLine(l, bpm, opts, tpl.get("cat")));
        Object layers = tpl.get("layers");
        if (layers instanceof List) for (Object lo : (List<Object>) layers) {
            Map<String, Object> layer = (Map<String, Object>) lo;
            List<Map<String, Object>> sub;
            if (Py.truthy(layer.get("tpl"))) {
                Map<String, Object> src = lib.get(layer.get("tpl"));
                if (src == null) throw new IllegalArgumentException("Неизвестный шаблон в слое: '" + layer.get("tpl") + "'");
                if (src == tpl) throw new IllegalArgumentException("Шаблон '" + tpl.get("key") + "' ссылается сам на себя");
                sub = expand(src, lib, depth + 1);
                Object only = layer.get("attrs");
                if (Py.truthy(only)) {
                    List<Map<String, Object>> f = new ArrayList<>();
                    for (Map<String, Object> l : sub) if (((List<Object>) only).contains(l.get("attr"))) f.add(l);
                    sub = f;
                }
            } else if (Py.truthy(layer.get("line"))) {
                sub = new ArrayList<>();
                sub.add(normLine(layer.get("line"), bpm, new HashMap<String, Object>(), null));
            } else continue;
            for (Map<String, Object> l : sub) out.add(applyLayer(l, layer));
        }
        return out;
    }

    /** один атрибут - одна строка; → строки, предупреждения */
    static List<Map<String, Object>> dedupe(List<Map<String, Object>> lines, List<String> warns) {
        Map<Object, Integer> seen = new HashMap<>();
        List<Map<String, Object>> out = new ArrayList<>();
        Set<String> w = new LinkedHashSet<>();
        for (Map<String, Object> l : lines) {
            if (seen.containsKey(l.get("attr"))) {
                w.add("атрибут " + String.valueOf(l.get("attr")).toUpperCase() + " задан несколько раз — используется последний слой");
                out.set(seen.get(l.get("attr")), null);
            }
            seen.put(l.get("attr"), out.size());
            out.add(l);
        }
        List<String> sw = new ArrayList<>(w);
        Collections.sort(sw);
        warns.addAll(sw);
        List<Map<String, Object>> r = new ArrayList<>();
        for (Map<String, Object> l : out) if (l != null) r.add(l);
        return r;
    }

    public static Set<String> needs(Map<String, Object> tpl, Map<String, Map<String, Object>> lib) {
        Set<String> s = new HashSet<>();
        try {
            for (Map<String, Object> l : expand(tpl, lib, 0)) {
                String c = ATTR_CAP.get(l.get("attr"));
                if (c == null) throw new IllegalArgumentException();
                s.add(c);
            }
        } catch (RuntimeException e) {
            s.clear();
            s.add("?");
        }
        return s;
    }

    static Object resolve(Object value, Map<String, Object> group) {
        if (value instanceof String && ((String) value).contains("$")) {
            String v = (String) value;
            boolean neg = v.startsWith("-");
            String name = stripLeft(stripLeft(v, '-'), '$');
            Object g = group.get(name);
            if (g == null) throw new IllegalArgumentException("нет $" + name + " у группы");
            return neg ? (Object) (-Py.toDouble(g)) : g;
        }
        return value;
    }

    private static String stripLeft(String s, char c) {
        int i = 0;
        while (i < s.length() && s.charAt(i) == c) i++;
        return s.substring(i);
    }

    static Object[] lineValues(Map<String, Object> line, Map<String, Object> group) {
        double s = Py.toDouble(line.containsKey("scale") ? line.get("scale") : 100L) / 100.0;
        return new Object[]{Py.num(Py.toDouble(resolve(line.get("lo"), group)) * s),
                Py.num(Py.toDouble(resolve(line.get("hi"), group)) * s)};
    }

    static Map<String, Object> moveDimLine(Map<String, Object> tpl, List<Map<String, Object>> lines,
                                           Map<String, Object> group, Map<String, Object> cfg) {
        Object md = cfg.containsKey("move_dim") ? cfg.get("move_dim") : Boolean.TRUE;
        if (!Py.truthy(md) || !"position".equals(tpl.get("cat"))) return null;
        Object caps = group.get("caps");
        if (!(caps instanceof List) || !((List<Object>) caps).contains("dim")) return null;
        for (Map<String, Object> l : lines) if ("dim".equals(l.get("attr"))) return null;
        Map<String, Object> base = null;
        for (Map<String, Object> l : lines) if ("pan".equals(l.get("attr")) || "tilt".equals(l.get("attr"))) { base = l; break; }
        if (base == null) return null;
        double lo;
        try {
            lo = Math.max(0, Math.min(100, Py.toDouble(cfg.containsKey("move_dim_lo") ? cfg.get("move_dim_lo") : 40L)));
        } catch (RuntimeException e) {
            lo = 40;
        }
        Map<String, Object> d = new LinkedHashMap<>();
        d.put("attr", "dim");
        d.put("form", "sin");
        d.put("lo", Py.num(lo));
        d.put("hi", 100L);
        d.put("phase", base.get("phase"));
        d.put("width", 100L);
        d.put("bpm", base.get("bpm"));
        d.put("scale", 100L);
        d.put("cat", base.containsKey("cat") ? base.get("cat") : "position");
        for (String k : LINE_EXTRAS) if (Py.truthy(base.get(k))) d.put(k, base.get(k));
        return d;
    }

    public static boolean hasMoveDim(Map<String, Object> tpl, Map<String, Object> group, Map<String, Object> cfg) {
        try {
            List<Map<String, Object>> lines = dedupe(expand(tpl, library(cfg), 0), new ArrayList<String>());
            return moveDimLine(tpl, lines, group, cfg) != null;
        } catch (IllegalArgumentException e) {
            return false;
        }
    }

    // ------------------------------------------------------------------ команды
    public static List<String> effectCommands(Map<String, Object> tpl, Map<String, Object> group, long effNo,
                                              Map<String, Object> cfg, Map<String, Map<String, Object>> lib,
                                              List<String> warns) {
        if (lib == null) lib = library(cfg);
        Map<String, Object> forms = (Map<String, Object>) cfg.get("forms");
        Map<String, Object> attrs = (Map<String, Object>) cfg.get("attrs");
        List<Map<String, Object>> lines = dedupe(expand(tpl, lib, 0), warns);
        Map<String, Object> extra = moveDimLine(tpl, lines, group, cfg);
        if (extra != null) {
            lines = new ArrayList<>(lines);
            lines.add(extra);
        }
        lines = new ArrayList<>(lines);
        Collections.sort(lines, new Comparator<Map<String, Object>>() {
            @Override
            public int compare(Map<String, Object> a, Map<String, Object> b) {
                return order(a) - order(b);
            }

            int order(Map<String, Object> l) {
                int i = LINE_ORDER.indexOf(l.get("attr"));
                return i < 0 ? 99 : i;
            }
        });
        String label = Py.cut(Py.str(group.get("name")) + " " + Py.str(tpl.get("name")), 32);
        String ref = "Effect 1." + effNo;
        List<String> cmds = new ArrayList<>();
        cmds.add("Delete " + ref + " /noconfirm");
        cmds.add("ClearAll");
        cmds.add("Group " + Py.str(group.get("id")));
        for (Map<String, Object> l : lines) {
            Object[] v = lineValues(l, group);
            Object a = attrs.get(l.get("attr")), f = forms.get(l.get("form"));
            if (a == null) throw new IllegalArgumentException("нет атрибута " + l.get("attr"));
            if (f == null) throw new IllegalArgumentException("нет формы " + l.get("form"));
            cmds.add("Attribute \"" + Py.str(a) + "\"");
            cmds.add("EffectForm " + Py.str(f));
            cmds.add("EffectLow " + Py.str(v[0]));
            cmds.add("EffectHigh " + Py.str(v[1]));
            cmds.add("EffectPhase " + Py.str(l.get("phase")));
            cmds.add("EffectWidth " + Py.str(Py.num(l.get("width"))));
            cmds.add("EffectBPM " + Py.str(Py.num(l.get("bpm"))));
        }
        cmds.add("Store " + ref + " /o");
        cmds.add("Store " + ref + ".* /o");
        cmds.add("Label " + ref + " \"" + label + "\"");
        for (String k : LINE_EXTRAS) {
            List<Long> vals = new ArrayList<>();
            boolean any = false;
            for (Map<String, Object> l : lines) {
                Object x = l.get(k);
                long n = Py.truthy(x) ? Py.toLong(x) : 0;
                vals.add(n);
                if (n != 0) any = true;
            }
            if (!any) continue;
            if (new HashSet<>(vals).size() == 1) cmds.add("Assign " + ref + ".* /" + k + "=" + vals.get(0));
            else for (int i = 0; i < vals.size(); i++)
                if (vals.get(i) != 0) cmds.add("Assign " + ref + "." + (i + 1) + " /" + k + "=" + vals.get(i));
        }
        Map<String, Object> sgs = (Map<String, Object>) cfg.get("speed_groups");
        Object cat = sgs.containsKey(tpl.get("cat")) ? tpl.get("cat") : (lines.isEmpty() ? null : lines.get(0).get("cat"));
        Object sg = cat == null ? null : sgs.get(cat);
        Object sgc = cfg.get("speed_group_cmd");
        if (Py.truthy(sg) && Py.truthy(sgc))
            cmds.add(((String) sgc).replace("{sg}", Py.str(sg)).replace("{eff}", String.valueOf(effNo)));
        return cmds;
    }

    public static List<String> macroCommands(Map<String, Object> cfg) {
        List<String> cmds = new ArrayList<>();
        long m = Py.toLong(cfg.get("macro_start"));
        Map<String, Object> sgs = (Map<String, Object>) cfg.get("speed_groups");
        java.util.TreeMap<Long, String> names = new java.util.TreeMap<>();
        for (Map.Entry<String, Object> e : sgs.entrySet()) names.put(Py.toLong(e.getValue()), e.getKey());
        for (Map.Entry<Long, String> e : names.entrySet()) {
            String cat = e.getValue().toUpperCase();
            String master = "SpecialMaster 3." + e.getKey();
            for (Object bpm : (List<Object>) cfg.get("speed_presets")) {
                cmds.add("Store Macro 1." + m + " /o");
                cmds.add("Store Macro 1." + m + ".1");
                cmds.add("Assign Macro 1." + m + ".1 /cmd=\"" + master + " At " + Py.str(bpm) + "\"");
                cmds.add("Label Macro 1." + m + " \"" + cat + " " + Py.str(bpm) + "\"");
                m++;
            }
            cmds.add("Store Macro 1." + m + " /o");
            cmds.add("Store Macro 1." + m + ".1");
            cmds.add("Assign Macro 1." + m + ".1 /cmd=\"Learn " + master + "\"");
            cmds.add("Label Macro 1." + m + " \"" + cat + " LEARN\"");
            m++;
        }
        return cmds;
    }

    /** одна строка отчёта: номер эффекта, группа, имя шаблона */
    public static final class Made {
        public final long effect;
        public final String group, name, key;

        Made(long effect, String group, String name, String key) {
            this.effect = effect;
            this.group = group;
            this.name = name;
            this.key = key;
        }
    }

    public static final class Result {
        public final List<String> cmds = new ArrayList<>();
        public final List<Made> report = new ArrayList<>();
        public final List<String> warnings = new ArrayList<>();
    }

    /** build(cfg, only, group_ids, make_macros) */
    public static Result build(Map<String, Object> cfg, Set<String> only, Set<Long> groupIds, boolean makeMacros) {
        Map<String, Map<String, Object>> lib = library(cfg);
        Result r = new Result();
        List<String> warns = new ArrayList<>();
        List<Object> groups = (List<Object>) cfg.get("groups");
        long start = Py.toLong(cfg.get("effect_start")), stride = Py.toLong(cfg.get("effect_stride"));
        for (int gi = 0; gi < groups.size(); gi++) {
            Map<String, Object> group = (Map<String, Object>) groups.get(gi);
            if (groupIds != null && !groupIds.isEmpty() && !groupIds.contains(Py.toLong(group.get("id")))) continue;
            Set<String> caps = new HashSet<>();
            for (Object c : (List<Object>) group.get("caps")) caps.add(String.valueOf(c));
            long base = start + gi * stride;
            Object t = group.get("templates");
            List<Object> wanted = Py.truthy(t) ? (List<Object>) t : new ArrayList<Object>(orderedKeys(lib));
            int slot = 0;
            for (Object ko : wanted) {
                String key = String.valueOf(ko);
                Map<String, Object> tpl = lib.get(key);
                if (tpl == null) {
                    warns.add("группа " + Py.str(group.get("id")) + ": неизвестный шаблон '" + key + "'");
                    continue;
                }
                if (only != null && !only.isEmpty() && !only.contains(key)) continue;
                try {
                    if (!caps.containsAll(needs(tpl, lib))) continue;
                    if (slot >= stride) {
                        warns.add("группа " + Py.str(group.get("id")) + ": эффектов больше effect_stride (" + stride
                                + "), остальные пропущены");
                        break;
                    }
                    long effNo = base + slot;
                    List<String> w = new ArrayList<>();
                    List<String> c = effectCommands(tpl, group, effNo, cfg, lib, w);
                    r.cmds.addAll(c);
                    for (String x : w) warns.add(tpl.get("name") + ": " + x);
                    r.report.add(new Made(effNo, Py.str(group.get("name")), Py.str(tpl.get("name")), key));
                    slot++;
                } catch (IllegalArgumentException e) {
                    warns.add(key + ": " + e.getMessage());
                }
            }
        }
        r.cmds.add("ClearAll");
        if (makeMacros) r.cmds.addAll(macroCommands(cfg));
        r.warnings.addAll(new LinkedHashSet<>(warns));
        return r;
    }

    // ------------------------------------------------------------------ формы с пульта
    static final String[][] FORM_NAMES = {
            {"chase", "chase"}, {"sin", "sin", "sine"}, {"cos", "cos", "cosine"},
            {"ramp_plus", "rampplus", "ramp+", "rampup"}, {"ramp_minus", "rampminus", "ramp-", "rampdown"},
            {"ramp", "ramp"}, {"phase1", "phase1"}, {"phase2", "phase2"}, {"phase3", "phase3"},
            {"bump", "bump"}, {"swing", "swing"}, {"random", "random"}, {"pwm", "pwm"},
    };

    /** ответ List Form → {ключ: номер}; missing получает ключи без пары */
    public static Map<String, Long> parseForms(String raw, List<String> missing) {
        Map<String, Long> byName = new HashMap<>();
        for (Patch.Group f : Patch.parseGroupList(raw)) {
            String n = f.name.toLowerCase().replaceAll("[\\s_]+", "");
            if (!byName.containsKey(n)) byName.put(n, f.id);
        }
        Map<String, Long> found = new LinkedHashMap<>();
        for (String[] fn : FORM_NAMES) {
            Long hit = null;
            for (int i = 1; i < fn.length && hit == null; i++) hit = byName.get(fn[i]);
            if (hit == null) missing.add(fn[0]);
            else found.put(fn[0], hit);
        }
        return found;
    }

    /** EffectForm N: номера из конфига → номера пульта */
    public static List<String> remapForms(List<String> cmds, Map<String, Object> old, Map<String, Long> now) {
        Map<Long, Long> m = new HashMap<>();
        for (Map.Entry<String, Object> e : old.entrySet()) if (now.containsKey(e.getKey())) m.put(Py.toLong(e.getValue()), now.get(e.getKey()));
        List<String> out = new ArrayList<>();
        for (String c : cmds) {
            if (c.startsWith("EffectForm ")) {
                long n = Long.parseLong(c.split(" ")[1]);
                c = "EffectForm " + (m.containsKey(n) ? m.get(n) : n);
            }
            out.add(c);
        }
        return out;
    }
}
