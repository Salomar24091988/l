package com.yan.malight;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

/** Общие кирпичики экранов LightDancer 1.2: фон, панели со срезанными углами, кнопки, нижние вкладки. */
public abstract class BaseActivity extends Activity {

    // смысловые цвета кнопок (tint) - рисуются в стиле Hud
    protected static final int BG = Hud.BG, CARD = Hud.PANEL, TEXT = Hud.TEXT, DIM = Hud.DIM,
            ON = 0xff2e7d32, OFF = 0xff333333, ACCENT = 0xffd84315, WARN = Hud.AMBER, DANGER = 0xff8e1b1b,
            BUSY = 0xff8d6e00;

    protected static final Class<?>[] TABS = {MainActivity.class, GeneratorActivity.class, ConsoleActivity.class,
            SettingsActivity.class};

    protected float dp;
    protected Engine engine;
    protected NavBar nav;
    private int tab;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        dp = getResources().getDisplayMetrics().density;
        engine = Engine.get(this);
        getWindow().setStatusBarColor(Hud.BG_TOP);
        getWindow().setNavigationBarColor(0xff04080c);
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_HIDDEN
                | WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
    }

    /** экран вкладки: прокручиваемая колонка + нижняя панель; → колонка */
    protected LinearLayout shell(int tab) {
        this.tab = tab;
        FrameLayout frame = new FrameLayout(this);
        GradientDrawable bg = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM,
                new int[]{Hud.BG_TOP, Hud.BG_MID, Hud.BG});
        frame.setBackground(bg);
        ScrollView scroll = new ScrollView(this);
        scroll.setVerticalScrollBarEnabled(false);
        LinearLayout root = column();
        root.setPadding(px(16), px(14), px(16), px(110));
        scroll.addView(root);
        frame.addView(scroll, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));
        nav = new NavBar(this);
        nav.current = tab;
        nav.listener = new NavBar.Listener() {
            @Override
            public void onTab(int t) { openTab(t); }

            @Override
            public void onCenter() {
                engine.settings.autopilot = !engine.settings.autopilot;
                engine.save();
                engine.log(engine.settings.autopilot ? "автопилот включён" : "автопилот на паузе");
                nav.centerOn = engine.settings.autopilot;
                nav.invalidate();
            }
        };
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM);
        lp.leftMargin = px(8);
        lp.rightMargin = px(8);
        frame.addView(nav, lp);
        setContentView(frame);
        return root;
    }

    protected void openTab(int t) {
        if (t == tab) return;
        Intent i = new Intent(this, TABS[t]);
        i.addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT | Intent.FLAG_ACTIVITY_NO_ANIMATION);
        startActivity(i);
        overridePendingTransition(0, 0);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (nav != null) {
            nav.centerOn = engine.settings.autopilot;
            nav.invalidate();
        }
    }

    @Override
    public void onBackPressed() {
        if (tab == 0) moveTaskToBack(true);       // приложение продолжает работать в фоне
        else openTab(0);
    }

    // ------------------------------------------------------------------ кирпичики
    protected int px(float v) { return Math.round(v * dp); }

    protected LinearLayout column() {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        return l;
    }

    protected Hud.Chamfer panel(int fill, int stroke, float cut, float glow) {
        return new Hud.Chamfer(fill, stroke, px(cut), Math.max(1, px(1)), px(glow), false);
    }

    protected LinearLayout card(LinearLayout parent) {
        LinearLayout l = column();
        l.setBackground(panel(Hud.PANEL, Hud.LINE, 14, 0));
        l.setPadding(px(14), px(12), px(14), px(12));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = px(10);
        parent.addView(l, lp);
        return l;
    }

    protected LinearLayout row(LinearLayout parent) {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = px(8);
        parent.addView(l, lp);
        return l;
    }

    protected TextView text(float size, int color) {
        TextView t = new TextView(this);
        t.setTextSize(size);
        t.setTextColor(color);
        return t;
    }

    protected TextView caption(String s) {
        TextView t = text(12, DIM);
        t.setText(s.toUpperCase());
        t.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        t.setLetterSpacing(0.12f);
        t.setPadding(px(2), px(18), 0, px(2));
        return t;
    }

    /** крупный заголовок вкладки */
    protected void title(LinearLayout root, String over, String big) {
        TextView o = text(11, DIM);
        o.setText(over.toUpperCase());
        o.setLetterSpacing(0.25f);
        o.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        root.addView(o);
        TextView t = text(30, TEXT);
        t.setText(big);
        t.setTypeface(Typeface.create("sans-serif-condensed", Typeface.BOLD));
        root.addView(t);
    }

    protected Button button(LinearLayout row, String label, View.OnClickListener l) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setTextSize(14);
        b.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        b.setMinHeight(px(50));
        b.setMinimumHeight(px(50));
        b.setMinWidth(0);
        b.setMinimumWidth(0);
        b.setPadding(px(6), 0, px(6), 0);
        b.setStateListAnimator(null);
        b.setOnClickListener(l);
        tint(b, OFF);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
        lp.leftMargin = row.getChildCount() == 0 ? 0 : px(8);
        row.addView(b, lp);
        return b;
    }

    /** смысл кнопки: ON - выбрано (оранжевое свечение), ACCENT - главное действие, OFF - обычная, DANGER - стоп */
    protected void tint(Button b, int color) {
        Object tag = b.getTag();
        boolean en = b.isEnabled();
        int key = color ^ (en ? 0 : 1);
        if (tag instanceof Integer && (Integer) tag == key) return;
        int fill, stroke, textColor;
        float glow = 0;
        if (color == ON) {
            fill = 0x2eff8a1f;
            stroke = Hud.ORANGE;
            textColor = Hud.ORANGE_LIGHT;
            glow = 6;
        } else if (color == ACCENT) {
            fill = 0x1f22d3ee;
            stroke = Hud.ICE;
            textColor = Hud.ICE_LIGHT;
        } else if (color == DANGER) {
            fill = 0x22f87171;
            stroke = Hud.RED;
            textColor = Hud.RED_LIGHT;
        } else if (color == BUSY) {
            fill = 0x1ffbbf24;
            stroke = Hud.AMBER;
            textColor = Hud.AMBER;
        } else {
            fill = Hud.PANEL;
            stroke = Hud.LINE;
            textColor = Hud.TEXT;
        }
        if (!en) {
            stroke = Hud.alpha(stroke, 0.25f);
            textColor = Hud.alpha(textColor, 0.4f);
            glow = 0;
        }
        if (glow > 0) b.setLayerType(View.LAYER_TYPE_SOFTWARE, null);
        b.setBackground(panel(fill, stroke, 9, glow));
        b.setTextColor(textColor);
        b.setTag(key);
    }

    protected EditText field(boolean number, boolean decimal) {
        EditText e = new EditText(this);
        e.setSingleLine(true);
        e.setTextColor(TEXT);
        e.setHintTextColor(0xff4d6b77);
        e.setTextSize(15);
        e.setBackground(panel(0xcc04080c, Hud.LINE_SOFT, 8, 0));
        e.setPadding(px(12), px(10), px(12), px(10));
        if (number) e.setInputType(InputType.TYPE_CLASS_NUMBER | (decimal ? InputType.TYPE_NUMBER_FLAG_DECIMAL : 0));
        return e;
    }

    /** подпись слева, поле справа */
    protected EditText labeled(LinearLayout parent, String label, boolean number, boolean decimal) {
        LinearLayout r = row(parent);
        TextView l = text(14, DIM);
        l.setText(label);
        l.setGravity(Gravity.CENTER_VERTICAL);
        r.addView(l, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 3));
        EditText e = field(number, decimal);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 2);
        lp.leftMargin = px(8);
        r.addView(e, lp);
        return e;
    }

    protected void toast(String s) { Toast.makeText(this, s, Toast.LENGTH_LONG).show(); }
}
