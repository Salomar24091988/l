import sys, json, os, time
sys.path.insert(0, os.getcwd())
import fake_ma, ma_wheel, ma_fxlink, ma_rig, ma_palette, ma_show
ma_wheel.install(); ma_fxlink.install(); ma_rig.install(); ma_palette.install(); ma_show.install()
import grandma2 as g, music_gui as mg
json.dump({"enabled": False, "host": "10.0.0.12"}, open(g.SETTINGS_FILE, "w"))
ctl = g.MA2Control(None)
class A:
    def __getattr__(self, k): return None
a = A(); a.ma2 = ctl; a.track = None; a.families = {}; a.patterns = []; a.section = None; a.family = None
import tkinter as tk
root = tk.Tk()
def pump():
    t=time.time()
    while time.time()-t<1.2:
        root.update(); time.sleep(0.05)
w = mg.MA2Window(root, a); root.update()
w.win.geometry("700x450+0+0"); root.withdraw(); root.update(); pump()
os.system("import -window root /tmp/claude-0/x/gui/shot_scroll_ma2.png")
# колесо
c = [cv for cv, b in ma_wheel._SCROLL_AREAS][0]
print("ma2 view before", c.yview())
c.event_generate("<Button-5>", x=10, y=10); root.update()
ev = type("E", (), {"widget": c, "num": 5, "delta": 0, "state": 0})()
ma_wheel._on_wheel(ev); root.update(); print("after wheel", c.yview())
r = mg.RigWindow(w); root.update()
r.win.geometry("600x400+0+0"); w.win.withdraw(); root.update(); pump()
os.system("import -window root /tmp/claude-0/x/gui/shot_scroll_rig.png")
s = mg.ShowWindow(r); root.update()
s.win.geometry("500x300+0+0"); r.win.withdraw(); root.update(); pump()
os.system("import -window root /tmp/claude-0/x/gui/shot_scroll_show.png")
print("areas", len(ma_wheel._SCROLL_AREAS))
print("OK")
for cv, b in ma_wheel._SCROLL_AREAS:
    h = cv.master
    print("win", cv.winfo_toplevel().winfo_width(), cv.winfo_toplevel().winfo_height(), "holder", h.winfo_width(), h.winfo_height(),
          "canvas", cv.winfo_width(), cv.winfo_height(), "body req", b.winfo_reqwidth(), b.winfo_reqheight(),
          "slaves", [ (s.winfo_class(), s.winfo_ismapped()) for s in h.grid_slaves()])
