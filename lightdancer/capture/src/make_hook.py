"""Собирает pyi_rth_capture.py: отдельная программа «MA2 → Capture» внутри exe."""
import sys, zipfile
lib, cap, out = sys.argv[1], sys.argv[2], sys.argv[3]
MODS = {"tkinter.ttk": "tkinter/ttk.py", "tkinter.filedialog": "tkinter/filedialog.py",
        "tkinter.messagebox": "tkinter/messagebox.py", "tkinter.commondialog": "tkinter/commondialog.py",
        "tkinter.dialog": "tkinter/dialog.py", "tkinter.simpledialog": "tkinter/simpledialog.py",
        "xml.etree": "xml/etree/__init__.py", "xml.etree.ElementTree": "xml/etree/ElementTree.py",
        "xml.etree.ElementPath": "xml/etree/ElementPath.py"}
z = zipfile.ZipFile(lib)
src = {name: (path.endswith("__init__.py"), z.read(path).decode("utf-8")) for name, path in MODS.items()}
capture = open(cap, encoding="utf-8").read()
hook = f'''# pyi_rth_capture: отдельная программа «MA2 → Capture» (окно ma2_capture), анализатор не запускается
_CAP_FRONT = False
_CAP_SRC = {src!r}
_CAP_MAIN = {capture!r}


def _cap_hide_console():
    try:
        import ctypes
        h = ctypes.windll.kernel32.GetConsoleWindow()
        if h:
            ctypes.windll.user32.ShowWindow(h, 0)
    except Exception:
        pass


def _cap_run():
    import sys, types
    _cap_hide_console()
    from importlib.machinery import ModuleSpec

    class Loader:
        def __init__(self, name):
            self.name = name

        def create_module(self, spec):
            return None

        def exec_module(self, module):
            ispkg, text = _CAP_SRC[self.name]
            module.__file__ = self.name.replace(".", "/") + ("/__init__.py" if ispkg else ".py")
            exec(compile(text, module.__file__, "exec"), module.__dict__)

    class Finder:
        def find_spec(self, name, path=None, target=None):
            if name not in _CAP_SRC:
                return None
            spec = ModuleSpec(name, Loader(name), is_package=_CAP_SRC[name][0])
            if _CAP_SRC[name][0]:
                spec.submodule_search_locations = []
            return spec

    if _CAP_FRONT:
        sys.meta_path.insert(0, Finder())
    else:
        sys.meta_path.append(Finder())
    mod = types.ModuleType("ma2_capture")
    mod.__file__ = "ma2_capture.py"
    sys.modules["ma2_capture"] = mod
    exec(compile(_CAP_MAIN, "ma2_capture.py", "exec"), mod.__dict__)
    mod.make_app().mainloop()


def _cap_fail():
    import os, traceback
    text = "MA2 → Capture не запустилась:\\n\\n" + traceback.format_exc()
    try:
        path = os.path.join(os.environ.get("TEMP", "."), "ma2_capture_error.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text[-1500:], "MA2 → Capture", 0x10)
    except Exception:
        pass


if __name__ != "__cap_test__":
    import os as _cap_os
    try:
        _cap_run()
        _cap_code = 0
    except SystemExit:
        _cap_code = 0
    except BaseException:
        _cap_fail()
        _cap_code = 1
    _cap_os._exit(_cap_code)
'''
open(out, "w", encoding="utf-8").write(hook)
print("hook", len(hook))
