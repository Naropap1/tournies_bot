"""
Testing Cog — !test_tourney
"""
import discord
from discord.ext import commands
from datetime import datetime

from db.models import Tournament, Entrant, Match
from config import BEST_OF_STANDARD, BEST_OF_FINALS
from bracket.engine import generate_bracket, get_open_matches
from bracket.draw import generate_bracket_image
from cogs.live import _bracket_states, _announce_open_matches

class TestingCog(commands.Cog, name="Testing"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="test_tourney")
    @commands.has_permissions(administrator=True)
    async def test_tourney(self, ctx: commands.Context, *, game: str = "Test Game"):
        """Creates a dummy 5-player tournament and starts it instantly."""
        # 1. Create Tournament
        tournament = Tournament(
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id,
            game=game,
            creator_id=ctx.author.id,
            scheduled_at=datetime.now(),
            frequency="monthly",
            status="scheduled",
            created_at=datetime.now(),
        )
        tournament.id = await self.bot.db.insert_tournament(tournament)

        # 2. Add 5 Entrants
        # ID 101, 102, 103, 104, 105
        entrant_ids = [101, 102, 103, 104, 105]
        for eid in entrant_ids:
            ent = Entrant(
                tournament_id=tournament.id,
                discord_id=eid,
                joined_at=datetime.now(),
            )
            await self.bot.db.insert_entrant(ent)

        await ctx.send(f"✅ Created dummy tournament for **{game}** with 5 players.")

        # 3. Start the tournament
        state = generate_bracket(tournament.id, entrant_ids, BEST_OF_STANDARD, BEST_OF_FINALS)
        _bracket_states[tournament.id] = state

        for m in state.matches:
            m.id = await self.bot.db.insert_match(m)

        await self.bot.db.update_tournament(tournament.id, status="live")
        
        embed = discord.Embed(
            title=f"🚀 Tournament Started: {game}",
            description=f"The bracket is LIVE with 5 players!",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)

        img_file = generate_bracket_image(state)
        await ctx.send(file=img_file)

        open_matches = get_open_matches(state)
        await _announce_open_matches(ctx, tournament, open_matches)


async def setup(bot: commands.Bot):
    await bot.add_cog(TestingCog(bot))
