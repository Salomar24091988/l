package com.yan.malight;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.view.Gravity;
import android.widget.FrameLayout;
import android.widget.ImageView;

/** Экран загрузки: логотип LightDancer плавно появляется, потом вкладка Live. */
public final class SplashActivity extends Activity {

    private final Handler h = new Handler();
    private boolean gone;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().setStatusBarColor(0xff000000);
        getWindow().setNavigationBarColor(0xff000000);
        FrameLayout f = new FrameLayout(this);
        f.setBackgroundColor(0xff000000);
        ImageView img = new ImageView(this);
        img.setImageResource(getResources().getIdentifier("splash", "drawable", getPackageName()));
        img.setScaleType(ImageView.ScaleType.FIT_CENTER);
        img.setAlpha(0f);
        img.setScaleX(0.94f);
        img.setScaleY(0.94f);
        f.addView(img, new FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.WRAP_CONTENT, Gravity.CENTER));
        setContentView(f);
        img.animate().alpha(1f).scaleX(1f).scaleY(1f).setDuration(900).start();
        h.postDelayed(new Runnable() {
            @Override
            public void run() { next(); }
        }, 1700);
    }

    private void next() {
        if (gone || isFinishing()) return;
        gone = true;
        startActivity(new Intent(this, MainActivity.class));
        overridePendingTransition(android.R.anim.fade_in, android.R.anim.fade_out);
        finish();
    }

    @Override
    public void onBackPressed() { }
}
