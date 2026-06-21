# Sonar

> A basic utility bot - free, open, and self-hosted.

One file. No dashboard. No subscriptions.

---

## Features

| Module | What it does |
|---|---|
| Moderation | `/ban`, `/kick`, `/timeout` (with duration), `/lock`, `/unlock` |
| Verification | Password in rules → type it in verify channel → get role |
| Confessions | Anonymous confessions with mod delete + report |
| Birthdays | Set birthday with timezone, auto-announcement |
| Polls | Multi-option polls with auto-close and results |
| Reminders | DM-based reminders |
| Starboard | ⭐ reaction threshold → posts to starboard channel |
| Invite Tracking | Tracks who invited who on member join, `/inviter` command |
| Welcome | Customizable join message |
| Logging | Unified mod/join log channel |

---

## Requirements

- Python 3.11+
- A Discord bot application with **Message Content Intent** and **Server Members Intent** enabled

```
pip install nextcord aiosqlite
```

---

## Setup

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Create a new application, add a Bot user
3. Enable **Message Content Intent** and **Server Members Intent** under Bot → Privileged Gateway Intents
4. Copy your bot token
5. Copy `sonar.example.idf` to `sonar.idf` and fill in your values
6. Invite your bot with `bot` and `applications.commands` scopes
7. Run:

```
python sonar.py
```

That's it.

---

## Configuration

All configuration lives in `sonar.idf` next to the bot file.
All channel and role values are **names**, not IDs.

### Verification

Put the password somewhere in your rules channel. Users type it in the channel
defined by `verify-channel`. Both messages are auto-deleted. Wrong attempts
trigger a cooldown after `verify-max-attempts` tries.

### Moderation

Admin roles are defined in `admins=(role1, role2, role3)`.
Timeout durations use human-readable strings: `30m`, `1h`, `2h30m`, `1d`.

### Starboard

React with ⭐ to any message. When it hits `threshold` stars it gets reposted
to the starboard channel. The star count on the starboard post updates live.

---

## License


Apache License 2.0
 is to make sure no nefarious evil individuals use this commercially.
