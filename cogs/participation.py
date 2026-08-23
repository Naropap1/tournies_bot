import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from db.models import Entrant

logger = logging.getLogger(__name__)


class ParticipationCog(commands.Cog, name="Participation"):
    """Commands for managing tournament signups."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="join")
    async def join_tournament(self, ctx: commands.Context, *, game: str) -> None:
        tournament = await self.bot.db.get_tournament_by_game(ctx.guild.id, game, status="scheduled")
        if not tournament:
            await ctx.send(f"❌ No scheduled `{game}` tournament found. Use `!upcoming` to see available events.")
            return

        existing = await self.bot.db.get_entrant(tournament.id, ctx.author.id)
        if existing:
            if existing.dropped:
                await self.bot.db.update_entrant(existing.id, dropped=False)
                await ctx.send(f"✅ Welcome back! You've re-joined the **{game}** tournament.")
                return
            await ctx.send(f"ℹ️ You're already signed up for the **{game}** tournament!")
            return
            
        entrant = Entrant(
            tournament_id=tournament.id,
            discord_id=ctx.author.id,
            joined_at=datetime.now(ZoneInfo("UTC")),
        )
        await self.bot.db.insert_entrant(entrant)

        entrants = await self.bot.db.get_entrants(tournament.id)

        embed = discord.Embed(
            title=f"✅ Joined: {game}",
            description=f"{ctx.author.mention} has signed up for the **{game}** tournament!\n**Roster:** {len(entrants)} player(s)",
            color=discord.Color.green(),
        )
        embed.add_field(name="📅 Event Date", value=f"<t:{int(tournament.scheduled_at.timestamp())}:F>", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="leave")
    async def leave_tournament(self, ctx: commands.Context, *, game: str) -> None:
        tournament = await self.bot.db.get_tournament_by_game(ctx.guild.id, game, status="scheduled")
        if not tournament:
            await ctx.send(f"❌ No scheduled `{game}` tournament found.")
            return

        existing = await self.bot.db.get_entrant(tournament.id, ctx.author.id)
        if not existing:
            await ctx.send(f"ℹ️ You aren't signed up for the **{game}** tournament.")
            return

        await self.bot.db.remove_entrant(tournament.id, ctx.author.id)
        entrants = await self.bot.db.get_entrants(tournament.id)
        await ctx.send(f"👋 {ctx.author.mention} has left the **{game}** tournament. **Roster:** {len(entrants)} player(s)")

    @commands.command(name="drop")
    async def drop_from_tournament(self, ctx: commands.Context, *, game: str = None) -> None:
        """
        Forfeit remaining matches in a live tournament.
        If you are in multiple, specify the game: !drop {game}
        """
        # We will dispatch a DQ command as if the user disqualified themselves.
        tournaments = await self.bot.db.get_upcoming_tournaments(ctx.guild.id)
        live_tournaments = [t for t in tournaments if t.status == "live"]
        
        if game:
            live_tournaments = [t for t in live_tournaments if t.game.lower() == game.lower()]

        if not live_tournaments:
            await ctx.send("❌ You're not currently in any live tournament.")
            return
            
        t = live_tournaments[0]
        entrant = await self.bot.db.get_entrant(t.id, ctx.author.id)
        if entrant and not entrant.dropped:
            await self.bot.db.update_entrant(entrant.id, dropped=True)
            
            # Use the live cog's dq logic for code reuse, but override permissions
            live_cog = self.bot.get_cog("Live Execution")
            if live_cog:
                # Mock admin permissions for self-DQ
                ctx.author._roles = ctx.author.roles # Ensure roles accessible
                
                # We can't easily fake the ctx.author.id to be an owner for the permission check inside dq.
                # So we'll just replicate the DQ logic here but with 'FF' instead of 'DQ'
                
                from bracket.engine import generate_bracket, get_match_for_player, report_match_result, is_bracket_complete
                from db.models import BracketSnapshot
                import json
                
                matches = await self.bot.db.get_matches(t.id)
                entrants = await self.bot.db.get_entrants(t.id)
                state = generate_bracket(t.id, [e.discord_id for e in entrants])
                state.matches = matches

                match = get_match_for_player(state, ctx.author.id)
                if not match:
                    await ctx.send(f"🏳️ {ctx.author.mention} has forfeited from the **{t.game}** tournament. (No active match to forfeit)")
                    return

                # Snapshot
                data = []
                for m in state.matches:
                    data.append({
                        'tournament_id': m.tournament_id,
                        'round_num': m.round_num,
                        'match_number': m.match_number,
                        'player1_id': m.player1_id,
                        'player2_id': m.player2_id,
                        'winner_id': m.winner_id,
                        'score': m.score,
                        'status': m.status,
                        'is_grand_finals': m.is_grand_finals,
                        'best_of': m.best_of
                    })
                    
                snapshot = BracketSnapshot(
                    tournament_id=t.id,
                    version=t.version,
                    matches_json=json.dumps(data),
                    created_at=datetime.now(ZoneInfo("UTC"))
                )
                await self.bot.db.insert_snapshot(snapshot)
                new_version = t.version + 1
                await self.bot.db.update_tournament(t.id, version=new_version)
                t.version = new_version

                winner_id = match.player1_id if match.player2_id == ctx.author.id else match.player2_id
                state, newly_opened = report_match_result(state, (match.round_num, match.match_number), winner_id, None)

                await self.bot.db.delete_matches(t.id)
                await self.bot.db.insert_matches(state.matches)

                await ctx.send(f"🏳️ **[{t.game}]** {ctx.author.mention} has forfeited. <@{winner_id}> advances.")
                
                if is_bracket_complete(state):
                    await live_cog._conclude_tournament(ctx.channel, t, state)
                else:
                    await live_cog._post_matchboard(ctx.channel, t, state)
            else:
                 await ctx.send("❌ Could not process drop. Live system offline.")
        else:
             await ctx.send(f"❌ You aren't active in `{t.game}`.")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ParticipationCog(bot))
