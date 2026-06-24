from datetime import datetime, timezone

import aiosqlite
import nextcord
from nextcord.ext import commands

from core import DB_PATH
from core.common import is_admin
from core.config import cget


class Confessions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _can_post(self, guild_id: int, user_id: int) -> bool:
        hourly_limit = int(cget("confessions", "hourly-limit", fallback="1"))
        if hourly_limit <= 0:
            return True
        since = datetime.now(timezone.utc).timestamp() - 3600
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM confessions WHERE guild_id=? AND user_id=? AND timestamp >= ?",
                (guild_id, user_id, datetime.fromtimestamp(since, tz=timezone.utc).isoformat()),
            ) as cur:
                row = await cur.fetchone()
        return bool(row and row[0] < hourly_limit)

    @nextcord.slash_command(name="confess", description="Submit an anonymous confession.")
    async def confess(self, interaction: nextcord.Interaction, content: str = nextcord.SlashOption(description="Your confession")):
        channel_name = cget("confessions", "channel", fallback=None)
        if not channel_name:
            return await interaction.response.send_message("❌ Confessions not configured.", ephemeral=True)
        if not await self._can_post(interaction.guild.id, interaction.user.id):
            return await interaction.response.send_message("❌ You have reached the hourly confession limit.", ephemeral=True)
        ch = nextcord.utils.get(interaction.guild.text_channels, name=channel_name)
        if not ch:
            return await interaction.response.send_message("❌ Confessions channel not found.", ephemeral=True)
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "INSERT INTO confessions (guild_id, user_id, content, timestamp) VALUES (?, ?, ?, ?)",
                (interaction.guild.id, interaction.user.id, content, datetime.now(timezone.utc).isoformat()),
            )
            confession_id = cur.lastrowid
            await db.commit()
        embed = nextcord.Embed(title=f"Anonymous Confession (#{confession_id})", description=content, color=0x4B3BFF)
        embed.set_footer(text=f"Use /confess-report {confession_id} to report this confession.")
        msg = await ch.send(embed=embed)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE confessions SET message_id=? WHERE id=?", (msg.id, confession_id))
            await db.commit()
        await interaction.response.send_message(f"✅ Your confession has been posted anonymously as #{confession_id}.", ephemeral=True)

    @nextcord.slash_command(name="confess-delete", description="[MOD] Delete a confession by ID.")
    async def confess_delete(self, interaction: nextcord.Interaction, confession_id: int = nextcord.SlashOption(description="Confession ID")):
        if not is_admin(interaction.user):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT message_id, channel_id FROM confessions WHERE id=? AND guild_id=?", (confession_id, interaction.guild.id)) as cur:
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
    async def confess_report(self, interaction: nextcord.Interaction, confession_id: int = nextcord.SlashOption(description="Confession ID to report"), reason: str = nextcord.SlashOption(description="Reason for report", required=False, default="No reason provided")):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT content FROM confessions WHERE id=? AND guild_id=?", (confession_id, interaction.guild.id)) as cur:
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


def setup(bot):
    bot.add_cog(Confessions(bot))
