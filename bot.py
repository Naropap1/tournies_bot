"""
Tournies Bot — Entry point.

Initializes the Discord bot, loads cogs, connects to the database,
and starts background alert tasks.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

import discord
from discord.ext import commands

from config import COMMAND_PREFIX, DISCORD_TOKEN, BOT_DESCRIPTION, DB_PATH
from db.database import Database
from startgg.client import StartGGClient

# ── Logging setup ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("tournies_bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("tournies_bot")

# ── Intents ────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class TourniesBot(commands.Bot):
    """Custom Bot subclass with database and Start.gg client lifecycle."""

    def __init__(self) -> None:
        super().__init__(
            command_prefix=COMMAND_PREFIX,
            description=BOT_DESCRIPTION,
            intents=intents,
            help_command=commands.DefaultHelpCommand(),
        )
        self.db = Database(DB_PATH)
        self.startgg = StartGGClient()

    async def setup_hook(self) -> None:
        """Called when the bot is starting up. Initialize DB and load cogs."""
        logger.info("Initializing database at %s ...", DB_PATH)
        await self.db.initialize()
        logger.info("Database initialized successfully.")

        # Load all cogs
        cog_names = [
            "cogs.scheduling",
            "cogs.participation",
            "cogs.live",
            "cogs.prestige",
            "tasks.alerts",
        ]
        for cog in cog_names:
            try:
                await self.load_extension(cog)
                logger.info("Loaded cog: %s", cog)
            except Exception as exc:
                logger.error("Failed to load cog %s: %s", cog, exc, exc_info=True)

    async def on_ready(self) -> None:
        """Fired when the bot has connected and is ready."""
        assert self.user is not None
        logger.info("Logged in as %s (ID: %s)", self.user, self.user.id)
        logger.info("Connected to %d guild(s)", len(self.guilds))
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="tournaments | !help",
            )
        )

    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        """Global command error handler."""
        if isinstance(error, commands.CommandNotFound):
            return  # Silently ignore unknown commands
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing argument: `{error.param.name}`. Use `!help {ctx.command}` for usage.")
            return
        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ You don't have permission to use this command.")
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"❌ Invalid argument. Use `!help {ctx.command}` for usage.")
            return
        # Unexpected errors
        logger.error("Unhandled command error in %s: %s", ctx.command, error, exc_info=error)
        await ctx.send("❌ An unexpected error occurred. Please try again later.")

    async def close(self) -> None:
        """Clean shutdown: close DB and Start.gg client before disconnecting."""
        logger.info("Shutting down...")
        await self.startgg.close()
        await self.db.close()
        await super().close()


def main() -> None:
    """Entry point — create and run the bot."""
    if not DISCORD_TOKEN:
        logger.critical("DISCORD_TOKEN is not set. Please configure your .env file.")
        sys.exit(1)

    bot = TourniesBot()

    # Graceful shutdown on SIGINT/SIGTERM
    try:
        bot.run(DISCORD_TOKEN, log_handler=None)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down.")


if __name__ == "__main__":
    main()
