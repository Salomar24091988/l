MA2_Capture.exe - отдельная программа «MA2 → Capture» (не зависит от MusicAnalyzer).
Сборка: python make_hook.py fxgen_lib.zip ma2_capture.py pyi_rth_capture.py,
затем скрипт pyi_rth_capture вставляется в копию MusicAnalyzer_app.exe перед pyi_rth_wheel
(функции read/write из music_analyzer_wheel/src/inject.py, Python 3.13 для marshal).
Недостающие модули (tkinter.ttk/filedialog/messagebox, xml.etree) встроены в скрипт.
