package com.yan.malight;

import android.os.Bundle;
import android.text.InputType;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import com.yan.malight.core.Director;
import com.yan.malight.core.Settings;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Вкладка Настройки: автопилот, темп в пульт, связь и раскладка. */
public final class SettingsActivity extends BaseActivity {

    private final Map<String, Button> modeBtns = new LinkedHashMap<>(), toggles = new LinkedHashMap<>();
    private final Map<String, EditText> fields = new LinkedHashMap<>();
    private TextView bpmInfo;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        LinearLayout root = shell(3);
        title(root, "LightDancer", "Настройки");

        root.addView(caption("Автопилот"));
        LinearLayout t1 = row(root);
        toggle(t1, "chaseOn", "Круг");
        toggle(t1, "fillOn", "Заливка");
        toggle(t1, "fxMove", "Позиции");
        LinearLayout t2 = row(root);
        toggle(t2, "fxColor", "Цвет");
        toggle(t2, "colorPair", "Пары цветов");
        toggle(t2, "fxgenOn", "Генератор");

        root.addView(caption("Темп в пульт (SpecialMaster 3.x)"));
        LinearLayout m1 = row(root);
        toggle(m1, "bpmOn", "Темп вкл");
        modeBtn(m1, "beat", "По доле");
        modeBtn(m1, "section", "По части");
        LinearLayout m2 = row(root);
        modeBtn(m2, "energy", "По энергии");
        modeBtn(m2, "stop", "Стоп в брейке");
        modeBtn(m2, "manual", "Ручной");
        LinearLayout m3 = row(root);
        button(m3, "−1 BPM", new View.OnClickListener() { @Override public void onClick(View v) { nudge(-1); } });
        button(m3, "+1 BPM", new View.OnClickListener() { @Override public void onClick(View v) { nudge(1); } });
        button(m3, "Заново", new View.OnClickListener() { @Override public void onClick(View v) {
            Director d = engine.director;
            if (d != null) d.pushBpm(true);
        } });
        bpmInfo = text(12, DIM);
        bpmInfo.setPadding(px(2), px(6), 0, 0);
        root.addView(bpmInfo);

