package com.yan.malight.core;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * Анализ звука как в MusicAnalyzer на компьютере:
 * огибающая ударов (spectral flux, окно 1024 / шаг 512), BPM автокорреляцией за 8 с,
 * фаза долей, первая доля такта по смене звучания, рисунок такта 3 зоны × 16 шагов,
 * секция (D дроп / M середина / B брейк), всплеск, 6 полос с автоусилением.
 * Без Android: звук подаётся в feed(), события - в Listener.
 */
public final class Analyzer {

    public interface Listener {
        void onBeat(int beatInBar, double period, String section);
        void onBar(Bar bar);
        void onLull();
    }

    /** Что анализатор знает о закончившемся такте */
    public static final class Bar {
        public int number, phrase;
        public int[] hits = new int[3];          // ударов за такт: низ, середина, верх
        public boolean[][] grid;                 // 3 × 16
        public float energy;                     // средняя громкость полос за такт 0..1
        public boolean burst;                    // всплеск (дроп после брейка)
        public String section;                   // D / M / B
        public boolean sectionChanged;
        public double bpm;
    }

    // ---- константы (как в music_analyzer.py)
    static final int HOP = 512, WIN = 1024;
    static final double TEMPO_SECONDS = 8, BPM_MIN = 70, BPM_MAX = 180;
    static final int BEATS_PER_BAR = 4, BARS_PER_PHRASE = 8, STEPS = 16;
    static final double PHASE_CORRECTION = 0.3, DOWNBEAT_MEMORY = 0.85, OCTAVE_RATIO = 0.5;
    static final double HIT_RATIO = 3.0, HIT_RELATIVE = 0.5, HIT_RISE = 1.5;
    static final int HIT_PEAK_FRAMES = 3, HIT_RISE_FRAMES = 10;
    static final int SECTION_KICK = 3, SECTION_BREAK_KICK = 1, SECTION_BREAK_LOW = 2, SECTION_HOLD = 2;
    static final double SECTION_LOUD = 0.35;
    static final double BURST_ENERGY = 1.35, BURST_MIN_ENERGY = 0.35, BURST_PEAK = 2.5;
    static final double SILENCE_RMS = 1e-3;
    static final int BANDS_RATE = 40, FFT_BANDS = 4096;
    static final double BAND_ATTACK = 0.6, BAND_RELEASE = 0.15, BAND_PEAK_DECAY = 0.998, BAND_MAX_GAIN = 100;
    static final double[][] BAND_EDGES = {{20, 60}, {60, 250}, {250, 500}, {500, 2000}, {2000, 4000}, {4000, 16000}};
    static final double[][] ZONES = {{30, 150}, {150, 2000}, {2000, 16000}};
    public static final String[] BAND_NAMES = {"sub", "bass", "lowmid", "mid", "highmid", "high"};

    private final int sr;
    private final double rate;                 // кадров огибающей в секунду
    private Listener listener;

    // ---- то, что показывает экран (читается из другого потока)
    public volatile double bpm;
    public volatile int beatInBar, bar, phrase;
    public volatile String section;
    public volatile float level;
    public volatile boolean sound;
    public final float[] bands = new float[6];
    public volatile long beatStamp;            // System.nanoTime() последней доли
    public volatile double gain = 1.0;         // чувствительность входа
    public volatile double leadSeconds = 0.0;  // опережение долей (задержка сети и пульта)

    // ---- огибающая
    private final Fft fftOnset = new Fft(WIN), fftBands = new Fft(FFT_BANDS);
    private final float[] winOnset = Fft.hann(WIN), winBands = Fft.hann(FFT_BANDS);
    private final float[] onsetBuf = new float[WIN];
    private int onsetFill;
    private final double[] mag = new double[WIN / 2 + 1], magBands = new double[FFT_BANDS / 2 + 1];
    private double[] prevSpec;
    private final int kickLo, kickHi;
    private final int[][] zoneBins = new int[3][2];
    private final int[][] beatBins = new int[16][2];   // 16 полос 100-4000 Гц для смены звучания
    private final int cap;
    private final double[] envKick, envFull, envTime;
    private final double[][] envZone;
    private int envHead, envCount;
    private long samples;
    private double lastSound = -10, lastTempo, lastBands;
    private boolean lullSent = true;

