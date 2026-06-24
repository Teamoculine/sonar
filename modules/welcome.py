import nextcord
from nextcord.ext import commands

from core.config import cget


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


def setup(bot):
    bot.add_cog(Welcome(bot))
