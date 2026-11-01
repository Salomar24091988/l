package com.yan.malight;

import android.graphics.Canvas;
import android.graphics.ColorFilter;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.graphics.drawable.Drawable;

/** Стиль LightDancer 1.2: тёмно-бирюзовый фон, циан и оранжевый, панели со срезанными углами. */
public final class Hud {

    private Hud() { }

    public static final int BG = 0xff04080c, BG_MID = 0xff07121a, BG_TOP = 0xff0e2a36, PANEL = 0xee07141c, ICE = 0xff22d3ee,
            ICE_LIGHT = 0xff9be9f7, LINE = 0x4722d3ee, LINE_SOFT = 0x2622d3ee, TEXT = 0xffeaf6fa, DIM = 0xff8fb3c0,
            ORANGE = 0xffff8a1f, ORANGE_LIGHT = 0xffffb366,
            WHITE = 0xffffffff, GREEN = 0xff34d399, RED = 0xfff87171, RED_LIGHT = 0xfffca5a5, AMBER = 0xfffbbf24;

    /** панель со срезанными углами (левый верхний и правый нижний), с обводкой и свечением */
    public static final class Chamfer extends Drawable {
        private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG), stroke = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Path path = new Path();
        private final float cut, sw, glow;
        private int fillColor, strokeColor;
        private boolean pressed;
        private final boolean octagon;

        public Chamfer(int fillColor, int strokeColor, float cut, float strokeWidth, float glow, boolean octagon) {
            this.fillColor = fillColor;
            this.strokeColor = strokeColor;
            this.cut = cut;
            this.sw = strokeWidth;
            this.glow = glow;
            this.octagon = octagon;
            fill.setStyle(Paint.Style.FILL);
            stroke.setStyle(Paint.Style.STROKE);
            stroke.setStrokeWidth(strokeWidth);
        }

        @Override
        protected void onBoundsChange(Rect b) {
            path.reset();
            float in = glow + sw / 2;
            float l = b.left + in, t = b.top + in, r = b.right - in, btm = b.bottom - in;
            float c = Math.min(cut, Math.min(r - l, btm - t) / 2);
            if (octagon) {
                float cx = (r - l) * 0.3f, cy = (btm - t) * 0.3f;
                path.moveTo(l + cx, t);
                path.lineTo(r - cx, t);
                path.lineTo(r, t + cy);
                path.lineTo(r, btm - cy);
                path.lineTo(r - cx, btm);
                path.lineTo(l + cx, btm);
                path.lineTo(l, btm - cy);
                path.lineTo(l, t + cy);
            } else {
                path.moveTo(l + c, t);
                path.lineTo(r, t);
                path.lineTo(r, btm - c);
                path.lineTo(r - c, btm);
                path.lineTo(l, btm);
                path.lineTo(l, t + c);
            }
            path.close();
        }

        @Override
        public void draw(Canvas canvas) {
            int f = fillColor;
            if (pressed) f = blend(f, strokeColor, 0.25f);
            fill.setColor(f);
            canvas.drawPath(path, fill);
            if (sw > 0 && (strokeColor >>> 24) != 0) {
                stroke.setColor(strokeColor);
                if (glow > 0) stroke.setShadowLayer(glow, 0, 0, strokeColor);
                else stroke.clearShadowLayer();
                canvas.drawPath(path, stroke);
            }
        }

        @Override
        public boolean isStateful() { return true; }

        @Override
        protected boolean onStateChange(int[] state) {
            boolean p = false;
            for (int s : state) if (s == android.R.attr.state_pressed) p = true;
            if (p == pressed) return false;
            pressed = p;
            invalidateSelf();
            return true;
        }

        @Override
        public void setAlpha(int a) { }

        @Override
        public void setColorFilter(ColorFilter cf) { }

        @Override
        public int getOpacity() { return PixelFormat.TRANSLUCENT; }
    }

    public static int blend(int a, int b, float t) {
        int aa = (a >>> 24), ar = (a >> 16) & 255, ag = (a >> 8) & 255, ab = a & 255;
        int ba = (b >>> 24), br = (b >> 16) & 255, bg = (b >> 8) & 255, bb = b & 255;
        return ((int) (aa + (ba - aa) * t) << 24) | ((int) (ar + (br - ar) * t) << 16)
                | ((int) (ag + (bg - ag) * t) << 8) | (int) (ab + (bb - ab) * t);
    }

    public static int alpha(int color, float a) {
        return ((int) (Math.max(0, Math.min(1, a)) * 255) << 24) | (color & 0xffffff);
    }
}