    // ---- полосы
    private final float[] bandRing = new float[FFT_BANDS];
    private final float[] bandWork = new float[FFT_BANDS];
    private int bandPos;
    private final int[][] bandBins = new int[6][2];
    private final double[] bandPeaks = new double[6];
    private double barBandSum;
    private int barBandCount;

    // ---- темп и доли
    private double currentBpm, bpmCandidate, period = 0.5;
    private int bpmCandidateCount;
    private Double nextBeat;
    private int phaseFlip;
    private double phaseFlipErr;
    private int beatCount, downbeat;
    private final double[] downbeatScores = new double[BEATS_PER_BAR];
    private final List<double[]> beatFrames = new ArrayList<>();
    private double[] prevBeatSpectrum;
    private Double barStart;
    private int barNo;

    // ---- секция и всплеск
    private String sectionNext;
    private int sectionNextCount;
    private final ArrayDeque<Float> trackEnergies = new ArrayDeque<>();
    private final ArrayDeque<Float> burstEnergy = new ArrayDeque<>();
    private double peakAverage;

    public Analyzer(int sampleRate) {
        sr = sampleRate;
        rate = (double) sr / HOP;
        double binOnset = (double) sr / WIN, binBands = (double) sr / FFT_BANDS;
        kickLo = (int) Math.ceil(30 / binOnset);
        kickHi = (int) Math.ceil(150 / binOnset);
        for (int z = 0; z < 3; z++) {
            zoneBins[z][0] = (int) Math.ceil(ZONES[z][0] / binOnset);
            zoneBins[z][1] = Math.min(WIN / 2 + 1, (int) Math.ceil(ZONES[z][1] / binOnset));
        }
        for (int b = 0; b < 6; b++) {
            bandBins[b][0] = (int) Math.ceil(BAND_EDGES[b][0] / binBands);
            bandBins[b][1] = Math.min(FFT_BANDS / 2 + 1, Math.max(bandBins[b][0] + 1, (int) Math.ceil(BAND_EDGES[b][1] / binBands)));
        }
        for (int i = 0; i < 16; i++) {
            double lo = 100 * Math.pow(40, i / 16.0), hi = 100 * Math.pow(40, (i + 1) / 16.0);
            beatBins[i][0] = (int) Math.floor(lo / binOnset);
            beatBins[i][1] = Math.max(beatBins[i][0] + 1, (int) Math.ceil(hi / binOnset));
        }
        cap = (int) (rate * TEMPO_SECONDS);
        envKick = new double[cap];
        envFull = new double[cap];
        envTime = new double[cap];
        envZone = new double[3][cap];
    }

    public void setListener(Listener l) { listener = l; }

    public int sampleRate() { return sr; }

    public double streamTime() { return (double) samples / sr; }

    /** Tap / ручной темп: сразу ставим BPM и фазу на этот момент */
    public synchronized void forceBpm(double value, boolean phaseNow) {
        if (value < 40 || value > 300) return;
        currentBpm = value;
        period = 60.0 / value;
        bpm = value;
        if (phaseNow) nextBeat = streamTime() + period;
    }

    // ------------------------------------------------------------------
    /** Мелкий блок звука (моно, -1..1) */
    public synchronized void feed(float[] x, int n) {
        double g = gain;
        double sum = 0;
        for (int i = 0; i < n; i++) {
            float v = (float) (x[i] * g);
            sum += v * v;
            onsetBuf[onsetFill++] = v;
            bandRing[bandPos] = v;
            bandPos = (bandPos + 1) % FFT_BANDS;
            samples++;
            if (onsetFill == WIN) {
                onsetFrame();
                System.arraycopy(onsetBuf, HOP, onsetBuf, 0, WIN - HOP);
                onsetFill = WIN - HOP;
            }
        }
        double now = streamTime();
        double rms = Math.sqrt(sum / Math.max(1, n) + 1e-12);
        if (rms > SILENCE_RMS) {
            lastSound = now;
            lullSent = false;
        }
        sound = now - lastSound < 0.5;
        if (now - lastBands >= 1.0 / BANDS_RATE) {
            lastBands = now;
            analyzeBands();
        }
        if (now - lastTempo >= 0.5) {
            lastTempo = now;
            trackBeat();
            if (!lullSent && now - lastSound > 2.0) {
                lullSent = true;
                if (listener != null) listener.onLull();
            }
        }
        tickBeats();
    }

