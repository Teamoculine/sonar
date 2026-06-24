import aiosqlite

from .config import cget

DB_PATH = cget("sonar", "database", fallback="sonar.db")


async def db_init(log):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS birthdays (
                guild_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                day         INTEGER NOT NULL,
                month       INTEGER NOT NULL,
                year        INTEGER,
                timezone    TEXT NOT NULL DEFAULT 'UTC',
                PRIMARY KEY (guild_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS confessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                message_id  INTEGER,
                content     TEXT NOT NULL,
                timestamp   TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reminders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                channel_id  INTEGER NOT NULL,
                remind_at   TEXT NOT NULL,
                content     TEXT NOT NULL,
                done        INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS starboard (
                guild_id        INTEGER NOT NULL,
                message_id      INTEGER NOT NULL,
                starboard_msg   INTEGER,
                star_count      INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, message_id)
            );
            CREATE TABLE IF NOT EXISTS invite_tracking (
                guild_id    INTEGER NOT NULL,
                inviter_id  INTEGER NOT NULL,
                invited_id  INTEGER NOT NULL,
                timestamp   TEXT NOT NULL,
                PRIMARY KEY (guild_id, invited_id)
            );
            CREATE TABLE IF NOT EXISTS verify_cooldowns (
                guild_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                attempts    INTEGER NOT NULL DEFAULT 0,
                last_try    TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS warnings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason      TEXT NOT NULL,
                timestamp   TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS polls (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER NOT NULL,
                channel_id  INTEGER NOT NULL,
                message_id  INTEGER NOT NULL,
                question    TEXT NOT NULL,
                options     TEXT NOT NULL,
                ends_at     TEXT NOT NULL,
                closed      INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        await db.commit()
    log.info(f"Database ready at {DB_PATH}")

