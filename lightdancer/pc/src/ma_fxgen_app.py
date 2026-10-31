"""Генератор эффектов MA2 (ma2_fxgen_gui.py) внутри LightDancer.

«LightDancer.exe --fxgen» открывает генератор вместо анализатора: тот же
Python, что внутри анализатора, отдельный Python ставить не нужно.
Файлы генератора лежат в папке программы:
  ma2_fxgen_gui.py - окно генератора (ставится установщиком);
  ma2_fxgen.py     - ядро генератора (свой файл; если его нет - спросим, где он);
  fxgen_lib.zip    - модули стандартной библиотеки Python, которых нет в анализаторе.
В окне анализатора «🎛 grandMA2…» → «FX-ГЕНЕРАТОР» есть кнопка «🎛 Открыть генератор».
"""
import os
import sys

FLAG = "--fxgen"
CORE = "ma2_fxgen.py"
GUI = "ma2_fxgen_gui.py"
LIB = "fxgen_lib.zip"
CORE_NOTE = os.path.join(os.path.expanduser("~"), ".ma2_fxgen_core_path")


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(sys.argv[0] or "."))


def launch():
    """Запускает генератор отдельным процессом (из окна анализатора)."""
    import subprocess
    launcher = os.path.join(app_dir(), "LightDancer.exe")
    if getattr(sys, "frozen", False) and os.path.isfile(launcher):
        # через запускатель: журнал LightDancer_generator_log.txt и окно с причиной, если генератор упадёт
        return subprocess.Popen([launcher, FLAG], cwd=app_dir(), close_fds=True)
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, FLAG]
    else:
        cmd = [sys.executable, os.path.abspath(sys.argv[0]), FLAG]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(cmd, cwd=app_dir(), creationflags=flags, close_fds=True)


def add_stdlib(folder):
    """Недостающие модули stdlib (tkinter.ttk, filedialog, …) - из fxgen_lib.zip."""
    lib = os.path.join(folder, LIB)
    if not os.path.isfile(lib):
        return False
    if lib not in sys.path:
        sys.path.append(lib)
    import tkinter
    sub = os.path.join(lib, "tkinter")
    path = getattr(tkinter, "__path__", None)
    if path is not None and sub not in list(path):
        try:
            path.append(sub)
        except AttributeError:
            tkinter.__path__ = list(path) + [sub]
    return True


def find_core(folder, note=CORE_NOTE):
    places = [os.path.join(folder, CORE)]
    try:
        with open(note, encoding="utf-8") as f:
            places.append(f.read().strip())
    except OSError:
        pass
    places.append(os.path.join(os.path.expanduser("~"), CORE))
    for p in places:
        if p and os.path.isfile(p):
            return p
    return None


def ask_core(folder):
    """Ядра нет рядом - спрашиваем файл и кладём копию в папку программы."""
    import shutil
    import tkinter as tk
    from tkinter import filedialog, messagebox
    root = tk.Tk()
    root.withdraw()
    try:
        if not messagebox.askokcancel(
                "Генератор эффектов MA2",
                "Не нашёл ядро генератора ma2_fxgen.py в папке программы:\n" + folder +
                "\n\nУкажите файл ma2_fxgen.py - я положу копию в папку программы.", parent=root):
            return None
        p = filedialog.askopenfilename(parent=root, title="Где лежит ma2_fxgen.py?",
                                       filetypes=[("ma2_fxgen.py", "ma2_fxgen.py"), ("Python", "*.py")])
        if not p:
            return None
        dst = os.path.join(folder, CORE)
        try:
            if os.path.abspath(p) != os.path.abspath(dst):
                shutil.copy2(p, dst)
            p = dst
        except OSError:
            pass
        try:
            with open(CORE_NOTE, "w", encoding="utf-8") as f:
                f.write(p)
        except OSError:
            pass
        return p
    finally:
        root.destroy()


def load(name, path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def fail(text):
    try:
        with open(os.path.join(app_dir(), "fxgen_error.txt"), "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Генератор эффектов MA2", text[-1800:], parent=root)
        root.destroy()
    except Exception:
        print(text, file=sys.stderr)


def main(folder=None):
    folder = folder or app_dir()
    try:
        add_stdlib(folder)
        if folder not in sys.path:
            sys.path.insert(0, folder)
        gui = os.path.join(folder, GUI)
        if not os.path.isfile(gui):
            fail(f"Нет файла {GUI} в папке программы:\n{folder}\n\nПереустановите LightDancer.")
            return 1
        core = find_core(folder) or ask_core(folder)
        if not core:
            return 1
        sys.path.insert(0, os.path.dirname(core))
        load("ma2_fxgen", core)
        app = load("ma2_fxgen_gui", gui)
        app.App().mainloop()
        return 0
    except SystemExit as e:
        return e.code or 0
    except BaseException:
        import traceback
        fail("Генератор не запустился:\n\n" + traceback.format_exc())
        return 1


def install():
    pass