    private void onsetFrame() {
        fftOnset.magnitude(onsetBuf, 0, winOnset, mag);
        int nb = mag.length;
        double[] spec = new double[nb];
        for (int i = 0; i < nb; i++) spec[i] = Math.log1p(mag[i] * 100);
        double t = (samples - WIN / 2.0) / sr;      // середина окна
        if (prevSpec != null) {
            double kick = 0, full = 0;
            double[] z = new double[3];
            for (int i = 0; i < nb; i++) {
                double f = spec[i] - prevSpec[i];
                if (f <= 0) continue;
                full += f;
                if (i >= kickLo && i < kickHi) kick += f;
                for (int k = 0; k < 3; k++) if (i >= zoneBins[k][0] && i < zoneBins[k][1]) z[k] += f;
            }
            int at = (envHead + envCount) % cap;
            if (envCount == cap) envHead = (envHead + 1) % cap;
            else envCount++;
            envKick[at] = kick;
            envFull[at] = full;
            envTime[at] = t;
            for (int k = 0; k < 3; k++) envZone[k][at] = z[k];
            // звучание кадра в 16 полосах - для поиска первой доли
            double[] v = new double[16];
            for (int b = 0; b < 16; b++) {
                double s = 0;
                int c = 0;
                for (int i = beatBins[b][0]; i < Math.min(nb, beatBins[b][1]); i++, c++) s += mag[i];
                v[b] = Math.log(s / Math.max(1, c) + 1e-6);
            }
            beatFrames.add(v);
            if (beatFrames.size() > 400) beatFrames.remove(0);
        }
        prevSpec = spec;
    }

    private double env(double[] a, int i) { return a[(envHead + i) % cap]; }