        LinearLayout box = null;
        for (String[] f : FIELDS) {
            if (f[2].equals("h")) {
                root.addView(caption(f[1]));
                box = card(root);
                continue;
            }
            EditText e = labeled(box, f[1], f[2].equals("n") || f[2].equals("d"), f[2].equals("d"));
            if (f[0].equals("password")) e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD);
            if (f[0].equals("host")) e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
            fields.put(f[0], e);
        }
        TextView hint = text(12, DIM);
        hint.setText("Пустые «свои экзекьюторы» = раскладка анализатора: пульс page.1-3, бег 4-6, поток 7-9, искры 10-12, "
                + "круг 13-14, заливка 15, цвета 16-27, позиции 30, пары 31-42. Эффекты генератора - страницы "
                + "«Генератор: первая страница» … +4.");
        hint.setPadding(px(2), px(10), 0, 0);
        root.addView(hint);
        LinearLayout r = row(root);
        tint(button(r, "Сохранить", new View.OnClickListener() { @Override public void onClick(View v) { saveSettings(); } }), ACCENT);
        button(r, "Как было", new View.OnClickListener() { @Override public void onClick(View v) { fillSettings(); } });
        fillSettings();
    }

    private static final String[][] FIELDS = {
            {"", "Связь с пультом", "h"},
            {"host", "IP пульта", "t"}, {"port", "Порт Telnet", "n"}, {"user", "Логин", "t"}, {"password", "Пароль", "t"},
            {"", "Звук", "h"},
            {"gain", "Чувствительность (1 = обычная)", "d"},
            {"leadMs", "Опережение долей, мс", "n"},
            {"", "Раскладка", "h"},
            {"page", "Страница стандартных эффектов", "n"},
            {"fxgenPage", "Генератор: первая страница", "n"},
            {"execPulse", "Свои экзекьюторы «пульс»", "t"},
            {"execRun", "Свои «бег»", "t"},
            {"execFlow", "Свои «поток»", "t"},
            {"execSpark", "Свои «искры»", "t"},
            {"posSmooth", "Плавность позиций, с", "d"},
            {"fillBase", "Заливка: база %", "n"}, {"fillPeak", "Заливка: пик %", "n"},
            {"", "Темп: мастера и множители", "h"},
            {"bpmDiv", "Делитель темпа", "n"},
            {"bpmManual", "Ручной темп, BPM", "d"},
            {"smDimmer", "Мастер диммера", "n"}, {"xDimmer", "  множитель", "d"},
            {"smPosition", "Мастер позиций", "n"}, {"xPosition", "  множитель", "d"},
            {"smColor", "Мастер цвета", "n"}, {"xColor", "  множитель", "d"},
            {"smStrobe", "Мастер строба", "n"}, {"xStrobe", "  множитель", "d"},
    };

    private void fillSettings() {
        for (Map.Entry<String, EditText> f : fields.entrySet()) f.getValue().setText(engine.settings.get(f.getKey()));
        paint();
    }

    private void saveSettings() {
        List<String> bad = new ArrayList<>();
        for (Map.Entry<String, EditText> f : fields.entrySet()) {
            if (!engine.settings.set(f.getKey(), f.getValue().getText().toString())) bad.add(f.getKey());
        }
        engine.save();
        engine.applyConnection();
        fillSettings();
        toast(bad.isEmpty() ? "Сохранено" : "Не разобрал: " + bad);
    }

    private void nudge(int delta) {
        Settings s = engine.settings;
        double base = s.bpmMode.equals("manual") ? s.bpmManual : engine.analyzer != null && engine.analyzer.bpm > 0
                ? Math.round(engine.analyzer.bpm) : s.bpmManual;
        s.bpmManual = Math.max(40, Math.min(300, base + delta));
        s.bpmMode = "manual";
        engine.save();
        Director d = engine.director;
        if (d != null) d.pushBpm(true);
        EditText f = fields.get("bpmManual");
        if (f != null) f.setText(s.get("bpmManual"));
        paint();
    }

    private void paint() {
        Settings s = engine.settings;
        for (Map.Entry<String, Button> e : modeBtns.entrySet()) tint(e.getValue(), s.bpmMode.equals(e.getKey()) ? ON : OFF);
        for (Map.Entry<String, Button> e : toggles.entrySet()) tint(e.getValue(), "true".equals(s.get(e.getKey())) ? ON : OFF);
        Director d = engine.director;
        bpmInfo.setText(s.bpmMode.equals("manual") ? "Ручной темп " + s.get("bpmManual") + " BPM" + (d != null && !d.bpmLast.isEmpty() ? " · " + d.bpmLast : "")
                : d != null && !d.bpmLast.isEmpty() ? d.bpmLast : "");
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (bpmInfo != null) paint();
    }

    private void modeBtn(LinearLayout row, final String mode, String label) {
        Button b = button(row, label, new View.OnClickListener() { @Override public void onClick(View v) {
            engine.settings.bpmMode = mode;
            engine.save();
            Director d = engine.director;
            if (d != null) d.pushBpm(true);
            paint();
        } });
        b.setTextSize(13);
        modeBtns.put(mode, b);
    }

    private void toggle(LinearLayout row, final String key, String label) {
        Button b = button(row, label, new View.OnClickListener() { @Override public void onClick(View v) {
            Settings s = engine.settings;
            if (key.equals("fxgenOn") && !s.fxgenOn && s.fxgenAssigned.trim().isEmpty()) {
                toast("Сначала вкладка Эффекты: «Создать на пульте» и «На экзекьюторы»");
                return;
            }
            s.set(key, String.valueOf(!"true".equals(s.get(key))));
            engine.save();
            Director d = engine.director;
            if (key.equals("bpmOn") && s.bpmOn && d != null) d.pushBpm(true);
            if (key.equals("fxgenOn") && d != null) d.forgetState();
            paint();
        } });
        b.setTextSize(13);
        toggles.put(key, b);
    }
}
