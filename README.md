# ArenaFlow

ArenaFlow is a small browser-based game scheduling and capacity control app for family entertainment center attractions. It is designed for a front-desk or attraction marshal station where staff need to book walk-up groups into timed games, track capacity, and print simple thermal tickets.

It works well for laser tag, but the app supports multiple attractions, so it can also be used for other timed-capacity experiences in the same building.

## What It Does

- Admin and marshal logins.
- Multiple attractions with schedule tabs.
- Per-attraction opening time, first game time, closing time, interval, and capacity.
- Per-attraction weekday/weekend schedules.
- Holiday or special-date overrides.
- Active capacity changes that apply from the current time forward and carry into future days.
- Automatic schedule date following with a `Today / Now` button and next-day rollover after close.
- Walk-up and basic party bookings.
- Optional group or party name.
- Ticket printing and reprinting.
- Network printer TCP mode, CUPS queue mode, and dry-run mode.
- Customer QR code links for moving a ticket to another available time.
- Ticket code plus 4-6 digit PIN protection for customer self-service.
- Optional per-attraction customer self-rescheduling controls.
- Theme picker and app logo upload.
- PostgreSQL with Docker, or SQLite for quick local development.

## Screens And Roles

Marshals can:

- View attraction schedules.
- Add walk-up or party bookings.
- Change active attraction capacity from the current time forward.
- Print and reprint tickets.
- Cancel bookings.

Admins can also:

- Change attraction schedules.
- Add or hide attractions.
- Configure printer settings.
- Configure customer QR website settings.
- Change themes, logos, and shared passwords.

## Recommended Install

Linux with Docker is the recommended production setup.

```bash
git clone https://github.com/YOUR-USER/arenaflow.git
cd arenaflow
cp .env.example .env
nano .env
docker compose -p arenaflow up -d --build
```

Open:

```text
http://SERVER-IP:8080
```

Default first-run logins:

```text
admin / admin123
marshal / marshal
```

Change both passwords immediately from the Admin settings screen before using ArenaFlow operationally.

Detailed Linux and Windows instructions are in [docs/INSTALL.md](docs/INSTALL.md).

GitHub publishing steps are in [docs/PUBLISHING.md](docs/PUBLISHING.md).

## Production Safety

Before exposing the app publicly:

- Change `LASERTAG_DB_PASSWORD` in `.env`.
- Change `LASERTAG_SECRET` in `.env`.
- Change the default admin and marshal passwords inside the app.
- Use HTTPS for customer QR links.
- Back up the PostgreSQL database before upgrades.
- Do not commit `.env`, local database files, uploaded production data, or Docker volumes.

See [SECURITY.md](SECURITY.md) for the full checklist.

## Printer Notes

The app starts in `dry_run` mode so tickets are logged but not sent to hardware.

For most network thermal/ticket printers:

```text
Mode: Network printer TCP
Host: printer IP address
Port: 9100
```

For a printer configured on a Linux server with CUPS:

```text
Mode: CUPS queue
CUPS queue: queue name
```

Set `Customer QR website` in Admin settings to the public HTTPS URL that points to this app, for example:

```text
https://games.example.com
```

Each printed ticket gets a unique ticket code and PIN. The QR code points to that specific ticket, and the customer can only move it to another available time if customer self-rescheduling is enabled for that attraction.

## Data Storage

Docker uses PostgreSQL.

The default Docker volume name is configurable:

```text
POSTGRES_VOLUME_NAME=arenaflow-postgres-data
```

Older installs may use:

```text
laser-tag-scheduler-postgres-data
```

Keep the same volume name when upgrading an existing installation so current settings and bookings remain available.

For quick development without Docker, the app uses SQLite:

```bash
python3 server.py
```

The local SQLite database is created at:

```text
data/scheduler.sqlite3
```

## Upgrading

For a Docker install:

```bash
git pull
docker compose -p arenaflow up -d --build
```

If your installation was created with a different Compose project name, keep using that same `-p` value.

For example, older deployments may use:

```bash
docker-compose -p laser-tag-scheduler up -d --build
```

## Project Status

ArenaFlow is intentionally simple. It is not a point-of-sale system and does not manage payments. It is meant to fill the operational gap between POS sales and attraction/game loading.

## License

This project is released under the MIT License. See [LICENSE](LICENSE).