    // ------------------------------------------------------------------
    private void trackBeat() {
        int n = envCount;
        if (n < rate * 4) return;
        double mk = 0, mf = 0;
        for (int i = 0; i < n; i++) {
            mk += env(envKick, i);
            mf += env(envFull, i);
        }
        mk /= n;
        mf /= n;
        if (mf < 1e-6) return;
        double[] onset = new double[n];
        double mean = 0;
        for (int i = 0; i < n; i++) {
            onset[i] = env(envKick, i) / (mk + 1e-9) + env(envFull, i) / (mf + 1e-9);
            mean += onset[i];
        }
        mean /= n;
        double[] x = new double[n];
        for (int i = 0; i < n; i++) x[i] = onset[i] - mean;
        int lo = (int) (60 * rate / BPM_MAX);
        int hi = Math.min((int) (60 * rate / BPM_MIN) + 1, n - 1);
        double[] ac = new double[hi + 2];
        for (int lag = 0; lag < ac.length && lag < n; lag++) {
            double s = 0;
            for (int i = 0; i + lag < n; i++) s += x[i] * x[i + lag];
            ac[lag] = s;
        }
        int k = lo;
        double best = -Double.MAX_VALUE;
        for (int lag = lo; lag < hi; lag++) {
            double w = Math.exp(-0.5 * Math.pow(Math.log(60 * rate / lag / 120) / Math.log(2), 2));
            if (ac[lag] * w > best) {
                best = ac[lag] * w;
                k = lag;
            }
        }
        // октавная ошибка: бочка на 1 и 3 даёт половинный темп
        while (k / 2 >= lo) {
            int h = Math.max(lo, k / 2 - 2), half = h;
            for (int j = h; j <= k / 2 + 2 && j < ac.length; j++) if (ac[j] > ac[half]) half = j;
            if (ac[half] < OCTAVE_RATIO * ac[k]) break;
            k = half;
        }
        double lag = k;
        if (k > 0 && k < ac.length - 1) {
            double l = ac[k - 1], m = ac[k], r = ac[k + 1], d = l - 2 * m + r;
            if (d != 0) lag += 0.5 * (l - r) / d;
        }
        double b = 60 * rate / lag;
        if (currentBpm > 0 && Math.abs(2 * b / currentBpm - 1) < 0.04) b *= 2;
        if (currentBpm <= 0) {
            currentBpm = b;
        } else if (Math.abs(b / currentBpm - 1) < 0.04) {
            currentBpm = currentBpm * 0.8 + b * 0.2;
            bpmCandidate = 0;
        } else {
            if (bpmCandidate > 0 && Math.abs(b / bpmCandidate - 1) < 0.04) bpmCandidateCount++;
            else {
                bpmCandidate = b;
                bpmCandidateCount = 1;
            }
            if (bpmCandidateCount >= 3) {
                currentBpm = b;
                bpmCandidate = 0;
            }
        }
        bpm = currentBpm;
        // фаза: при каком сдвиге сетка долей сильнее всего совпадает с ударами
        double per = 60 * rate / currentBpm;
        // для фазы бочка весит вдвое: в электронике долю задаёт она, хэты и бас - на офф-битах
        double[] ph = new double[n];
        for (int i = 0; i < n; i++) ph[i] = 2 * env(envKick, i) / (mk + 1e-9) + env(envFull, i) / (mf + 1e-9);
        int bestShift = 0;
        double bestScore = -1;
        for (int shift = 0; shift < (int) per; shift++) {
            double s = 0;
            for (int j = 0; ; j++) {
                int idx = (int) Math.round(n - 1 - shift - j * per);
                if (idx < 0) break;
                s += ph[idx];
            }
            if (s > bestScore) {
                bestScore = s;
                bestShift = shift;
            }
        }
        double lastBeat = env(envTime, n - 1 - bestShift);
        period = 60 / currentBpm;
        double now = streamTime();
        double predicted = lastBeat + period * Math.ceil((now - lastBeat) / period + 1e-9);
        if (nextBeat == null) nextBeat = predicted;
        else {
            double err = predicted - nextBeat;
            err = ((err + period / 2) % period + period) % period - period / 2;
            if (Math.abs(err) > 0.25 * period) {
                // сетка «переехала» на слабую долю (хэты и бас на офф-битах): не усредняем
                // (получилась бы середина между ударами), а ждём, что новая фаза держится 3 оценки
                phaseFlip = Math.abs(err - phaseFlipErr) < 0.1 * period ? phaseFlip + 1 : 1;
                phaseFlipErr = err;
                if (phaseFlip >= 3) {
                    nextBeat += err;
                    phaseFlip = 0;
                }
            } else {
                phaseFlip = 0;
                nextBeat += PHASE_CORRECTION * err;
            }
        }
    }

    private void tickBeats() {
        if (nextBeat == null) return;
        double now = streamTime() + leadSeconds;
        if (now - nextBeat > 2 * period) nextBeat += Math.floor((now - nextBeat) / period) * period;
        while (now >= nextBeat) {
            onBeat(nextBeat - leadSeconds);
            nextBeat += period;
        }
    }

    private Double prevBeatTime;

