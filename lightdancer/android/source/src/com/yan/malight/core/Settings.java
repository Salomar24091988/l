package com.yan.malight.core;

import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.LinkedHashMap;
import java.util.Map;

/** Настройки приложения. Имена полей = ключи в хранилище телефона. */
public final class Settings {
    // пульт
    public boolean enabled = false;
    public String host = "10.0.0.12";
    public int port = 30000;
    public String user = "remote";
    public String password = "1234";

    // звук
    public double gain = 1.0;            // чувствительность входа
    public int leadMs = 0;               // опережение долей, мс (задержка Wi-Fi и пульта)

    // раскладка экзекьюторов (как создаёт анализатор на компьютере)
    public int page = 10;
    public String execPulse = "";        // свои экзекьюторы группы через пробел, пусто - page.1-3
    public String execRun = "";          // page.4-6
    public String execFlow = "";         // page.7-9
    public String execSpark = "";        // page.10-12

    // эффекты генератора (страницы 11-15), как ma_fxlink на ПК
    public boolean fxgenOn = true;       // автопилот играет эффекты генератора вместо page.1-12
    public int fxgenPage = 11;
    public String fxgenAssigned = "";    // JSON: что поставлено на экзекьюторы

    // автопилот
    public boolean autopilot = true;
    public boolean chaseOn = true;       // круговой chase page.13/14 на разгонах
    public boolean fxMove = true;        // позиции голов page.30: Go+ по долям
    public double posSmooth = 0.6;
    public boolean fxColor = true;       // цвет page.16-27 и пары page.31-42
    public boolean colorPair = true;
    public boolean fillOn = false;       // заливка page.15
    public int fillBase = 25;
    public int fillPeak = 50;
    public String hold = "";             // ручная группа: пульс / бег / поток / искры / пусто - авто

    // BPM в speed-мастера (SpecialMaster 3.N)
    public boolean bpmOn = true;
    public String bpmMode = "beat";      // beat / section / energy / manual / stop
    public int bpmDiv = 2;
    public double bpmManual = 120;
    public int smDimmer = 1, smPosition = 2, smColor = 3, smStrobe = 4;
    public double xDimmer = 1.0, xPosition = 0.5, xColor = 0.25, xStrobe = 2.0;

    public Map<String, String> toMap() {
        Map<String, String> m = new LinkedHashMap<>();
        for (Field f : Settings.class.getFields()) {
            if (Modifier.isStatic(f.getModifiers())) continue;
            try {
                m.put(f.getName(), String.valueOf(f.get(this)));
            } catch (IllegalAccessException ignored) { }
        }
        return m;
    }

    public void fromMap(Map<String, ?> m) {
        for (Field f : Settings.class.getFields()) {
            if (Modifier.isStatic(f.getModifiers()) || !m.containsKey(f.getName())) continue;
            set(f.getName(), String.valueOf(m.get(f.getName())));
        }
    }

    /** поставить значение из текста; false - не разобралось */
    public boolean set(String name, String value) {
        try {
            Field f = Settings.class.getField(name);
            Class<?> t = f.getType();
            String v = value == null ? "" : value.trim();
            if (t == String.class) f.set(this, v);
            else if (t == int.class) f.setInt(this, (int) Math.round(Double.parseDouble(v.replace(',', '.'))));
            else if (t == double.class) f.setDouble(this, Double.parseDouble(v.replace(',', '.')));
            else if (t == boolean.class) f.setBoolean(this, v.equals("true") || v.equals("1"));
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    public String get(String name) {
        try {
            return String.valueOf(Settings.class.getField(name).get(this));
        } catch (Exception e) {
            return "";
        }
    }
}
