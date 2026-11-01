package com.yan.malight;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.view.MotionEvent;
import android.view.View;

/** Нижняя панель: Live, Эффекты, [автопилот], Пульт, Настройки. */
public final class NavBar extends View {

    public interface Listener {
        void onTab(int tab);

        void onCenter();
    }

    static final String[] LABELS = {"Live", "Эффекты", "Пульт", "Настройки"};

    private final float dp;
    private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path path = new Path();
    public int current;
    public boolean centerOn;
    public Listener listener;
    private int down = -2;

    public NavBar(Context c) {
        super(c);
        dp = c.getResources().getDisplayMetrics().density;
        setLayerType(LAYER_TYPE_SOFTWARE, null);       // свечение
    }

    @Override
    protected void onMeasure(int w, int h) {
        setMeasuredDimension(MeasureSpec.getSize(w), (int) (96 * dp));
    }

    /** -1 центр, 0..3 вкладки */
    private int slot(float x) {
        float w = getWidth(), mid = 88 * dp, side = (w - mid) / 4;
        if (x >= side * 2 && x <= side * 2 + mid) return -1;
        int i = (int) (x / side);
        if (x > side * 2 + mid) i = 2 + (int) ((x - side * 2 - mid) / side);
        return Math.max(0, Math.min(3, i));
    }

    @Override
    public boolean onTouchEvent(MotionEvent e) {
        if (e.getY() < 18 * dp) return false;
        if (e.getAction() == MotionEvent.ACTION_DOWN) {
            down = slot(e.getX());
            invalidate();
            return true;
        }
        if (e.getAction() == MotionEvent.ACTION_UP) {
            int s = slot(e.getX());
            if (s == down && listener != null) {
                performClick();
                if (s == -1) listener.onCenter();
                else listener.onTab(s);
            }
            down = -2;
            invalidate();
            return true;
        }
        if (e.getAction() == MotionEvent.ACTION_CANCEL) {
            down = -2;
            invalidate();
        }
        return true;
    }

    @Override
    public boolean performClick() { return super.performClick(); }

    @Override
    protected void onDraw(Canvas c) {
        float w = getWidth(), h = getHeight(), top = 22 * dp, cut = 16 * dp;
        // панель
        path.reset();
        path.moveTo(cut, top);
        path.lineTo(w - cut, top);
        path.lineTo(w, top + cut);
        path.lineTo(w, h);
        path.lineTo(0, h);
        path.lineTo(0, top + cut);
        path.close();
        p.clearShadowLayer();
        p.setStyle(Paint.Style.FILL);
        p.setColor(0xf2080a0e);
        c.drawPath(path, p);
        p.setStyle(Paint.Style.STROKE);
        p.setStrokeWidth(1 * dp);
        p.setColor(Hud.LINE);
        c.drawLine(cut, top, w - cut, top, p);

        float mid = 88 * dp, side = (w - mid) / 4, cy = top + (h - top) / 2;
        for (int i = 0; i < 4; i++) {
            float cx = i < 2 ? side * i + side / 2 : side * 2 + mid + side * (i - 2) + side / 2;
            boolean on = i == current;
            int col = on ? Hud.ICE : (down == i ? Hud.ICE_LIGHT : Hud.DIM);
            p.setColor(col);
            if (on) p.setShadowLayer(8 * dp, 0, 0, Hud.ICE);
            else p.clearShadowLayer();
            icon(c, i, cx, cy - 9 * dp);
            p.setStyle(Paint.Style.FILL);
            p.clearShadowLayer();
            p.setTextSize(11 * dp);
            p.setTextAlign(Paint.Align.CENTER);
            p.setFakeBoldText(on);
            c.drawText(LABELS[i], cx, cy + 18 * dp, p);
        }
        // центр: автопилот
        float s = 34 * dp, ccx = w / 2, ccy = top + 12 * dp;
        path.reset();
        float k = s * 0.42f;
        path.moveTo(ccx - k, ccy - s);
        path.lineTo(ccx + k, ccy - s);
        path.lineTo(ccx + s, ccy - k);
        path.lineTo(ccx + s, ccy + k);
        path.lineTo(ccx + k, ccy + s);
        path.lineTo(ccx - k, ccy + s);
        path.lineTo(ccx - s, ccy + k);
        path.lineTo(ccx - s, ccy - k);
        path.close();
        p.setStyle(Paint.Style.FILL);
        p.clearShadowLayer();
        p.setColor(centerOn ? 0xff2a1806 : 0xff07141c);
        if (down == -1) p.setColor(0xff3a2208);
        c.drawPath(path, p);
        p.setStyle(Paint.Style.STROKE);
        p.setStrokeWidth(2 * dp);
        p.setColor(centerOn ? Hud.ORANGE : Hud.DIM);
        if (centerOn) p.setShadowLayer(14 * dp, 0, 0, Hud.ORANGE);
        c.drawPath(path, p);
        p.setStyle(Paint.Style.FILL);
        Path tri = new Path();
        float t = 12 * dp;
        if (centerOn) {
            tri.moveTo(ccx - t * 0.6f, ccy - t);
            tri.lineTo(ccx + t, ccy);
            tri.lineTo(ccx - t * 0.6f, ccy + t);
            tri.close();
            c.drawPath(tri, p);
        } else {
            c.drawRect(ccx - t * 0.7f, ccy - t * 0.8f, ccx - t * 0.15f, ccy + t * 0.8f, p);
            c.drawRect(ccx + t * 0.15f, ccy - t * 0.8f, ccx + t * 0.7f, ccy + t * 0.8f, p);
        }
        p.clearShadowLayer();
        p.setTextSize(10 * dp);
        p.setTextAlign(Paint.Align.CENTER);
        p.setFakeBoldText(true);
        p.setColor(centerOn ? Hud.ORANGE_LIGHT : Hud.DIM);
        c.drawText(centerOn ? "АВТОПИЛОТ" : "ПАУЗА", ccx, h - 8 * dp, p);
        p.setFakeBoldText(false);
    }

