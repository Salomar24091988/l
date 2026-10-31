package com.yan.malight.core;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Разбор ответов пульта (группы, приборы, формы) и противофаза - как в ma2_fxgen.py / ma2_fxgen_gui.py. */
public final class Patch {

    private static final Pattern ANSI = Pattern.compile("\u001b\\[[0-9;?]*[A-Za-z]");

    public static String cleanText(String t) {
        return ANSI.matcher(t == null ? "" : t).replaceAll("").replace("\r", "");
    }

    /** ответ пульта только на свою команду (как own_reply в ядре) */
    public static String ownReply(String reply, String cmd) {
        StringBuilder out = new StringBuilder();
        boolean mine = true;
        String want = squash(cmd).toLowerCase(Locale.ROOT);
        for (String line : cleanText(reply).split("\n", -1)) {
            String low = squash(line).toLowerCase(Locale.ROOT);
            int i;
            if ((i = low.indexOf("executing :")) >= 0) mine = low.substring(i + 11).trim().equals(want);
            else if (low.startsWith("error :")) mine = low.substring(7).trim().equals(want);
            if (mine) {
                if (out.length() > 0) out.append('\n');
                out.append(line);
            }
        }
        return out.toString();
    }

    private static String squash(String s) { return s.trim().replaceAll("\\s+", " "); }

    // ------------------------------------------------------------------ группы
    public static final class Group {
        public long id;
        public String name;
        public List<String> caps = new ArrayList<>();
        public int count;
        public String type = "";
        public String how = "";

        Group(long id, String name) {
            this.id = id;
            this.name = name;
        }
    }

    static final String[] SKIP = {"executing", "list", "[", "no.", "no ", "#", "name", "ok", "error", "welcome",
            "logged", "login", "user", "command"};
    private static final Pattern G_ROW = Pattern.compile("^(?:group\\s+)?(\\d+)\\s*[:.)]?\\s+(.*)$", Pattern.CASE_INSENSITIVE);
    private static final Pattern G_DUP = Pattern.compile("^(\\d+)\\s+(.*)$");
    private static final Pattern G_NAME_Q = Pattern.compile("name\\s*=\\s*\"([^\"]*)\"", Pattern.CASE_INSENSITIVE);
    private static final Pattern G_NAME = Pattern.compile("name\\s*=\\s*(.+?)(?=\\s{2,}|\\s+\\w+\\s*=|$)", Pattern.CASE_INSENSITIVE);

    public static List<Group> parseGroupList(String text) {
        TreeMap<Long, String> groups = new TreeMap<>();
        for (String raw : cleanText(text).split("\n")) {
            String line = raw.trim();
            if (line.isEmpty()) continue;
            String low = line.toLowerCase(Locale.ROOT);
            boolean skip = false;
            for (String p : SKIP) if (low.startsWith(p)) { skip = true; break; }
            if (skip) continue;
            Matcher m = G_ROW.matcher(line);
            if (!m.matches()) continue;
            long gid = Long.parseLong(m.group(1));
            String rest = m.group(2).trim();
            Matcher dup = G_DUP.matcher(rest);
            if (dup.matches() && Long.parseLong(dup.group(1)) == gid) rest = dup.group(2).trim();
            Matcher nq = G_NAME_Q.matcher(rest), nm = G_NAME.matcher(rest);
            String name;
            if (nq.find()) name = nq.group(1);
            else if (nm.find()) name = nm.group(1);
            else if (rest.startsWith("\"") && rest.indexOf('"', 1) > 0) name = rest.substring(1, rest.indexOf('"', 1));
            else if (rest.startsWith("'") && rest.indexOf('\'', 1) > 0) name = rest.substring(1, rest.indexOf('\'', 1));
            else name = rest.split("\\s{2,}|\\t|\\s+:\\s+")[0];
            name = stripQuotes(name.trim());
            if (!name.isEmpty() && gid > 0 && !groups.containsKey(gid)) groups.put(gid, name);
        }
        List<Group> out = new ArrayList<>();
        for (Map.Entry<Long, String> e : groups.entrySet()) out.add(new Group(e.getKey(), e.getValue()));
        return out;
    }

