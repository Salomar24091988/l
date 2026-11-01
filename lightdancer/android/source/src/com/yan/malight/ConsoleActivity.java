package com.yan.malight;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Typeface;
import android.os.Bundle;
import android.os.Handler;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.inputmethod.EditorInfo;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import com.yan.malight.core.Director;
import com.yan.malight.core.FxLink;
import com.yan.malight.core.Json;
import com.yan.malight.core.Settings;

import java.util.ArrayList;
import java.util.List;

/** Вкладка Пульт: связь, что играет автопилот, экзекьюторы 11-15, команда вручную, журнал. */
public final class ConsoleActivity extends BaseActivity {

    private final Handler ui = new Handler();
    private View dot;
    private TextView connTitle, connSub, genNote, logText;
    private Button connBtn, genBtn, stdBtn;
    private ExecGrid grid;
    private EditText cmdField;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        LinearLayout root = shell(2);
        title(root, "grandMA2 · Telnet", "Пульт");

        // связь
        LinearLayout conn = card(root);
        LinearLayout cr = new LinearLayout(this);
        cr.setGravity(Gravity.CENTER_VERTICAL);
        dot = new View(this);
        cr.addView(dot, new LinearLayout.LayoutParams(px(12), px(12)));
        LinearLayout ct = column();
        ct.setPadding(px(12), 0, 0, 0);
        connTitle = text(16, TEXT);
        connTitle.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        connSub = text(12, DIM);
        connSub.setTypeface(Typeface.MONOSPACE);
        ct.addView(connTitle);
        ct.addView(connSub);
        cr.addView(ct, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        conn.addView(cr);
        LinearLayout cb = row(conn);
        connBtn = button(cb, "", new View.OnClickListener() { @Override public void onClick(View v) { toggleMa(); } });
        button(cb, "Изменить", new View.OnClickListener() { @Override public void onClick(View v) { openTab(3); } });

        // что играет автопилот
        root.addView(caption("Что играет автопилот"));
        LinearLayout src = row(root);
        genBtn = button(src, "Эффекты генератора", new View.OnClickListener() { @Override public void onClick(View v) { setGen(true); } });
        stdBtn = button(src, "Стандарт", new View.OnClickListener() { @Override public void onClick(View v) { setGen(false); } });
        genNote = text(12, DIM);
        genNote.setPadding(px(2), px(6), 0, 0);
        root.addView(genNote);

        // экзекьюторы
        root.addView(caption("Экзекьюторы"));
        LinearLayout gc = card(root);
        grid = new ExecGrid(this);
        gc.addView(grid);

        // команда
        root.addView(caption("Команда на пульт"));
        LinearLayout c = row(root);
        cmdField = field(false, false);
        cmdField.setHint("Go Executor 11.1");
        cmdField.setImeOptions(EditorInfo.IME_ACTION_SEND);
        cmdField.setOnEditorActionListener(new TextView.OnEditorActionListener() {
            @Override
            public boolean onEditorAction(TextView v, int id, android.view.KeyEvent ev) {
                sendCmd();
                return true;
            }
        });
        c.addView(cmdField, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 2));
        tint(button(c, "Отправить", new View.OnClickListener() { @Override public void onClick(View v) { sendCmd(); } }), ACCENT);

