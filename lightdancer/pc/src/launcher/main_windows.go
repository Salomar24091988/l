// LightDancer.exe - запуск анализатора (LightDancer_app.exe) из папки программы.
//
//   - временные файлы программы - в папке программы\tmp (не на диске C:), старые
//     распаковки _MEI* оттуда убираются;
//   - окно консоли анализатора скрыто, всё, что он пишет, - в LightDancer_log.txt
//     (генератор --fxgen - LightDancer_generator_log.txt, Capture - LightDancer_capture_log.txt);
//     если анализатор закрылся с ошибкой, показывается окно с концом журнала;
//   - «--console» - то же с видимой консолью, которая не закрывается после выхода.
package main

import (
	"bytes"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

const (
	appTitle  = "LightDancer"
	logName   = "LightDancer_log.txt"
	logLimit  = 5 << 20
	tailLimit = 6000
)

var appNames = []string{"LightDancer_app.exe", "MusicAnalyzer_app.exe"}

func message(text string, icon uintptr) {
	user32 := syscall.NewLazyDLL("user32.dll")
	box := user32.NewProc("MessageBoxW")
	t, _ := syscall.UTF16PtrFromString(text)
	c, _ := syscall.UTF16PtrFromString(appTitle)
	box.Call(0, uintptr(unsafe.Pointer(t)), uintptr(unsafe.Pointer(c)), icon)
}

const (
	mbIconError   = 0x10
	mbIconWarning = 0x30
)

func cleanTemp(tmp string) {
	old, _ := filepath.Glob(filepath.Join(tmp, "_MEI*"))
	for _, d := range old {
		st, err := os.Stat(d)
		// распаковки работающих окон не трогаем: только те, что старше 12 часов
		if err == nil && st.IsDir() && time.Since(st.ModTime()) > 12*time.Hour {
			os.RemoveAll(d)
		}
	}
}

// tailWriter: пишет в файл до logLimit и помнит конец вывода для окна ошибки
type tailWriter struct {
	f       *os.File
	written int
	tail    []byte
}

func (w *tailWriter) Write(p []byte) (int, error) {
	if w.f != nil && w.written < logLimit {
		n, _ := w.f.Write(p)
		w.written += n
	}
	w.tail = append(w.tail, p...)
	if len(w.tail) > tailLimit {
		w.tail = append([]byte(nil), w.tail[len(w.tail)-tailLimit:]...)
	}
	return len(p), nil
}

func quote(s string) string {
	if s == "" || strings.ContainsAny(s, " \t\"") {
		return `"` + strings.ReplaceAll(s, `"`, `\"`) + `"`
	}
	return s
}

func main() {
	self, err := os.Executable()
	if err != nil {
		message("Не найден путь программы: "+err.Error(), mbIconError)
		os.Exit(1)
	}
	dir := filepath.Dir(self)
	os.Chdir(dir)

	app := ""
	for _, n := range appNames {
		if st, err := os.Stat(filepath.Join(dir, n)); err == nil && !st.IsDir() {
			app = filepath.Join(dir, n)
			break
		}
	}
	if app == "" {
		message("В папке программы нет "+appNames[0]+":\n"+dir+"\n\nПереустановите LightDancer.", mbIconError)
		os.Exit(1)
	}

	tmp := filepath.Join(dir, "tmp")
	os.MkdirAll(tmp, 0o755)
	cleanTemp(tmp)
	env := append(os.Environ(), "TMP="+tmp, "TEMP="+tmp)

	console := false
	var args []string
	for _, a := range os.Args[1:] {
		if a == "--console" {
			console = true
			continue
		}
		args = append(args, a)
	}

	if console {
		// своя консоль через cmd /k: после выхода окно остаётся, ошибку видно
		line := quote(app)
		for _, a := range args {
			line += " " + quote(a)
		}
		cmd := exec.Command(os.Getenv("ComSpec"))
		if cmd.Path == "" {
			cmd = exec.Command("cmd.exe")
		}
		cmd.Dir = dir
		cmd.Env = env
		cmd.SysProcAttr = &syscall.SysProcAttr{
			CmdLine:       `cmd.exe /k "` + line + `"`,
			CreationFlags: 0x00000010, // CREATE_NEW_CONSOLE
		}
		if err := cmd.Start(); err != nil {
			message("Не запустился "+filepath.Base(app)+":\n"+err.Error(), mbIconError)
			os.Exit(1)
		}
		return
	}

	// генератор и Capture - свой журнал, чтобы не затереть журнал работающего анализатора
	name, what := logName, "LightDancer"
	for _, a := range args {
		switch a {
		case "--fxgen":
			if name == logName {
				name, what = "LightDancer_generator_log.txt", "Генератор эффектов"
			}
		case "--capture":
			name, what = "LightDancer_capture_log.txt", "Перенос в Capture"
		}
	}
	logPath := filepath.Join(dir, name)
	f, _ := os.Create(logPath)
	out := &tailWriter{f: f}
	if f != nil {
		fmt.Fprintf(f, "%s  запуск %s %s\r\n", time.Now().Format("2006-01-02 15:04:05"), filepath.Base(app), strings.Join(args, " "))
	}
	cmd := exec.Command(app, args...)
	cmd.Dir = dir
	cmd.Env = env
	cmd.Stdout = io.Writer(out)
	cmd.Stderr = io.Writer(out)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	start := time.Now()
	if err := cmd.Start(); err != nil {
		message("Не запустился "+filepath.Base(app)+":\n"+err.Error(), mbIconError)
		os.Exit(1)
	}
	err = cmd.Wait()
	code := 0
	if cmd.ProcessState != nil {
		code = cmd.ProcessState.ExitCode()
	}
	if f != nil {
		fmt.Fprintf(f, "\r\n%s  выход, код %d, работал %s\r\n", time.Now().Format("2006-01-02 15:04:05"), code,
			time.Since(start).Round(time.Second))
		f.Close()
	}
	// генератор сам показал окно с ошибкой (fxgen_error.txt) - второе не нужно
	if st, e := os.Stat(filepath.Join(dir, "fxgen_error.txt")); e == nil && st.ModTime().After(start) {
		os.Exit(code)
	}
	if code != 0 || (err != nil && code == 0 && cmd.ProcessState == nil) {
		tail := strings.TrimSpace(string(bytes.ToValidUTF8(out.tail, []byte("?"))))
		if len(tail) > 1500 {
			tail = "…" + tail[len(tail)-1500:]
		}
		if tail == "" {
			tail = "(анализатор ничего не написал)"
		}
		message(fmt.Sprintf("%s закрылся с ошибкой (код %d).\n\n%s\n\nПолный журнал: %s", what, code, tail, logPath),
			mbIconWarning)
		os.Exit(code)
	}
}
