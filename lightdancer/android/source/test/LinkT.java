package com.yan.malight.core;
import java.util.*;
@SuppressWarnings("unchecked")
public class LinkT {
  public static void main(String[] a) throws Exception {
    Map<String,Object> cfg = FxGen.defaultConfig();
    List<Object> gs = (List<Object>) cfg.get("groups");
    String[][] defs = {{"1","Spot A","dim pt rgb"},{"2","Spot B","dim pt rgb"},{"3","Wash","dim rgb"},{"4","Blinder","dim"}};
    for (String[] d : defs) {
      Map<String,Object> m = new LinkedHashMap<>(); m.put("id", Long.parseLong(d[0])); m.put("name", d[1]);
      m.put("caps", new ArrayList<Object>(Arrays.asList(d[2].split(" ")))); m.put("size", 20L); m.put("shut_lo", 0L);
      m.put("shut_hi", 100L); m.put("count", 6L); m.put("templates", null); gs.add(m);
    }
    FxGen.Result r = FxGen.build(cfg, null, null, true);
    System.err.println(Patch.phaseCopies(r, gs, 500));
    List<Object> looks = FxLink.looks(r);
    Settings s = new Settings();
    FxLink.Script sc = FxLink.assignScript(looks, 11, s);
    Map<String,Object> out = new LinkedHashMap<>();
    out.put("looks", looks); out.put("cmds", sc.cmds); out.put("assigned", sc.assigned);
    System.out.println(Json.write(out));
    // автопилот
    s.fxgenAssigned = Json.write(sc.assigned);
    Director d = new Director(s, null, null);
    for (String g : FxLink.GROUPS) for (int v = 0; v < 3; v++) System.err.println(g + " " + v + " → " + d.fxExec(g, v) + "  " + Director.execList(d.fxExec(g, v)));
    System.err.println("круг → " + d.fxExec("круг", 0));
    s.fxgenOn = false;
    System.err.println("выкл: пульс → " + d.fxExec("пульс", 0));
    System.err.println("used " + Arrays.toString(FxLink.usedPerPage(sc.assigned, 11)));
  }
}
