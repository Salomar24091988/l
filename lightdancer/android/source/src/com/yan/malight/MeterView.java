package com.yan.malight;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.view.View;

import com.yan.malight.core.Analyzer;

/** 4 доли такта и 6 полос спектра. */
public final class MeterView extends View {

    private static final int[] BAND_COLORS = {0xffe53935, 0xfffb8c00, 0xfffdd835, 0xff43a047, 0xff1e88e5, 0xff8e24aa};
    private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final float dp;
    public Analyzer analyzer;
    public boolean listening;

    public MeterView(Context c) {
        super(c);
        dp = c.getResources().getDisplayMetrics().density;
    }

    @Override
    protected void onMeasure(int w, int h) {
        setMeasuredDimension(MeasureSpec.getSize(w), (int) (120 * dp));
    }

    @Override
    protected void onDraw(Canvas c) {
        Analyzer a = analyzer;
        float w = getWidth(), h = getHeight();
        // доли
        float r = 14 * dp, top = 4 * dp;
        boolean flash = a != null && listening && (System.nanoTime() - a.beatStamp) < 130_000_000L;
        for (int i = 0; i < 4; i++) {
            float cx = w / 2 + (i - 1.5f) * 44 * dp;
            boolean cur = a != null && listening && a.bpm > 0 && a.beatInBar == i + 1;
            p.setStyle(Paint.Style.FILL);
            p.setColor(cur ? (flash ? (i == 0 ? 0xffff5252 : 0xffffffff) : (i == 0 ? 0xff8b2c2c : 0xff777777)) : 0xff2a2a2a);
            c.drawCircle(cx, top + r, cur && flash ? r * 1.15f : r, p);
        }
        // полосы
        float y0 = top + 2 * r + 12 * dp, bh = h - y0 - 2 * dp;
        float gap = 6 * dp, bw = (w - gap * 7) / 6;
        for (int i = 0; i < 6; i++) {
            float v = a == null || !listening ? 0 : Math.max(0, Math.min(1, a.bands[i]));
            float x = gap + i * (bw + gap);
            p.setColor(0xff1d1d1d);
            c.drawRect(x, y0, x + bw, y0 + bh, p);
            p.setColor(BAND_COLORS[i]);
            c.drawRect(x, y0 + bh * (1 - v), x + bw, y0 + bh, p);
        }
    }
}
