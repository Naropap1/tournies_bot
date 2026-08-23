import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from config import DEFAULT_FREQUENCY, VALID_FREQUENCIES
from db.models import Tournament

logger = logging.getLogger(__name__)

def _parse_datetime(date_str: str, time_str: str) -> datetime:
    """
    Parse flexible date/time inputs into a datetime in EST timezone,
    then convert to UTC for storage.
    """
    time_str = time_str.upper().strip()
    est = ZoneInfo("America/New_York")
    
    for fmt_t in ("%I%p", "%I:%M%p", "%H:%M"):
        for fmt_d in ("%Y-%m-%d", "%m/%d/%Y", "%b-%d-%Y"):
            try:
                dt_naive = datetime.strptime(f"{date_str} {time_str}", f"{fmt_d} {fmt_t}")
                dt_est = dt_naive.replace(tzinfo=est)
                return dt_est.astimezone(ZoneInfo("UTC"))
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
        self, ctx: commands.Context, *, args: str
    ) -> None:
        """
        Schedule a new tournament. All times are parsed as EST.
        Usage: !create {game} {date} {time} [frequency] [rules...]
        Example: !create Smash Bros 2026-09-15 7PM monthly Best of 3 until finals. No items.
        """
        import re
        from config import VALID_FREQUENCIES, DEFAULT_FREQUENCY
        
        match = re.search(r'\s+(\d{4}-\d{2}-\d{2})\s+', f" {args} ")
        if not match:
            await ctx.send("❌ Could not parse date. Usage: `!create {game} {YYYY-MM-DD} {Time} [Frequency] [Rules...]`")
            return
            
        date = match.group(1)
        game = args[:args.find(date)].strip()
        
        rest = args[args.find(date) + len(date):].strip()
        rest_parts = rest.split(maxsplit=2)
        
        if len(rest_parts) < 1:
            await ctx.send("❌ Missing time. Usage: `!create {game} {YYYY-MM-DD} {Time} [Frequency] [Rules...]`")
            return
            
        time = rest_parts[0]
        frequency = DEFAULT_FREQUENCY
        rules = "Standard rules apply."
        
        if len(rest_parts) > 1:
            if rest_parts[1].lower() in VALID_FREQUENCIES:
                frequency = rest_parts[1].lower()
                if len(rest_parts) > 2:
                    rules = rest_parts[2]
            else:
                rules = rest.split(maxsplit=1)[1]

        try:
            scheduled_at = _parse_datetime(date, time)
        except ValueError as e:
            await ctx.send(f"❌ {e}")
            return

        if scheduled_at <= datetime.now(ZoneInfo("UTC")):
            await ctx.send("❌ Cannot schedule a tournament in the past.")
            return

        existing = await self.bot.db.get_tournament_by_game(ctx.guild.id, game, status="scheduled")
        if existing:
            await ctx.send(f"❌ A `{game}` tournament is already scheduled. Use `!move {game}` to reschedule.")
            return

        tournament = Tournament(
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id,
            game=game,
            scheduled_at=scheduled_at,
            frequency=frequency,
            status="scheduled",
            created_at=datetime.now(ZoneInfo("UTC")),
            rules=rules,
            owners=[ctx.author.id]
        )
        tournament_id = await self.bot.db.insert_tournament(tournament)

        embed = discord.Embed(
            title=f"🏆 Tournament Created: {game}",
            description="**Times are parsed as EST.** Displaying in your local timezone below:",
            color=discord.Color.green(),
        )
        embed.add_field(name="📅 Date", value=f"<t:{int(scheduled_at.timestamp())}:F>", inline=True)
        embed.add_field(name="🔄 Frequency", value=frequency.capitalize(), inline=True)
        embed.add_field(name="👑 Owners", value=f"<@{ctx.author.id}>", inline=True)
        embed.add_field(name="📜 Rules", value=f"`!rules {game}`", inline=False)
        embed.add_field(name="📝 How to Join", value=f"`!join {game}`", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="move")
    async def move_tournament(self, ctx: commands.Context, *, args: str) -> None:
        """Reschedule a tournament (owners only). Uses EST."""
        import re
        match = re.search(r'\s+(\d{4}-\d{2}-\d{2})\s+', f" {args} ")
        if not match:
            await ctx.send("❌ Could not parse date. Usage: `!move {game} {YYYY-MM-DD} {Time}`")
            return
            
        date = match.group(1)
        game = args[:args.find(date)].strip()
        
        rest = args[args.find(date) + len(date):].strip()
        rest_parts = rest.split()
        
        if len(rest_parts) < 1:
            await ctx.send("❌ Missing time. Usage: `!move {game} {YYYY-MM-DD} {Time}`")
            return
            
        time = rest_parts[0]
        
        tournament = await self.bot.db.get_tournament_by_game(ctx.guild.id, game, status="scheduled")
        if not tournament:
            await ctx.send(f"❌ No scheduled `{game}` tournament found.")
            return

        if ctx.author.id not in tournament.owners and not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Only tournament owners can reschedule.")
            return

        try:
            new_time = _parse_datetime(date, time)
        except ValueError as e:
            await ctx.send(f"❌ {e}")
            return

        old_time = tournament.scheduled_at
        await self.bot.db.update_tournament(tournament.id, scheduled_at=new_time)

        embed = discord.Embed(
            title=f"📅 Tournament Rescheduled: {game}",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Old Date", value=f"<t:{int(old_time.timestamp())}:F>", inline=True)
        embed.add_field(name="New Date", value=f"<t:{int(new_time.timestamp())}:F>", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="co_owner")
    async def co_owner(self, ctx: commands.Context, *, args: str) -> None:
        """Add a co-owner to a tournament."""
        args = args.strip()
        parts = args.split()
        if len(parts) < 2:
            await ctx.send("❌ Usage: `!co_owner {game} @Player`")
            return
            
        last_part = parts[-1]
        member_id = None
        game = " ".join(parts[:-1])
        
        if last_part.startswith('@') and last_part[1:].isdigit():
            member_id = int(last_part[1:])
        elif last_part.isdigit() and len(last_part) < 17:
            member_id = int(last_part)
        elif last_part.startswith('<@') and last_part.endswith('>'):
            try:
                member_id = int(last_part[2:-1].replace('!', ''))
            except ValueError:
                pass
                
        if not member_id:
            await ctx.send("❌ Could not resolve the player ping. Usage: `!co_owner {game} @Player`")
            return

        tournament = await self.bot.db.get_tournament_by_game(ctx.guild.id, game, status="scheduled")
        if not tournament:
            tournament = await self.bot.db.get_tournament_by_game(ctx.guild.id, game, status="live")
        
        if not tournament:
            await ctx.send(f"❌ No active `{game}` tournament found.")
            return

        if ctx.author.id not in tournament.owners and not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Only tournament owners can add co-owners.")
            return

        if member_id in tournament.owners:
            await ctx.send(f"❌ <@{member_id}> is already an owner.")
            return

        await self.bot.db.add_owner(tournament.id, member_id)
        
        # Display nicely for dummy vs real users
        mention = f\"<@{member_id}>\"
        await ctx.send(f"✅ {mention} has been added as a co-owner for `{game}`!")

    @commands.command(name="rules")
    async def rules(self, ctx: commands.Context, *, game: str) -> None:
        """View the rules for a specific tournament."""
        tournament = await self.bot.db.get_tournament_by_game(ctx.guild.id, game, status="scheduled")
        if not tournament:
            tournament = await self.bot.db.get_tournament_by_game(ctx.guild.id, game, status="live")
            
        if not tournament:
            await ctx.send(f"❌ No active `{game}` tournament found.")
            return

        embed = discord.Embed(
            title=f"📜 Rules: {game}",
            description=tournament.rules,
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

    @commands.command(name="upcoming")
    async def upcoming_tournaments(self, ctx: commands.Context) -> None:
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
            owners_str = ", ".join(f"<@{o}>" for o in t.owners)
            
            embed.add_field(
                name=f"{status_emoji} {t.game} — <t:{int(t.scheduled_at.timestamp())}:R>",
                value=(
                    f"**Date:** <t:{int(t.scheduled_at.timestamp())}:F>\n"
                    f"**Owners:** {owners_str}\n"
                    f"**Roster ({len(entrants)}):** {len(entrants)} signed up\n"
                    f"**Status:** {t.status.capitalize()}"
                ),
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.command(name="delete")
    async def delete_tournament(self, ctx: commands.Context, *, game: str) -> None:
        tournament = await self.bot.db.get_tournament_by_game(ctx.guild.id, game, status="scheduled")
        if not tournament:
            tournament = await self.bot.db.get_tournament_by_game(ctx.guild.id, game, status="live")
            
        if not tournament:
            await ctx.send(f"❌ No active or scheduled `{game}` tournament found.")
            return

        is_owner = ctx.author.id in tournament.owners
        is_admin = ctx.author.guild_permissions.administrator
        if not (is_owner or is_admin):
            await ctx.send("❌ Only a tournament co-owner or a server administrator can delete this tournament.")
            return

        import asyncio
        await ctx.send(f"⚠️ **WARNING:** You are about to completely delete the `{game}` tournament and ALL of its match data, entrants, and snapshots! This action **CANNOT BE UNDONE**.\n\nType `!yes` in the next 15 seconds to confirm deletion.")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == "!yes"

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=15.0)
        except asyncio.TimeoutError:
            await ctx.send(f"⏳ Deletion of `{game}` timed out and was cancelled.")
            return

        await self.bot.db.delete_tournament(tournament.id)
        await ctx.send(f"🗑️ The `{game}` tournament has been completely deleted.")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SchedulingCog(bot))
