Unicode true
SetCompressor /SOLID lzma
!include "MUI2.nsh"
!include "LogicLib.nsh"

!define APP "LightDancer"
!define OLDAPP "MusicAnalyzer"
!define VERSION "2026.10.31.3"
!define UNINST "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP}"

Name "${APP}"
OutFile "LightDancer_Setup.exe"
InstallDir "$LOCALAPPDATA\${APP}"
InstallDirRegKey HKCU "Software\${APP}" "InstallDir"
RequestExecutionLevel user
BrandingText "${APP} ${VERSION} - Ian Konsta presents"
VIProductVersion "${VERSION}"
VIAddVersionKey "ProductName" "${APP}"
VIAddVersionKey "CompanyName" "Ian Konsta"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "FileDescription" "${APP} - установка"

!define MUI_ICON "LightDancer.ico"
!define MUI_UNICON "LightDancer.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\LightDancer.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Запустить LightDancer"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Russian"

!macro KillAll
  nsExec::Exec 'taskkill /F /IM LightDancer_app.exe'
  nsExec::Exec 'taskkill /F /IM LightDancer.exe'
  nsExec::Exec 'taskkill /F /IM MusicAnalyzer_app.exe'
  nsExec::Exec 'taskkill /F /IM MusicAnalyzer.exe'
  nsExec::Exec 'taskkill /F /IM ma_core.exe'
!macroend

Var OldDir
Var OldAutostart

; бывший MusicAnalyzer: данные - в новую папку, программу, ярлыки и запись в «Удалении программ» - убрать
Function MoveFromOld
  StrCpy $OldDir "$LOCALAPPDATA\${OLDAPP}"
  ReadRegStr $0 HKCU "Software\${OLDAPP}" "InstallDir"
  ${If} $0 != ""
    StrCpy $OldDir $0
  ${EndIf}
  StrCpy $OldAutostart 0
  ${If} ${FileExists} "$SMSTARTUP\${OLDAPP}.lnk"
    StrCpy $OldAutostart 1
  ${EndIf}
  ${IfNot} ${FileExists} "$OldDir\*.*"
    Return
  ${EndIf}
  DetailPrint "Переезд из $OldDir"
  ${If} $OldDir != $INSTDIR
  ${AndIfNot} ${FileExists} "$INSTDIR\grandma2.json"
    CopyFiles /SILENT "$OldDir\*.json" "$INSTDIR"
    CopyFiles /SILENT "$OldDir\*.db*" "$INSTDIR"
    CopyFiles /SILENT "$OldDir\*_log.txt" "$INSTDIR"
    CopyFiles /SILENT "$OldDir\*.lua" "$INSTDIR"
    ${If} ${FileExists} "$OldDir\ma2_fxgen.py"
      CopyFiles /SILENT "$OldDir\ma2_fxgen.py" "$INSTDIR"
    ${EndIf}
  ${EndIf}
  ; старая программа (данные в старой папке остаются копией)
  Delete "$OldDir\MusicAnalyzer.exe"
  Delete "$OldDir\MusicAnalyzer_app.exe"
  Delete "$OldDir\MusicAnalyzer.ico"
  Delete "$OldDir\Uninstall.exe"
  ${If} $OldDir != $INSTDIR
    Delete "$OldDir\ma_core.exe"
    Delete "$OldDir\ma2_fxgen_gui.py"
    Delete "$OldDir\fxgen_lib.zip"
    Delete "$OldDir\ma2_capture.py"
    Delete "$OldDir\README.txt"
    Delete "$OldDir\ИЗМЕНЕНИЯ.txt"
    RMDir /r "$OldDir\tmp"
    FileOpen $1 "$OldDir\Программа переехала в LightDancer.txt" w
    FileWriteWord $1 0xFEFF
    FileWriteUTF16LE $1 "MusicAnalyzer теперь называется LightDancer: $INSTDIR$\r$\n"
    FileWriteUTF16LE $1 "Настройки и база скопированы туда. Эта папка - старая копия данных, её можно удалить.$\r$\n"
    FileClose $1
  ${EndIf}
  Delete "$DESKTOP\${OLDAPP}.lnk"
  Delete "$DESKTOP\Генератор эффектов MA2.lnk"
  Delete "$DESKTOP\Перенос MA2 в Capture.lnk"
  Delete "$SMSTARTUP\${OLDAPP}.lnk"
  RMDir /r "$SMPROGRAMS\${OLDAPP}"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${OLDAPP}"
  DeleteRegKey HKCU "Software\${OLDAPP}"
FunctionEnd

Function CloseApp
  nsExec::ExecToStack 'cmd /c tasklist /NH | findstr /I "MusicAnalyzer_app.exe LightDancer_app.exe"'
  Pop $0
  ${If} $0 == 0
    MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION "LightDancer (MusicAnalyzer) сейчас запущен. Закрыть его и продолжить?" IDOK close
    Abort
    close:
  ${EndIf}
  !insertmacro KillAll
  Sleep 700
FunctionEnd

Function .onInit
  Call CloseApp
FunctionEnd

