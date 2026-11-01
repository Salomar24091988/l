package com.yan.malight;

import android.Manifest;
import android.content.pm.PackageManager;
import android.graphics.Typeface;
import android.os.Bundle;
import android.os.Handler;
import android.text.SpannableString;
import android.text.style.StyleSpan;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import com.yan.malight.core.Analyzer;
import com.yan.malight.core.Director;
import com.yan.malight.core.Settings;

import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

/** Вкладка Live: кольцо, темп, уровни, спектр, что играет автопилот. */
public final class MainActivity extends BaseActivity {

    private final Handler ui = new Handler();
    private TextView maPill, bpmText, barText, autoHead, autoText, colorText, posText, speedText, micText;
    private final TextView[] stat = new TextView[4];
    private LiveViews.Ring ring;
    private LiveViews.Beats beats;
    private LiveViews.Spectrum spectrum;
    private Button listenBtn;
    private final Map<String, Button> holdBtns = new LinkedHashMap<>();
    private boolean wantListen;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        LinearLayout root = shell(0);

        // шапка
        LinearLayout head = new LinearLayout(this);
        head.setOrientation(LinearLayout.HORIZONTAL);
        head.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout brand = column();
        TextView by = text(10, DIM);
        by.setText("IAN KONSTA PRESENTS");
        by.setLetterSpacing(0.3f);
        brand.addView(by);
        TextView title = text(30, Hud.WHITE);
        title.setTypeface(Typeface.create("sans-serif-light", Typeface.ITALIC));
        SpannableString ts = new SpannableString("LightDancer");
        ts.setSpan(new StyleSpan(Typeface.BOLD_ITALIC), 5, 11, 0);
        title.setText(ts);
        title.setShadowLayer(14 * dp, 0, 0, 0x889cc4f0);
        brand.addView(title);
        head.addView(brand, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        maPill = text(12, Hud.DIM);
        maPill.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        maPill.setPadding(px(12), px(8), px(12), px(8));
        maPill.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { openTab(2); } });
        head.addView(maPill);
        root.addView(head);

        // кольцо
        ring = new LiveViews.Ring(this);
        root.addView(ring);

        // темп
        LinearLayout tempo = card(root);
        LinearLayout tr = new LinearLayout(this);
        tr.setOrientation(LinearLayout.HORIZONTAL);
        tr.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout tl = column();
        LinearLayout bpmRow = new LinearLayout(this);
        bpmRow.setGravity(Gravity.BOTTOM);
        bpmText = text(40, Hud.WHITE);
        bpmText.setTypeface(Typeface.create("sans-serif-condensed", Typeface.BOLD));
        bpmText.setIncludeFontPadding(false);
        bpmRow.addView(bpmText);
        barText = text(13, DIM);
        barText.setPadding(px(10), 0, 0, px(5));
        bpmRow.addView(barText);
        tl.addView(bpmRow);
        beats = new LiveViews.Beats(this);
        LinearLayout.LayoutParams blp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        blp.topMargin = px(6);
        tl.addView(beats, blp);
        tr.addView(tl, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        listenBtn = new Button(this);
        listenBtn.setStateListAnimator(null);
        listenBtn.setMinWidth(0);
        listenBtn.setMinimumWidth(0);
        listenBtn.setMinHeight(0);
        listenBtn.setMinimumHeight(0);
        listenBtn.setTextSize(13);
        listenBtn.setAllCaps(false);
        listenBtn.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { toggleListen(); } });
        LinearLayout.LayoutParams llp = new LinearLayout.LayoutParams(px(104), px(56));
        llp.leftMargin = px(14);
        tr.addView(listenBtn, llp);
        tempo.addView(tr);
        micText = text(12, DIM);
        micText.setPadding(0, px(6), 0, 0);
        tempo.addView(micText);

        // уровни
        LinearLayout tiles = row(root);
        String[] names = {"Бас", "Мид", "Верх", "Громкость"};
        for (int i = 0; i < 4; i++) {
            LinearLayout t = column();
            t.setGravity(Gravity.CENTER);
            t.setBackground(panel(Hud.PANEL, 0x479cc4f0, 10, 0));
            t.setPadding(0, px(10), 0, px(10));
            TextView n = text(11, DIM);
            n.setText(names[i]);
            t.addView(n);
            stat[i] = text(22, i == 3 ? Hud.WHITE : Hud.ICE_LIGHT);
            stat[i].setTypeface(Typeface.create("sans-serif-condensed", Typeface.BOLD));
            t.addView(stat[i]);
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
            lp.leftMargin = i == 0 ? 0 : px(8);
            tiles.addView(t, lp);
        }

        // какие эффекты держать
        root.addView(caption("Эффекты"));
        LinearLayout hold = row(root);
        holdBtn(hold, "", "Авто");
        for (String g : Director.GROUPS) holdBtn(hold, g, g.substring(0, 1).toUpperCase() + g.substring(1));

        // спектр
        spectrum = new LiveViews.Spectrum(this);
        LinearLayout.LayoutParams slp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        slp.topMargin = px(14);
        root.addView(spectrum, slp);

        // автопилот
        LinearLayout info = card(root);
        autoHead = text(12, DIM);
        autoHead.setLetterSpacing(0.1f);
        autoHead.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        info.addView(autoHead);
        autoText = text(17, Hud.WHITE);
        autoText.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        autoText.setPadding(0, px(4), 0, px(4));
        info.addView(autoText);
        colorText = text(13, DIM);
        posText = text(13, DIM);
        speedText = text(13, DIM);
        info.addView(colorText);
        info.addView(posText);
        info.addView(speedText);

        // кнопки
        LinearLayout r2 = row(root);
        Button tap = button(r2, "TAP", new View.OnClickListener() { @Override public void onClick(View v) { engine.tap(); } });
        tap.setTextSize(17);
        tint(tap, ACCENT);
        Button stop = button(r2, "Стоп всё", new View.OnClickListener() { @Override public void onClick(View v) { stopAll(); } });
        tint(stop, DANGER);

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

    private void stopAll() {
        Director d = engine.director;
        if (!engine.settings.enabled) { toast("Пульт выключен"); return; }
        if (d != null) d.stopAll();
        engine.log("Стоп всё");
    }

    private void holdBtn(LinearLayout row, final String value, String label) {
        Button b = button(row, label, new View.OnClickListener() { @Override public void onClick(View v) {
            engine.settings.hold = value;
            engine.save();
            engine.log(value.isEmpty() ? "эффекты: авто" : "эффекты: держать «" + value + "»");
        } });
        b.setTextSize(12);
        b.setPadding(0, 0, 0, 0);
        b.setMinHeight(px(44));
        b.setMinimumHeight(px(44));
        holdBtns.put(value, b);
    }

    // ------------------------------------------------------------------ обновление
    private final Runnable refresh = new Runnable() {
        @Override
        public void run() {
            update();
            ui.postDelayed(this, 80);
        }
    };

    private String lastPill = "";

    private void update() {
        Settings s = engine.settings;
        Analyzer a = engine.analyzer;
        Director d = engine.director;
        boolean listen = engine.listening;
        ring.analyzer = a;
        ring.listening = listen;
        beats.analyzer = a;
        beats.listening = listen;
        spectrum.analyzer = a;
        spectrum.listening = listen;

        String pill = !s.enabled ? "MA2 выкл" : engine.ma.online ? "MA2 онлайн" : "MA2 связь…";
        if (!pill.equals(lastPill)) {
            lastPill = pill;
            int col = !s.enabled ? Hud.DIM : engine.ma.online ? Hud.GREEN : Hud.AMBER;
            maPill.setText("●  " + pill);
            maPill.setTextColor(col);
            maPill.setBackground(panel(Hud.alpha(col, 0.12f), Hud.alpha(col, 0.5f), 8, 0));
        }

        if (listen && a != null && a.bpm > 0) {
            bpmText.setText(String.format(Locale.US, "%.0f", a.bpm));
            String sec = a.section == null ? "" : a.section.equals("D") ? "дроп" : a.section.equals("B") ? "брейк" : "середина";
            barText.setText("BPM · такт " + a.bar + (sec.isEmpty() ? "" : " · " + sec));
        } else {
            bpmText.setText("—");
            barText.setText(listen ? "ищу темп…" : "BPM");
        }
        micText.setText(engine.audioStatus + (listen && a != null && !a.sound ? " · тишина" : ""));
        listenBtn.setText(listen ? "Слушаю" : "Слушать");
        if (!Integer.valueOf(listen ? 1 : 2).equals(listenBtn.getTag())) {
            listenBtn.setTag(listen ? 1 : 2);
            if (listen) listenBtn.setLayerType(View.LAYER_TYPE_SOFTWARE, null);
            listenBtn.setBackground(new Hud.Chamfer(listen ? 0x24ffffff : 0x1f9cc4f0, listen ? Hud.WHITE : Hud.ICE,
                    px(10), px(2), px(listen ? 8 : 0), false));
            listenBtn.setTextColor(listen ? Hud.WHITE : Hud.ICE_LIGHT);
        }

        float[] v = new float[4];
        if (a != null && listen) {
            v[0] = Math.max(a.bands[0], a.bands[1]);
            v[1] = Math.max(a.bands[2], a.bands[3]);
            v[2] = Math.max(a.bands[4], a.bands[5]);
            v[3] = Math.min(1, a.level);
        }
        for (int i = 0; i < 4; i++) stat[i].setText(String.format(Locale.US, "%.2f", v[i]));

        if (d != null) {
            boolean gen = d.genActive();
            autoHead.setText(("Автопилот · " + (!s.autopilot ? "пауза" : gen ? "эффекты генератора" : "стандарт " + s.page + ".x")).toUpperCase());
            autoText.setText(!s.autopilot ? "на паузе: нажмите кнопку в центре внизу"
                    : (d.autoWhy.isEmpty() ? "ждёт музыку" : d.autoWhy));
            colorText.setText("Цвет: " + (s.fxColor ? or(d.colorLast) : "выкл"));
            posText.setText("Позиции: " + (s.fxMove ? or(d.posLast) : "выкл"));
            speedText.setText("Темп: " + (s.bpmOn ? or(d.bpmLast) : "выкл"));
        }
        for (Map.Entry<String, Button> e : holdBtns.entrySet()) tint(e.getValue(), s.hold.equals(e.getKey()) ? ON : OFF);
        if (nav != null && nav.centerOn != s.autopilot) {
            nav.centerOn = s.autopilot;
            nav.invalidate();
        }
    }

    static String or(String v) { return v == null || v.isEmpty() ? "—" : v; }

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
}
