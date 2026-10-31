package com.yan.malight;

import android.Manifest;
import android.app.Activity;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.view.inputmethod.EditorInfo;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import com.yan.malight.core.Analyzer;
import com.yan.malight.core.Director;
import com.yan.malight.core.Settings;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class MainActivity extends BaseActivity {


    private Engine engine;
    private final Handler ui = new Handler();

    private TextView audioLine, maLine, bpmText, barText, autoText, colorText, posText, speedText, logText;
    private MeterView meter;
    private Button listenBtn, maBtn;
    private final Map<String, Button> modeBtns = new LinkedHashMap<>(), holdBtns = new LinkedHashMap<>(),
            toggles = new LinkedHashMap<>();
    private final Map<String, EditText> fields = new LinkedHashMap<>();
    private LinearLayout settingsBox;
    private EditText cmdField;
    private boolean wantListen;

    // ------------------------------------------------------------------ экран
    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        engine = Engine.get(this);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        getWindow().setStatusBarColor(BG);
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_HIDDEN);

        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(BG);
        LinearLayout root = column();
        root.setPadding(px(12), px(10), px(12), px(24));
        scroll.addView(root);
        setContentView(scroll);

        TextView by = text(12, DIM);
        by.setText("Ian Konsta presents");
        root.addView(by);
        TextView title = text(26, TEXT);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        android.text.SpannableString ts = new android.text.SpannableString("LightDancer");
        ts.setSpan(new android.text.style.ForegroundColorSpan(0xfff032a8), 5, 11, 0);
        title.setText(ts);
        root.addView(title);
        audioLine = text(13, DIM);
        maLine = text(13, DIM);
        root.addView(audioLine);
        root.addView(maLine);

        // темп и доли
        LinearLayout head = card(root);
        bpmText = text(46, TEXT);
        bpmText.setTypeface(Typeface.DEFAULT_BOLD);
        bpmText.setGravity(Gravity.CENTER);
        head.addView(bpmText);
        barText = text(15, DIM);
        barText.setGravity(Gravity.CENTER);
        head.addView(barText);
        meter = new MeterView(this);
        head.addView(meter);

        // главные кнопки
        LinearLayout r1 = row(root);
        listenBtn = button(r1, "▶ Слушать", new View.OnClickListener() { @Override public void onClick(View v) { toggleListen(); } });
        maBtn = button(r1, "Пульт", new View.OnClickListener() { @Override public void onClick(View v) { toggleMa(); } });
        LinearLayout r2 = row(root);
        button(r2, "TAP", new View.OnClickListener() { @Override public void onClick(View v) { engine.tap(); } }).setTextSize(18);
        Button stop = button(r2, "■ Стоп всё", new View.OnClickListener() { @Override public void onClick(View v) { stopAll(); } });
        tint(stop, 0xff8e1b1b);

        LinearLayout r3 = row(root);
        Button gen = button(r3, "🎛 Генератор эффектов MA2", new View.OnClickListener() { @Override public void onClick(View v) {
            startActivity(new android.content.Intent(MainActivity.this, GeneratorActivity.class));
        } });
        tint(gen, 0xff37474f);

        // что делает автопилот
        LinearLayout info = card(root);
        autoText = text(15, TEXT);
        colorText = text(14, DIM);
        posText = text(14, DIM);
        speedText = text(14, DIM);
        info.addView(autoText);
        info.addView(colorText);
        info.addView(posText);
        info.addView(speedText);

        // группа
        root.addView(caption("Эффекты"));
        LinearLayout hold = row(root);
        holdBtn(hold, "", "Авто");
        for (String g : Director.GROUPS) holdBtn(hold, g, g);

        LinearLayout t1 = row(root);
        toggle(t1, "autopilot", "Автопилот");
        toggle(t1, "chaseOn", "Круг");
        toggle(t1, "fillOn", "Заливка");
        LinearLayout t2 = row(root);
        toggle(t2, "fxColor", "Цвет");
        toggle(t2, "colorPair", "Пары");
        toggle(t2, "fxMove", "Позиции");

        // темп в speed-мастера
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
        button(m3, "Темп заново", new View.OnClickListener() { @Override public void onClick(View v) {
            Director d = engine.director;
            if (d != null) d.pushBpm(true);
        } });

        // команда вручную
        root.addView(caption("Команда на пульт"));
        LinearLayout c = row(root);
        cmdField = new EditText(this);
        cmdField.setSingleLine(true);
        cmdField.setTextColor(TEXT);
        cmdField.setHintTextColor(DIM);
        cmdField.setHint("Go Executor 10.1");
        cmdField.setImeOptions(EditorInfo.IME_ACTION_SEND);
        cmdField.setOnEditorActionListener(new TextView.OnEditorActionListener() { @Override public boolean onEditorAction(TextView v, int id, android.view.KeyEvent ev) { sendCmd(); return true; } });
        c.addView(cmdField, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 3));
        button(c, "Отправить", new View.OnClickListener() { @Override public void onClick(View v) { sendCmd(); } });

        // журнал
        root.addView(caption("Журнал"));
        logText = text(12, DIM);
        logText.setTypeface(Typeface.MONOSPACE);
        card(root).addView(logText);

        // настройки
        Button sb = button(row(root), "⚙ Настройки", new View.OnClickListener() { @Override public void onClick(View v) { settingsBox.setVisibility(settingsBox.getVisibility() == View.VISIBLE ? View.GONE : View.VISIBLE); } });
        tint(sb, OFF);
        settingsBox = card(root);
        settingsBox.setVisibility(View.GONE);
        buildSettings();

        refresh.run();
    }

    // ------------------------------------------------------------------ действия
    private void toggleListen() {
        if (engine.listening) {
            wantListen = false;
            EngineService.stop(this);
            return;
        }
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            wantListen = true;
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, 1);
            return;
        }
        EngineService.start(this);
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] perms, int[] res) {
        if (res.length > 0 && res[0] == PackageManager.PERMISSION_GRANTED) {
            if (wantListen) EngineService.start(this);
        } else {
            toast("Без микрофона анализ не работает. Разрешите его в настройках телефона.");
        }
        wantListen = false;
    }

    private void toggleMa() {
        Settings s = engine.settings;
        s.enabled = !s.enabled;
        engine.save();
        engine.applyConnection();
        engine.log(s.enabled ? "пульт включён: " + s.host : "пульт выключен");
    }

    private void stopAll() {
        Director d = engine.director;
        if (!engine.settings.enabled) { toast("Пульт выключен"); return; }
        if (d != null) d.stopAll();
        engine.log("Стоп всё: Off Executor " + engine.settings.page + ".1 Thru " + engine.settings.page + ".50");
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
    }

    private void sendCmd() {
        String cmd = cmdField.getText().toString().trim();
        if (cmd.isEmpty()) return;
        if (!engine.settings.enabled) { toast("Сначала включите пульт"); return; }
        engine.ma.send(cmd, null);
        cmdField.setText("");
    }

    // ------------------------------------------------------------------ настройки
    private static final String[][] FIELDS = {
            {"host", "IP пульта", "t"}, {"port", "Порт Telnet", "n"}, {"user", "Логин", "t"}, {"password", "Пароль", "t"},
            {"page", "Страница экзекьюторов", "n"},
            {"gain", "Чувствительность входа (1 = обычная)", "d"},
            {"leadMs", "Опережение долей, мс (задержка сети)", "n"},
            {"bpmDiv", "Делитель темпа", "n"},
            {"smDimmer", "Speed-мастер диммера", "n"}, {"xDimmer", "  множитель", "d"},
            {"smPosition", "Speed-мастер позиций", "n"}, {"xPosition", "  множитель", "d"},
            {"smColor", "Speed-мастер цвета", "n"}, {"xColor", "  множитель", "d"},
            {"smStrobe", "Speed-мастер строба", "n"}, {"xStrobe", "  множитель", "d"},
            {"bpmManual", "Ручной темп, BPM", "d"},
            {"posSmooth", "Плавность позиций, с", "d"},
            {"fillBase", "Заливка: база %", "n"}, {"fillPeak", "Заливка: пик %", "n"},
            {"execPulse", "Свои экзекьюторы «пульс» (через пробел)", "t"},
            {"execRun", "Свои экзекьюторы «бег»", "t"},
            {"execFlow", "Свои экзекьюторы «поток»", "t"},
            {"execSpark", "Свои экзекьюторы «искры»", "t"},
    };

    private void buildSettings() {
        TextView hint = text(13, DIM);
        hint.setText("Пустые «свои экзекьюторы» = раскладка анализатора: пульс " + "page.1-3, бег 4-6, поток 7-9, искры 10-12, "
                + "круг 13-14, заливка 15, цвета 16-27, позиции 30, пары 31-42.");
        settingsBox.addView(hint);
        for (String[] f : FIELDS) {
            TextView l = text(13, DIM);
            l.setText(f[1]);
            l.setPadding(0, px(8), 0, 0);
            settingsBox.addView(l);
            EditText e = new EditText(this);
            e.setSingleLine(true);
            e.setTextColor(TEXT);
            e.setInputType(f[2].equals("n") ? InputType.TYPE_CLASS_NUMBER
                    : f[2].equals("d") ? InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL
                    : f[0].equals("password") ? InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD
                    : InputType.TYPE_CLASS_TEXT);
            if (f[0].equals("host")) e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
            settingsBox.addView(e);
            fields.put(f[0], e);
        }
        LinearLayout r = row(settingsBox);
        button(r, "Сохранить", new View.OnClickListener() { @Override public void onClick(View v) { saveSettings(); } });
        Button reset = button(r, "Как было", new View.OnClickListener() { @Override public void onClick(View v) { fillSettings(); } });
        tint(reset, OFF);
        fillSettings();
    }

    private void fillSettings() {
        for (Map.Entry<String, EditText> f : fields.entrySet()) f.getValue().setText(engine.settings.get(f.getKey()));
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

    // ------------------------------------------------------------------ обновление экрана
    private final Runnable refresh = new Runnable() {
        @Override
        public void run() {
            update();
            ui.postDelayed(this, 50);
        }
    };

    private int logStamp = -1;

    private void update() {
        Settings s = engine.settings;
        Analyzer a = engine.analyzer;
        Director d = engine.director;
        boolean listen = engine.listening;

        audioLine.setText("🎤 " + engine.audioStatus + (listen && a != null && !a.sound ? " · тишина" : ""));
        maLine.setText("🎛 " + engine.ma.status + (engine.ma.online ? "  · команд " + engine.ma.sent
                + (engine.ma.errors > 0 ? " · ошибок " + engine.ma.errors : "") : ""));
        maLine.setTextColor(engine.ma.online ? 0xff81c784 : s.enabled ? WARN : DIM);

        if (listen && a != null && a.bpm > 0) {
            bpmText.setText(String.format(java.util.Locale.US, "%.1f", a.bpm));
            String sec = a.section == null ? "" : a.section.equals("D") ? "дроп" : a.section.equals("B") ? "брейк" : "середина";
            barText.setText("такт " + a.bar + " · фраза " + a.phrase + (sec.isEmpty() ? "" : " · " + sec));
        } else {
            bpmText.setText("—");
            barText.setText(listen ? "ищу темп…" : "нажмите «Слушать»");
        }
        meter.analyzer = a;
        meter.listening = listen;
        meter.invalidate();

        listenBtn.setText(listen ? "■ Не слушать" : "▶ Слушать");
        tint(listenBtn, listen ? ON : ACCENT);
        maBtn.setText(s.enabled ? "Пульт: вкл" : "Пульт: выкл");
        tint(maBtn, s.enabled ? (engine.ma.online ? ON : 0xff8d6e00) : OFF);

        if (d != null) {
            autoText.setText("Автопилот: " + (s.autopilot ? (d.autoWhy.isEmpty() ? "ждёт музыку" : d.autoWhy) : "выключен")
                    + (d.autoCmd != null ? "  [" + d.autoCmd + "]" : ""));
            colorText.setText("Цвет: " + (s.fxColor ? or(d.colorLast) : "выкл"));
            posText.setText("Позиции: " + (s.fxMove ? or(d.posLast) : "выкл"));
            speedText.setText("Темп: " + (s.bpmOn ? or(d.bpmLast) + (s.bpmMode.equals("manual") ? "  (ручной " + Director_num(s.bpmManual) + ")" : "") : "выкл"));
        }
        for (Map.Entry<String, Button> e : holdBtns.entrySet()) tint(e.getValue(), s.hold.equals(e.getKey()) ? ON : OFF);
        for (Map.Entry<String, Button> e : modeBtns.entrySet()) tint(e.getValue(), s.bpmMode.equals(e.getKey()) ? ON : OFF);
        for (Map.Entry<String, Button> e : toggles.entrySet()) tint(e.getValue(), "true".equals(s.get(e.getKey())) ? ON : OFF);

        List<String> tail = engine.logTail(14);
        int stamp = tail.isEmpty() ? 0 : tail.get(tail.size() - 1).hashCode() ^ tail.size();
        if (stamp != logStamp) {
            logStamp = stamp;
            StringBuilder sb = new StringBuilder();
            for (int i = tail.size() - 1; i >= 0; i--) sb.append(tail.get(i)).append('\n');
            logText.setText(sb.length() == 0 ? "пусто" : sb.toString().trim());
        }
    }

    private static String or(String v) { return v == null || v.isEmpty() ? "—" : v; }

    private static String Director_num(double v) {
        return v == Math.rint(v) ? String.valueOf((long) v) : String.valueOf(v);
    }

    @Override
    protected void onResume() {
        super.onResume();
        ui.removeCallbacks(refresh);
        ui.post(refresh);
    }

    @Override
    protected void onPause() {
        ui.removeCallbacks(refresh);
        super.onPause();
    }

    private void holdBtn(LinearLayout row, final String value, String label) {
        Button b = button(row, label, new View.OnClickListener() { @Override public void onClick(View v) {
            engine.settings.hold = value;
            engine.save();
            engine.log(value.isEmpty() ? "эффекты: авто" : "эффекты: держать «" + value + "»");
        } });
        b.setTextSize(13);
        holdBtns.put(value, b);
    }

    private void modeBtn(LinearLayout row, final String mode, String label) {
        Button b = button(row, label, new View.OnClickListener() { @Override public void onClick(View v) {
            engine.settings.bpmMode = mode;
            engine.save();
            Director d = engine.director;
            if (d != null) d.pushBpm(true);
        } });
        b.setTextSize(13);
        modeBtns.put(mode, b);
    }

    private void toggle(LinearLayout row, final String key, String label) {
        Button b = button(row, label, new View.OnClickListener() { @Override public void onClick(View v) {
            Settings s = engine.settings;
            s.set(key, String.valueOf(!"true".equals(s.get(key))));
            engine.save();
            if (key.equals("bpmOn") && s.bpmOn) {
                Director d = engine.director;
                if (d != null) d.pushBpm(true);
            }
        } });
        b.setTextSize(13);
        toggles.put(key, b);
    }

}
