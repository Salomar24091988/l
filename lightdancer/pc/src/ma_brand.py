"""LightDancer: имя и иконка окон.

Анализатор собран под старым именем: окно называлось «Music analyzer», иконка
стандартная tkinter. Здесь все окна программы получают иконку LightDancer.ico
из папки программы, а заголовок анализатора - «LightDancer».
"""
import os
import sys

TITLE = "LightDancer — Ian Konsta presents"
OLD_TITLES = ("Music analyzer", "MusicAnalyzer")


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(sys.argv[0] or "."))


def rename(text):
    if isinstance(text, str):
        for old in OLD_TITLES:
            if text.startswith(old):
                return TITLE + text[len(old):]
    return text


def install():
    import tkinter as tk
    ico = os.path.join(app_dir(), "LightDancer.ico")

    wm_title = tk.Wm.wm_title

    def title(self, string=None):
        return wm_title(self, rename(string))

    tk.Wm.wm_title = title
    tk.Wm.title = title

    tk_init = tk.Tk.__init__

    def init(self, *a, **k):
        tk_init(self, *a, **k)
        if os.path.isfile(ico):
            try:
                self.iconbitmap(default=ico)        # default - и для всех Toplevel
            except Exception:
                pass

    tk.Tk.__init__ = init