    private void onBeat(double beatTime) {
        int position = beatCount % BEATS_PER_BAR;
        beatCount++;
        // смена звучания между долями: на первой доле меняются аккорды
        double[] spectrum = beatSpectrum();
        if (spectrum != null && prevBeatSpectrum != null) {
            double nov = 0;
            for (int i = 0; i < 16; i++) nov += Math.abs(spectrum[i] - prevBeatSpectrum[i]);
            nov /= 16;
            int prev = (position - 1 + BEATS_PER_BAR) % BEATS_PER_BAR;
            downbeatScores[prev] = DOWNBEAT_MEMORY * downbeatScores[prev] + (1 - DOWNBEAT_MEMORY) * nov;
        }
        if (spectrum != null) prevBeatSpectrum = spectrum;
        prevBeatTime = beatTime;
        int best = 0;
        for (int i = 1; i < BEATS_PER_BAR; i++) if (downbeatScores[i] > downbeatScores[best]) best = i;
        if (downbeatScores[best] > 1.1 * downbeatScores[downbeat]) downbeat = best;
        beatInBar = ((position - downbeat) % BEATS_PER_BAR + BEATS_PER_BAR) % BEATS_PER_BAR + 1;
        if (beatInBar == 1) {
            if (barStart != null) {
                double length = (beatTime - barStart) / (BEATS_PER_BAR * period);
                if (length > 0.8 && length < 1.2) recognizeBar(barStart, beatTime);
            }
            barStart = beatTime;
            barNo++;
            bar = barNo;
            phrase = (barNo - 1) % BARS_PER_PHRASE + 1;
        }
        beatStamp = System.nanoTime();
        if (listener != null && streamTime() - lastSound < 0.5) listener.onBeat(beatInBar, period, section);
    }

    /** медиана звучания кадров с прошлой доли (удары барабанов в медиану почти не попадают) */
    private double[] beatSpectrum() {
        int m = beatFrames.size();
        if (m < 3) {
            beatFrames.clear();
            return null;
        }
        double[] out = new double[16];
        double[] col = new double[m];
        for (int b = 0; b < 16; b++) {
            for (int i = 0; i < m; i++) col[i] = beatFrames.get(i)[b];
            Arrays.sort(col, 0, m);
            out[b] = col[m / 2];
        }
        beatFrames.clear();
        return out;
    }

    // ------------------------------------------------------------------
    private void recognizeBar(double start, double end) {
        if (streamTime() - lastSound > end - start) return;
        int n = envCount;
        if (n == 0 || env(envTime, 0) > start) return;
        // пики потока по зонам и фон (медиана)
        double[][] flux = new double[3][n];
        for (int z = 0; z < 3; z++) for (int i = 0; i < n; i++) flux[z][i] = env(envZone[z], i);
        double[] background = new double[3];
        double[][] peaks = new double[3][n];
        for (int z = 0; z < 3; z++) {
            double[] s = flux[z].clone();
            Arrays.sort(s);
            background[z] = s[n / 2] + 1e-9;
            for (int i = 0; i < n; i++) {
                double v = flux[z][i];
                boolean isMax = true;
                for (int j = Math.max(0, i - HIT_PEAK_FRAMES); j <= Math.min(n - 1, i + HIT_PEAK_FRAMES); j++)
                    if (flux[z][j] > v) { isMax = false; break; }
                double recent = 0;
                for (int j = i - HIT_RISE_FRAMES; j < i; j++) recent += flux[z][Math.max(0, j)];
                recent /= HIT_RISE_FRAMES;
                peaks[z][i] = isMax && v > HIT_RISE * recent ? v : 0;
            }
        }
        double step = (end - start) / STEPS;
        double[][] strength = new double[3][STEPS];
        for (int i = 0; i < n; i++) {
            int idx = (int) Math.floor((env(envTime, i) - start) / step + 0.5);
            if (idx < 0 || idx >= STEPS) continue;
            for (int z = 0; z < 3; z++) strength[z][idx] = Math.max(strength[z][idx], peaks[z][i]);
        }
        Bar b = new Bar();
        b.grid = new boolean[3][STEPS];
        double peakMax = 0;
        for (int z = 0; z < 3; z++) {
            double mx = 0;
            for (int s = 0; s < STEPS; s++) mx = Math.max(mx, strength[z][s]);
            double thr = Math.max(HIT_RATIO * background[z], HIT_RELATIVE * mx);
            for (int s = 0; s < STEPS; s++) {
                b.grid[z][s] = strength[z][s] > HIT_RATIO * background[z] && strength[z][s] >= thr;
                if (b.grid[z][s]) {
                    b.hits[z]++;
                    peakMax = Math.max(peakMax, strength[z][s] / background[z]);
                }
            }
        }
        float energy = barBandCount > 0 ? (float) (barBandSum / barBandCount) : level;
        barBandSum = 0;
        barBandCount = 0;
        b.energy = energy;
        updateSection(b);
        // всплеск: громкость такта резко выше прошлых или удар намного сильнее обычного
        double prevMean = 0;
        for (float e : burstEnergy) prevMean += e;
        prevMean = burstEnergy.isEmpty() ? 0 : prevMean / burstEnergy.size();
        b.burst = burstEnergy.size() >= 4 && ((energy > BURST_ENERGY * prevMean && energy >= BURST_MIN_ENERGY)
                || (peakAverage > 0 && peakMax > BURST_PEAK * peakAverage));
        burstEnergy.addLast(energy);
        if (burstEnergy.size() > 8) burstEnergy.removeFirst();
        peakAverage += 0.2 * (peakMax - peakAverage);
        b.number = barNo;
        b.phrase = (barNo - 1) % BARS_PER_PHRASE + 1;
        b.bpm = currentBpm;
        if (listener != null) listener.onBar(b);
    }

