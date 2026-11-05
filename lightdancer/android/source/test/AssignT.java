package com.yan.malight.core;
import java.util.*;
@SuppressWarnings("unchecked")
public class AssignT {
  public static void main(String[] a) throws Exception {
    int port = Integer.parseInt(a[0]);
    FxJobs.Out out = new FxJobs.Out() {
      public void log(String t, boolean e) { if (e) System.out.println("! " + t.split("\n")[0]); }
      public void progress(int d, int n) { }
    };
    FxJobs j = new FxJobs("127.0.0.1", port, "remote", "1234");
    List<Patch.Group> gs = j.pull(out);
    Map<String,Object> cfg = FxGen.defaultConfig();
    List<Object> list = (List<Object>) cfg.get("groups");
    for (Patch.Group g : gs.subList(0, 4)) {
      Map<String,Object> m = new LinkedHashMap<>(); m.put("id", g.id); m.put("name", g.name); m.put("caps", new ArrayList<Object>(g.caps));
      m.put("size", 20L); m.put("shut_lo", 0L); m.put("shut_hi", 100L); m.put("templates", null); list.add(m);
    }
    FxGen.Result r = FxGen.build(cfg, new HashSet<>(Arrays.asList("dim_chase", "pt_circle", "rgb_rainbow", "dim_strobe")), null, false);
    System.out.println(Patch.phaseCopies(r, list, 500));
    int err = new FxJobs("127.0.0.1", port, "remote", "1234").send(r.cmds, cfg, 0.0, out);
    System.out.println("create: effects " + r.report.size() + " cmds " + r.cmds.size() + " errors " + err);
    List<Object> looks = FxLink.looks(r);
    Settings s = new Settings();
    FxLink.Script sc = FxLink.assignScript(looks, 11, s);
    err = new FxJobs("127.0.0.1", port, "remote", "1234").send(sc.cmds, FxGen.defaultConfig(), 0.0, out);
    System.out.println("assign: looks " + looks.size() + " cmds " + sc.cmds.size() + " errors " + err);
    s.fxgenAssigned = Json.write(sc.assigned);
    Ma2Client ma = new Ma2Client(new Ma2Client.Log() { public void line(String t, boolean e) { } });
    ma.configure("127.0.0.1", port, "remote", "1234", true);
    for (int i = 0; i < 50 && !ma.online; i++) Thread.sleep(100);
    Director d = new Director(s, ma, null);
    String e1 = d.fxExec("пульс", 0), e2 = d.fxExec("бег", 1);
    d.switchTo(e1, null); d.switchTo(e2, e1);
    Thread.sleep(800);
    System.out.println("online " + ma.online + " pulse " + e1 + " run " + e2);
    System.exit(0);
  }
}