    private static String stripQuotes(String s) {
        int a = 0, b = s.length();
        while (a < b && s.charAt(a) == '"') a++;
        while (b > a && s.charAt(b - 1) == '"') b--;
        return s.substring(a, b);
    }

    // возможности по словам в имени группы (CAP_HINTS ядра)
    static final Object[][] CAP_HINTS = {
            {new String[]{"par64", "par 64", "dimmer", "front", "fresnel", "profile", "blinder", "pc ", "фронт", "диммер"}, new String[]{"dim"}},
            {new String[]{"spot", "alpha", "viper", "pointe", "sharpy", "mh", "moving", "head", "спот", "голов"}, new String[]{"dim", "pt", "shutter"}},
            {new String[]{"beam", "бим"}, new String[]{"dim", "pt", "rgb"}},
            {new String[]{"wash", "aura", "mac", "вош"}, new String[]{"dim", "pt", "rgb"}},
            {new String[]{"led", "rgb", "q7", "batten", "pixel", "strip", "bar", "cyc", "лед"}, new String[]{"dim", "rgb"}},
    };
    public static final List<String> GEN_CAPS = Arrays.asList("dim", "pt", "rgb", "shutter");

    public static List<String> guessCaps(String name) {
        String n = " " + name.toLowerCase(Locale.ROOT) + " ";
        Set<String> caps = new HashSet<>();
        caps.add("dim");
        for (Object[] h : CAP_HINTS) {
            for (String w : (String[]) h[0]) if (n.contains(w)) { caps.addAll(Arrays.asList((String[]) h[1])); break; }
        }
        List<String> out = new ArrayList<>();
        for (String c : GEN_CAPS) if (caps.contains(c)) out.add(c);
        return out;
    }

    // ------------------------------------------------------------------ типы приборов
    static final Object[][] TYPE_RULES = {
            {"fog|haze|smoke|hazer|дым", "-", new String[]{}},
            {"impression|x4 ?(?:l|s|xs)\\b|aura|spiider|b-?eye|mac ?(?:quantum ?wash|wash)|led ?wash", "wash", new String[]{"dim", "pt", "shutter", "rgb", "zoom"}},
            {"flare|atomic|jdc|strobe|blinder|molefay", "par", new String[]{"dim", "rgb", "shutter"}},
            {"quantum ?profile|bmfl|viper|encore|forte|tarrantula|mac ?ultra|esprite|scenius|ghibli|pearl", "spot",
                    new String[]{"dim", "pt", "shutter", "rgb", "wheel", "zoom", "focus", "iris", "prism", "gobo", "frost"}},
            {"ledbeam|led ?beam|b-?eye|spiider|zoom ?wash", "wash", new String[]{"dim", "pt", "shutter", "rgb", "zoom"}},
            {"blinder|molefay|strobe|atomic|jdc|x4 ?bar", "par", new String[]{"dim", "shutter"}},
            {"front|source ?four|zoom ?profile|ellipsoidal|leko|fresnel|conventional", "par", new String[]{"dim"}},
            {"sharpy|beam|pointe|mythos|b-?eye|k10|k20|megapointe", "spot", new String[]{"dim", "pt", "shutter", "wheel", "prism", "gobo", "frost", "focus"}},
            {"spot|profile|bmfl|robin.*(?:600|800|1200)e?|viper|encore|forte|pearl|scenius|ghibli|tarrantula", "spot",
                    new String[]{"dim", "pt", "shutter", "wheel", "zoom", "focus", "iris", "prism", "gobo", "frost"}},
            {"wash|aura|lyre|led ?beam|spiider|b-?eye|quantum|zoom", "wash", new String[]{"dim", "pt", "shutter", "rgb", "zoom"}},
            {"par|rgb|led|bar|batten|cyc|panel|flood|hex|tri|quad", "par", new String[]{"dim", "rgb", "shutter"}},
            {"dimmer|generic|conventional|halogen|fresnel|pc", "par", new String[]{"dim"}},
    };
    private static final List<Pattern> TYPE_PATTERNS = new ArrayList<>();

    static {
        for (Object[] r : TYPE_RULES) TYPE_PATTERNS.add(Pattern.compile((String) r[0]));
    }

