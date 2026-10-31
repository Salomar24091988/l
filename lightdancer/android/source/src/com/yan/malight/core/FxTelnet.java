package com.yan.malight.core;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.nio.charset.Charset;

/** Telnet генератора: команда - ответ (как MA2Telnet в ma2_fxgen.py). Отдельно от автопилота. */
public final class FxTelnet {
    private static final Charset UTF8 = Charset.forName("UTF-8");
    public final String host;
    public final int port;
    private final Socket sock;
    private final InputStream in;
    private final OutputStream out;
    private byte[] eol = {'\r', '\n'};

    public FxTelnet(String host, int port) throws IOException {
        this.host = host;
        this.port = port;
        sock = new Socket();
        sock.setTcpNoDelay(true);
        sock.connect(new InetSocketAddress(host, port), 5000);
        sock.setSoTimeout(50);
        in = sock.getInputStream();
        out = sock.getOutputStream();
    }

    private void write(String line) throws IOException {
        out.write(line.getBytes(UTF8));
        out.write(eol);
        out.flush();
    }

    static String decode(byte[] d, int n) {
        ByteArrayOutputStream o = new ByteArrayOutputStream();
        for (int i = 0; i < n; i++) {
            if ((d[i] & 0xff) == 255 && i + 2 < n) { i += 2; continue; }
            o.write(d[i]);
        }
        return new String(o.toByteArray(), UTF8);
    }

    private static void sleep(double s) {
        try { Thread.sleep((long) (s * 1000)); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
    }

    public String read(double wait) throws IOException {
        sleep(wait);
        ByteArrayOutputStream data = new ByteArrayOutputStream();
        byte[] buf = new byte[4096];
        while (true) {
            try {
                int n = in.read(buf);
                if (n < 0) {
                    if (data.size() == 0) throw new IOException("пульт закрыл соединение");
                    break;
                }
                data.write(buf, 0, n);
            } catch (SocketTimeoutException e) {
                break;
            }
        }
        byte[] d = data.toByteArray();
        return decode(d, d.length);
    }

    public String send(String line, double wait) throws IOException {
        write(line);
        return read(wait);
    }

    /** команда и чтение, пока пульт не замолчит на settle секунд */
    public String query(String line, double settle, double maxWait) throws IOException {
        write(line);
        ByteArrayOutputStream data = new ByteArrayOutputStream();
        byte[] buf = new byte[65536];
        long t0 = System.nanoTime(), last = t0;
        while ((System.nanoTime() - t0) / 1e9 < maxWait) {
            try {
                int n = in.read(buf);
                if (n < 0) break;
                data.write(buf, 0, n);
                last = System.nanoTime();
            } catch (SocketTimeoutException e) {
                double now = System.nanoTime();
                if (data.size() > 0 && (now - last) / 1e9 >= settle) break;
                if (data.size() == 0 && (now - t0) / 1e9 > Math.max(settle * 3, 1.5)) break;
            }
        }
        byte[] d = data.toByteArray();
        return decode(d, d.length);
    }

    /** → null, если вошли; иначе ответ пульта */
    public String login(String user, String password) throws IOException {
        read(1.0);
        String line = "Login \"" + user + "\" \"" + password + "\"";
        String r = send(line, 0.8);
        if (r.toLowerCase().contains("illegal character")) {
            boolean fixed = false;
            for (byte[] e : new byte[][]{{'\r'}, {'\n'}}) {
                eol = e;
                String r2 = send(line, 0.8);
                if (!r2.toLowerCase().contains("illegal character")) {
                    r = r2;
                    fixed = true;
                    break;
                }
            }
            if (!fixed) eol = new byte[]{'\r', '\n'};
        }
        String low = r.toLowerCase();
        if (low.contains("logged in")) return null;
        for (String w : new String[]{"error", "denied", "invalid", "wrong"})
            if (low.contains(w)) return Patch.cleanText(r).trim();
        return null;
    }

    public void close(boolean logout) {
        try { if (logout) send("Logout", 0.2); } catch (IOException ignored) { }
        try { sock.close(); } catch (IOException ignored) { }
    }
}
