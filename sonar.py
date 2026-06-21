"""
Sonar - A free, open, self-hosted Discord utility bot.
https://github.com/Teamoculine/sonar

Drop this file anywhere, fill in sonar.idf, run with:
    pip install nextcord aiosqlite
    python sonar.py

WE ARE MOVING TO GITLAB SOON!
"""

import nextcord
from nextcord.ext import commands, tasks
import aiosqlite
import configparser
import asyncio
import re
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

# ─────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("sonar")

# ─────────────────────────────────────────
# IDF CONFIG PARSER
# ─────────────────────────────────────────

def parse_idf_list(value: str) -> list[str]:
    """Parse (a, b, c) style IDF list into a Python list."""
    value = value.strip()
    if value.startswith("(") and value.endswith(")"):
        value = value[1:-1]
    return [v.strip() for v in value.split(",") if v.strip()]

def load_config(path: str = "sonar.idf") -> configparser.ConfigParser:
    if not os.path.exists(path):
        log.error(f"Config file '{path}' not found. Create it from sonar.example.idf.")
        raise SystemExit(1)
    cfg = configparser.ConfigParser(inline_comment_prefixes=(";",))
    cfg.read(path)
    return cfg

cfg = load_config()

def cget(section: str, key: str, fallback=None):
    return cfg.get(section, key, fallback=fallback)

def clist(section: str, key: str, fallback=None) -> list[str]:
    val = cfg.get(section, key, fallback=None)
    if val is None:
        return fallback or []
    return parse_idf_list(val)

# ─────────────────────────────────────────
# DURATION PARSER
# ─────────────────────────────────────────