Section "LightDancer (программа)" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"
  Call MoveFromOld
  SetOverwrite on
  File "LightDancer.exe"
  File "LightDancer_app.exe"
  File "ma_core.exe"
  File "LightDancer.ico"
  File "README.txt"
  File "ИЗМЕНЕНИЯ.txt"
  ; генератор эффектов MA2: окно, ядро и недостающие модули Python
  File "ma2_fxgen_gui.py"
  File "fxgen_lib.zip"
  ; перенос патча MA2 в визуализатор Capture (окно по --fxgen --capture)
  File "ma2_capture.py"
  ; ядро: своё, поправленное позже, не затираем
  SetOverwrite ifnewer
  File "ma2_fxgen.py"
  SetOverwrite on
  ; данные: только если их ещё нет - переустановка базу и настройки не затирает
  SetOverwrite off
  File "music_patterns.db"
  File "grandma2.json"
  File "audio_sync.json"
  File "wled_static.json"
  SetOverwrite on
  CreateDirectory "$INSTDIR\tmp"

  CreateDirectory "$SMPROGRAMS\${APP}"
  CreateShortcut "$SMPROGRAMS\${APP}\LightDancer.lnk" "$INSTDIR\LightDancer.exe" "" "$INSTDIR\LightDancer.ico"
  CreateShortcut "$SMPROGRAMS\${APP}\LightDancer (с консолью).lnk" "$INSTDIR\LightDancer.exe" "--console" "$INSTDIR\LightDancer.ico"
  CreateShortcut "$SMPROGRAMS\${APP}\Генератор эффектов MA2.lnk" "$INSTDIR\LightDancer.exe" "--fxgen" "$INSTDIR\LightDancer.ico"
  CreateShortcut "$SMPROGRAMS\${APP}\Перенос MA2 в Capture.lnk" "$INSTDIR\LightDancer.exe" "--fxgen --capture" "$INSTDIR\LightDancer.ico"
  CreateShortcut "$SMPROGRAMS\${APP}\Папка с данными.lnk" "$INSTDIR"
  CreateShortcut "$SMPROGRAMS\${APP}\Удалить LightDancer.lnk" "$INSTDIR\Uninstall.exe"

  ${If} $OldAutostart == 1
    CreateShortcut "$SMSTARTUP\LightDancer.lnk" "$INSTDIR\LightDancer.exe" "" "$INSTDIR\LightDancer.ico"
  ${EndIf}
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\${APP}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${UNINST}" "DisplayName" "${APP}"
  WriteRegStr HKCU "${UNINST}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST}" "DisplayIcon" "$INSTDIR\LightDancer.ico"
  WriteRegStr HKCU "${UNINST}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKCU "${UNINST}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST}" "NoRepair" 1
SectionEnd

Section "Ярлык на рабочем столе" SecDesktop
  CreateShortcut "$DESKTOP\LightDancer.lnk" "$INSTDIR\LightDancer.exe" "" "$INSTDIR\LightDancer.ico"
  CreateShortcut "$DESKTOP\Генератор эффектов MA2.lnk" "$INSTDIR\LightDancer.exe" "--fxgen" "$INSTDIR\LightDancer.ico"
  CreateShortcut "$DESKTOP\Перенос MA2 в Capture.lnk" "$INSTDIR\LightDancer.exe" "--fxgen --capture" "$INSTDIR\LightDancer.ico"
SectionEnd

Section /o "Запускать вместе с Windows" SecAutostart
  CreateShortcut "$SMSTARTUP\LightDancer.lnk" "$INSTDIR\LightDancer.exe" "" "$INSTDIR\LightDancer.ico"
SectionEnd

Function un.onInit
  nsExec::Exec 'taskkill /F /IM LightDancer_app.exe'
  nsExec::Exec 'taskkill /F /IM LightDancer.exe'
  nsExec::Exec 'taskkill /F /IM ma_core.exe'
FunctionEnd

Section "Uninstall"
  Delete "$INSTDIR\LightDancer.exe"
  Delete "$INSTDIR\LightDancer_log.txt"
  Delete "$INSTDIR\LightDancer_generator_log.txt"
  Delete "$INSTDIR\LightDancer_capture_log.txt"
  Delete "$INSTDIR\LightDancer_app.exe"
  Delete "$INSTDIR\ma_core.exe"
  Delete "$INSTDIR\LightDancer.ico"
  Delete "$INSTDIR\README.txt"
  Delete "$INSTDIR\ИЗМЕНЕНИЯ.txt"
  Delete "$INSTDIR\ma2_fxgen_gui.py"
  Delete "$INSTDIR\fxgen_lib.zip"
  Delete "$INSTDIR\ma2_capture.py"
  Delete "$DESKTOP\Перенос MA2 в Capture.lnk"
  Delete "$INSTDIR\fxgen_error.txt"
  Delete "$DESKTOP\Генератор эффектов MA2.lnk"
  RMDir /r "$INSTDIR\tmp"
  Delete "$DESKTOP\LightDancer.lnk"
  Delete "$SMSTARTUP\LightDancer.lnk"
  RMDir /r "$SMPROGRAMS\${APP}"
  MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON2 "Удалить и данные: базу паттернов, настройки grandMA2 / WLED и журналы?" IDNO keep
    Delete "$INSTDIR\music_patterns.db"
    Delete "$INSTDIR\grandma2.json"
    Delete "$INSTDIR\audio_sync.json"
    Delete "$INSTDIR\wled_static.json"
    Delete "$INSTDIR\ma2_fxgen.py"
    Delete "$INSTDIR\*.txt"
    Delete "$INSTDIR\*.old"
  keep:
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "${UNINST}"
  DeleteRegKey HKCU "Software\${APP}"
SectionEnd