    /** → [вид, возможности] */
    public static Object[] guessFixtureType(String name) {
        String n = name == null ? "" : name.toLowerCase(Locale.ROOT);
        for (int i = 0; i < TYPE_RULES.length; i++)
            if (TYPE_PATTERNS.get(i).matcher(n).find())
                return new Object[]{TYPE_RULES[i][1], Arrays.asList((String[]) TYPE_RULES[i][2])};
        return new Object[]{"par", Collections.singletonList("dim")};
    }

    // ------------------------------------------------------------------ приборы
    public static final class Fixture {
        public long id;
        public String name, type;
        public int subs = 1;
        public boolean chan;
    }

    static final Pattern FIX_ROW = Pattern.compile(
            "^\\s*(?:Fixture|Channel)\\s+\\d+\\s+(.*?)\\s{2,}(\\d+|-)\\s+(\\d+|-)\\s+"
                    + "(\\d+)\\s+(.+?)\\s{2,}(\\d+\\.\\d+|-)\\s+(?:Yes|No)\\s+"
                    + "(-?[\\d.]+)\\s+(-?[\\d.]+)\\s+(-?[\\d.]+)\\s+"
                    + "(-?[\\d.]+)\\s+(-?[\\d.]+)\\s+(-?[\\d.]+)(.*)$", Pattern.CASE_INSENSITIVE);
    private static final Pattern SUBS = Pattern.compile("\\((\\d+)\\)\\s*$");

    static List<String> rows(String text) {
        List<String> out = new ArrayList<>();
        for (String line : (text == null ? "" : text).split("\\r?\\n|\\r")) {
            line = ANSI.matcher(line).replaceAll("").replaceAll("\\s+$", "");
            line = line.replaceFirst("^\\s*\\d+h\\d+m[\\d.]+s\\s*:\\s?", "");
            if (!line.trim().isEmpty()) out.add(line);
        }
        return out;
    }

    /** List Fixture / List Channel 3.9.x → приборы (без FixID - номер канала, chan) */
    public static List<Fixture> parseFixtureTable(String text) {
        List<Fixture> out = new ArrayList<>();
        Set<Long> seen = new HashSet<>();
        for (String line : rows(text)) {
            line = line.replaceFirst("^\\s*\\[[^\\]]*\\]>\\s*", "");
            Matcher m = FIX_ROW.matcher(line);
            if (!m.matches() || (m.group(2).equals("-") && m.group(3).equals("-"))) continue;
            Fixture f = new Fixture();
            f.chan = m.group(2).equals("-");
            f.id = Long.parseLong(f.chan ? m.group(3) : m.group(2));
            if (!seen.add(f.id)) continue;
            f.name = m.group(1).trim();
            f.type = m.group(5).trim();
            Matcher s = SUBS.matcher(m.group(13));
            f.subs = s.find() ? Integer.parseInt(s.group(1)) : 1;
            out.add(f);
        }
        return out;
    }

    private static final Pattern WORD = Pattern.compile("[a-zа-я0-9]{3,}");
    private static final Set<String> STOP = new HashSet<>(Arrays.asList("all", "mode", "standard", "basic", "normal",
            "extended", "bit", "lamp", "the", "все", "группа", "group"));

    /** номер правила TYPE_RULES, которое узнаёт имя (кроме дыма); -1 - не узнано */
    static int ruleIndex(String low) {
        for (int i = 1; i < TYPE_RULES.length; i++) if (TYPE_PATTERNS.get(i).matcher(low).find()) return i;
        return -1;
    }

