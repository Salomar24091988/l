package com.yan.malight.core;

import java.math.BigDecimal;
import java.math.RoundingMode;

/** То, как Python пишет числа: генератор должен слать на пульт те же строки, что ma2_fxgen.py. */
public final class Py {
    private Py() { }

    /** str(x) для int / float / str */
    public static String str(Object v) {
        if (v == null) return "None";
        if (v instanceof Double || v instanceof Float) {
            double d = ((Number) v).doubleValue();
            if (Double.isNaN(d)) return "nan";
            if (Double.isInfinite(d)) return d > 0 ? "inf" : "-inf";
            if (d == Math.rint(d) && Math.abs(d) < 1e16) return (long) d + ".0";
            String r = Double.toString(d);           // кратчайшее, как repr в Python
            if (r.contains("E")) r = new BigDecimal(r).toPlainString();
            return r;
        }
        if (v instanceof Boolean) return (Boolean) v ? "True" : "False";
        return String.valueOf(v);
    }

    /** float(x) */
    public static double toDouble(Object v) {
        if (v instanceof Number) return ((Number) v).doubleValue();
        if (v instanceof Boolean) return (Boolean) v ? 1 : 0;
        return Double.parseDouble(String.valueOf(v).trim());
    }

    /** int(x) */
    public static long toLong(Object v) {
        if (v instanceof Number) {
            double d = ((Number) v).doubleValue();
            return (long) d;                         // int() отбрасывает дробную часть
        }
        if (v instanceof Boolean) return (Boolean) v ? 1 : 0;
        return Long.parseLong(String.valueOf(v).trim());
    }

    /** round(x, 2) - банковское округление Python по точному двоичному значению */
    public static double round2(double v) {
        return new BigDecimal(v).setScale(2, RoundingMode.HALF_EVEN).doubleValue();
    }

    /** ma2_fxgen.num: round(float(v), 2) → int, если целое */
    public static Object num(Object v) {
        double d = round2(toDouble(v));
        if (d == Math.rint(d)) return (long) d;
        return d;
    }

    /** «пусто» в смысле layer.get(k) not in (None, "") */
    public static boolean given(Object v) {
        return v != null && !"".equals(v);
    }

    /** bool(x) */
    public static boolean truthy(Object v) {
        if (v == null) return false;
        if (v instanceof Boolean) return (Boolean) v;
        if (v instanceof Number) return ((Number) v).doubleValue() != 0;
        if (v instanceof String) return !((String) v).isEmpty();
        if (v instanceof java.util.Collection) return !((java.util.Collection<?>) v).isEmpty();
        if (v instanceof java.util.Map) return !((java.util.Map<?, ?>) v).isEmpty();
        return true;
    }

    /** a == b по-питоновски для чисел (1 == 1.0) и строк */
    public static boolean eq(Object a, Object b) {
        if (a instanceof Number && b instanceof Number)
            return ((Number) a).doubleValue() == ((Number) b).doubleValue();
        return a == null ? b == null : a.equals(b);
    }

    /** f-строка с первыми n символами (срез [:n] по символам, не по UTF-16) */
    public static String cut(String s, int n) {
        if (s.codePointCount(0, s.length()) <= n) return s;
        return s.substring(0, s.offsetByCodePoints(0, n));
    }
}
