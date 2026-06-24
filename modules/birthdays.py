from datetime import datetime, timezone

import aiosqlite
import nextcord
from nextcord.ext import commands, tasks

from core import DB_PATH
from core.common import VALID_TZ
from core.config import cget


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
    async def birthday_set(self, interaction: nextcord.Interaction, day: int = nextcord.SlashOption(description="Day (1-31)"), month: int = nextcord.SlashOption(description="Month (1-12)"), year: int = nextcord.SlashOption(description="Year (optional)", required=False), timezone_name: str = nextcord.SlashOption(name="timezone", description="Your timezone (default: UTC)", required=False, default="UTC")):
        if not (1 <= day <= 31) or not (1 <= month <= 12):
            return await interaction.response.send_message("❌ Invalid date.", ephemeral=True)
        if timezone_name not in VALID_TZ:
            return await interaction.response.send_message(f"❌ Unknown timezone. Valid options: {', '.join(sorted(VALID_TZ))}", ephemeral=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                INSERT INTO birthdays (guild_id, user_id, day, month, year, timezone)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    day=excluded.day, month=excluded.month,
                    year=excluded.year, timezone=excluded.timezone
                """,
                (interaction.guild.id, interaction.user.id, day, month, year, timezone_name),
            )
            await db.commit()
        await interaction.response.send_message(
            f"✅ Birthday set to {day:02d}/{month:02d}" + (f"/{year}" if year else "") + f" ({timezone_name}).",
            ephemeral=True,
        )

    @nextcord.slash_command(name="birthday-remove", description="Remove your birthday.")
    async def birthday_remove(self, interaction: nextcord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM birthdays WHERE guild_id=? AND user_id=?", (interaction.guild.id, interaction.user.id))
            await db.commit()
        await interaction.response.send_message("✅ Birthday removed.", ephemeral=True)

    @nextcord.slash_command(name="birthday-list", description="List upcoming birthdays in this server.")
    async def birthday_list(self, interaction: nextcord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT user_id, day, month, year FROM birthdays WHERE guild_id=? ORDER BY month, day", (interaction.guild.id,)) as cur:
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


def setup(bot):
    bot.add_cog(Birthdays(bot))