    private void updateSection(Bar b) {
        int stepBeat = STEPS / BEATS_PER_BAR, kick = 0, low = 0;
        for (int s0 = 0; s0 < stepBeat; s0++) {
            int c = 0;
            for (int s = s0; s < STEPS; s += stepBeat) if (b.grid[0][s]) c++;
            kick = Math.max(kick, c);
        }
        for (int s = 0; s < STEPS; s++) if (b.grid[0][s]) low++;
        trackEnergies.addLast(b.energy);
        if (trackEnergies.size() > 64) trackEnergies.removeFirst();   // ~2 минуты: телефон треки не делит
        int below = 0;
        for (float e : trackEnergies) if (e <= b.energy) below++;
        double loud = (double) below / trackEnergies.size();
        String raw = kick >= SECTION_KICK && loud >= SECTION_LOUD ? "D"
                : (kick <= SECTION_BREAK_KICK || low <= SECTION_BREAK_LOW) ? "B" : "M";
        b.sectionChanged = false;
        if (section == null) section = raw;
        else if (raw.equals(section)) {
            sectionNext = null;
            sectionNextCount = 0;
        } else {
            sectionNextCount = raw.equals(sectionNext) ? sectionNextCount + 1 : 1;
            sectionNext = raw;
            if (sectionNextCount >= SECTION_HOLD) {
                section = raw;
                sectionNext = null;
                sectionNextCount = 0;
                b.sectionChanged = true;
            }
        }
        b.section = section;
    }

    // ------------------------------------------------------------------
    private void analyzeBands() {
        int start = bandPos;
        for (int i = 0; i < FFT_BANDS; i++) bandWork[i] = bandRing[(start + i) % FFT_BANDS];
        fftBands.magnitude(bandWork, 0, winBands, magBands);
        boolean quiet = streamTime() - lastSound > 0.2;
        double maxPeak = 0;
        double[] e = new double[6];
        for (int b = 0; b < 6; b++) {
            double s = 0;
            int c = 0;
            for (int i = bandBins[b][0]; i < bandBins[b][1]; i++, c++) s += magBands[i] * magBands[i];
            e[b] = Math.sqrt(s / Math.max(1, c));
            bandPeaks[b] = Math.max(bandPeaks[b] * BAND_PEAK_DECAY, e[b]);
            maxPeak = Math.max(maxPeak, bandPeaks[b]);
        }
        double sum = 0;
        for (int b = 0; b < 6; b++) {
            double ref = Math.max(bandPeaks[b], maxPeak / BAND_MAX_GAIN);
            double target = ref > 0 ? e[b] / ref : 0;
            if (e[b] < 1e-4 || quiet) target = 0;
            double speed = target > bands[b] ? BAND_ATTACK : BAND_RELEASE;
            bands[b] += (float) ((target - bands[b]) * speed);
            sum += bands[b];
        }
        level = (float) (sum / 6);
        barBandSum += level;
        barBandCount++;
    }
}
