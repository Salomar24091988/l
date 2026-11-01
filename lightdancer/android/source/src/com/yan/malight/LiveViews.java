package com.yan.malight;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.view.View;

import com.yan.malight.core.Analyzer;

/** Рисованные элементы экрана Live: кольцо с волной, доли такта, спектр. */
public final class LiveViews {

    private LiveViews() { }

    static float band(Analyzer a, boolean listening, int i) {
        if (a == null || !listening) return 0;
        return Math.max(0, Math.min(1, a.bands[Math.max(0, Math.min(5, i))]));
    }

    /** значение спектра в точке x 0..1 (между 6 полосами) */
    static float spectrumAt(Analyzer a, boolean listening, float x) {
        float f = x * 5;
        int i = (int) Math.floor(f);
        float t = f - i;
        return band(a, listening, i) * (1 - t) + band(a, listening, i + 1) * t;
    }

    static boolean flash(Analyzer a, boolean listening, long ms) {
        return a != null && listening && a.bpm > 0 && (System.nanoTime() - a.beatStamp) < ms * 1_000_000L;
    }

    /** кольцо: дуги крутятся в темп, в центре - волна по спектру, на долю - вспышка */
    public static final class Ring extends View {
        private final float dp;
        private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final RectF r = new RectF();
        public Analyzer analyzer;
        public boolean listening;
        private float angle;
        private long last;
        private final float[] wave = new float[19];

        public Ring(Context c) {
            super(c);
            dp = c.getResources().getDisplayMetrics().density;
            setLayerType(LAYER_TYPE_SOFTWARE, null);
        }

        @Override
        protected void onMeasure(int w, int h) {
            setMeasuredDimension(MeasureSpec.getSize(w), (int) (230 * dp));
        }

        @Override
        protected void onDraw(Canvas c) {
            Analyzer a = analyzer;
            long now = System.nanoTime();
            float dt = last == 0 ? 0 : Math.min(0.1f, (now - last) / 1e9f);
            last = now;
            double bpm = a != null && listening && a.bpm > 0 ? a.bpm : 0;
            angle = (angle + dt * (bpm > 0 ? (float) (bpm / 60.0 * 22) : 6)) % 360;
            boolean fl = flash(a, listening, 140);

            float cx = getWidth() / 2f, cy = getHeight() / 2f, R = Math.min(getWidth(), getHeight()) / 2f - 14 * dp;
            p.setStyle(Paint.Style.STROKE);
            p.clearShadowLayer();
            p.setStrokeWidth(1.5f * dp);
            p.setColor(0x2622d3ee);
            c.drawCircle(cx, cy, R + 8 * dp, p);
            p.setColor(0x1422d3ee);
            c.drawLine(cx - R, cy, cx + R, cy, p);
            c.drawLine(cx, cy - R, cx, cy + R, p);

            // дуги
            p.setStrokeWidth(6 * dp);
            p.setStrokeCap(Paint.Cap.ROUND);
            r.set(cx - R, cy - R, cx + R, cy + R);
            int[] cols = {Hud.ICE, Hud.ORANGE, Hud.ICE};
            float[] start = {0, 125, 215}, sweep = {95, 55, 40};
            for (int i = 0; i < 3; i++) {
                p.setColor(cols[i]);
                p.setShadowLayer((fl && i == 1 ? 18 : 9) * dp, 0, 0, cols[i]);
                c.drawArc(r, start[i] + (i == 1 ? -angle : angle), sweep[i], false, p);
            }
            p.clearShadowLayer();
            // внутренний круг
            float inner = R * 0.78f * (fl ? 1.04f : 1f);
            p.setStyle(Paint.Style.FILL);
            p.setColor(fl ? 0x2622d3ee : 0x0f22d3ee);
            c.drawCircle(cx, cy, inner, p);
            p.setStyle(Paint.Style.STROKE);
            p.setStrokeWidth(1 * dp);
            p.setColor(0x4722d3ee);
            c.drawCircle(cx, cy, inner, p);

            // волна
            int n = wave.length;
            float bw = 4 * dp, gap = 3.2f * dp, total = n * bw + (n - 1) * gap, x0 = cx - total / 2, maxH = inner * 0.7f;
            p.setStyle(Paint.Style.FILL);
            for (int i = 0; i < n; i++) {
                float d = Math.abs(i - (n - 1) / 2f) / ((n - 1) / 2f);       // 0 в центре, 1 по краям
                float target = spectrumAt(a, listening, d) * (1 - d * 0.55f);
                if (!listening) target = 0.04f + 0.03f * (float) Math.sin(now / 4e8 + i);
                wave[i] += (target - wave[i]) * 0.35f;
                float h = Math.max(3 * dp, wave[i] * maxH * 2);
                float x = x0 + i * (bw + gap);
                p.setColor(wave[i] > 0.75f ? Hud.ORANGE : Hud.ICE);
                p.setShadowLayer(6 * dp, 0, 0, Hud.ICE);
                c.drawRoundRect(x, cy - h / 2, x + bw, cy + h / 2, bw / 2, bw / 2, p);
            }
            p.clearShadowLayer();
            postInvalidateOnAnimation();
        }
    }

