package com.yan.malight;

import android.content.Context;
import android.content.SharedPreferences;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;

import com.yan.malight.core.Analyzer;
import com.yan.malight.core.Director;
import com.yan.malight.core.Ma2Client;
import com.yan.malight.core.Settings;

import java.text.SimpleDateFormat;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/** Всё приложение без экрана: звук → анализ → автопилот → пульт. Один на процесс. */
public final class Engine {

    private static Engine instance;

    public static synchronized Engine get(Context c) {
        if (instance == null) instance = new Engine(c.getApplicationContext());
        return instance;
    }

    public final Settings settings = new Settings();
    public final Ma2Client ma;
    public volatile Analyzer analyzer;
    public volatile Director director;
    public volatile String audioStatus = "не слушаю";
    public volatile boolean listening;

    private final Context ctx;
    private final ArrayDeque<String> log = new ArrayDeque<>();
    private volatile Thread audioThread;
    private final SimpleDateFormat time = new SimpleDateFormat("HH:mm:ss", Locale.US);

    private Engine(Context c) {
        ctx = c;
        load();
        ma = new Ma2Client(new Ma2Client.Log() {
            @Override
            public void line(String text, boolean error) { log((error ? "⚠ " : "") + text); }
        });
        ma.listenerOnline = new Runnable() { @Override public void run() {
            Director d = director;
            if (d != null) {
                d.resetSent();
                d.forgetState();
            }
        } };
        makeAnalysis(48000);
        applyConnection();
    }

    private void makeAnalysis(int rate) {
        Analyzer a = new Analyzer(rate);
        Director d = new Director(settings, ma, a);
        a.setListener(d);
        a.gain = settings.gain;
        a.leadSeconds = settings.leadMs / 1000.0;
        analyzer = a;
        director = d;
    }

    // ------------------------------------------------------------------ настройки
    public void load() {
        SharedPreferences p = ctx.getSharedPreferences("malight", Context.MODE_PRIVATE);
        Map<String, ?> all = p.getAll();
        if (!all.isEmpty()) settings.fromMap(all);
    }

    public void save() {
        SharedPreferences.Editor e = ctx.getSharedPreferences("malight", Context.MODE_PRIVATE).edit();
        for (Map.Entry<String, String> kv : settings.toMap().entrySet()) e.putString(kv.getKey(), kv.getValue());
        e.apply();
        Analyzer a = analyzer;
        if (a != null) {
            a.gain = settings.gain;
            a.leadSeconds = settings.leadMs / 1000.0;
        }
    }

    public void applyConnection() {
        int port = settings.port > 0 ? settings.port : 30000;
        ma.configure(settings.host.trim(), port, settings.user.trim(), settings.password, settings.enabled);
    }

    // ------------------------------------------------------------------ генератор эффектов
    /** состояние экрана «Эффекты»: groups, off (выключенные шаблоны), opts */
    @SuppressWarnings("unchecked")
    public synchronized Map<String, Object> gen() {
        if (gen == null) {
            String js = ctx.getSharedPreferences("malight", Context.MODE_PRIVATE).getString("fxgen", null);
            try {
                if (js != null) gen = (Map<String, Object>) com.yan.malight.core.Json.parse(js);
            } catch (RuntimeException ignored) {
            }
            if (gen == null) gen = new java.util.LinkedHashMap<>();
            if (!(gen.get("groups") instanceof List)) gen.put("groups", new ArrayList<Object>());
            if (!(gen.get("off") instanceof List)) gen.put("off", new ArrayList<Object>());
            if (!(gen.get("opts") instanceof Map)) gen.put("opts", new java.util.LinkedHashMap<String, Object>());
        }
        return gen;
    }

    public synchronized void saveGen() {
        if (gen == null) return;
        ctx.getSharedPreferences("malight", Context.MODE_PRIVATE).edit()
                .putString("fxgen", com.yan.malight.core.Json.write(gen)).apply();
    }

    private Map<String, Object> gen;
    public volatile boolean genBusy;

    /** эффекты, созданные генератором на пульте (looks), для «Поставить на экзекьюторы» */
    @SuppressWarnings("unchecked")
    public synchronized List<Object> genLink() {
        Object l = gen().get("link");
        return l instanceof List ? (List<Object>) l : new ArrayList<Object>();
    }

    public synchronized void setGenLink(List<Object> looks) {
        gen().put("link", looks);
        saveGen();
    }

    /** поставить эффекты генератора на экзекьюторы fxgenPage…+4 (как «Взять эффекты генератора» на ПК).
     *  Работает долго - звать не из UI-потока. → итог одной строкой */
    public String assignGen(com.yan.malight.core.FxJobs j, com.yan.malight.core.FxJobs.Out out) {
        List<Object> looks = genLink();
        if (looks.isEmpty()) return "нет эффектов генератора: сначала «Создать на пульте»";
        int page = settings.fxgenPage > 0 ? settings.fxgenPage : 11;
        com.yan.malight.core.FxLink.Script sc = com.yan.malight.core.FxLink.assignScript(looks, page, settings);
        out.log("Ставлю " + sc.assigned.size() + " эффектов генератора на страницы " + page + "-" + (page + 4)
                + " (" + sc.cmds.size() + " команд)", false);
        Director d = director;
        String old = d != null ? d.autoCmd : null;
        ma.paused = true;
        genBusy = true;
        int errors;
        try {
            errors = j.send(new ArrayList<>(sc.cmds), com.yan.malight.core.FxGen.defaultConfig(), 0.05, out);
        } catch (Exception e) {
            out.log("Не поставил: " + e.getMessage(), true);
            return "нет связи с пультом";
        } finally {
            ma.paused = false;
            genBusy = false;
        }
        if (j.stop) return "остановлено";
        settings.fxgenAssigned = com.yan.malight.core.Json.write(sc.assigned);
        settings.fxgenOn = true;
        save();
        if (d != null) {
            if (old != null && settings.enabled) ma.send("Off Executor " + old.replace("-", " Thru "), null);
            d.forgetState();
            d.resetSent();
        }
        String msg = "на экзекьюторах " + page + "-" + (page + 4) + ": " + sc.assigned.size() + " эффектов"
                + (errors > 0 ? ", ошибок " + errors : "");
        log("Генератор → автопилот: " + msg);
        return msg;
    }

