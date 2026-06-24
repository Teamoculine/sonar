"""
Sonar - A free, open, self-hosted Discord utility bot.
https://github.com/Teamoculine/sonar

Run with:
    pip install nextcord aiosqlite
    python sonar.py

WE ARE MOVING TO GITLAB SOON!
"""

import asyncio
import importlib.util
from pathlib import Path

from core import bot, db_init, log
from core.config import cget


@bot.event
async def on_ready():
    await db_init(log)
    log.info(f"Sonar online as {bot.user} ({bot.user.id})")
    await bot.sync_all_application_commands()
    log.info("Slash commands synced.")


@bot.event
async def on_application_command_error(interaction, error: Exception):
    log.error(f"Command error: {error}")
    try:
        await interaction.response.send_message("❌ An error occurred.", ephemeral=True)
    except Exception:
        pass


async def _load_modules():
    modules_dir = Path(__file__).resolve().parent / "modules"
    for path in sorted(modules_dir.glob("*.py")):
        spec = importlib.util.spec_from_file_location(f"modules.{path.stem}", path)
        if not spec or not spec.loader:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        setup = getattr(module, "setup", None)
        if setup is None:
            continue
        result = setup(bot)
        if asyncio.iscoroutine(result):
            await result


if __name__ == "__main__":
    asyncio.run(_load_modules())
    token = cget("sonar", "token", fallback=None)
    if not token:
        log.error("No token found in [sonar] token= in sonar.idf")
        raise SystemExit(1)
    bot.run(token)
