import com.yan.malight.core.*;
import java.util.*;
@SuppressWarnings("unchecked")
public class JobT {
  public static void main(String[] a) throws Exception {
    FxJobs j = new FxJobs("127.0.0.1", Integer.parseInt(a[0]), "remote", "1234");
    FxJobs.Out out = new FxJobs.Out() {
      public void log(String t, boolean e) { System.out.println((e ? "! " : "  ") + t); }
      public void progress(int d, int n) { }
    };
    List<Patch.Group> gs = j.pull(out);
    Map<String,Object> cfg = FxGen.defaultConfig();
    List<Object> list = (List<Object>) cfg.get("groups");
    for (Patch.Group g : gs.subList(0, 3)) {
      Map<String,Object> m = new LinkedHashMap<>(); m.put("id", g.id); m.put("name", g.name); m.put("caps", new ArrayList<Object>(g.caps));
      m.put("size", 20L); m.put("shut_lo", 0L); m.put("shut_hi", 100L); m.put("templates", null); list.add(m);
    }
    FxGen.Result r = FxGen.build(cfg, new HashSet<>(Arrays.asList("dim_chase", "pt_circle", "rgb_rainbow")), null, false);
    System.out.println("effects " + r.report.size() + " cmds " + r.cmds.size());
    long t0 = System.currentTimeMillis();
    int err = j.send(r.cmds, cfg, 0.01, out);
    System.out.println("errors " + err + " in " + (System.currentTimeMillis() - t0) + " ms");
  }
}
