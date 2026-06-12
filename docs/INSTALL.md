# Installing ArenaFlow

Linux with Docker is the preferred production setup. Windows is supported for testing and small installs through Docker Desktop, but Linux is usually easier to keep running on a server.

## Linux Server Install

### 1. Install Docker

Install Docker Engine and Docker Compose using the official packages for your Linux distribution.

Confirm Docker is working:

```bash
docker --version
docker compose version
```

Some older systems use the legacy command:

```bash
docker-compose --version
```

ArenaFlow works with either command. Use `docker compose` where available.

### 2. Download ArenaFlow

```bash
sudo mkdir -p /opt/arenaflow
sudo chown "$USER:$USER" /opt/arenaflow
git clone https://github.com/kjsupe/arenaflow.git /opt/arenaflow
cd /opt/arenaflow
```

If you downloaded a zip file instead, extract it into `/opt/arenaflow`.

### 3. Create Environment Settings

```bash
cp .env.example .env
nano .env
```

Set these values:

```text
APP_PORT=8080
LASERTAG_DB_PASSWORD=replace-with-a-strong-database-password
LASERTAG_SECRET=replace-with-a-long-random-secret
POSTGRES_VOLUME_NAME=arenaflow-postgres-data
```

Generate a strong secret with:

```bash
openssl rand -base64 48
```

If port `8080` is already used by another app, set `APP_PORT` to a different open port, such as `8088`.

### 4. Start The App

```bash
docker compose -p arenaflow up -d --build
```

Legacy Compose:

```bash
docker-compose -p arenaflow up -d --build
```

Check status:

```bash
docker compose -p arenaflow ps
```

Open:

```text
http://SERVER-IP:8080
```

Use the configured `APP_PORT` if you changed it.

### 5. First Login

Default first-run logins:

```text
admin / admin123
marshal / marshal
```

Log in as admin and immediately change both passwords from Admin settings.

Then configure:

- Venue timezone.
- Attractions.
- Weekly schedules.
- Holiday overrides.
- Max players per game.
- Active capacity count.
- Printer mode.
- Customer QR website URL.
- Customer self-rescheduling preference.

## Reverse Proxy And QR Codes

If staff only use ArenaFlow on the local network for marshal scheduling, a reverse proxy is not required. Staff can use the local server address, such as:

```text
http://SERVER-IP:8080
```

If customers will scan QR codes from home or cellular data and change their own ticket time, ArenaFlow needs a public HTTPS URL. A reverse proxy is the usual way to provide that URL.

Common options include Nginx, Nginx Proxy Manager, Caddy, Traefik, and similar tools. ArenaFlow is not affiliated with any reverse proxy project, so use the one you already understand and can maintain.

Example with Nginx Proxy Manager:

1. Create a proxy host such as `games.example.com`.
2. Forward it to the Linux server IP and the ArenaFlow `APP_PORT`.
3. Enable SSL.
4. In ArenaFlow Admin settings, set `Customer QR website` to:

```text
https://games.example.com
```

The customer-facing ticket page is public, but customers still need the ticket code and PIN for changes.

## Network Printer Setup

Start in dry-run mode until bookings work correctly.

For common network thermal printers:

```text
Mode: Network printer TCP
Host: printer IP address
Port: 9100
```

For Linux CUPS:

```bash
lpstat -p -d
```

Use the queue name shown by CUPS in ArenaFlow settings.

## Windows Install

Windows is easiest with Docker Desktop.

### 1. Install Requirements

Install:

- Docker Desktop for Windows.
- Git for Windows.

Enable the WSL2 backend when Docker Desktop asks.

### 2. Download And Configure

Open PowerShell:

```powershell
git clone https://github.com/kjsupe/arenaflow.git
cd arenaflow
Copy-Item .env.example .env
notepad .env
```

Set strong values for:

```text
LASERTAG_DB_PASSWORD
LASERTAG_SECRET
```

### 3. Start

```powershell
docker compose -p arenaflow up -d --build
```

Open:

```text
http://localhost:8080
```

Network printer TCP mode should work from Docker Desktop if the Windows computer can reach the printer IP. CUPS mode is intended for Linux servers.

## Backups

Create a backup folder:

```bash
mkdir -p backups
```

Linux/macOS shell:

```bash
docker compose -p arenaflow exec -T db pg_dump -U lasertag lasertag > "backups/arenaflow-$(date +%F).sql"
```

PowerShell:

```powershell
docker compose -p arenaflow exec -T db pg_dump -U lasertag lasertag | Out-File -Encoding utf8 backups/arenaflow-backup.sql
```

Back up before upgrades.

## Upgrades

If installed from Git:

```bash
cd /opt/arenaflow
git pull
docker compose -p arenaflow up -d --build
```

Use the same Compose project name and same `POSTGRES_VOLUME_NAME` every time.

If you originally deployed with:

```bash
docker-compose -p laser-tag-scheduler
```

keep using that same project name unless you intentionally migrate containers.

## Stop Without Deleting Data

```bash
docker compose -p arenaflow down
```

This stops containers but keeps the PostgreSQL volume.

Do not run `docker volume prune` unless you have confirmed it will not remove data for ArenaFlow or other apps on the server.
