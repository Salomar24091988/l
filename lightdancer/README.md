# LightDancer — снимок версии

«Ian Konsta presents». Снимок от 2026-10-31.

| Папка | Что |
|---|---|
| `pc/` | LightDancer ПК 2026.10.31.3: хук-модули `src/` (ma_bpm, ma_rig, ma_show, ma_palette, ma_wheel, ma_fxlink, ma_pos, ma_colx, ma_brand…), установщик `src/installer.nsi`, запускатель `src/launcher/` (Go), генератор `ma2_fxgen_gui.py` + `core/ma2_fxgen.py`, плагин MA2 `plugins/MovesExec.lua` |
| `capture/` | MA2 → Capture (`src/ma2_capture.py`), готовые файлы шоу `big_fest/` |
| `android/` | LightDancer Android 1.1: исходники `source/` (build.sh, без Gradle), логотип `logo/` |
| `builds/` | готовые сборки: `LightDancer_Setup_2026.10.31.3.exe`, `LightDancer_1.1.apk`, `MA2_Capture_2026.10.31.zip` |

Важно:
- Это облачная копия. На ПК Яна генератор откатан к 2026.10.31.1 + кнопки «Удалить выбранные / Удалить старые», а живые команды MA2 идут через MIDI Show Control. Этих правок здесь нет, их нужно забрать с `D:\l` / `%LOCALAPPDATA%\LightDancer`.
- Ключ подписи Android (`ma_mobile.jks`) в репозиторий не кладём, он лежит в файлах проекта.
- Состояние проекта — в `../STATE.md`.
