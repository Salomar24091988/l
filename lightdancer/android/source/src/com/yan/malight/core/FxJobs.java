package com.yan.malight.core;

import java.io.IOException;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** Работа генератора с пультом: чтение групп и патча, отправка эффектов (как start_send в ma2_fxgen_gui). */
public final class FxJobs {

    public interface Out {
        void log(String text, boolean error);

        void progress(int done, int total);
    }

    public volatile boolean stop;

    private final String host, user, password;
    private final int port;

    public FxJobs(String host, int port, String user, String password) {
        this.host = host;
        this.port = port;
        this.user = user;
        this.password = password;
    }

    private FxTelnet connect() throws IOException {
        FxTelnet ma = new FxTelnet(host, port);
        String bad = ma.login(user, password);
        if (bad != null) {
            ma.close(false);
            throw new IOException("логин не прошёл: " + (bad.length() > 120 ? bad.substring(0, 120) : bad));
        }
        return ma;
    }

    private static String ask(FxTelnet ma, String cmd, double wait) throws IOException {
        return Patch.ownReply(ma.query(cmd, 0.6, wait), cmd);
    }

    /** группы пульта с типами приборов и возможностями */
    public List<Patch.Group> pull(Out out) throws IOException {
        FxTelnet ma = connect();
        try {
            out.progress(0, 4);
            String glist = ask(ma, "List Group", 8);
            out.progress(1, 4);
            String fix = ask(ma, "List Fixture", 15);
            out.progress(2, 4);
            String chan = ask(ma, "List Channel", 10);
            out.progress(3, 4);
            List<Patch.Group> groups = Patch.parseGroupList(glist);
            List<Patch.Fixture> fixtures = Patch.parseFixtureTable(fix + "\n" + chan);
            Patch.applyPatch(groups, fixtures);
            out.log("С пульта: групп " + groups.size() + ", приборов " + fixtures.size(), false);
            if (groups.isEmpty()) out.log("List Group не разобран:\n" + Patch.cleanText(glist).trim(), true);
            out.progress(4, 4);
            return groups;
        } finally {
            ma.close(true);
        }
    }

    /** отправить команды; → число ошибок */
    @SuppressWarnings("unchecked")
    public int send(List<String> cmds, Map<String, Object> cfg, double delay, Out out) throws IOException {
        int errors = 0;
        boolean reconnected = false;
        Set<String> skip = new HashSet<>();
        FxTelnet ma = connect();
        try {
            List<String> missing = new ArrayList<>();
            String raw = ma.query("List Form", 0.5, 6);
            Map<String, Long> forms = FxGen.parseForms(raw, missing);
            if (!forms.isEmpty()) {
                cmds = FxGen.remapForms(cmds, (Map<String, Object>) cfg.get("forms"), forms);
                out.log("Формы с пульта: " + forms, false);
                if (!missing.isEmpty()) out.log("Нет на пульте форм: " + missing + " - номера из конфига", true);
            } else out.log("List Form не разобран - номера форм из конфига", true);
            int i = 0;
            while (i < cmds.size()) {
                if (stop) {
                    out.log("Остановлено", true);
                    break;
                }
                String c = cmds.get(i);
                String kw = c.startsWith("Assign SpecialMaster") && c.contains(" At Effect ") ? "speed" : c.split(" ", 2)[0];
                if (skip.contains(kw)) {
                    out.progress(++i, cmds.size());
                    continue;
                }
                String r;
                try {
                    r = ma.send(c, delay);
                } catch (IOException e) {
                    if (reconnected) throw e;
                    reconnected = true;
                    out.log("Связь оборвалась (" + e.getMessage() + ") - переподключаюсь…", true);
                    ma.close(false);
                    ma = connect();
                    if (!c.startsWith("ClearAll") && !c.startsWith("Group"))
                        while (i > 0 && !cmds.get(i).equals("ClearAll")) i--;
                    continue;
                }
                String own = Patch.ownReply(r, c).toLowerCase();
                boolean bad = own.contains("error") || own.contains("illegal") || own.contains("unknown");
                if (bad && c.startsWith("Delete ")) bad = false;      // пустая ячейка пула - не ошибка
                if (bad) {
                    errors++;
                    String t = Patch.cleanText(Patch.ownReply(r, c)).trim();
                    out.log("ERR " + c + "\n    " + (t.length() > 200 ? t.substring(0, 200) : t), true);
                    if (kw.equals("speed")) {
                        skip.add(kw);
                        out.log("Привязка к SpeedMaster не принята пультом - дальше не отправляю", true);
                    }
                }
                out.progress(++i, cmds.size());
            }
            ma.send("ClearAll", 0.2);
        } finally {
            ma.close(true);
        }
        return errors;
    }
}
