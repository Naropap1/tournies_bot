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
    @commands.command(name="join_dummy")
    @commands.has_permissions(administrator=True)
    async def join_dummy(self, ctx: commands.Context, *, args: str) -> None:
        """Join a fake user to a tournament for testing."""
        args = args.strip()
        parts = args.split()
        if len(parts) < 2:
            await ctx.send("❌ Usage: `!join_dummy {game} {fake_id}`")
            return
            
        last_part = parts[-1]
        player_id = None
        game = " ".join(parts[:-1])
        
        if last_part.startswith('@') and last_part[1:].isdigit():
            player_id = int(last_part[1:])
        elif last_part.isdigit():
            player_id = int(last_part)
        elif last_part.startswith('<@') and last_part.endswith('>'):
            try:
                player_id = int(last_part[2:-1].replace('!', ''))
            except ValueError:
                pass
                
        if not player_id:
            await ctx.send("❌ Could not parse fake ID. Example: `!join_dummy Smash Bros 101`")
            return

        tournament = await self.bot.db.get_tournament_by_game(ctx.guild.id, game, status="scheduled")
        if not tournament:
            await ctx.send(f"❌ No scheduled `{game}` tournament found.")
            return

        existing = await self.bot.db.get_entrant(tournament.id, player_id)
        if existing:
            if existing.dropped:
                await self.bot.db.update_entrant(existing.id, dropped=False)
                await ctx.send(f"✅ Re-enrolled `<@{player_id}>` into `{game}`.")
            else:
                await ctx.send(f"❌ `<@{player_id}>` is already in the tournament.")
            return

        ent = Entrant(
            tournament_id=tournament.id,
            discord_id=player_id,
            joined_at=datetime.now(ZoneInfo("UTC"))
        )
        await self.bot.db.insert_entrant(ent)
        await ctx.send(f"✅ Fake user `<@{player_id}>` joined `{game}`!")

async def setup(bot: commands.Bot):
    await bot.add_cog(TestingCog(bot))
