from datetime import datetime, timezone

import aiosqlite
import nextcord
from nextcord.ext import commands

from core import DB_PATH, log
from core.config import cget


class Verification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: nextcord.Message):
        if message.author.bot or not message.guild:
            return
        verify_channel_name = cget("server", "verify-channel", fallback=None)
        if not verify_channel_name or message.channel.name != verify_channel_name:
            return
        password = cget("server", "verification-password", fallback=None)
        if not password:
            return
        guild_id = message.guild.id
        user_id = message.author.id
        cooldown_secs = int(cget("server", "verify-cooldown", fallback="30"))
        max_attempts = int(cget("server", "verify-max-attempts", fallback="3"))
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT attempts, last_try FROM verify_cooldowns WHERE guild_id=? AND user_id=?", (guild_id, user_id)) as cur:
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
                        await message.author.send(f"⏳ Too many failed attempts. Try again in {remaining}s.")
                    except Exception:
                        pass
                    return
                if elapsed >= cooldown_secs:
                    await db.execute("DELETE FROM verify_cooldowns WHERE guild_id=? AND user_id=?", (guild_id, user_id))
                    await db.commit()
        try:
            await message.delete()
        except Exception:
            pass
        if message.content.strip() != password:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    """
                    INSERT INTO verify_cooldowns (guild_id, user_id, attempts, last_try)
                    VALUES (?, ?, 1, ?)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET
                        attempts = attempts + 1,
                        last_try = excluded.last_try
                    """,
                    (guild_id, user_id, now.isoformat()),
                )
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
            await db.execute("DELETE FROM verify_cooldowns WHERE guild_id=? AND user_id=?", (guild_id, user_id))
            await db.commit()
        try:
            await message.author.send("✅ You've been verified. Welcome!")
        except Exception:
            pass


def setup(bot):
    bot.add_cog(Verification(bot))