def parse_duration(s: str) -> Optional[timedelta]:
    """
    Parse duration strings like 1h30m, 2d, 45s, 1h30m20s.
    Returns timedelta or None if invalid.
    Max 28 days (Discord timeout limit).
    """
    pattern = re.compile(r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?")
    match = pattern.fullmatch(s.strip().lower())
    if not match or not any(match.groups()):
        return None
    days = int(match.group(1) or 0)
    hours = int(match.group(2) or 0)
    minutes = int(match.group(3) or 0)
    seconds = int(match.group(4) or 0)
    delta = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
    if delta.total_seconds() <= 0 or delta > timedelta(days=28):
        return None
    return delta

def fmt_duration(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    d, r = divmod(total, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s: parts.append(f"{s}s")
    return "".join(parts) or "0s"

# ─────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────

DB_PATH = cget("sonar", "database", fallback="sonar.db")

async def db_init():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
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
        """)
        await db.commit()
    log.info(f"Database ready at {DB_PATH}")

# ─────────────────────────────────────────
# PERMISSION HELPER
# ─────────────────────────────────────────

def is_admin(member: nextcord.Member) -> bool:
    """Check if member has any of the configured admin roles or is the server owner."""
    if member.guild.owner_id == member.id:
        return True
    admin_roles = clist("server", "admins", fallback=[])
    return any(r.name.lower() in [a.lower() for a in admin_roles] for r in member.roles)

def admin_only():
    async def predicate(interaction: nextcord.Interaction):
        if not is_admin(interaction.user):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.", ephemeral=True
            )
            return False
        return True
    return nextcord.ext.application_checks.check(predicate)

# ─────────────────────────────────────────
# BOT SETUP
# ─────────────────────────────────────────

intents = nextcord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(intents=intents)
invite_cache: dict[int, dict[str, nextcord.Invite]] = {}

# ─────────────────────────────────────────
# MODULE: CORE
# ─────────────────────────────────────────

class Core(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @nextcord.slash_command(name="ping", description="Check bot latency.")
    async def ping(self, interaction: nextcord.Interaction):
        ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"Pong! `{ms}ms`", ephemeral=True)

    @nextcord.slash_command(name="help", description="List all Sonar commands.")
    async def help(self, interaction: nextcord.Interaction):
        embed = nextcord.Embed(
            title="Sonar — Command Reference",
            color=0x4B3BFF
        )
        embed.add_field(name="Core", value="`/ping` `/help`", inline=False)
        embed.add_field(name="Moderation", value="`/ban` `/kick` `/timeout` `/lock` `/unlock`", inline=False)
        embed.add_field(name="Verification", value="`/verify`", inline=False)
        embed.add_field(name="Confessions", value="`/confess` `/confess-delete` `/confess-report`", inline=False)
        embed.add_field(name="Birthdays", value="`/birthday-set` `/birthday-remove` `/birthday-list`", inline=False)
        embed.add_field(name="Polls", value="`/poll`", inline=False)
        embed.add_field(name="Reminders", value="`/remind`", inline=False)
        embed.add_field(name="Starboard", value="React ⭐ to any message.", inline=False)
        embed.add_field(name="Invite Tracking", value="`/inviter`", inline=False)
        embed.set_footer(text="Sonar — free, open, self-hosted.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ─────────────────────────────────────────
# MODULE: MODERATION
# ─────────────────────────────────────────

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _log(self, guild: nextcord.Guild, embed: nextcord.Embed):
        log_channel_name = cget("logging", "channel", fallback=None)
        if not log_channel_name:
            return
        ch = nextcord.utils.get(guild.text_channels, name=log_channel_name)
        if ch:
            await ch.send(embed=embed)

    @nextcord.slash_command(name="ban", description="Ban a member.")
    async def ban(
        self,
        interaction: nextcord.Interaction,
        member: nextcord.Member = nextcord.SlashOption(description="Member to ban"),
        reason: str = nextcord.SlashOption(description="Reason", required=False, default="No reason provided")
    ):
        if not is_admin(interaction.user):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
        if member.top_role >= interaction.user.top_role and interaction.guild.owner_id != interaction.user.id:
            return await interaction.response.send_message("❌ Cannot ban someone with equal or higher role.", ephemeral=True)
        await member.ban(reason=f"{interaction.user}: {reason}")
        embed = nextcord.Embed(title="🔨 Ban", color=0xFF4444)
        embed.add_field(name="User", value=str(member))
        embed.add_field(name="Moderator", value=str(interaction.user))
        embed.add_field(name="Reason", value=reason, inline=False)
        await interaction.response.send_message(embed=embed)
        await self._log(interaction.guild, embed)

    @nextcord.slash_command(name="kick", description="Kick a member.")
    async def kick(
        self,
        interaction: nextcord.Interaction,
        member: nextcord.Member = nextcord.SlashOption(description="Member to kick"),
        reason: str = nextcord.SlashOption(description="Reason", required=False, default="No reason provided")
    ):
        if not is_admin(interaction.user):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
        if member.top_role >= interaction.user.top_role and interaction.guild.owner_id != interaction.user.id:
            return await interaction.response.send_message("❌ Cannot kick someone with equal or higher role.", ephemeral=True)
        await member.kick(reason=f"{interaction.user}: {reason}")
        embed = nextcord.Embed(title="👢 Kick", color=0xFF8800)
        embed.add_field(name="User", value=str(member))
        embed.add_field(name="Moderator", value=str(interaction.user))
        embed.add_field(name="Reason", value=reason, inline=False)
        await interaction.response.send_message(embed=embed)
        await self._log(interaction.guild, embed)

    @nextcord.slash_command(name="timeout", description="Timeout a member.")
    async def timeout(
        self,
        interaction: nextcord.Interaction,
        member: nextcord.Member = nextcord.SlashOption(description="Member to timeout"),
        duration: str = nextcord.SlashOption(description="Duration e.g. 1h30m, 2d, 45s"),
        reason: str = nextcord.SlashOption(description="Reason", required=False, default="No reason provided")
    ):
        if not is_admin(interaction.user):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
        delta = parse_duration(duration)
        if not delta:
            return await interaction.response.send_message(
                "❌ Invalid duration. Use formats like `1h`, `30m`, `1h30m`, `2d`. Max 28 days.", ephemeral=True
            )
        until = datetime.now(timezone.utc) + delta
        await member.timeout(until, reason=f"{interaction.user}: {reason}")
        embed = nextcord.Embed(title="⏱️ Timeout", color=0xFFCC00)
        embed.add_field(name="User", value=str(member))
        embed.add_field(name="Moderator", value=str(interaction.user))
        embed.add_field(name="Duration", value=fmt_duration(delta))
        embed.add_field(name="Reason", value=reason, inline=False)
        await interaction.response.send_message(embed=embed)
        await self._log(interaction.guild, embed)

    @nextcord.slash_command(name="lock", description="Lock a channel (remove Send Messages for @everyone).")
    async def lock(
        self,
        interaction: nextcord.Interaction,
        channel: nextcord.TextChannel = nextcord.SlashOption(description="Channel to lock", required=False)
    ):
        if not is_admin(interaction.user):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
        ch = channel or interaction.channel
        await ch.set_permissions(interaction.guild.default_role, send_messages=False)
        embed = nextcord.Embed(title="🔒 Channel Locked", description=ch.mention, color=0xFF4444)
        embed.add_field(name="Moderator", value=str(interaction.user))
        await interaction.response.send_message(embed=embed)
        await self._log(interaction.guild, embed)

    @nextcord.slash_command(name="unlock", description="Unlock a channel (restore Send Messages for @everyone).")
    async def unlock(
        self,
        interaction: nextcord.Interaction,
        channel: nextcord.TextChannel = nextcord.SlashOption(description="Channel to unlock", required=False)
    ):
        if not is_admin(interaction.user):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
        ch = channel or interaction.channel
        await ch.set_permissions(interaction.guild.default_role, send_messages=None)
        embed = nextcord.Embed(title="🔓 Channel Unlocked", description=ch.mention, color=0x44FF88)
        embed.add_field(name="Moderator", value=str(interaction.user))
        await interaction.response.send_message(embed=embed)
        await self._log(interaction.guild, embed)

# ─────────────────────────────────────────
# MODULE: VERIFICATION
# ─────────────────────────────────────────

class Verification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: nextcord.Message):
        if message.author.bot or not message.guild:
            return

        verify_channel_name = cget("server", "verify-channel", fallback=None)
        if not verify_channel_name:
            return
        if message.channel.name != verify_channel_name:
            return

        password = cget("server", "verification-password", fallback=None)
        if not password:
            return

        guild_id = message.guild.id
        user_id = message.author.id
        cooldown_secs = int(cget("server", "verify-cooldown", fallback="30"))
        max_attempts = int(cget("server", "verify-max-attempts", fallback="3"))

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT attempts, last_try FROM verify_cooldowns WHERE guild_id=? AND user_id=?",
                (guild_id, user_id)
            ) as cur:
                row = await cur.fetchone()

            now = datetime.now(timezone.utc)

            if row:
                attempts, last_try_str = row
                last_try = datetime.fromisoformat(last_try_str)
                elapsed = (now - last_try).total_seconds()
                if attempts >= max_attempts and elapsed < cooldown_secs:
                    remaining = int(cooldown_secs - elapsed)
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    try:
                        await message.author.send(
                            f"⏳ Too many failed attempts. Try again in {remaining}s."
                        )
                    except Exception:
                        pass
                    return
                if elapsed >= cooldown_secs:
                    await db.execute(
                        "DELETE FROM verify_cooldowns WHERE guild_id=? AND user_id=?",
                        (guild_id, user_id)
                    )
                    await db.commit()

        try:
            await message.delete()
        except Exception:
            pass

        if message.content.strip() != password:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    INSERT INTO verify_cooldowns (guild_id, user_id, attempts, last_try)
                    VALUES (?, ?, 1, ?)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET
                        attempts = attempts + 1,
                        last_try = excluded.last_try
                """, (guild_id, user_id, now.isoformat()))
                await db.commit()
            try:
                await message.author.send("❌ Wrong password. Check the rules and try again.")
            except Exception:
                pass
            return

        verified_role_name = cget("server", "verified-role", fallback=None)
        unverified_role_name = cget("server", "unverified-role", fallback=None)

        verified_role = nextcord.utils.get(message.guild.roles, name=verified_role_name) if verified_role_name else None
        unverified_role = nextcord.utils.get(message.guild.roles, name=unverified_role_name) if unverified_role_name else None

        try:
            if verified_role:
                await message.author.add_roles(verified_role)
            if unverified_role:
                await message.author.remove_roles(unverified_role)
        except nextcord.Forbidden:
            log.warning(f"Missing permissions to assign roles in {message.guild.name}")
            return

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM verify_cooldowns WHERE guild_id=? AND user_id=?",
                (guild_id, user_id)
            )
            await db.commit()

        try:
            await message.author.send("✅ You've been verified. Welcome!")
        except Exception:
            pass

# ─────────────────────────────────────────
# MODULE: CONFESSIONS
# ─────────────────────────────────────────

class Confessions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @nextcord.slash_command(name="confess", description="Submit an anonymous confession.")
    async def confess(
        self,
        interaction: nextcord.Interaction,
        content: str = nextcord.SlashOption(description="Your confession")
    ):
        channel_name = cget("confessions", "channel", fallback=None)
        if not channel_name:
            return await interaction.response.send_message("❌ Confessions not configured.", ephemeral=True)

        ch = nextcord.utils.get(interaction.guild.text_channels, name=channel_name)
        if not ch:
            return await interaction.response.send_message("❌ Confessions channel not found.", ephemeral=True)

        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "INSERT INTO confessions (guild_id, user_id, content, timestamp) VALUES (?, ?, ?, ?)",
                (interaction.guild.id, interaction.user.id, content, datetime.now(timezone.utc).isoformat())
            )
            confession_id = cur.lastrowid
            await db.commit()

        embed = nextcord.Embed(
            title=f"Anonymous Confession (#{confession_id})",
            description=content,
            color=0x4B3BFF
        )
        embed.set_footer(text=f"Use /confess-report {confession_id} to report this confession.")
        msg = await ch.send(embed=embed)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE confessions SET message_id=? WHERE id=?", (msg.id, confession_id))
            await db.commit()

        await interaction.response.send_message(
            f"✅ Your confession has been posted anonymously as #{confession_id}.", ephemeral=True
        )

    @nextcord.slash_command(name="confess-delete", description="[MOD] Delete a confession by ID.")
    async def confess_delete(
        self,
        interaction: nextcord.Interaction,
        confession_id: int = nextcord.SlashOption(description="Confession ID")
    ):
        if not is_admin(interaction.user):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT message_id, channel_id FROM confessions WHERE id=? AND guild_id=?",
                (confession_id, interaction.guild.id)
            ) as cur:
                row = await cur.fetchone()

            if not row:
                return await interaction.response.send_message("❌ Confession not found.", ephemeral=True)

            message_id = row[0]
            channel_name = cget("confessions", "channel", fallback=None)
            ch = nextcord.utils.get(interaction.guild.text_channels, name=channel_name) if channel_name else None

            if ch and message_id:
                try:
                    msg = await ch.fetch_message(message_id)
                    await msg.delete()
                except Exception:
                    pass

            await db.execute("DELETE FROM confessions WHERE id=?", (confession_id,))
            await db.commit()

        await interaction.response.send_message(f"✅ Confession #{confession_id} deleted.", ephemeral=True)

    @nextcord.slash_command(name="confess-report", description="Report a confession to moderators.")
    async def confess_report(
        self,
        interaction: nextcord.Interaction,
        confession_id: int = nextcord.SlashOption(description="Confession ID to report"),
        reason: str = nextcord.SlashOption(description="Reason for report", required=False, default="No reason provided")
    ):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT content FROM confessions WHERE id=? AND guild_id=?",
                (confession_id, interaction.guild.id)
            ) as cur:
                row = await cur.fetchone()

        if not row:
            return await interaction.response.send_message("❌ Confession not found.", ephemeral=True)

        log_channel_name = cget("logging", "channel", fallback=None)
        if log_channel_name:
            ch = nextcord.utils.get(interaction.guild.text_channels, name=log_channel_name)
            if ch:
                embed = nextcord.Embed(title="🚨 Confession Report", color=0xFF4444)
                embed.add_field(name="Confession ID", value=str(confession_id))
                embed.add_field(name="Content", value=row[0], inline=False)
                embed.add_field(name="Reason", value=reason, inline=False)
                embed.add_field(name="Reported by", value=str(interaction.user))
                await ch.send(embed=embed)

        await interaction.response.send_message("✅ Report submitted to moderators.", ephemeral=True)

