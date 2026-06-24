from datetime import datetime, timezone

import aiosqlite
import nextcord
from nextcord.ext import commands

from core import DB_PATH, invite_cache
from core.common import is_admin
from core.config import cget, clist


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
                (guild.id, inviter.id if inviter else 0, member.id, datetime.now(timezone.utc).isoformat()),
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
        unverified_role_name = cget("server", "unverified-role", fallback=None)
        if unverified_role_name:
            role = nextcord.utils.get(guild.roles, name=unverified_role_name)
            if role:
                try:
                    await member.add_roles(role)
                except Exception:
                    pass
        autorole_names = clist("server", "autorole", fallback=[])
        if autorole_names:
            roles = [role for role in guild.roles if role.name in autorole_names]
            if roles:
                try:
                    await member.add_roles(*roles)
                except Exception:
                    pass

    @nextcord.slash_command(name="inviter", description="Check who invited a member.")
    async def inviter(self, interaction: nextcord.Interaction, member: nextcord.Member = nextcord.SlashOption(description="Member to check")):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT inviter_id, timestamp FROM invite_tracking WHERE guild_id=? AND invited_id=?", (interaction.guild.id, member.id)) as cur:
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


def setup(bot):
    bot.add_cog(InviteTracking(bot))
