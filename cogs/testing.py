import discord
from discord.ext import commands
from datetime import datetime
from zoneinfo import ZoneInfo

from db.models import Tournament, Entrant
from bracket.engine import generate_bracket
from bracket.draw import generate_bracket_image

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
            scheduled_at=datetime.now(ZoneInfo("UTC")),
            frequency="monthly",
            status="scheduled",
            created_at=datetime.now(ZoneInfo("UTC")),
            rules="Test rules.",
            version=1,
            owners=[ctx.author.id]
        )
        tournament.id = await self.bot.db.insert_tournament(tournament)

        # 2. Add 5 Entrants
        # ID 101, 102, 103, 104, 105
        entrant_ids = [101, 102, 103, 104, 105]
        for eid in entrant_ids:
            ent = Entrant(
                tournament_id=tournament.id,
                discord_id=eid,
                joined_at=datetime.now(ZoneInfo("UTC")),
            )
            await self.bot.db.insert_entrant(ent)

        await ctx.send(f"✅ Created dummy tournament for **{game}** with 5 players.")

        # 3. Start the tournament using the actual live cog start command
        live_cog = self.bot.get_cog("Live Bracket")
        if live_cog:
            await ctx.invoke(live_cog.start_tournament, game=game)
        else:
            await ctx.send("❌ Live cog not found.")


async def setup(bot: commands.Bot):
    await bot.add_cog(TestingCog(bot))
