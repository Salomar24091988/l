#!/bin/sh
# Сборка LightDancer APK без Gradle. Нужны: openjdk (javac), aapt, dalvik-exchange (dx), zipalign, apksigner,
# android.jar платформы 23 (Debian/Ubuntu: apt install aapt zipalign apksigner dalvik-exchange android-sdk-platform-23).
set -e
cd "$(dirname "$0")"
AJ=${ANDROID_JAR:-/usr/lib/android-sdk/platforms/android-23/android.jar}
KS=${KEYSTORE:-../keystore/ma_mobile.jks}
OUT=${OUT:-LightDancer.apk}
export JAVA_TOOL_OPTIONS=
rm -rf build && mkdir -p build/classes
javac -source 8 -target 8 -nowarn -Xlint:-options -encoding UTF-8 -bootclasspath "$AJ" -d build/classes $(find src -name '*.java')
dalvik-exchange --dex --output=build/classes.dex build/classes
aapt package -f -M AndroidManifest.xml -S res -I "$AJ" -F build/u.apk
(cd build && zip -q u.apk classes.dex)
zipalign -f 4 build/u.apk build/a.apk
apksigner sign --ks "$KS" --ks-pass pass:malight123 --key-pass pass:malight123 --out "$OUT" build/a.apk
echo "готово: $OUT"
