import nextcord
from nextcord.ext import commands


class Core(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @nextcord.slash_command(name="ping", description="Check bot latency.")
    async def ping(self, interaction: nextcord.Interaction):
        ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"Pong! `{ms}ms`", ephemeral=True)

    @nextcord.slash_command(name="help", description="List all Sonar commands.")
    async def help(self, interaction: nextcord.Interaction):
        embed = nextcord.Embed(title="Sonar — Command Reference", color=0x4B3BFF)
        embed.add_field(name="Core", value="`/ping` `/help`", inline=False)
        embed.add_field(name="Moderation", value="`/ban` `/kick` `/timeout` `/warn` `/purge` `/lock` `/unlock`", inline=False)
        embed.add_field(name="Verification", value="`/verify`", inline=False)
        embed.add_field(name="Confessions", value="`/confess` `/confess-delete` `/confess-report`", inline=False)
        embed.add_field(name="Birthdays", value="`/birthday-set` `/birthday-remove` `/birthday-list`", inline=False)
        embed.add_field(name="Polls", value="`/poll`", inline=False)
        embed.add_field(name="Reminders", value="`/remind` `/reminders-list`", inline=False)
        embed.add_field(name="Starboard", value="React ⭐ to any message.", inline=False)
        embed.add_field(name="Invite Tracking", value="`/inviter`", inline=False)
        embed.set_footer(text="Sonar — free, open, self-hosted.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


def setup(bot):
    bot.add_cog(Core(bot))
