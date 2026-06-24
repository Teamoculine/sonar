import logging

import nextcord
from nextcord.ext import commands

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("sonar")

intents = nextcord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(intents=intents)
invite_cache: dict[int, dict[str, nextcord.Invite]] = {}

