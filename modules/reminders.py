from datetime import datetime, timezone

import aiosqlite
import nextcord
from nextcord.ext import commands, tasks

from core import DB_PATH
from core.config import fmt_duration, parse_duration


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
            async with db.execute("SELECT id, user_id, content FROM reminders WHERE done=0 AND remind_at <= ?", (now.isoformat(),)) as cur:
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
    async def remind(self, interaction: nextcord.Interaction, duration: str = nextcord.SlashOption(description="When to remind you. E.g. 1h, 30m, 2h30m"), reminder: str = nextcord.SlashOption(description="What to remind you about")):
        delta = parse_duration(duration)
        if not delta:
            return await interaction.response.send_message("❌ Invalid duration.", ephemeral=True)
        remind_at = datetime.now(timezone.utc) + delta
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO reminders (user_id, channel_id, remind_at, content) VALUES (?, ?, ?, ?)", (interaction.user.id, interaction.channel.id, remind_at.isoformat(), reminder))
            await db.commit()
        await interaction.response.send_message(f"✅ I'll DM you in **{fmt_duration(delta)}**: {reminder}", ephemeral=True)

    @nextcord.slash_command(name="reminders-list", description="List your active reminders.")
    async def reminders_list(self, interaction: nextcord.Interaction):
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT id, remind_at, content FROM reminders WHERE user_id=? AND done=0 AND remind_at > ? ORDER BY remind_at ASC",
                (interaction.user.id, now),
            ) as cur:
                rows = await cur.fetchall()
        if not rows:
            return await interaction.response.send_message("You have no active reminders.", ephemeral=True)
        lines = []
        now_dt = datetime.now(timezone.utc)
        for reminder_id, remind_at, content in rows:
            when = datetime.fromisoformat(remind_at)
            remaining = when - now_dt
            lines.append(f"`#{reminder_id}` in **{fmt_duration(remaining)}**: {content}")
        embed = nextcord.Embed(title="⏰ Active Reminders", description="\n".join(lines), color=0x4B3BFF)
        await interaction.response.send_message(embed=embed, ephemeral=True)


def setup(bot):
    bot.add_cog(Reminders(bot))
