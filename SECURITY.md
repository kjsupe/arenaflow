# Security Checklist

ArenaFlow can be exposed to the public internet for customer QR code ticket changes, so production installs need basic hardening.

## Do Before Going Live

- Change the default `admin` password.
- Change the default `marshal` password.
- Set a strong `LASERTAG_DB_PASSWORD` in `.env`.
- Set a strong `LASERTAG_SECRET` in `.env`.
- Use HTTPS for the public customer QR URL.
- Keep `.env` out of GitHub.
- Keep `data/` and database backups out of GitHub.
- Back up PostgreSQL before upgrades.

Generate a strong secret:

```bash
openssl rand -base64 48
```

## Public URL Guidance

Marshal scheduling can run on a local network address, such as `http://SERVER-IP:8080`. A public URL is only needed if customers will scan QR codes and change their own ticket time from outside your local network.

For customer self-rescheduling, point QR codes to a public HTTPS URL that reaches ArenaFlow through a reverse proxy.

Recommended:

```text
https://games.example.com
```

Common reverse proxy options include Nginx, Nginx Proxy Manager, Caddy, Traefik, and similar tools. ArenaFlow is not affiliated with any reverse proxy project, and operators should use the reverse proxy they already know and maintain.

Set this in Admin settings as `Customer QR website`.

The ticket page requires both:

- Ticket code.
- PIN.

This helps prevent someone from changing random tickets by guessing URLs.

## Admin Exposure

If the app is publicly reachable for QR codes, the login page is also reachable unless your reverse proxy restricts it.

At minimum:

- Use strong admin and marshal passwords.
- Do not reuse passwords from other systems.
- Use HTTPS.
- Keep the server patched.

For stricter deployments, use reverse proxy rules, VPN, or network firewall rules to limit staff/admin access while leaving customer ticket URLs available.

## Docker And Volume Safety

Production data lives in the PostgreSQL Docker volume configured by `POSTGRES_VOLUME_NAME`.

Do not run broad cleanup commands without checking volumes first:

```bash
docker volume ls
```

Avoid:

```bash
docker volume prune
```

unless you are certain it will not delete ArenaFlow or other app data.

## Sensitive Data

Do not share, post, or commit:

- `.env`
- SQLite files
- PostgreSQL dumps
- `data/`
- Real ticket print logs
- Production screenshots with customer names or ticket codes
- Real uploaded logos if you do not want them public

The included `.gitignore` is configured to help prevent common mistakes, but operators should still review files before sharing logs, screenshots, backups, or repo changes.

## Reporting Issues

Use GitHub Issues for general bug reports. Do not include secrets, customer data, ticket codes, PINs, database backups, or `.env` contents in public issues.
