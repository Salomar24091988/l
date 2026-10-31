package com.yan.malight;

import android.app.AlertDialog;
import android.content.DialogInterface;
import android.graphics.Typeface;
import android.os.Bundle;
import android.os.Handler;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;

import com.yan.malight.core.Director;
import com.yan.malight.core.FxGen;
import com.yan.malight.core.FxJobs;
import com.yan.malight.core.Patch;
import com.yan.malight.core.Py;
import com.yan.malight.core.Settings;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** Генератор эффектов MA2 в телефоне: те же шаблоны и команды, что «Генератор эффектов MA2» на ПК. */
@SuppressWarnings("unchecked")
public final class GeneratorActivity extends BaseActivity {

    static final String[] CAPS = {"dim", "pt", "rgb", "shutter"};
    static final String[] CAP_TITLES = {"Диммер", "Движение", "Цвет RGB", "Шторка"};
    static final Map<String, String> CAT_TITLES = new LinkedHashMap<>();

    static {
        CAT_TITLES.put("dimmer", "Диммер");
        CAT_TITLES.put("position", "Движение");
        CAT_TITLES.put("color", "Цвет RGB");
        CAT_TITLES.put("strobe", "Строб");
        CAT_TITLES.put("combo", "Комбо");
    }

    private Engine engine;
    private final Handler ui = new Handler();
    private Map<String, Object> st;
    private LinearLayout groupsBox, tplBox;
    private TextView summary, status, logText;
    private ProgressBar prog;
    private Button pullBtn, sendBtn, stopBtn;
    private final Map<String, Button> tplBtns = new LinkedHashMap<>();
    private final Map<String, EditText> optFields = new LinkedHashMap<>();
    private final Map<String, Button> optToggles = new LinkedHashMap<>();
    private final ArrayDeque<String> log = new ArrayDeque<>();
    private volatile FxJobs job;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        engine = Engine.get(this);
        st = engine.gen();
        getWindow().setStatusBarColor(BG);
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_HIDDEN);
        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(BG);
        LinearLayout root = column();
        root.setPadding(px(12), px(10), px(12), px(24));
        scroll.addView(root);
        setContentView(scroll);

        TextView title = text(22, TEXT);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setText("Генератор эффектов MA2");
        root.addView(title);
        TextView sub = text(13, DIM);
        sub.setText("Те же шаблоны и команды, что генератор LightDancer на ПК. Эффекты в пул Effects с 1."
                + "<номер>, макросы скорости для SpecialMaster 3.x.");
        root.addView(sub);

        // действия
        LinearLayout r1 = row(root);
        pullBtn = button(r1, "⇩ Группы с пульта", new View.OnClickListener() {
            @Override public void onClick(View v) { pull(); }
        });
        sendBtn = button(r1, "▶ Создать на пульте", new View.OnClickListener() {
            @Override public void onClick(View v) { confirmSend(); }
        });
        tint(sendBtn, ON);
        LinearLayout r2 = row(root);
        stopBtn = button(r2, "■ Стоп", new View.OnClickListener() {
            @Override public void onClick(View v) {
                FxJobs j = job;
                if (j != null) j.stop = true;
            }
        });
        tint(stopBtn, 0xff8e1b1b);
        status = text(14, TEXT);
        status.setPadding(px(8), 0, 0, 0);
        status.setGravity(Gravity.CENTER_VERTICAL);
        r2.addView(status, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 2));
        prog = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        root.addView(prog, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, px(10)));
        summary = text(15, TEXT);
        summary.setPadding(0, px(6), 0, 0);
        root.addView(summary);

        // группы
        root.addView(caption("Группы (тап по имени - брать / не брать)"));
        groupsBox = column();
        root.addView(groupsBox);

        // шаблоны
        root.addView(caption("Шаблоны"));
        tplBox = column();
        root.addView(tplBox);
        buildTemplates();

        // настройки
        root.addView(caption("Настройки"));
        LinearLayout o = card(root);
        LinearLayout t1 = row(o);
        optToggle(t1, "macros", "Макросы скорости", true);
        optToggle(t1, "move_dim", "Диммер в движении", true);
        LinearLayout t2 = row(o);
        optToggle(t2, "antiphase", "Противофаза (копии)", false);
        optField(o, "move_dim_lo", "Диммер в движении от, %", "40", true);
        optField(o, "phase_shift_no", "Копии противофазы: номер + ", "500", false);
        optField(o, "effect_start", "Первый эффект (Effect 1.N)", "101", false);
        optField(o, "effect_stride", "Шаг между группами", "100", false);
        optField(o, "macro_start", "Первый макрос", "201", false);
        optField(o, "delay", "Пауза между командами, с", "0.12", true);

        // журнал
        root.addView(caption("Журнал"));
        logText = text(12, DIM);
        logText.setTypeface(Typeface.MONOSPACE);
        card(root).addView(logText);

        renderGroups();
        refresh();
        setBusy(false, "");
    }

    @Override
    protected void onPause() {
        engine.saveGen();
        super.onPause();
    }

    // ------------------------------------------------------------------ состояние
    private List<Object> groups() { return (List<Object>) st.get("groups"); }

    private Set<String> off() {
        Set<String> s = new HashSet<>();
        for (Object o : (List<Object>) st.get("off")) s.add(String.valueOf(o));
        return s;
    }

    private Map<String, Object> opts() { return (Map<String, Object>) st.get("opts"); }

    private String opt(String k, String def) {
        Object v = opts().get(k);
        return v == null ? def : String.valueOf(v);
    }

    private boolean optOn(String k, boolean def) {
        Object v = opts().get(k);
        return v == null ? def : Py.truthy(v);
    }

    private void saveSoon() {
        refresh();
        engine.saveGen();
    }

    /** конфиг генератора из того, что на экране; null - что-то не так (сообщение в status) */
    private Map<String, Object> config() {
        Map<String, Object> cfg = FxGen.defaultConfig();
        List<Object> gs = (List<Object>) cfg.get("groups");
        for (Object o : groups()) {
            Map<String, Object> g = (Map<String, Object>) o;
            if (!Py.truthy(g.get("use"))) continue;
            Map<String, Object> c = new LinkedHashMap<>();
            c.put("id", g.get("id"));
            c.put("name", g.get("name"));
            c.put("caps", new ArrayList<Object>((List<Object>) g.get("caps")));
            c.put("size", g.containsKey("size") ? g.get("size") : 20L);
            c.put("shut_lo", 0L);
            c.put("shut_hi", 100L);
            c.put("count", g.containsKey("count") ? g.get("count") : 6L);
            c.put("templates", null);
            gs.add(c);
        }
        try {
            for (String k : new String[]{"effect_start", "effect_stride", "macro_start"})
                cfg.put(k, Py.num(Double.parseDouble(opt(k, Py.str(cfg.get(k))).replace(',', '.'))));
            cfg.put("move_dim", optOn("move_dim", true));
            cfg.put("move_dim_lo", Py.num(Double.parseDouble(opt("move_dim_lo", "40").replace(',', '.'))));
        } catch (NumberFormatException e) {
            return null;
        }
        return cfg;
    }

    private FxGen.Result build(Map<String, Object> cfg, StringBuilder note) {
        Set<String> only = new HashSet<>();
        Set<String> offs = off();
        for (Map<String, Object> t : FxGen.templates()) if (!offs.contains(t.get("key"))) only.add((String) t.get("key"));
        if (only.isEmpty() || ((List<Object>) cfg.get("groups")).isEmpty()) return null;
        FxGen.Result r = FxGen.build(cfg, only, null, optOn("macros", true));
        if (optOn("antiphase", false) && !r.report.isEmpty()) {
            long shift = 500;
            try { shift = Long.parseLong(opt("phase_shift_no", "500").trim()); } catch (NumberFormatException ignored) { }
            note.append(Patch.phaseCopies(r, (List<Object>) cfg.get("groups"), shift));
        }
        return r;
    }

    private void refresh() {
        Map<String, Object> cfg = config();
        if (cfg == null) {
            summary.setText("⚠ Проверьте числа в настройках");
            return;
        }
        StringBuilder note = new StringBuilder();
        FxGen.Result r = build(cfg, note);
        if (r == null) {
            summary.setText(groups().isEmpty() ? "Нет групп: нажмите «⇩ Группы с пульта»" : "Не выбраны группы или шаблоны");
            return;
        }
        double delay = 0.12;
        try { delay = Double.parseDouble(opt("delay", "0.12").replace(',', '.')); } catch (NumberFormatException ignored) { }
        double min = r.cmds.size() * (delay + 0.06) / 60;
        String s = r.report.size() + " эффектов · " + r.cmds.size() + " команд · ~" + Math.max(1, Math.round(min)) + " мин";
        if (note.length() > 0) s += "\n" + note;
        if (!r.warnings.isEmpty()) s += "\n⚠ " + r.warnings.get(0) + (r.warnings.size() > 1 ? " … и ещё " + (r.warnings.size() - 1) : "");
        summary.setText(s);
    }

    // ------------------------------------------------------------------ группы
    private void renderGroups() {
        groupsBox.removeAllViews();
        if (groups().isEmpty()) {
            TextView t = text(14, DIM);
            t.setText("Групп пока нет. Пульт должен быть включён в настройках главного экрана (IP, логин).");
            groupsBox.addView(t);
            return;
        }
        for (Object o : groups()) groupsBox.addView(groupRow((Map<String, Object>) o));
    }

    private View groupRow(final Map<String, Object> g) {
        final LinearLayout c = card(new LinearLayout(this));
        ((ViewGroup) c.getParent()).removeView(c);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = px(6);
        c.setLayoutParams(lp);
        final TextView name = text(16, TEXT);
        name.setTypeface(Typeface.DEFAULT_BOLD);
        final Runnable paint = new Runnable() {
            @Override
            public void run() {
                boolean use = Py.truthy(g.get("use"));
                name.setText((use ? "☑ " : "☐ ") + Py.str(g.get("id")) + "  " + Py.str(g.get("name")));
                name.setTextColor(use ? TEXT : DIM);
            }
        };
        paint.run();
        name.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                g.put("use", !Py.truthy(g.get("use")));
                paint.run();
                saveSoon();
            }
        });
        c.addView(name);
        TextView info = text(12, DIM);
        String type = Py.truthy(g.get("type")) ? Py.str(g.get("type")) : "";
        Object cnt = g.get("count");
        info.setText((type.isEmpty() ? "" : type + " · ") + (Py.truthy(cnt) ? cnt + " шт · " : "")
                + (Py.truthy(g.get("how")) ? Py.str(g.get("how")) : ""));
        c.addView(info);
        LinearLayout caps = row(c);
        final List<Object> have = (List<Object>) g.get("caps");
        for (int i = 0; i < CAPS.length; i++) {
            final String cap = CAPS[i];
            final Button b = button(caps, CAP_TITLES[i], null);
            b.setTextSize(12);
            b.setMinHeight(px(38));
            tint(b, have.contains(cap) ? ON : OFF);
            b.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    if (have.contains(cap)) have.remove(cap);
                    else {
                        // порядок как в генераторе: dim, pt, rgb, shutter
                        List<Object> n = new ArrayList<>();
                        for (String x : CAPS) if (x.equals(cap) || have.contains(x)) n.add(x);
                        have.clear();
                        have.addAll(n);
                    }
                    tint(b, have.contains(cap) ? ON : OFF);
                    saveSoon();
                }
            });
        }
        LinearLayout sz = row(c);
        TextView l = text(13, DIM);
        l.setText("Амплитуда движения, °");
        l.setGravity(Gravity.CENTER_VERTICAL);
        sz.addView(l, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 2));
        final EditText e = new EditText(this);
        e.setSingleLine(true);
        e.setTextColor(TEXT);
        e.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL);
        e.setText(Py.str(g.containsKey("size") ? g.get("size") : 20L));
        e.setOnFocusChangeListener(new View.OnFocusChangeListener() {
            @Override
            public void onFocusChange(View v, boolean has) {
                if (has) return;
                try {
                    g.put("size", Py.num(Double.parseDouble(e.getText().toString().replace(',', '.'))));
                } catch (NumberFormatException ex) {
                    e.setText(Py.str(g.get("size")));
                }
                saveSoon();
            }
        });
        sz.addView(e, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        return c;
    }

    // ------------------------------------------------------------------ шаблоны
    private void buildTemplates() {
        Map<String, List<Map<String, Object>>> byCat = new LinkedHashMap<>();
        for (String c : CAT_TITLES.keySet()) byCat.put(c, new ArrayList<Map<String, Object>>());
        for (Map<String, Object> t : FxGen.templates()) {
            String c = String.valueOf(t.get("cat"));
            if (!byCat.containsKey(c)) byCat.put(c, new ArrayList<Map<String, Object>>());
            byCat.get(c).add(t);
        }
        for (Map.Entry<String, List<Map<String, Object>>> e : byCat.entrySet()) {
            if (e.getValue().isEmpty()) continue;
            final List<Map<String, Object>> list = e.getValue();
            LinearLayout head = row(tplBox);
            TextView h = text(14, TEXT);
            h.setTypeface(Typeface.DEFAULT_BOLD);
            h.setText((CAT_TITLES.containsKey(e.getKey()) ? CAT_TITLES.get(e.getKey()) : e.getKey()) + " (" + list.size() + ")");
            h.setGravity(Gravity.CENTER_VERTICAL);
            head.addView(h, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 2));
            Button all = button(head, "все / ни одного", new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    List<Object> off = (List<Object>) st.get("off");
                    boolean anyOn = false;
                    for (Map<String, Object> t : list) if (!off.contains(t.get("key"))) anyOn = true;
                    for (Map<String, Object> t : list) {
                        off.remove(t.get("key"));
                        if (anyOn) off.add(t.get("key"));
                    }
                    paintTemplates();
                    saveSoon();
                }
            });
            all.setTextSize(12);
            tint(all, OFF);
            LinearLayout r = null;
            for (int i = 0; i < list.size(); i++) {
                final Map<String, Object> t = list.get(i);
                if (i % 2 == 0) r = row(tplBox);
                Button b = button(r, Py.str(t.get("name")) + (t.containsKey("bpm") ? "\n" + Py.str(t.get("bpm")) + " BPM" : ""),
                        new View.OnClickListener() {
                            @Override
                            public void onClick(View v) {
                                List<Object> off = (List<Object>) st.get("off");
                                if (!off.remove(t.get("key"))) off.add(t.get("key"));
                                paintTemplates();
                                saveSoon();
                            }
                        });
                b.setTextSize(12);
                tplBtns.put((String) t.get("key"), b);
            }
            if (list.size() % 2 == 1) {
                View pad = new View(this);
                LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, 1, 1);
                lp.leftMargin = px(6);
                r.addView(pad, lp);
            }
        }
        paintTemplates();
    }

    private void paintTemplates() {
        Set<String> off = off();
        for (Map.Entry<String, Button> e : tplBtns.entrySet()) tint(e.getValue(), off.contains(e.getKey()) ? OFF : ON);
    }

    // ------------------------------------------------------------------ настройки
    private void optToggle(LinearLayout row, final String key, String label, final boolean def) {
        final Button b = button(row, label, null);
        b.setTextSize(13);
        tint(b, optOn(key, def) ? ON : OFF);
        b.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                opts().put(key, !optOn(key, def));
                tint(b, optOn(key, def) ? ON : OFF);
                saveSoon();
            }
        });
        optToggles.put(key, b);
    }

    private void optField(LinearLayout parent, final String key, String label, final String def, boolean decimal) {
        LinearLayout r = row(parent);
        TextView l = text(13, DIM);
        l.setText(label);
        l.setGravity(Gravity.CENTER_VERTICAL);
        r.addView(l, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 2));
        final EditText e = new EditText(this);
        e.setSingleLine(true);
        e.setTextColor(TEXT);
        e.setInputType(InputType.TYPE_CLASS_NUMBER | (decimal ? InputType.TYPE_NUMBER_FLAG_DECIMAL : 0));
        e.setText(opt(key, def));
        e.setOnFocusChangeListener(new View.OnFocusChangeListener() {
            @Override
            public void onFocusChange(View v, boolean has) {
                if (has) return;
                String t = e.getText().toString().trim();
                try {
                    Double.parseDouble(t.replace(',', '.'));
                    opts().put(key, t);
                } catch (NumberFormatException ex) {
                    e.setText(opt(key, def));
                }
                saveSoon();
            }
        });
        r.addView(e, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        optFields.put(key, e);
    }

    /** поля, которые ещё в фокусе, - в состояние */
    private void commitFields() {
        View f = getCurrentFocus();
        if (f != null) f.clearFocus();
    }

    // ------------------------------------------------------------------ пульт
    private final FxJobs.Out out = new FxJobs.Out() {
        @Override
        public void log(final String text, final boolean error) {
            engine.log((error ? "⚠ " : "") + "Генератор: " + text.split("\n")[0]);
            ui.post(new Runnable() {
                @Override
                public void run() { addLog(text); }
            });
        }

        @Override
        public void progress(final int done, final int total) {
            ui.post(new Runnable() {
                @Override
                public void run() {
                    prog.setMax(Math.max(1, total));
                    prog.setProgress(done);
                    if (job != null) status.setText(done + " / " + total);
                }
            });
        }
    };

    private void addLog(String t) {
        for (String l : t.split("\n")) {
            log.addLast(l);
            while (log.size() > 40) log.removeFirst();
        }
        StringBuilder sb = new StringBuilder();
        List<String> all = new ArrayList<>(log);
        for (int i = all.size() - 1; i >= 0; i--) sb.append(all.get(i)).append('\n');
        logText.setText(sb.toString().trim());
    }

    private void setBusy(boolean busy, String text) {
        pullBtn.setEnabled(!busy);
        sendBtn.setEnabled(!busy);
        stopBtn.setEnabled(busy);
        tint(pullBtn, busy ? OFF : ACCENT);
        tint(sendBtn, busy ? OFF : ON);
        tint(stopBtn, busy ? 0xff8e1b1b : OFF);
        status.setText(text);
    }

    private FxJobs newJob() {
        Settings s = engine.settings;
        if (s.host.trim().isEmpty()) {
            toast("Впишите IP пульта в настройках главного экрана");
            return null;
        }
        return new FxJobs(s.host.trim(), s.port > 0 ? s.port : 30000, s.user.trim(), s.password);
    }

    private void pull() {
        commitFields();
        final FxJobs j = newJob();
        if (j == null) return;
        job = j;
        setBusy(true, "читаю пульт…");
        new Thread(new Runnable() {
            @Override
            public void run() {
                String msg;
                try {
                    final List<Patch.Group> got = j.pull(out);
                    ui.post(new Runnable() {
                        @Override
                        public void run() { mergeGroups(got); }
                    });
                    msg = "групп с пульта: " + got.size();
                } catch (Exception e) {
                    out.log("Не прочитал пульт: " + e.getMessage(), true);
                    msg = "нет связи с пультом";
                }
                final String m = msg;
                ui.post(new Runnable() {
                    @Override
                    public void run() {
                        job = null;
                        setBusy(false, m);
                    }
                });
            }
        }, "fx-pull").start();
    }

    /** группы с пульта: новые добавляются, у известных обновляются имя и тип, свои правки остаются */
    private void mergeGroups(List<Patch.Group> got) {
        Map<Long, Map<String, Object>> byId = new LinkedHashMap<>();
        for (Object o : groups()) {
            Map<String, Object> g = (Map<String, Object>) o;
            byId.put(Py.toLong(g.get("id")), g);
        }
        List<Object> out = new ArrayList<>();
        for (Patch.Group p : got) {
            Map<String, Object> g = byId.remove(p.id);
            if (g == null) {
                g = new LinkedHashMap<>();
                g.put("id", p.id);
                g.put("caps", new ArrayList<Object>(p.caps));
                g.put("size", 20L);
                g.put("use", true);
            }
            g.put("name", p.name);
            g.put("type", p.type);
            g.put("how", p.how);
            if (p.count > 0) g.put("count", (long) p.count);
            out.add(g);
        }
        for (Map<String, Object> g : byId.values()) {        // на пульте больше нет - оставляем, но не берём
            g.put("use", false);
            g.put("how", "нет на пульте");
            out.add(g);
        }
        st.put("groups", out);
        renderGroups();
        saveSoon();
    }

    private void confirmSend() {
        commitFields();
        Map<String, Object> cfg = config();
        if (cfg == null) {
            toast("Проверьте числа в настройках");
            return;
        }
        StringBuilder note = new StringBuilder();
        final FxGen.Result r = build(cfg, note);
        if (r == null || r.report.isEmpty()) {
            toast("Нечего отправлять: нет групп или шаблонов");
            return;
        }
        final FxJobs j = newJob();
        if (j == null) return;
        double delay = 0.12;
        try { delay = Double.parseDouble(opt("delay", "0.12").replace(',', '.')); } catch (NumberFormatException ignored) { }
        final double d = delay;
        final Map<String, Object> c = cfg;
        new AlertDialog.Builder(this)
                .setTitle("Создать на пульте")
                .setMessage("Создать " + r.report.size() + " эффектов (" + r.cmds.size() + " команд, ~"
                        + Math.max(1, Math.round(r.cmds.size() * (delay + 0.06) / 60)) + " мин) на " + engine.settings.host
                        + "?\n\nЭффекты и макросы с этими номерами перезапишутся. Автопилот на это время замолчит.")
                .setPositiveButton("Создать", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface di, int w) { send(j, r, c, d); }
                })
                .setNegativeButton("Отмена", null)
                .show();
    }

    private void send(final FxJobs j, final FxGen.Result r, final Map<String, Object> cfg, final double delay) {
        job = j;
        setBusy(true, "отправляю…");
        engine.ma.paused = true;
        engine.genBusy = true;
        for (String w : r.warnings) out.log("⚠ " + w, false);
        out.log("Отправка на " + engine.settings.host + " - " + r.cmds.size() + " команд", false);
        new Thread(new Runnable() {
            @Override
            public void run() {
                String msg;
                try {
                    int errors = j.send(new ArrayList<>(r.cmds), cfg, delay, out);
                    msg = j.stop ? "остановлено" : "готово, ошибок " + errors;
                    out.log("Готово. Эффектов " + r.report.size() + ", ошибок: " + errors, errors > 0);
                } catch (Exception e) {
                    msg = "отправка прервана";
                    out.log("Отправка прервана: " + e.getMessage(), true);
                } finally {
                    engine.ma.paused = false;
                    engine.genBusy = false;
                    Director dr = engine.director;
                    if (dr != null) {
                        dr.forgetState();
                        dr.resetSent();
                    }
                }
                final String m = msg;
                ui.post(new Runnable() {
                    @Override
                    public void run() {
                        job = null;
                        setBusy(false, m);
                    }
                });
            }
        }, "fx-send").start();
    }

    @Override
    public void onBackPressed() {
        if (job != null) {
            toast("Идёт работа с пультом - сначала «Стоп»");
            return;
        }
        super.onBackPressed();
    }
}
