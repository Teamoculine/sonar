from datetime import datetime, timezone

import aiosqlite
import nextcord
from nextcord.ext import commands

from core import DB_PATH, log
from core.common import is_admin
from core.config import cget, fmt_duration, parse_duration


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

    async def _warn(self, guild: nextcord.Guild, member: nextcord.Member, moderator: nextcord.Member, reason: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                (guild.id, member.id, moderator.id, reason, datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()

    @nextcord.slash_command(name="ban", description="Ban a member.")
    async def ban(self, interaction: nextcord.Interaction, member: nextcord.Member = nextcord.SlashOption(description="Member to ban"), reason: str = nextcord.SlashOption(description="Reason", required=False, default="No reason provided")):
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
    async def kick(self, interaction: nextcord.Interaction, member: nextcord.Member = nextcord.SlashOption(description="Member to kick"), reason: str = nextcord.SlashOption(description="Reason", required=False, default="No reason provided")):
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
    async def timeout(self, interaction: nextcord.Interaction, member: nextcord.Member = nextcord.SlashOption(description="Member to timeout"), duration: str = nextcord.SlashOption(description="Duration e.g. 1h30m, 2d, 45s"), reason: str = nextcord.SlashOption(description="Reason", required=False, default="No reason provided")):
        if not is_admin(interaction.user):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
        delta = parse_duration(duration)
        if not delta:
            return await interaction.response.send_message("❌ Invalid duration. Use formats like `1h`, `30m`, `1h30m`, `2d`. Max 28 days.", ephemeral=True)
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
    async def lock(self, interaction: nextcord.Interaction, channel: nextcord.TextChannel = nextcord.SlashOption(description="Channel to lock", required=False)):
        if not is_admin(interaction.user):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
        ch = channel or interaction.channel
        await ch.set_permissions(interaction.guild.default_role, send_messages=False)
        embed = nextcord.Embed(title="🔒 Channel Locked", description=ch.mention, color=0xFF4444)
        embed.add_field(name="Moderator", value=str(interaction.user))
        await interaction.response.send_message(embed=embed)
        await self._log(interaction.guild, embed)

    @nextcord.slash_command(name="unlock", description="Unlock a channel (restore Send Messages for @everyone).")
    async def unlock(self, interaction: nextcord.Interaction, channel: nextcord.TextChannel = nextcord.SlashOption(description="Channel to unlock", required=False)):
        if not is_admin(interaction.user):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
        ch = channel or interaction.channel
        await ch.set_permissions(interaction.guild.default_role, send_messages=None)
        embed = nextcord.Embed(title="🔓 Channel Unlocked", description=ch.mention, color=0x44FF88)
        embed.add_field(name="Moderator", value=str(interaction.user))
        await interaction.response.send_message(embed=embed)
        await self._log(interaction.guild, embed)

    @nextcord.slash_command(name="warn", description="Warn a member.")
    async def warn(self, interaction: nextcord.Interaction, member: nextcord.Member = nextcord.SlashOption(description="Member to warn"), reason: str = nextcord.SlashOption(description="Reason", required=False, default="No reason provided")):
        if not is_admin(interaction.user):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
        if member.top_role >= interaction.user.top_role and interaction.guild.owner_id != interaction.user.id:
            return await interaction.response.send_message("❌ Cannot warn someone with equal or higher role.", ephemeral=True)
        await self._warn(interaction.guild, member, interaction.user, reason)
        embed = nextcord.Embed(title="⚠️ Warn", color=0xFFCC00)
        embed.add_field(name="User", value=str(member))
        embed.add_field(name="Moderator", value=str(interaction.user))
        embed.add_field(name="Reason", value=reason, inline=False)
        await interaction.response.send_message(embed=embed)
        await self._log(interaction.guild, embed)

    @nextcord.slash_command(name="purge", description="Delete recent messages in a channel.")
    async def purge(self, interaction: nextcord.Interaction, amount: int = nextcord.SlashOption(description="Messages to delete", min_value=1, max_value=100), channel: nextcord.TextChannel = nextcord.SlashOption(description="Channel to purge", required=False), user: nextcord.Member = nextcord.SlashOption(description="Only delete messages from this user", required=False)):
        if not is_admin(interaction.user):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
        target = channel or interaction.channel
        deleted = 0
        async for message in target.history(limit=amount * 2):
            if deleted >= amount:
                break
            if user and message.author.id != user.id:
                continue
            if message.pinned:
                continue
            try:
                await message.delete()
                deleted += 1
            except Exception:
                pass
        embed = nextcord.Embed(title="🧹 Purge", color=0x55CCFF)
        embed.add_field(name="Channel", value=target.mention)
        embed.add_field(name="Deleted", value=str(deleted))
        embed.add_field(name="Moderator", value=str(interaction.user), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await self._log(interaction.guild, embed)


def setup(bot):
    bot.add_cog(Moderation(bot))