# ─────────────────────────────────────────
# MODULE: BIRTHDAYS
# ─────────────────────────────────────────

VALID_TZ = {
    "UTC", "US/Eastern", "US/Central", "US/Mountain", "US/Pacific",
    "Europe/London", "Europe/Amsterdam", "Europe/Budapest", "Europe/Berlin",
    "Europe/Paris", "Europe/Bucharest", "Asia/Tokyo", "Asia/Shanghai",
    "Australia/Sydney", "America/Sao_Paulo"
}

class Birthdays(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.birthday_check.start()

    def cog_unload(self):
        self.birthday_check.cancel()

    @tasks.loop(hours=1)
    async def birthday_check(self):
        now_utc = datetime.now(timezone.utc)
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT guild_id, user_id, day, month FROM birthdays") as cur:
                rows = await cur.fetchall()

        for guild_id, user_id, day, month in rows:
            if now_utc.day == day and now_utc.month == month and now_utc.hour == 9:
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue
                channel_name = cget("birthdays", "channel", fallback=None)
                if not channel_name:
                    continue
                ch = nextcord.utils.get(guild.text_channels, name=channel_name)
                if not ch:
                    continue
                member = guild.get_member(user_id)
                name = member.mention if member else f"<@{user_id}>"
                await ch.send(f"🎂 Happy birthday, {name}! 🎉")

    @nextcord.slash_command(name="birthday-set", description="Set your birthday.")
    async def birthday_set(
        self,
        interaction: nextcord.Interaction,
        day: int = nextcord.SlashOption(description="Day (1-31)"),
        month: int = nextcord.SlashOption(description="Month (1-12)"),
        year: int = nextcord.SlashOption(description="Year (optional)", required=False),
        timezone_name: str = nextcord.SlashOption(
            name="timezone",
            description="Your timezone (default: UTC)",
            required=False,
            default="UTC"
        )
    ):
        if not (1 <= day <= 31) or not (1 <= month <= 12):
            return await interaction.response.send_message("❌ Invalid date.", ephemeral=True)
        if timezone_name not in VALID_TZ:
            return await interaction.response.send_message(
                f"❌ Unknown timezone. Valid options: {', '.join(sorted(VALID_TZ))}", ephemeral=True
            )

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO birthdays (guild_id, user_id, day, month, year, timezone)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    day=excluded.day, month=excluded.month,
                    year=excluded.year, timezone=excluded.timezone
            """, (interaction.guild.id, interaction.user.id, day, month, year, timezone_name))
            await db.commit()

        await interaction.response.send_message(
            f"✅ Birthday set to {day:02d}/{month:02d}" + (f"/{year}" if year else "") + f" ({timezone_name}).",
            ephemeral=True
        )

    @nextcord.slash_command(name="birthday-remove", description="Remove your birthday.")
    async def birthday_remove(self, interaction: nextcord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM birthdays WHERE guild_id=? AND user_id=?",
                (interaction.guild.id, interaction.user.id)
            )
            await db.commit()
        await interaction.response.send_message("✅ Birthday removed.", ephemeral=True)

    @nextcord.slash_command(name="birthday-list", description="List upcoming birthdays in this server.")
    async def birthday_list(self, interaction: nextcord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT user_id, day, month, year FROM birthdays WHERE guild_id=? ORDER BY month, day",
                (interaction.guild.id,)
            ) as cur:
                rows = await cur.fetchall()

        if not rows:
            return await interaction.response.send_message("No birthdays set.", ephemeral=True)

        lines = []
        for user_id, day, month, year in rows:
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else f"<@{user_id}>"
            yr = f"/{year}" if year else ""
            lines.append(f"**{name}** — {day:02d}/{month:02d}{yr}")

        embed = nextcord.Embed(title="🎂 Birthdays", description="\n".join(lines), color=0xFF69B4)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ─────────────────────────────────────────
# MODULE: POLLS
# ─────────────────────────────────────────

class Polls(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.poll_checker.start()

    def cog_unload(self):
        self.poll_checker.cancel()

    @tasks.loop(minutes=1)
    async def poll_checker(self):
        now = datetime.now(timezone.utc)
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT id, guild_id, channel_id, message_id, question, options FROM polls WHERE closed=0 AND ends_at <= ?",
                (now.isoformat(),)
            ) as cur:
                rows = await cur.fetchall()

            for poll_id, guild_id, channel_id, message_id, question, options_str in rows:
                await self._close_poll(poll_id, guild_id, channel_id, message_id, question, options_str, db)

            await db.commit()

    async def _close_poll(self, poll_id, guild_id, channel_id, message_id, question, options_str, db):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        ch = guild.get_channel(channel_id)
        if not ch:
            return
        try:
            msg = await ch.fetch_message(message_id)
        except Exception:
            return

        options = options_str.split("||")
        emojis = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
        results = []
        for i, opt in enumerate(options):
            emoji = emojis[i]
            reaction = nextcord.utils.get(msg.reactions, emoji=emoji)
            count = (reaction.count - 1) if reaction else 0
            results.append((opt.strip(), count, emoji))

        results.sort(key=lambda x: x[1], reverse=True)
        winner = results[0]

        embed = nextcord.Embed(title=f"📊 Poll Closed: {question}", color=0x4B3BFF)
        for opt, count, emoji in results:
            bar = "█" * min(count, 20)
            embed.add_field(name=f"{emoji} {opt}", value=f"{bar} {count} vote(s)", inline=False)
        embed.set_footer(text=f"Winner: {winner[2]} {winner[0]} with {winner[1]} vote(s)")

        await msg.edit(embed=embed)
        await msg.clear_reactions()
        await db.execute("UPDATE polls SET closed=1 WHERE id=?", (poll_id,))

    @nextcord.slash_command(name="poll", description="Create a poll.")
    async def poll(
        self,
        interaction: nextcord.Interaction,
        question: str = nextcord.SlashOption(description="Poll question"),
        options: str = nextcord.SlashOption(description="Options separated by | (max 10). E.g: Yes|No|Maybe"),
        duration: str = nextcord.SlashOption(description="Duration e.g. 1h, 30m, 1h30m")
    ):
        opts = [o.strip() for o in options.split("|") if o.strip()]
        if len(opts) < 2 or len(opts) > 10:
            return await interaction.response.send_message("❌ Need 2–10 options.", ephemeral=True)

        delta = parse_duration(duration)
        if not delta:
            return await interaction.response.send_message("❌ Invalid duration.", ephemeral=True)

        emojis = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
        ends_at = datetime.now(timezone.utc) + delta

        embed = nextcord.Embed(title=f"📊 {question}", color=0x4B3BFF)
        for i, opt in enumerate(opts):
            embed.add_field(name=f"{emojis[i]} {opt}", value="\u200b", inline=False)
        embed.set_footer(text=f"Poll ends in {fmt_duration(delta)}")

        await interaction.response.send_message("✅ Poll created!", ephemeral=True)
        msg = await interaction.channel.send(embed=embed)

        for i in range(len(opts)):
            await msg.add_reaction(emojis[i])

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO polls (guild_id, channel_id, message_id, question, options, ends_at) VALUES (?,?,?,?,?,?)",
                (interaction.guild.id, interaction.channel.id, msg.id, question, "||".join(opts), ends_at.isoformat())
            )
            await db.commit()

# ─────────────────────────────────────────
# MODULE: REMINDERS
# ─────────────────────────────────────────

class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reminder_check.start()

    def cog_unload(self):
        self.reminder_check.cancel()

    @tasks.loop(seconds=30)
    async def reminder_check(self):
        now = datetime.now(timezone.utc)
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT id, user_id, content FROM reminders WHERE done=0 AND remind_at <= ?",
                (now.isoformat(),)
            ) as cur:
                rows = await cur.fetchall()

            for reminder_id, user_id, content in rows:
                user = self.bot.get_user(user_id)
                if user:
                    try:
                        await user.send(f"⏰ **Reminder:** {content}")
                    except Exception:
                        pass
                await db.execute("UPDATE reminders SET done=1 WHERE id=?", (reminder_id,))

            await db.commit()

    @nextcord.slash_command(name="remind", description="Set a reminder (sent via DM).")
    async def remind(
        self,
        interaction: nextcord.Interaction,
        duration: str = nextcord.SlashOption(description="When to remind you. E.g. 1h, 30m, 2h30m"),
        reminder: str = nextcord.SlashOption(description="What to remind you about")
    ):
        delta = parse_duration(duration)
        if not delta:
            return await interaction.response.send_message("❌ Invalid duration.", ephemeral=True)

        remind_at = datetime.now(timezone.utc) + delta

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO reminders (user_id, channel_id, remind_at, content) VALUES (?, ?, ?, ?)",
                (interaction.user.id, interaction.channel.id, remind_at.isoformat(), reminder)
            )
            await db.commit()

        await interaction.response.send_message(
            f"✅ I'll DM you in **{fmt_duration(delta)}**: {reminder}", ephemeral=True
        )

# ─────────────────────────────────────────
# MODULE: STARBOARD
# ─────────────────────────────────────────

class Starboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: nextcord.RawReactionActionEvent):
        if str(payload.emoji) != "⭐":
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        starboard_name = cget("starboard", "channel", fallback=None)
        if not starboard_name:
            return

        threshold = int(cget("starboard", "threshold", fallback="3"))
        starboard_ch = nextcord.utils.get(guild.text_channels, name=starboard_name)
        if not starboard_ch:
            return

        source_ch = guild.get_channel(payload.channel_id)
        if not source_ch or source_ch.id == starboard_ch.id:
            return

        try:
            msg = await source_ch.fetch_message(payload.message_id)
        except Exception:
            return

        star_reaction = nextcord.utils.get(msg.reactions, emoji="⭐")
        star_count = star_reaction.count if star_reaction else 0

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT starboard_msg, star_count FROM starboard WHERE guild_id=? AND message_id=?",
                (guild.id, msg.id)
            ) as cur:
                row = await cur.fetchone()

            if star_count < threshold:
                return

            description = msg.content or ""
            if msg.attachments:
                description += f"\n{msg.attachments[0].url}"

            embed = nextcord.Embed(description=description, color=0xFFD700)
            embed.set_author(name=msg.author.display_name, icon_url=msg.author.display_avatar.url)
            embed.add_field(name="Source", value=f"[Jump]({msg.jump_url})")
            embed.set_footer(text=f"⭐ {star_count}")
            if msg.attachments and msg.attachments[0].content_type and msg.attachments[0].content_type.startswith("image"):
                embed.set_image(url=msg.attachments[0].url)

            if row:
                starboard_msg_id = row[0]
                try:
                    sb_msg = await starboard_ch.fetch_message(starboard_msg_id)
                    await sb_msg.edit(embed=embed)
                except Exception:
                    pass
                await db.execute(
                    "UPDATE starboard SET star_count=? WHERE guild_id=? AND message_id=?",
                    (star_count, guild.id, msg.id)
                )
            else:
                sb_msg = await starboard_ch.send(embed=embed)
                await db.execute(
                    "INSERT INTO starboard (guild_id, message_id, starboard_msg, star_count) VALUES (?,?,?,?)",
                    (guild.id, msg.id, sb_msg.id, star_count)
                )

            await db.commit()

# ─────────────────────────────────────────
# MODULE: INVITE TRACKING
# ─────────────────────────────────────────

class InviteTracking(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            try:
                invites = await guild.fetch_invites()
                invite_cache[guild.id] = {inv.code: inv for inv in invites}
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_invite_create(self, invite: nextcord.Invite):
        if invite.guild:
            invite_cache.setdefault(invite.guild.id, {})[invite.code] = invite

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: nextcord.Invite):
        if invite.guild and invite.guild.id in invite_cache:
            invite_cache[invite.guild.id].pop(invite.code, None)

    @commands.Cog.listener()
    async def on_member_join(self, member: nextcord.Member):
        guild = member.guild
        inviter = None

        try:
            new_invites = await guild.fetch_invites()
            new_cache = {inv.code: inv for inv in new_invites}
            old_cache = invite_cache.get(guild.id, {})

            for code, inv in old_cache.items():
                new_inv = new_cache.get(code)
                if new_inv and new_inv.uses > inv.uses:
                    inviter = inv.inviter
                    break

            invite_cache[guild.id] = new_cache
        except Exception:
            pass

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO invite_tracking (guild_id, inviter_id, invited_id, timestamp) VALUES (?,?,?,?)",
                (guild.id, inviter.id if inviter else 0, member.id, datetime.now(timezone.utc).isoformat())
            )
            await db.commit()

        log_channel_name = cget("logging", "channel", fallback=None)
        if log_channel_name:
            ch = nextcord.utils.get(guild.text_channels, name=log_channel_name)
            if ch:
                inviter_str = inviter.mention if inviter else "Unknown"
                embed = nextcord.Embed(title="📥 Member Joined", color=0x44FF88)
                embed.add_field(name="Member", value=member.mention)
                embed.add_field(name="Invited by", value=inviter_str)
                await ch.send(embed=embed)

        # Assign unverified role on join
        unverified_role_name = cget("server", "unverified-role", fallback=None)
        if unverified_role_name:
            role = nextcord.utils.get(guild.roles, name=unverified_role_name)
            if role:
                try:
                    await member.add_roles(role)
                except Exception:
                    pass

    @nextcord.slash_command(name="inviter", description="Check who invited a member.")
    async def inviter(
        self,
        interaction: nextcord.Interaction,
        member: nextcord.Member = nextcord.SlashOption(description="Member to check")
    ):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT inviter_id, timestamp FROM invite_tracking WHERE guild_id=? AND invited_id=?",
                (interaction.guild.id, member.id)
            ) as cur:
                row = await cur.fetchone()

        if not row:
            return await interaction.response.send_message("No invite data for this member.", ephemeral=True)

        inviter_id, ts = row
        inviter = interaction.guild.get_member(inviter_id)
        inviter_str = inviter.mention if inviter else (f"<@{inviter_id}>" if inviter_id else "Unknown")
        ts_fmt = datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M UTC")

        embed = nextcord.Embed(title="📥 Invite Info", color=0x4B3BFF)
        embed.add_field(name="Member", value=member.mention)
        embed.add_field(name="Invited by", value=inviter_str)
        embed.add_field(name="Joined at", value=ts_fmt)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ─────────────────────────────────────────
# MODULE: WELCOME
# ─────────────────────────────────────────

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: nextcord.Member):
        channel_name = cget("welcome", "channel", fallback=None)
        if not channel_name:
            return
        ch = nextcord.utils.get(member.guild.text_channels, name=channel_name)
        if not ch:
            return
        template = cget("welcome", "message", fallback="Welcome to {server}, {user}!")
        msg = template.replace("{user}", member.mention).replace("{server}", member.guild.name)
        await ch.send(msg)

# ─────────────────────────────────────────
# BOT EVENTS
# ─────────────────────────────────────────

@bot.event
async def on_ready():
    await db_init()
    log.info(f"Sonar online as {bot.user} ({bot.user.id})")
    await bot.sync_all_application_commands()
    log.info("Slash commands synced.")

@bot.event
async def on_application_command_error(interaction: nextcord.Interaction, error: Exception):
    log.error(f"Command error: {error}")
    try:
        await interaction.response.send_message("❌ An error occurred.", ephemeral=True)
    except Exception:
        pass

# ─────────────────────────────────────────
# REGISTER COGS
# ─────────────────────────────────────────

bot.add_cog(Core(bot))
bot.add_cog(Moderation(bot))
bot.add_cog(Verification(bot))
bot.add_cog(Confessions(bot))
bot.add_cog(Birthdays(bot))
bot.add_cog(Polls(bot))
bot.add_cog(Reminders(bot))
bot.add_cog(Starboard(bot))
bot.add_cog(InviteTracking(bot))
bot.add_cog(Welcome(bot))

# ─────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────

if __name__ == "__main__":
    token = cget("sonar", "token", fallback=None)
    if not token:
        log.error("No token found in [sonar] token= in sonar.idf")
        raise SystemExit(1)
    bot.run(token)
