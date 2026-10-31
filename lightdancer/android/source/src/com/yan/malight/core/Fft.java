package com.yan.malight.core;

/** Быстрое преобразование Фурье для вещественного сигнала длиной 2^k: модули 0..n/2. */
public final class Fft {
    private final int n;
    private final double[] re, im, cos, sin;
    private final int[] rev;

    public Fft(int n) {
        if (Integer.bitCount(n) != 1) throw new IllegalArgumentException("n = 2^k");
        this.n = n;
        re = new double[n];
        im = new double[n];
        cos = new double[n / 2];
        sin = new double[n / 2];
        for (int i = 0; i < n / 2; i++) {
            cos[i] = Math.cos(-2 * Math.PI * i / n);
            sin[i] = Math.sin(-2 * Math.PI * i / n);
        }
        rev = new int[n];
        int bits = Integer.numberOfTrailingZeros(n);
        for (int i = 0; i < n; i++) rev[i] = Integer.reverse(i) >>> (32 - bits);
    }

    public int size() { return n; }

    /** x[0..n) · окно → mag[0..n/2] (модули спектра) */
    public void magnitude(float[] x, int offset, float[] window, double[] mag) {
        for (int i = 0; i < n; i++) {
            re[rev[i]] = x[offset + i] * window[i];
            im[rev[i]] = 0;
        }
        for (int size = 2; size <= n; size <<= 1) {
            int half = size >> 1, step = n / size;
            for (int start = 0; start < n; start += size) {
                for (int k = 0; k < half; k++) {
                    int a = start + k, b = a + half;
                    double c = cos[k * step], s = sin[k * step];
                    double tr = re[b] * c - im[b] * s, ti = re[b] * s + im[b] * c;
                    re[b] = re[a] - tr;
                    im[b] = im[a] - ti;
                    re[a] += tr;
                    im[a] += ti;
                }
            }
        }
        for (int i = 0; i <= n / 2; i++) mag[i] = Math.sqrt(re[i] * re[i] + im[i] * im[i]);
    }

    public static float[] hann(int n) {
        float[] w = new float[n];
        for (int i = 0; i < n; i++) w[i] = (float) (0.5 - 0.5 * Math.cos(2 * Math.PI * i / (n - 1)));
        return w;
    }
}
