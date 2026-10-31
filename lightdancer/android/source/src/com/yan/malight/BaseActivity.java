package com.yan.malight;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

/** Общие кирпичики экранов: тёмная тема, карточки, ряды кнопок. */
public abstract class BaseActivity extends Activity {

    protected static final int BG = 0xff111111, CARD = 0xff1b1b1b, TEXT = 0xffeeeeee, DIM = 0xff9a9a9a,
            ON = 0xff2e7d32, OFF = 0xff333333, ACCENT = 0xffd84315, WARN = 0xffffb300;

    protected float dp;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        dp = getResources().getDisplayMetrics().density;
    }

    // ------------------------------------------------------------------ кирпичики
    protected int px(float v) { return Math.round(v * dp); }

    protected LinearLayout column() {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        return l;
    }

    protected LinearLayout card(LinearLayout parent) {
        LinearLayout l = column();
        GradientDrawable g = new GradientDrawable();
        g.setColor(CARD);
        g.setCornerRadius(px(10));
        l.setBackground(g);
        l.setPadding(px(12), px(10), px(12), px(10));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = px(8);
        parent.addView(l, lp);
        return l;
    }

    protected LinearLayout row(LinearLayout parent) {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = px(6);
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
        TextView t = text(13, DIM);
        t.setText(s.toUpperCase());
        t.setPadding(px(2), px(14), 0, 0);
        return t;
    }

    protected Button button(LinearLayout row, String label, View.OnClickListener l) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setTextColor(Color.WHITE);
        b.setTextSize(14);
        b.setMinHeight(px(48));
        b.setPadding(px(4), 0, px(4), 0);
        b.setOnClickListener(l);
        tint(b, ACCENT);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
        lp.leftMargin = row.getChildCount() == 0 ? 0 : px(6);
        row.addView(b, lp);
        return b;
    }

    protected void tint(Button b, int color) {
        Object tag = b.getTag();
        if (tag instanceof Integer && (Integer) tag == color) return;
        GradientDrawable g = new GradientDrawable();
        g.setColor(color);
        g.setCornerRadius(px(8));
        b.setBackground(g);
        b.setTag(color);
    }

    protected void toast(String s) { Toast.makeText(this, s, Toast.LENGTH_LONG).show(); }
}
