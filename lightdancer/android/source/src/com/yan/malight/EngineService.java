package com.yan.malight;

import android.app.Notification;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.net.wifi.WifiManager;
import android.os.IBinder;
import android.os.PowerManager;

/** Держит приложение живым, пока телефон слушает: выключенный экран не останавливает анализ. */
public final class EngineService extends Service {

    public static final String START = "com.yan.malight.START", STOP = "com.yan.malight.STOP";

    private PowerManager.WakeLock cpu;
    private WifiManager.WifiLock wifi;

    public static void start(Context c) {
        c.startService(new Intent(c, EngineService.class).setAction(START));
    }

    public static void stop(Context c) {
        c.startService(new Intent(c, EngineService.class).setAction(STOP));
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Engine e = Engine.get(this);
        String a = intent == null ? START : intent.getAction();
        if (STOP.equals(a)) {
            e.stopAudio();
            release();
            stopForeground(true);
            stopSelf();
            return START_NOT_STICKY;
        }
        startForeground(1, notification());
        lock();
        e.startAudio();
        return START_STICKY;
    }

    @SuppressWarnings("deprecation")
    private Notification notification() {
        PendingIntent open = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP), PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        PendingIntent stop = PendingIntent.getService(this, 1, new Intent(this, EngineService.class).setAction(STOP),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        return new Notification.Builder(this)
                .setSmallIcon(android.R.drawable.ic_media_play)
                .setContentTitle("LightDancer слушает")
                .setContentText("Анализ музыки и управление пультом")
                .setContentIntent(open)
                .setOngoing(true)
                .addAction(android.R.drawable.ic_media_pause, "Стоп", stop)
                .build();
    }

    @SuppressWarnings("deprecation")
    private void lock() {
        try {
            if (cpu == null) {
                cpu = ((PowerManager) getSystemService(POWER_SERVICE)).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "malight:audio");
                cpu.setReferenceCounted(false);
            }
            cpu.acquire();
            if (wifi == null) {
                wifi = ((WifiManager) getApplicationContext().getSystemService(WIFI_SERVICE))
                        .createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "malight:wifi");
                wifi.setReferenceCounted(false);
            }
            wifi.acquire();
        } catch (Exception ignored) {
        }
    }

    private void release() {
        try { if (cpu != null && cpu.isHeld()) cpu.release(); } catch (Exception ignored) { }
        try { if (wifi != null && wifi.isHeld()) wifi.release(); } catch (Exception ignored) { }
    }

    @Override
    public void onDestroy() {
        Engine.get(this).stopAudio();
        release();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) { return null; }
}