    // ------------------------------------------------------------------ журнал
    public void log(String text) {
        synchronized (log) {
            log.addLast(time.format(new Date()) + "  " + text);
            while (log.size() > 300) log.removeFirst();
        }
    }

    public List<String> logTail(int n) {
        synchronized (log) {
            List<String> all = new ArrayList<>(log);
            return all.subList(Math.max(0, all.size() - n), all.size());
        }
    }

    // ------------------------------------------------------------------ звук
    public synchronized void startAudio() {
        if (audioThread != null) return;
        listening = true;
        Thread t = new Thread(new Runnable() { @Override public void run() { audioLoop(); } }, "audio");
        t.setPriority(Thread.MAX_PRIORITY);
        audioThread = t;
        t.start();
    }

    public synchronized void stopAudio() {
        listening = false;
        Thread t = audioThread;
        audioThread = null;
        if (t != null) t.interrupt();
        audioStatus = "не слушаю";
    }

    private AudioRecord open(int[] rateOut) {
        // без обработки (UNPROCESSED = 9, Android 7+), иначе распознавание речи (без автоусиления), иначе микрофон
        int[] sources = {9, MediaRecorder.AudioSource.VOICE_RECOGNITION, MediaRecorder.AudioSource.MIC};
        int[] rates = {48000, 44100};
        for (int src : sources) {
            for (int rate : rates) {
                try {
                    int min = AudioRecord.getMinBufferSize(rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
                    if (min <= 0) continue;
                    AudioRecord r = new AudioRecord(src, rate, AudioFormat.CHANNEL_IN_MONO,
                            AudioFormat.ENCODING_PCM_16BIT, Math.max(min, rate / 5 * 2));
                    if (r.getState() == AudioRecord.STATE_INITIALIZED) {
                        rateOut[0] = rate;
                        log("звук: " + (src == 9 ? "без обработки" : src == MediaRecorder.AudioSource.VOICE_RECOGNITION
                                ? "без автоусиления" : "микрофон") + ", " + rate + " Гц");
                        return r;
                    }
                    r.release();
                } catch (Exception ignored) {
                }
            }
        }
        return null;
    }

    private void audioLoop() {
        int[] rate = {48000};
        AudioRecord rec = open(rate);
        if (rec == null) {
            audioStatus = "микрофон не открылся (нет разрешения или занят)";
            log("⚠ " + audioStatus);
            listening = false;
            audioThread = null;
            return;
        }
        if (analyzer == null || analyzer.sampleRate() != rate[0]) makeAnalysis(rate[0]);
        int block = rate[0] / 100;                      // 10 мс
        short[] buf = new short[block];
        float[] f = new float[block];
        double lastBpm = 0;
        try {
            rec.startRecording();
            audioStatus = "слушаю";
            while (audioThread == Thread.currentThread()) {
                int n = rec.read(buf, 0, block);
                if (n <= 0) {
                    if (n < 0) {
                        audioStatus = "ошибка чтения звука " + n;
                        break;
                    }
                    continue;
                }
                for (int i = 0; i < n; i++) f[i] = buf[i] / 32768f;
                Analyzer a = analyzer;
                Director d = director;
                a.feed(f, n);
                double t = a.streamTime();
                if (t - lastBpm >= 0.5) {
                    lastBpm = t;
                    d.pushBpm(false);
                }
                d.fillTick();
            }
        } catch (Exception e) {
            audioStatus = "звук остановлен: " + e.getMessage();
            log("⚠ " + audioStatus);
        } finally {
            try { rec.stop(); } catch (Exception ignored) { }
            rec.release();
            if (audioThread == Thread.currentThread()) audioThread = null;
            listening = audioThread != null;
            if (!listening) audioStatus = "не слушаю";
        }
    }

    // ------------------------------------------------------------------ кнопки
    public void tap() {
        // Tap: ручной темп по последним нажатиям
        long now = System.nanoTime();
        taps.add(now);
        while (taps.size() > 8) taps.remove(0);
        if (taps.size() >= 2 && (now - taps.get(taps.size() - 2)) > 2_000_000_000L) {
            taps.clear();
            taps.add(now);
            return;
        }
        if (taps.size() < 3) return;
        double per = (taps.get(taps.size() - 1) - taps.get(0)) / 1e9 / (taps.size() - 1);
        double bpm = Math.round(60 / per * 10) / 10.0;
        if (bpm < 40 || bpm > 300) return;
        settings.bpmManual = bpm;
        settings.bpmMode = "manual";
        save();
        Director d = director;
        if (d != null) d.pushBpm(true);
        log("Tap: " + bpm + " BPM (ручной режим)");
    }

    private final List<Long> taps = new ArrayList<>();
}
