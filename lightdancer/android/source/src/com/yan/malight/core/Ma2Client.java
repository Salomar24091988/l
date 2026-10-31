package com.yan.malight.core;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.Charset;
import java.util.ArrayDeque;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * Telnet к grandMA2 (порт 30000, Setup → Console → Global Settings → Telnet = Login Enabled).
 * Своя очередь команд: команды с ключом (темп, фейдер) заменяют неотправленную прошлую.
 * Обрыв - переподключение каждые 3 с. Конец строки подбирается сам (ILLEGAL CHARACTER).
 */
public final class Ma2Client {

    public interface Log { void line(String text, boolean error); }

    private static final Charset UTF8 = Charset.forName("UTF-8");
    private static final Pattern ANSI = Pattern.compile("\u001b\\[[0-9;?]*[A-Za-z]");

    private final Log log;
    private volatile String host = "";
    private volatile int port = 30000;
    private volatile String user = "remote", password = "1234";
    private volatile boolean enabled;
    private volatile Thread thread;
    private volatile Socket socket;
    public volatile String status = "выключено";
    public volatile boolean online;
    public volatile int sent, errors;
    /** генератор пишет на пульт тем же пользователем - автопилот молчит, чтобы не сбить выбор приборов */
    public volatile boolean paused;

    private final ArrayDeque<String> queue = new ArrayDeque<>();
    private final Map<String, String> keyed = new LinkedHashMap<>();
    private String eol = "\r\n";

    /** вызывается после каждого входа на пульт (заново прислать темп и т.п.) */
    public volatile Runnable listenerOnline;

    public Ma2Client(Log log) { this.log = log; }

    public synchronized void configure(String host, int port, String user, String password, boolean enabled) {
        boolean changed = !host.equals(this.host) || port != this.port || !user.equals(this.user)
                || !password.equals(this.password);
        this.host = host;
        this.port = port;
        this.user = user;
        this.password = password;
        this.enabled = enabled;
        if (changed) closeSocket();
        if (enabled && thread == null) {
            Thread t = new Thread(new Runnable() { @Override public void run() { loop(); } }, "ma2");
            t.setDaemon(true);
            thread = t;
            t.start();
        }
        if (!enabled) {
            closeSocket();
            status = "выключено";
        }
        notifyAll();
    }

    public void stop() {
        enabled = false;
        Thread t = thread;
        thread = null;
        closeSocket();
        synchronized (this) { notifyAll(); }
        if (t != null) t.interrupt();
    }

    /** команда в очередь; key != null - последняя с этим ключом заменяет прошлую неотправленную */
    public synchronized void send(String command, String key) {
        if (!enabled || paused || command == null || command.isEmpty()) return;
        if (key != null) {
            keyed.put(key, command);
        } else {
            if (queue.size() > 200) queue.pollFirst();        // пульт не успевает - старое выкидываем
            queue.addLast(command);
        }
        notifyAll();
    }

    private void closeSocket() {
        Socket s = socket;
        socket = null;
        online = false;
        if (s != null) try { s.close(); } catch (Exception ignored) { }
    }

    private synchronized String next(long waitMs) throws InterruptedException {
        if (queue.isEmpty() && keyed.isEmpty()) wait(waitMs);
        if (!queue.isEmpty()) return queue.pollFirst();
        if (!keyed.isEmpty()) {
            String k = keyed.keySet().iterator().next();
            return keyed.remove(k);
        }
        return null;
    }

    private void loop() {
        while (thread == Thread.currentThread()) {
            if (!enabled || host.isEmpty()) {
                synchronized (this) { try { wait(1000); } catch (InterruptedException e) { return; } }
                continue;
            }
            try {
                status = "подключаюсь к " + host + "…";
                Socket s = new Socket();
                s.setTcpNoDelay(true);
                s.connect(new InetSocketAddress(host, port), 4000);
                s.setSoTimeout(60);
                socket = s;
                InputStream in = s.getInputStream();
                OutputStream out = s.getOutputStream();
                read(in, 800);
                String login = "Login \"" + user + "\"" + (password.isEmpty() ? "" : " \"" + password + "\"");
                write(out, login);
                String r = read(in, 900);
                if (r.toLowerCase().contains("illegal character")) {
                    for (String e : new String[]{"\r", "\n"}) {
                        eol = e;
                        write(out, login);
                        r = read(in, 900);
                        if (!r.toLowerCase().contains("illegal character")) break;
                    }
                }
                String low = r.toLowerCase();
                if (low.contains("error") && !low.contains("logged in")) {
                    status = "пульт не принял логин " + user;
                    log.line("MA2: логин не принят: " + clean(r), true);
                } else {
                    online = true;
                    status = "на связи: " + host;
                    log.line("MA2: подключено " + host + ":" + port + " (" + user + ")", false);
                }
                synchronized (this) { queue.clear(); keyed.clear(); }
                if (listenerOnline != null && online) listenerOnline.run();
                while (socket == s && enabled) {
                    String cmd = next(200);
                    if (cmd != null) {
                        write(out, cmd);
                        sent++;
                        log.line("› " + cmd, false);
                    }
                    String reply = read(in, 0);
                    if (!reply.isEmpty()) {
                        for (String line : clean(reply).split("\n")) {
                            String l = line.trim();
                            if (l.toLowerCase().startsWith("error")) {
                                errors++;
                                log.line("MA2: " + l, true);
                            }
                        }
                    }
                }
                if (enabled) {
                    status = "нет связи с " + host + " - повтор через 3 с";
                    if (online) log.line("MA2: связь потеряна", true);
                }
            } catch (InterruptedException e) {
                return;
            } catch (Exception e) {
                if (enabled) {
                    status = "нет связи с " + host + " - повтор через 3 с";
                    if (online) log.line("MA2: связь потеряна: " + e.getMessage(), true);
                }
            }
            closeSocket();
            if (!enabled) continue;
            synchronized (this) { try { wait(3000); } catch (InterruptedException e) { return; } }
        }
    }

    private void write(OutputStream out, String line) throws java.io.IOException {
        out.write((line + eol).getBytes(UTF8));
        out.flush();
    }

    /** прочитать, что пришло; waitMs - сколько ждать сначала */
    private String read(InputStream in, long waitMs) {
        StringBuilder sb = new StringBuilder();
        byte[] buf = new byte[4096];
        long until = System.currentTimeMillis() + waitMs;
        if (waitMs == 0) {
            // между командами не ждём: забираем только то, что уже пришло
            try { if (in.available() <= 0) return ""; } catch (Exception e) { closeSocket(); return ""; }
        }
        while (true) {
            try {
                int n = in.read(buf);
                if (n < 0) {
                    closeSocket();
                    break;
                }
                for (int i = 0; i < n; i++) {
                    int b = buf[i] & 0xff;
                    if (b == 255 && i + 2 < n) { i += 2; continue; }        // telnet IAC
                    sb.append((char) b);
                }
            } catch (java.net.SocketTimeoutException e) {
                if (System.currentTimeMillis() >= until) break;
            } catch (Exception e) {
                closeSocket();
                break;
            }
        }
        return new String(sb.toString().getBytes(Charset.forName("ISO-8859-1")), UTF8);
    }

    static String clean(String s) { return ANSI.matcher(s).replaceAll("").replace("\r", ""); }
}
