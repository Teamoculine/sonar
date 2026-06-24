from datetime import datetime, timezone

import aiosqlite
import nextcord
from nextcord.ext import commands, tasks

from core import DB_PATH
from core.config import fmt_duration, parse_duration


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
            async with db.execute("SELECT id, guild_id, channel_id, message_id, question, options FROM polls WHERE closed=0 AND ends_at <= ?", (now.isoformat(),)) as cur:
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

    async def _sync_poll(self, guild_id: int, message_id: int):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT id, channel_id, question, options, closed FROM polls WHERE guild_id=? AND message_id=?",
                (guild_id, message_id),
            ) as cur:
                row = await cur.fetchone()
            if not row or row[4]:
                return
            poll_id, channel_id, question, options_str, _closed = row
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
        winner = results[0] if results else None
        embed = nextcord.Embed(title=f"📊 {question}", color=0x4B3BFF)
        for opt, count, emoji in results:
            bar = "█" * min(count, 20)
            embed.add_field(name=f"{emoji} {opt}", value=f"{bar} {count} vote(s)", inline=False)
        if winner:
            embed.set_footer(text=f"Leading: {winner[2]} {winner[0]} with {winner[1]} vote(s)")
        await msg.edit(embed=embed)

    @nextcord.slash_command(name="poll", description="Create a poll.")
    async def poll(self, interaction: nextcord.Interaction, question: str = nextcord.SlashOption(description="Poll question"), options: str = nextcord.SlashOption(description="Options separated by | (max 10). E.g: Yes|No|Maybe"), duration: str = nextcord.SlashOption(description="Duration e.g. 1h, 30m, 1h30m")):
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
            await db.execute("INSERT INTO polls (guild_id, channel_id, message_id, question, options, ends_at) VALUES (?,?,?,?,?,?)", (interaction.guild.id, interaction.channel.id, msg.id, question, "||".join(opts), ends_at.isoformat()))
            await db.commit()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: nextcord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        if str(payload.emoji) not in ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]:
            return
        await self._sync_poll(payload.guild_id, payload.message_id)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: nextcord.RawReactionActionEvent):
        if str(payload.emoji) not in ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]:
            return
        await self._sync_poll(payload.guild_id, payload.message_id)


def setup(bot):
    bot.add_cog(Polls(bot))