    /** 4 доли такта полосками */
    public static final class Beats extends View {
        private final float dp;
        private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        public Analyzer analyzer;
        public boolean listening;

        public Beats(Context c) {
            super(c);
            dp = c.getResources().getDisplayMetrics().density;
            setLayerType(LAYER_TYPE_SOFTWARE, null);
        }

        @Override
        protected void onMeasure(int w, int h) {
            setMeasuredDimension(MeasureSpec.getSize(w), (int) (16 * dp));
        }

        @Override
        protected void onDraw(Canvas c) {
            Analyzer a = analyzer;
            int cur = a != null && listening && a.bpm > 0 ? a.beatInBar : 0;
            boolean fl = flash(a, listening, 160);
            float gap = 6 * dp, w = (getWidth() - gap * 3) / 4f, h = 6 * dp, y = (getHeight() - h) / 2;
            for (int i = 0; i < 4; i++) {
                float x = i * (w + gap);
                if (i + 1 == cur) {
                    p.setColor(Hud.ORANGE);
                    p.setShadowLayer((fl ? 12 : 6) * dp, 0, 0, Hud.ORANGE);
                } else {
                    p.setColor(i + 1 < cur ? Hud.ICE : 0x2622d3ee);
                    p.clearShadowLayer();
                }
                c.drawRoundRect(x, y, x + w, y + h, h / 2, h / 2, p);
            }
            p.clearShadowLayer();
            postInvalidateOnAnimation();
        }
    }

    /** спектр: 40 столбиков с отражением */
    public static final class Spectrum extends View {
        private final float dp;
        private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        public Analyzer analyzer;
        public boolean listening;
        private final float[] v = new float[40], peak = new float[40], jitter = new float[40];

        public Spectrum(Context c) {
            super(c);
            dp = c.getResources().getDisplayMetrics().density;
            java.util.Random r = new java.util.Random(7);
            for (int i = 0; i < jitter.length; i++) jitter[i] = 0.75f + 0.5f * r.nextFloat();
        }

        @Override
        protected void onMeasure(int w, int h) {
            setMeasuredDimension(MeasureSpec.getSize(w), (int) (84 * dp));
        }

        @Override
        protected void onDraw(Canvas c) {
            Analyzer a = analyzer;
            int n = v.length;
            float base = getHeight() * 0.8f, maxH = base - 2 * dp, gap = 2 * dp, w = (getWidth() - gap * (n - 1)) / n;
            for (int i = 0; i < n; i++) {
                float t = Math.min(1, spectrumAt(a, listening, i / (float) (n - 1)) * jitter[i]);
                v[i] += (t - v[i]) * (t > v[i] ? 0.5f : 0.15f);
                peak[i] = Math.max(v[i], peak[i] - 0.012f);
                float h = Math.max(1.5f * dp, v[i] * maxH), x = i * (w + gap);
                p.setColor(v[i] > 0.7f ? Hud.ORANGE : Hud.ICE);
                c.drawRect(x, base - h, x + w, base, p);
                p.setColor(0x3322d3ee);
                c.drawRect(x, base + 2 * dp, x + w, base + 2 * dp + h * 0.22f, p);
                p.setColor(Hud.ICE_LIGHT);
                float py = base - peak[i] * maxH - 3 * dp;
                if (peak[i] > 0.05f) c.drawRect(x, py, x + w, py + 1.5f * dp, p);
            }
            p.setColor(0x4722d3ee);
            c.drawRect(0, base, getWidth(), base + 1 * dp, p);
            postInvalidateOnAnimation();
        }
    }
}