    /**
     * Группам с пульта - тип приборов и возможности: «All <тип>» - все приборы этого типа,
     * иначе по похожести имени группы на имена / типы приборов, иначе по виду (spot / wash / par)
     * в имени, иначе по словам в имени (как guess_caps).
     */
    public static void applyPatch(List<Group> groups, List<Fixture> fixtures) {
        List<String> typesLong = new ArrayList<>();
        for (Fixture f : fixtures) if (!f.type.isEmpty() && !typesLong.contains(f.type)) typesLong.add(f.type);
        Collections.sort(typesLong, new Comparator<String>() {
            @Override
            public int compare(String a, String b) { return b.length() - a.length(); }
        });
        for (Group g : groups) {
            String low = g.name.toLowerCase(Locale.ROOT);
            String type = null;
            int count = 0;
            for (String t : typesLong) if (low.contains(t.toLowerCase(Locale.ROOT))) { type = t; break; }
            if (type != null) {
                for (Fixture f : fixtures) if (type.equals(f.type)) count += f.subs;
                g.how = "все приборы типа";
            } else if (ruleIndex(low) >= 0) {
                // тип угадывается по самому имени группы (Sharpy, Aura, Quantum Profile…)
                Object[] r = TYPE_RULES[ruleIndex(low)];
                g.type = "";
                g.caps = new ArrayList<>();
                for (String c : GEN_CAPS) if (Arrays.asList((String[]) r[2]).contains(c)) g.caps.add(c);
                g.how = "по имени группы (" + r[1] + ")";
                continue;
            } else {
                // по имени: больше всего общих слов
                List<String> words = new ArrayList<>();
                Matcher m = WORD.matcher(low);
                while (m.find()) if (!STOP.contains(m.group())) words.add(m.group());
                int best = 0;
                Map<Fixture, Integer> hits = new LinkedHashMap<>();
                for (Fixture f : fixtures) {
                    String t = (f.name + " " + f.type).toLowerCase(Locale.ROOT);
                    int h = 0;
                    for (String w : words) if (t.contains(w)) h++;
                    if (h > 0) {
                        hits.put(f, h);
                        best = Math.max(best, h);
                    }
                }
                Map<String, Integer> byType = new HashMap<>();
                for (Map.Entry<Fixture, Integer> e : hits.entrySet()) {
                    if (e.getValue() != best || e.getKey().type.isEmpty()) continue;
                    Integer n = byType.get(e.getKey().type);
                    byType.put(e.getKey().type, (n == null ? 0 : n) + 1);
                    count += e.getKey().subs;
                }
                if (!byType.isEmpty()) {
                    type = Collections.max(byType.entrySet(), new Comparator<Map.Entry<String, Integer>>() {
                        @Override
                        public int compare(Map.Entry<String, Integer> a, Map.Entry<String, Integer> b) { return a.getValue() - b.getValue(); }
                    }).getKey();
                    g.how = "по имени";
                } else {
                    count = 0;
                    for (String kind : new String[]{"spot", "wash", "par"}) {
                        if (!low.contains(kind)) continue;
                        for (Fixture f : fixtures)
                            if (!f.type.isEmpty() && kind.equals(guessFixtureType(f.type)[0])) { type = f.type; break; }
                        if (type != null) break;
                    }
                    if (type != null) g.how = "по виду";
                }
            }
            if (type != null) {
                g.type = type;
                List<String> caps = new ArrayList<>();
                @SuppressWarnings("unchecked") List<String> tc = (List<String>) guessFixtureType(type)[1];
                for (String c : GEN_CAPS) if (tc.contains(c)) caps.add(c);
                g.caps = caps;
                if (count > 0) g.count = count;
            } else {
                g.caps = guessCaps(g.name);
                g.how = "по имени группы";
            }
        }
    }

    // ------------------------------------------------------------------ противофаза
    static final Pattern PHASE_RE = Pattern.compile("(phase\\W{0,3})(-?\\d+(?:\\.\\d+)?)(\\s*thru\\s*)?(-?\\d+(?:\\.\\d+)?)?",
            Pattern.CASE_INSENSITIVE);
    static final Pattern EFFECT_NO = Pattern.compile("(\\bEffect\\s+(?:1\\.)?)(\\d+)", Pattern.CASE_INSENSITIVE);

