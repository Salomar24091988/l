import socket, sys, threading
port = int(sys.argv[1]); logf = open(sys.argv[2], "w")
LG = open("/tmp/claude-0/diag/lg.txt").read().split("===== > List Layer")[0].split("\n", 1)[1]
FIX = open("/tmp/claude-0/diag3/fix.txt").read(); CHAN = open("/tmp/claude-0/diag3/chan.txt").read()
FORMS = "Executing : List Form\n No. Name\nForm 1 1 Stomp\nForm 2 2 Sin\nForm 3 3 Cos\nForm 4 4 Ramp Plus\nForm 5 5 Ramp Minus\nForm 6 6 Ramp\nForm 7 7 Phase 1\nForm 8 8 Phase 2\nForm 9 9 Phase 3\nForm 10 10 Bump\nForm 11 11 Swing\nForm 12 12 Random\nForm 13 13 PWM\nForm 14 14 Chase\n"
def serve(c):
    c.sendall(b"Welcome to grandMA2\r\n")
    buf = b""
    while True:
        d = c.recv(4096)
        if not d: break
        buf += d
        while b"\r\n" in buf:
            line, buf = buf.split(b"\r\n", 1)
            cmd = line.decode()
            logf.write(cmd + "\n"); logf.flush()
            if cmd.startswith("Login"): r = "Logged in as User 'remote'\r\n"
            elif cmd == "List Group": r = LG
            elif cmd == "List Fixture": r = FIX
            elif cmd == "List Channel": r = CHAN
            elif cmd == "List Form": r = FORMS
            elif cmd.startswith("Assign SpecialMaster"): r = f"Error : {cmd}\r\nError #66: ILLEGAL OBJECT\r\n"
            elif cmd == "Logout": r = "bye\r\n"
            else: r = f"Executing : {cmd}\r\n"
            c.sendall(r.encode())
    c.close()
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(("127.0.0.1", port)); s.listen(5)
while True:
    c, _ = s.accept(); threading.Thread(target=serve, args=(c,), daemon=True).start()
