import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("72.60.150.220", username="root", password="Zqkwdaz10011&", timeout=30)

def run(cmd, timeout=90):
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    return out.strip(), err.strip()

print("=== Containers ===")
out, _ = run("docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'")
print(out)

print("\n=== Networks ===")
out, _ = run("docker network ls")
print(out)

print("\n=== Compose files ===")
out, _ = run("find /root /opt /srv -name 'docker-compose.yml' 2>/dev/null")
print(out)

print("\n=== Portas ===")
out, _ = run("ss -tlnp | grep LISTEN")
print(out)

print("\n=== Disco ===")
out, _ = run("df -h /")
print(out)

print("\n=== Tools ===")
out, _ = run("git --version; docker compose version")
print(out)

client.close()
print("\nDone.")
