# ArenaFlow User Guide

This guide covers basic day-to-day use after ArenaFlow is installed and the first admin setup is complete.

## First Admin Setup

Log in with the default admin account, then change both shared passwords before using ArenaFlow live.

Default first-run logins:

```text
admin / admin123
marshal / marshal
```

From Admin settings, configure:

- Venue name and timezone.
- Full-color app logo.
- Attractions.
- Weekly schedules.
- Holiday overrides.
- Max players per game.
- Default capacity count.
- Printer settings.
- Customer QR website.
- Customer self-rescheduling settings.

## Attractions

Each attraction has its own schedule, ticket wording, and capacity settings.

Use `Add Attraction` for another timed-capacity experience, such as laser tag, axe throwing, ropes course sessions, or another bookable attraction.

Use `Show on marshal schedule` to hide an attraction from the desk without deleting its history.

Unused test attractions can be permanently deleted from Admin settings. Attractions with booking history cannot be deleted because past bookings and print logs may still reference them. Hide those attractions instead.

## Daily Marshal Workflow

1. Log in with the marshal account.
2. Choose the attraction tab.
3. Confirm the schedule date.
4. Confirm active capacity.
5. Select the next available game time.
6. Enter the number of players.
7. Optionally enter a group or party name.
8. Add notes if useful.
9. Choose whether to print a ticket.
10. Click `Book Players`.

The schedule automatically selects the next available game time unless a marshal manually picks a slot.

The `Today / Now` button returns the schedule to the venue's current operating date. After the attraction closes, ArenaFlow can automatically advance to the next operating date.

## Active Capacity

Active capacity is meant for practical operating changes, such as fewer working blasters or fewer available positions.

When a marshal changes active capacity, it applies from the current time forward and carries into future days until someone changes it again.

Actual game capacity is the lower of:

- Max players per game.
- Active capacity count.

## Bookings

Group names are optional. If no name is entered, ArenaFlow stores the booking as `Walk-in`.

Booking types are:

- `Walk-up`
- `Party`

The party option is intentionally basic. ArenaFlow is not meant to replace a POS or party booking system.

## Tickets

Tickets show:

- Attraction.
- Game date.
- Game time.
- Number of players admitted.
- Ticket code.
- PIN.
- Optional QR code.

Admins can configure ticket wording, receipt logo, QR label, footer text, ticket width, and printer mode.

Start in dry-run printer mode until the schedule and ticket layout look correct.

## Customer Self-Rescheduling

If enabled, the ticket QR code lets customers move their own ticket to another available time.

Customers need the ticket code and PIN. They can only move that specific ticket.

Admins can disable customer self-rescheduling per attraction.

Admins can also decide whether customers may move into the last game of the day.

## Canceling And Reprinting

Use `Reprint` if a customer loses a ticket or the printer fails.

Use `Cancel` if the group should be removed from the game.

Cancelled bookings no longer count against game capacity.

## Recommended Operating Practices

- Keep admin access limited.
- Change default passwords.
- Use dry-run printer mode when testing changes.
- Test one real ticket before a busy operating period.
- Back up the database before upgrading.
- Use `Show on marshal schedule: No` instead of deleting attractions with history.

## Getting Help

ArenaFlow is free software. There is no guaranteed support or emergency response.

For setup and troubleshooting, start with:

- [INSTALL.md](INSTALL.md)
- [SECURITY.md](../SECURITY.md)
- [GitHub Issues](https://github.com/kjsupe/arenaflow/issues)
