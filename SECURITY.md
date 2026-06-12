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

Customer QR codes can point to the same app through a reverse proxy.

Recommended:

```text
https://games.example.com
```

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

## What Not To Publish

Never commit or upload:

- `.env`
- SQLite files
- PostgreSQL dumps
- `data/`
- Real ticket print logs
- Production screenshots with customer names or ticket codes
- Real uploaded logos if you do not want them public

The included `.gitignore` is configured to help prevent common mistakes, but review `git status` before every push.

## Reporting Issues

If you publish this project publicly, add your preferred security contact method here, such as a GitHub security advisory policy or email address.
