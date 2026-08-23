"""
Background Alert Tasks — Tournament reminders, auto-deletion, and auto-recurrence.

Runs as a discord.ext.tasks loop checking for:
  - 1-week-out creator ping
  - 24-hour-out channel announcement
  - Auto-deletion of underpopulated events
"""

import logging
from datetime import datetime, timedelta

import discord
from discord.ext import commands, tasks

from config import (
    ALERT_1_WEEK_HOURS,
    ALERT_24_HOURS,
    ALERT_CHECK_INTERVAL_MINUTES,
    MIN_ENTRANTS,
)

logger = logging.getLogger(__name__)


class AlertsCog(commands.Cog, name="Alerts"):
    """Background task loop for tournament alerts and auto-management."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Start the alert loop when the cog loads."""
        self.alert_loop.start()
        logger.info("Alert loop started (interval: %d min)", ALERT_CHECK_INTERVAL_MINUTES)

    async def cog_unload(self) -> None:
        """Stop the alert loop on cog unload."""
        self.alert_loop.cancel()
        logger.info("Alert loop stopped.")

    @tasks.loop(minutes=ALERT_CHECK_INTERVAL_MINUTES)
    async def alert_loop(self) -> None:
        """Main alert loop — runs periodically to check all scheduled tournaments."""
        try:
            await self._process_alerts()
        except Exception as e:
            logger.error("Error in alert loop: %s", e, exc_info=True)

    @alert_loop.before_loop
    async def before_alert_loop(self) -> None:
        """Wait until the bot is fully ready before starting the loop."""
        await self.bot.wait_until_ready()
        logger.info("Alert loop waiting complete, bot is ready.")

    async def _process_alerts(self) -> None:
        """Check all guilds for upcoming tournaments needing alerts or cleanup."""
        now = datetime.now()

        for guild in self.bot.guilds:
            tournaments = await self.bot.db.get_upcoming_tournaments(guild.id)

            for t in tournaments:
                if t.status != "scheduled":
                    continue

                hours_until = (t.scheduled_at - now).total_seconds() / 3600

                # ── 1-Week Alert ────────────────────────────────────────
                if hours_until <= ALERT_1_WEEK_HOURS and hours_until > ALERT_24_HOURS:
                    if not await self.bot.db.has_alert_been_sent(t.id, "1_week"):
                        await self._send_1_week_alert(t)
                        await self.bot.db.log_alert(t.id, "1_week")

                # ── 24-Hour Alert ───────────────────────────────────────
                if hours_until <= ALERT_24_HOURS and hours_until > 0:
                    if not await self.bot.db.has_alert_been_sent(t.id, "24_hour"):
                        await self._send_24_hour_alert(t, guild)
                        await self.bot.db.log_alert(t.id, "24_hour")

                # ── Auto-Deletion: Event time arrived with <2 players ──
                if hours_until <= 0:
                    entrants = await self.bot.db.get_entrants(t.id)
                    if len(entrants) < MIN_ENTRANTS:
                        await self._auto_delete_tournament(t, guild, len(entrants))

    async def _send_1_week_alert(self, t) -> None:
        """DM the tournament creator as a 1-week check-in."""
        try:
            creator = await self.bot.fetch_user(t.creator_id)
            if creator:
                embed = discord.Embed(
                    title=f"📅 1-Week Reminder: {t.game}",
                    description=(
                        f"Your **{t.game}** tournament is in **1 week**!\n"
                        f"**Date:** <t:{int(t.scheduled_at.timestamp())}:F>\n\n"
                        f"Make sure players are signed up. Currently scheduled in "
                        f"the server."
                    ),
                    color=discord.Color.blue(),
                )
                await creator.send(embed=embed)
                logger.info("Sent 1-week alert to %s for tournament #%d", creator, t.id)
        except discord.Forbidden:
            logger.warning("Cannot DM creator %d for tournament #%d (DMs disabled)", t.creator_id, t.id)
        except Exception as e:
            logger.error("Failed to send 1-week alert for tournament #%d: %s", t.id, e)

    async def _send_24_hour_alert(self, t, guild: discord.Guild) -> None:
        """Post a 24-hour warning in the tournament's channel or #general."""
        channel = guild.get_channel(t.channel_id)

        # Fallback: try to find a #general channel in the same category
        if not channel:
            for ch in guild.text_channels:
                if ch.name.lower() == "general":
                    channel = ch
                    break

        if not channel:
            logger.warning("No channel found for 24-hour alert, tournament #%d", t.id)
            return

        entrants = await self.bot.db.get_entrants(t.id)
        roster_count = len(entrants)

        embed = discord.Embed(
            title=f"⏰ Tournament Tomorrow: {t.game}",
            description=(
                f"The **{t.game}** tournament is **tomorrow**!\n"
                f"**Time:** <t:{int(t.scheduled_at.timestamp())}:F>\n"
                f"**Roster:** {roster_count} player(s)\n\n"
                f"Sign up now with `!join {t.game}` if you haven't already!"
            ),
            color=discord.Color.orange(),
        )
        try:
            await channel.send("@here", embed=embed)
            logger.info("Sent 24-hour alert in #%s for tournament #%d", channel.name, t.id)
        except Exception as e:
            logger.error("Failed to send 24-hour alert for tournament #%d: %s", t.id, e)

    async def _auto_delete_tournament(self, t, guild: discord.Guild, entrant_count: int) -> None:
        """Cancel an auto-scheduled tournament that didn't get enough signups."""
        await self.bot.db.update_tournament(t.id, status="cancelled")

        channel = guild.get_channel(t.channel_id)
        if channel:
            try:
                await channel.send(
                    f"🗑️ The **{t.game}** tournament has been auto-cancelled "
                    f"(only {entrant_count}/{MIN_ENTRANTS} players signed up)."
                )
            except Exception as e:
                logger.error("Failed to announce auto-deletion for tournament #%d: %s", t.id, e)

        logger.info(
            "Auto-deleted tournament #%d (%s) — only %d entrants",
            t.id, t.game, entrant_count,
        )


async def setup(bot: commands.Bot) -> None:
    """Load the Alerts background task cog."""
    await bot.add_cog(AlertsCog(bot))
