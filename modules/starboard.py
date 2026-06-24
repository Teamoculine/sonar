import aiosqlite
import nextcord
from nextcord.ext import commands

from core import DB_PATH
from core.config import cget


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
            async with db.execute("SELECT starboard_msg, star_count FROM starboard WHERE guild_id=? AND message_id=?", (guild.id, msg.id)) as cur:
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
                await db.execute("UPDATE starboard SET star_count=? WHERE guild_id=? AND message_id=?", (star_count, guild.id, msg.id))
            else:
                sb_msg = await starboard_ch.send(embed=embed)
                await db.execute("INSERT INTO starboard (guild_id, message_id, starboard_msg, star_count) VALUES (?,?,?,?)", (guild.id, msg.id, sb_msg.id, star_count))
            await db.commit()


def setup(bot):
    bot.add_cog(Starboard(bot))