        // журнал
        root.addView(caption("Журнал"));
        LinearLayout lc = card(root);
        lc.setBackground(panel(0xb3000000, Hud.LINE_SOFT, 10, 0));
        logText = text(11, 0xffa9c6d0);
        logText.setTypeface(Typeface.MONOSPACE);
        lc.addView(logText);
    }

    private void toggleMa() {
        Settings s = engine.settings;
        s.enabled = !s.enabled;
        engine.save();
        engine.applyConnection();
        engine.log(s.enabled ? "пульт включён: " + s.host : "пульт выключен");
    }

    private void setGen(boolean on) {
        Settings s = engine.settings;
        if (on && s.fxgenAssigned.trim().isEmpty()) {
            toast("Сначала вкладка Эффекты: «Создать на пульте» и «На экзекьюторы»");
            return;
        }
        if (s.fxgenOn == on) return;
        Director d = engine.director;
        String old = d != null ? d.autoCmd : null;
        s.fxgenOn = on;
        engine.save();
        if (d != null) {
            if (old != null && s.enabled) engine.ma.send("Off Executor " + old.replace("-", " Thru "), null);
            d.forgetState();
        }
        engine.log(on ? "автопилот: эффекты генератора" : "автопилот: стандартные эффекты " + s.page + ".1-12");
    }

    private void sendCmd() {
        String cmd = cmdField.getText().toString().trim();
        if (cmd.isEmpty()) return;
        if (!engine.settings.enabled) { toast("Сначала включите пульт"); return; }
        engine.ma.send(cmd, null);
        engine.log("» " + cmd);
        cmdField.setText("");
    }

    private final Runnable refresh = new Runnable() {
        @Override
        public void run() {
            update();
            ui.postDelayed(this, 250);
        }
    };

    private int logStamp = -1;
    private int lastDot;

    private void update() {
        Settings s = engine.settings;
        int col = !s.enabled ? Hud.DIM : engine.ma.online ? Hud.GREEN : Hud.AMBER;
        if (col != lastDot) {
            lastDot = col;
            android.graphics.drawable.GradientDrawable g = new android.graphics.drawable.GradientDrawable();
            g.setShape(android.graphics.drawable.GradientDrawable.OVAL);
            g.setColor(col);
            dot.setBackground(g);
        }
        connTitle.setText(!s.enabled ? "Пульт выключен" : engine.ma.online ? "Подключено" : "Подключаюсь…");
        connSub.setText(s.host + " · " + s.user + (engine.ma.online ? " · команд " + engine.ma.sent
                + (engine.ma.errors > 0 ? " · ошибок " + engine.ma.errors : "") : "") + "\n" + engine.ma.status);
        connBtn.setText(s.enabled ? "Выключить" : "Включить");
        tint(connBtn, s.enabled ? (engine.ma.online ? ON : BUSY) : ACCENT);

        Director d = engine.director;
        boolean has = !s.fxgenAssigned.trim().isEmpty();
        tint(genBtn, s.fxgenOn && has ? ON : OFF);
        tint(stdBtn, s.fxgenOn && has ? OFF : ON);
        stdBtn.setText("Стандарт " + s.page + ".x");
        genNote.setText(!has ? "Эффекты генератора ещё не поставлены на экзекьюторы (вкладка Эффекты)."
                : s.fxgenOn ? "Пульс ← Dimmer, бег ← Position, поток ← Color, искры ← Strobe. Круг, цвет, позиции и заливка - как раньше."
                : "Автопилот играет свои эффекты " + s.page + ".1-12.");
        grid.update(s, d != null ? d.autoCmd : null);

        List<String> tail = engine.logTail(12);
        int stamp = tail.isEmpty() ? 0 : tail.get(tail.size() - 1).hashCode() ^ tail.size();
        if (stamp != logStamp) {
            logStamp = stamp;
            StringBuilder sb = new StringBuilder();
            for (int i = tail.size() - 1; i >= 0; i--) sb.append(tail.get(i)).append('\n');
            logText.setText(sb.length() == 0 ? "пусто" : sb.toString().trim());
        }
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

    /** страницы генератора: занятые экзекьюторы, горящие - те, что включил автопилот */
    static final class ExecGrid extends View {
        private final float dp;
        private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        private int page = 11;
        private int[] used = new int[5];
        private int litPage = -1, litFrom, litTo;
        private String src = "";

        ExecGrid(Context c) {
            super(c);
            dp = c.getResources().getDisplayMetrics().density;
            setLayerType(LAYER_TYPE_SOFTWARE, null);
        }

        @SuppressWarnings("unchecked")
        void update(Settings s, String auto) {
            page = s.fxgenPage > 0 ? s.fxgenPage : 11;
            if (!s.fxgenAssigned.equals(src)) {
                src = s.fxgenAssigned;
                used = new int[5];
                try {
                    Object o = src.trim().isEmpty() ? null : Json.parse(src);
                    if (o instanceof List) used = FxLink.usedPerPage((List<Object>) o, page);
                } catch (RuntimeException ignored) {
                }
            }
            litPage = -1;
            if (auto != null && auto.matches("\\d+\\.\\d+(-\\d+\\.\\d+)?")) {
                String[] ab = auto.split("-");
                String[] a = ab[0].split("\\."), z = ab[ab.length - 1].split("\\.");
                litPage = Integer.parseInt(a[0]);
                litFrom = Integer.parseInt(a[1]);
                litTo = Integer.parseInt(z[1]);
            }
            invalidate();
        }

        @Override
        protected void onMeasure(int w, int h) {
            setMeasuredDimension(MeasureSpec.getSize(w), (int) (5 * 40 * dp));
        }

        @Override
        protected void onDraw(Canvas c) {
            float rowH = 40 * dp, labelW = 78 * dp, w = getWidth();
            for (int r = 0; r < 5; r++) {
                float y = r * rowH;
                int pg = page + r;
                p.clearShadowLayer();
                p.setTypeface(Typeface.create("sans-serif-condensed", Typeface.BOLD));
                p.setTextSize(17 * dp);
                p.setColor(pg == litPage ? Hud.ORANGE : Hud.ICE_LIGHT);
                c.drawText(String.valueOf(pg), 0, y + 18 * dp, p);
                p.setTypeface(Typeface.DEFAULT);
                p.setTextSize(11 * dp);
                p.setColor(Hud.DIM);
                c.drawText(FxLink.PAGE_TITLES[r], 0, y + 32 * dp, p);
                int n = used[r];
                int cells = Math.max(8, Math.min(24, n));
                float gap = 3 * dp, cw = (w - labelW - gap * (cells - 1)) / cells, top = y + 6 * dp, bot = y + rowH - 8 * dp;
                for (int i = 0; i < cells; i++) {
                    int no = i + 1;
                    float x = labelW + i * (cw + gap);
                    boolean busy = no <= n, lit = pg == litPage && no >= litFrom && no <= litTo;
                    if (cells < n && i == cells - 1) busy = true;
                    p.setStyle(Paint.Style.FILL);
                    if (lit) {
                        p.setColor(0xccff8a1f);
                        p.setShadowLayer(8 * dp, 0, 0, Hud.ORANGE);
                    } else {
                        p.clearShadowLayer();
                        p.setColor(busy ? 0x3322d3ee : 0x08ffffff);
                    }
                    c.drawRect(x, top, x + cw, bot, p);
                    p.clearShadowLayer();
                    p.setStyle(Paint.Style.STROKE);
                    p.setStrokeWidth(1 * dp);
                    p.setColor(lit ? Hud.ORANGE_LIGHT : busy ? 0x8c22d3ee : 0x14ffffff);
                    c.drawRect(x, top, x + cw, bot, p);
                }
                if (n > cells) {
                    p.setStyle(Paint.Style.FILL);
                    p.setTextSize(10 * dp);
                    p.setColor(Hud.DIM);
                    p.setTextAlign(Paint.Align.RIGHT);
                    c.drawText(n + " шт", w, y + rowH - 0.5f * dp, p);
                    p.setTextAlign(Paint.Align.LEFT);
                }
            }
            p.setStyle(Paint.Style.FILL);
        }
    }
}
