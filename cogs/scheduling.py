"""
Scheduling Cog — !create, !move, !upcoming

Handles tournament creation, rescheduling, and viewing upcoming events.
"""

import logging
from datetime import datetime

import discord
from discord.ext import commands

from config import DEFAULT_FREQUENCY, VALID_FREQUENCIES
from db.models import Tournament

logger = logging.getLogger(__name__)


def _parse_datetime(date_str: str, time_str: str) -> datetime:
    """
    Parse flexible date/time inputs into a datetime.

    Accepts:
      date: 2026-09-15, 09/15/2026, Sep-15-2026
      time: 7PM, 7:00PM, 19:00
    """
    # Normalize time
    time_str = time_str.upper().strip()
    for fmt_t in ("%I%p", "%I:%M%p", "%H:%M"):
        for fmt_d in ("%Y-%m-%d", "%m/%d/%Y", "%b-%d-%Y"):
            try:
                return datetime.strptime(f"{date_str} {time_str}", f"{fmt_d} {fmt_t}")
            except ValueError:
                continue
    raise ValueError(
        f"Could not parse date/time: `{date_str} {time_str}`.\n"
        f"Accepted formats: `2026-09-15 7PM`, `09/15/2026 7:00PM`, `Sep-15-2026 19:00`"
    )


class SchedulingCog(commands.Cog, name="Scheduling"):
    """Commands for creating and managing tournament schedules."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="create")
    async def create_tournament(
        self, ctx: commands.Context, game: str, date: str, time: str, frequency: str = DEFAULT_FREQUENCY
    ) -> None:
        """
        Schedule a new tournament.

        Usage: !create {game} {date} {time} [frequency]
        Example: !create Smash 2026-09-15 7PM monthly
        Frequency options: monthly, quarterly, bi-annually, annually (default: monthly)
        """
        frequency = frequency.lower()
        if frequency not in VALID_FREQUENCIES:
            await ctx.send(
                f"❌ Invalid frequency `{frequency}`. Choose from: {', '.join(VALID_FREQUENCIES)}"
            )
            return

        try:
            scheduled_at = _parse_datetime(date, time)
        except ValueError as e:
            await ctx.send(f"❌ {e}")
            return

        if scheduled_at <= datetime.now():
            await ctx.send("❌ Cannot schedule a tournament in the past.")
            return

        # Check for existing scheduled tournament for this game in this guild
        existing = await self.bot.db.get_tournament_by_game(ctx.guild.id, game, status="scheduled")
        if existing:
            await ctx.send(
                f"❌ A `{game}` tournament is already scheduled for "
                f"<t:{int(existing.scheduled_at.timestamp())}:F>. Use `!move {game}` to reschedule."
            )
            return

        tournament = Tournament(
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id,
            game=game,
            creator_id=ctx.author.id,
            scheduled_at=scheduled_at,
            frequency=frequency,
            status="scheduled",
            created_at=datetime.now(),
        )
        tournament_id = await self.bot.db.insert_tournament(tournament)
        logger.info(
            "Tournament #%d created: %s on %s by %s",
            tournament_id, game, scheduled_at.isoformat(), ctx.author,
        )

        embed = discord.Embed(
            title=f"🏆 Tournament Created: {game}",
            color=discord.Color.green(),
        )
        embed.add_field(name="📅 Date", value=f"<t:{int(scheduled_at.timestamp())}:F>", inline=True)
        embed.add_field(name="🔄 Frequency", value=frequency.capitalize(), inline=True)
        embed.add_field(name="👑 Creator", value=ctx.author.mention, inline=True)
        embed.add_field(name="📝 How to Join", value=f"`!join {game}`", inline=False)
        embed.set_footer(text=f"Tournament ID: {tournament_id}")
        await ctx.send(embed=embed)

    @commands.command(name="move")
    async def move_tournament(
        self, ctx: commands.Context, game: str, date: str, time: str
    ) -> None:
        """
        Reschedule a tournament (creator only).

        Usage: !move {game} {date} {time}
        Example: !move Smash 2026-09-20 8PM
        """
        tournament = await self.bot.db.get_tournament_by_game(ctx.guild.id, game, status="scheduled")
        if not tournament:
            await ctx.send(f"❌ No scheduled `{game}` tournament found.")
            return

        if tournament.creator_id != ctx.author.id:
            await ctx.send("❌ Only the tournament creator can reschedule.")
            return

        try:
            new_time = _parse_datetime(date, time)
        except ValueError as e:
            await ctx.send(f"❌ {e}")
            return

        if new_time <= datetime.now():
            await ctx.send("❌ Cannot reschedule to a past date.")
            return

        old_time = tournament.scheduled_at
        await self.bot.db.update_tournament(tournament.id, scheduled_at=new_time)
        logger.info(
            "Tournament #%d (%s) rescheduled: %s -> %s",
            tournament.id, game, old_time.isoformat(), new_time.isoformat(),
        )

        embed = discord.Embed(
            title=f"📅 Tournament Rescheduled: {game}",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Old Date", value=f"<t:{int(old_time.timestamp())}:F>", inline=True)
        embed.add_field(name="New Date", value=f"<t:{int(new_time.timestamp())}:F>", inline=True)
        embed.set_footer(text=f"Rescheduled by {ctx.author.display_name}")
        await ctx.send(embed=embed)

    @commands.command(name="upcoming")
    async def upcoming_tournaments(self, ctx: commands.Context) -> None:
        """
        View all scheduled and live events with their rosters.

        Usage: !upcoming
        """
        tournaments = await self.bot.db.get_upcoming_tournaments(ctx.guild.id)
        if not tournaments:
            await ctx.send("📭 No upcoming tournaments scheduled. Use `!create` to make one!")
            return

        embed = discord.Embed(
            title="🏆 Upcoming Tournaments",
            color=discord.Color.blue(),
        )
        for t in sorted(tournaments, key=lambda x: x.scheduled_at):
            entrants = await self.bot.db.get_entrants(t.id)
            status_emoji = "🟢" if t.status == "live" else "📅"
            roster = ", ".join(f"<@{e.discord_id}>" for e in entrants) if entrants else "_No signups yet_"

            embed.add_field(
                name=f"{status_emoji} {t.game} — <t:{int(t.scheduled_at.timestamp())}:R>",
                value=(
                    f"**Date:** <t:{int(t.scheduled_at.timestamp())}:F>\n"
                    f"**Frequency:** {t.frequency.capitalize()}\n"
                    f"**Creator:** <@{t.creator_id}>\n"
                    f"**Roster ({len(entrants)}):** {roster}\n"
                    f"**Status:** {t.status.capitalize()}"
                ),
                inline=False,
            )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Load the Scheduling cog."""
    await bot.add_cog(SchedulingCog(bot))
