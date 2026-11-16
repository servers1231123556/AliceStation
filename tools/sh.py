import os, sys, paramiko

HOST = os.environ.get("SH_HOST", "192.168.0.90")
PORT = int(os.environ.get("SH_PORT", "2222"))
USER = os.environ.get("SH_USER", "root")
PWD = os.environ.get("SH_PASS", "1")


def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PWD,
              timeout=15, banner_timeout=20, auth_timeout=20,
              look_for_keys=False, allow_agent=False)
    return c


def main():
    args = sys.argv[1:]
    if not args:
        print("usage: sh.py --file <script> | --cmd <cmd> | --push <local> <remote> | --pull <remote> <local>")
        return
    c = connect()
    try:
        if args[0] == "--push":
            local, remote = args[1], args[2]
            with open(local, "rb") as f:
                data = f.read()
            stdin, stdout, stderr = c.exec_command("cat > '%s'" % remote)
            stdin.write(data)
            stdin.channel.shutdown_write()
            rc = stdout.channel.recv_exit_status()
            print("pushed %s -> %s (%d bytes) rc=%d" % (local, remote, len(data), rc))
            return
        if args[0] == "--pull":
            remote, local = args[1], args[2]
            stdin, stdout, stderr = c.exec_command("cat '%s'" % remote)
            data = stdout.read()
            rc = stdout.channel.recv_exit_status()
            with open(local, "wb") as f:
                f.write(data)
            print("pulled %s -> %s (%d bytes) rc=%d" % (remote, local, len(data), rc))
            return
        if args[0] == "--file":
            with open(args[1], "r", encoding="utf-8") as f:
                cmd = f.read()
        else:
            cmd = args[0]
        stdin, stdout, stderr = c.exec_command(cmd, timeout=300)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        rc = stdout.channel.recv_exit_status()
        sys.stdout.buffer.write(out.encode("utf-8", "replace"))
        if err.strip():
            sys.stdout.buffer.write(("\n--- STDERR ---\n" + err).encode("utf-8", "replace"))
        sys.stdout.buffer.write(("\n[exit %s]\n" % rc).encode())
    finally:
        c.close()


main()