    /** значки 24×24 dp, центр в (cx, cy) */
    private void icon(Canvas c, int i, float cx, float cy) {
        float u = dp, x = cx - 12 * u, y = cy - 12 * u;
        p.setStyle(Paint.Style.STROKE);
        p.setStrokeWidth(2 * u);
        p.setStrokeCap(Paint.Cap.ROUND);
        p.setStrokeJoin(Paint.Join.ROUND);
        Path q = new Path();
        switch (i) {
            case 0:
                q.moveTo(x + 3 * u, y + 12 * u);
                q.lineTo(x + 6 * u, y + 12 * u);
                q.lineTo(x + 9 * u, y + 5 * u);
                q.lineTo(x + 13 * u, y + 19 * u);
                q.lineTo(x + 16 * u, y + 12 * u);
                q.lineTo(x + 21 * u, y + 12 * u);
                c.drawPath(q, p);
                break;
            case 1:
                c.drawRect(x + 4 * u, y + 4 * u, x + 11 * u, y + 11 * u, p);
                c.drawRect(x + 13 * u, y + 4 * u, x + 20 * u, y + 11 * u, p);
                c.drawRect(x + 4 * u, y + 13 * u, x + 11 * u, y + 20 * u, p);
                c.drawRect(x + 13 * u, y + 13 * u, x + 20 * u, y + 20 * u, p);
                break;
            case 2:
                c.drawRect(x + 3 * u, y + 5 * u, x + 21 * u, y + 19 * u, p);
                c.drawLine(x + 7 * u, y + 15 * u, x + 7 * u, y + 11 * u, p);
                c.drawLine(x + 12 * u, y + 15 * u, x + 12 * u, y + 9 * u, p);
                c.drawLine(x + 17 * u, y + 15 * u, x + 17 * u, y + 13 * u, p);
                break;
            default:
                c.drawLine(x + 4 * u, y + 7 * u, x + 14 * u, y + 7 * u, p);
                c.drawLine(x + 18 * u, y + 7 * u, x + 20 * u, y + 7 * u, p);
                c.drawLine(x + 4 * u, y + 17 * u, x + 8 * u, y + 17 * u, p);
                c.drawLine(x + 12 * u, y + 17 * u, x + 20 * u, y + 17 * u, p);
                c.drawCircle(x + 16 * u, y + 7 * u, 2 * u, p);
                c.drawCircle(x + 10 * u, y + 17 * u, 2 * u, p);
        }
    }
}
