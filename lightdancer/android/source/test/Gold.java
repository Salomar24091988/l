import com.yan.malight.core.*;
import java.nio.file.*;
import java.util.*;
@SuppressWarnings("unchecked")
public class Gold {
  public static void main(String[] a) throws Exception {
    List<Object> cases = (List<Object>) Json.parse(new String(Files.readAllBytes(Paths.get(a[0])), "UTF-8"));
    int bad = 0, n = 0, cmdsTotal = 0;
    for (Object co : cases) {
      Map<String, Object> c = (Map<String, Object>) co;
      Map<String, Object> cfg = (Map<String, Object>) c.get("cfg");
      Set<String> only = c.get("only") == null ? null : new HashSet<String>((List<String>) (List<?>) c.get("only"));
      FxGen.Result r = FxGen.build(cfg, only, null, (Boolean) c.get("macros"));
      List<Object> want = (List<Object>) c.get("cmds");
      cmdsTotal += r.cmds.size();
      boolean ok = want.equals(new ArrayList<Object>(r.cmds));
      List<Object> wrep = (List<Object>) c.get("report");
      ok &= wrep.size() == r.report.size();
      List<Object> ww = (List<Object>) c.get("warns");
      boolean wok = ww.equals(new ArrayList<Object>(r.warnings));
      if (!ok || !wok) {
        bad++;
        if (bad <= 3) {
          System.out.println("CASE " + n + " cmds ok=" + ok + " warns ok=" + wok);
          for (int i = 0; i < Math.max(want.size(), r.cmds.size()); i++) {
            String x = i < want.size() ? (String) want.get(i) : "<none>", y = i < r.cmds.size() ? r.cmds.get(i) : "<none>";
            if (!x.equals(y)) { System.out.println("  #" + i + " py: " + x + "\n      java: " + y); break; }
          }
          if (!wok) System.out.println("  warns py=" + ww + "\n  java=" + r.warnings);
        }
      }
      n++;
    }
    System.out.println("cases " + n + " bad " + bad + " java cmds " + cmdsTotal);
  }
}