    /** сдвиг фазы групп: группы с одинаковыми возможностями делят круг поровну */
    @SuppressWarnings("unchecked")
    public static Map<String, Double> groupOffsets(List<Object> groups) {
        Map<String, List<Map<String, Object>>> kinds = new LinkedHashMap<>();
        for (Object o : groups) {
            Map<String, Object> g = (Map<String, Object>) o;
            List<String> c = new ArrayList<>();
            Object caps = g.get("caps");
            if (caps instanceof List) for (Object x : (List<Object>) caps) c.add(String.valueOf(x));
            Collections.sort(c);
            String k = c.toString();
            if (!kinds.containsKey(k)) kinds.put(k, new ArrayList<Map<String, Object>>());
            kinds.get(k).add(g);
        }
        Map<String, Double> out = new LinkedHashMap<>();
        for (List<Map<String, Object>> same : kinds.values()) {
            for (int i = 0; i < same.size(); i++) {
                Map<String, Object> g = same.get(i);
                String own = g.get("phase_shift") == null ? "" : String.valueOf(g.get("phase_shift")).trim();
                double v;
                try {
                    v = !own.isEmpty() ? Double.parseDouble(own) : (same.size() > 1 ? 360.0 * i / same.size() : 0.0);
                } catch (NumberFormatException e) {
                    v = 0;
                }
                out.put(Py.str(g.get("name")), v);
            }
        }
        return out;
    }

    static String shiftPhase(String cmd, double off, int[] hits) {
        Matcher m = PHASE_RE.matcher(cmd);
        StringBuffer sb = new StringBuffer();
        while (m.find()) {
            hits[0]++;
            String a = Py.str(Py.num(Double.parseDouble(m.group(2)) + off));
            String rep = m.group(4) == null ? m.group(1) + a
                    : m.group(1) + a + (m.group(3) != null ? m.group(3) : " Thru ") + Py.str(Py.num(Double.parseDouble(m.group(4)) + off));
            m.appendReplacement(sb, Matcher.quoteReplacement(rep));
        }
        m.appendTail(sb);
        return sb.toString();
    }

    /** копии эффектов со сдвигом фазы (номер + shift); исходные не трогаются. → сводка */
    public static String phaseCopies(FxGen.Result r, List<Object> groups, long shift) {
        Map<String, Double> offs = groupOffsets(groups);
        boolean any = false;
        for (double v : offs.values()) if (v % 360 != 0) any = true;
        if (!any) return "противофаза: групп с одинаковыми возможностями нет";
        List<String> cmds = r.cmds;
        List<String> extra = new ArrayList<>();
        StringBuilder names = new StringBuilder();
        int copies = 0;
        for (FxGen.Made e : r.report) {
            Double o = offs.get(e.group);
            double off = o == null ? 0 : ((o % 360) + 360) % 360;
            if (off == 0) continue;
            int start = cmds.indexOf("Delete Effect 1." + e.effect + " /noconfirm");
            if (start < 0) continue;
            int end = start + 1;
            while (end < cmds.size() && !cmds.get(end).startsWith("Delete Effect ") && !isTail(cmds, end)) end++;
            List<String> block = new ArrayList<>();
            int[] hits = {0};
            for (String c : cmds.subList(start, end)) {
                if (c.toLowerCase(Locale.ROOT).contains("macro")) continue;
                Matcher m = EFFECT_NO.matcher(c);
                StringBuffer sb = new StringBuffer();
                while (m.find()) {
                    String n = Long.parseLong(m.group(2)) == e.effect ? String.valueOf(e.effect + shift) : m.group(2);
                    m.appendReplacement(sb, Matcher.quoteReplacement(m.group(1) + n));
                }
                m.appendTail(sb);
                block.add(shiftPhase(sb.toString(), off, hits));
            }
            if (hits[0] > 0) {
                extra.addAll(block);
                copies++;
            }
        }
        if (copies == 0) return "противофаза не создана: в командах не нашёл phase";
        int tail = cmds.lastIndexOf("ClearAll");
        cmds.addAll(tail < 0 ? cmds.size() : tail, extra);
        for (Map.Entry<String, Double> e : offs.entrySet())
            if (e.getValue() % 360 != 0) names.append(names.length() > 0 ? ", " : "").append(e.getKey()).append(' ')
                    .append(Py.str(Py.num(e.getValue()))).append('°');
        return "противофаза: " + copies + " копий со сдвигом фазы (Effect +" + shift + "): " + names;
    }

    /** последний ClearAll сборки (перед макросами) */
    private static boolean isTail(List<String> cmds, int i) {
        return cmds.get(i).equals("ClearAll") && i == cmds.lastIndexOf("ClearAll")
                && (i + 1 == cmds.size() || cmds.get(i + 1).startsWith("Store Macro"));
    }
}
