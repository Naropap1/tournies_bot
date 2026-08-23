import logging
import random
from datetime import datetime
from io import BytesIO
import json
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from bracket.engine import generate_bracket, report_match_result, get_open_matches, is_bracket_complete, get_winner, BracketState, BracketRoute
from bracket.draw import generate_bracket_image
from db.models import BracketSnapshot, Match, Entrant, Tournament

logger = logging.getLogger(__name__)

def _serialize_matches(matches) -> str:
    # We serialize matches to json
    data = []
    for m in matches:
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
    return json.dumps(data)

def _deserialize_matches(json_str: str) -> list[Match]:
    data = json.loads(json_str)
    return [Match(
        id=None,
        tournament_id=d['tournament_id'],
        round_num=d['round_num'],
        match_number=d['match_number'],
        player1_id=d['player1_id'],
        player2_id=d['player2_id'],
        winner_id=d['winner_id'],
        score=d['score'],
        status=d['status'],
        is_grand_finals=d['is_grand_finals'],
        best_of=d['best_of']
    ) for d in data]

class LiveCog(commands.Cog, name="Live Bracket"):
    """Commands for running active tournaments."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _get_bracket_image(self, guild, state):
        names_map = {}
        for m in state.matches:
            for pid in (m.player1_id, m.player2_id):
                if pid and pid not in names_map:
                    member = guild.get_member(pid)
                    names_map[pid] = member.display_name if member else str(pid)
        return generate_bracket_image(state, names_map=names_map)

    async def _post_matchboard(self, channel, tournament, state: BracketState):
        open_matches = get_open_matches(state)
        if not open_matches:
            return

        desc = ""
        for m in open_matches:
            p1 = f"<@{m.player1_id}>"
            p2 = f"<@{m.player2_id}>"
            title = f"Round {m.round_num}" if m.round_num > 0 else (f"Grand Finals" if m.round_num == 0 else f"Losers Round {abs(m.round_num)}")
            desc += f"**{title} (Match {m.match_number})**\n{p1} vs {p2}\n\n"
        
        embed = discord.Embed(
            title=f"[{tournament.game}] ⚔️ Open Matches (State: {tournament.version})",
            description=desc + f"\n*Report wins with `!win {tournament.game}`. (Or `!win {tournament.game} @Winner` to report for someone else).*".strip(),
            color=discord.Color.red()
        )
        await channel.send(embed=embed)

    @commands.command(name="start")
    async def start_tournament(self, ctx: commands.Context, *, game: str) -> None:
        tournament = await self.bot.db.get_tournament_by_game(ctx.guild.id, game, status="scheduled")
        if not tournament:
            await ctx.send(f"❌ No scheduled `{game}` tournament found.")
            return

        if ctx.author.id not in tournament.owners and not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Only tournament owners can start the bracket.")
            return

        entrants = await self.bot.db.get_entrants(tournament.id)
        if len(entrants) < 2:
            await ctx.send(f"❌ Cannot start `{game}` tournament with less than 2 players.")
            return

        await self.bot.db.update_tournament(tournament.id, status="live", version=1)

        entrant_ids = [e.discord_id for e in entrants]
        # Randomly shuffle entrants to generate random seeds, as per standard defaults
        random.shuffle(entrant_ids)
        
        state = generate_bracket(tournament.id, entrant_ids)
        await self.bot.db.insert_matches(state.matches)

        await ctx.send(f"🏆 **[{game}] Tournament has begun!** Roster locked with {len(entrants)} players.")
        
        image_file = self._get_bracket_image(ctx.guild, state)
        await ctx.send(content=f"**[{game}] Initial Bracket:** (State: 1)", file=image_file)
        
        await self._post_matchboard(ctx.channel, tournament, state)

    @commands.command(name="bracket")
    async def view_bracket(self, ctx: commands.Context, *, game: str) -> None:
        tournament = await self.bot.db.get_tournament_by_game(ctx.guild.id, game, status="live")
        if not tournament:
            await ctx.send(f"❌ No active `{game}` tournament found.")
            return

        matches = await self.bot.db.get_matches(tournament.id)
        if not matches:
            await ctx.send("❌ No matches found for this tournament.")
            return

        entrants = await self.bot.db.get_entrants(tournament.id)
        state = generate_bracket(tournament.id, [e.discord_id for e in entrants])
        state.matches = matches
        
        image_file = self._get_bracket_image(ctx.guild, state)
        await ctx.send(content=f"**[{game}] Current Bracket:** (State: {tournament.version})", file=image_file)

    @commands.command(name="win")
    async def report_win(self, ctx: commands.Context, *, args: str) -> None:
        args = args.strip()
        parts = args.split()
        winner_id = None
        game = args
        
        if parts:
            last_part = parts[-1]
            if last_part.startswith('@') and last_part[1:].isdigit():
                winner_id = int(last_part[1:])
                game = " ".join(parts[:-1])
            elif last_part.isdigit() and len(last_part) < 17:
                winner_id = int(last_part)
                game = " ".join(parts[:-1])
            elif last_part.startswith('<@') and last_part.endswith('>'):
                try:
                    winner_id = int(last_part[2:-1].replace('!', ''))
                    game = " ".join(parts[:-1])
                except ValueError:
                    pass
        
        # If the user didn't specify a winner, default to the author
        if not winner_id:
            winner_id = ctx.author.id
            
        tournament = await self.bot.db.get_tournament_by_game(ctx.guild.id, game, status="live")
        if not tournament:
            await ctx.send(f"❌ No active `{game}` tournament found.")
            return
        matches = await self.bot.db.get_matches(tournament.id)
        entrants = await self.bot.db.get_entrants(tournament.id)
        state = generate_bracket(tournament.id, [e.discord_id for e in entrants])
        state.matches = matches

        # Find the match
        from bracket.engine import get_match_for_player
        match = get_match_for_player(state, winner_id)

        if not match:
            await ctx.send(f"❌ <@{winner_id}> does not have any open matches in `{game}`.")
            return

        # Create a snapshot before modifying
        snapshot = BracketSnapshot(
            tournament_id=tournament.id,
            version=tournament.version,
            matches_json=_serialize_matches(state.matches),
            created_at=datetime.now(ZoneInfo("UTC"))
        )
        await self.bot.db.insert_snapshot(snapshot)
        
        new_version = tournament.version + 1
        await self.bot.db.update_tournament(tournament.id, version=new_version)
        tournament.version = new_version

        # Apply win
        try:
            state, newly_opened = report_match_result(state, (match.round_num, match.match_number), winner_id, None)
        except Exception as e:
            await ctx.send(f"❌ Error applying result: {e}")
            return

        await self.bot.db.delete_matches(tournament.id)
        await self.bot.db.insert_matches(state.matches)

        loser_id = match.player1_id if match.player2_id == winner_id else match.player2_id
        
        w_ping = f"<@{winner_id}>"
        l_ping = f"<@{loser_id}>"
        await ctx.send(f"✅ **[{game}]** {w_ping} defeated {l_ping}!")
        
        image_file = self._get_bracket_image(ctx.guild, state)
        await ctx.send(content=f"**[{game}] Bracket Updated:** (State: {tournament.version})", file=image_file)

        if is_bracket_complete(state):
            await self._conclude_tournament(ctx.channel, tournament, state)
        else:
            if newly_opened:
                await self._post_matchboard(ctx.channel, tournament, state)

    @commands.command(name="revert")
    async def revert_bracket(self, ctx: commands.Context, *, args: str) -> None:
        args = args.strip()
        parts = args.split()
        if len(parts) < 2:
            await ctx.send("❌ Usage: `!revert {game} {version}`")
            return
            
        try:
            version = int(parts[-1])
            game = " ".join(parts[:-1])
        except ValueError:
            await ctx.send("❌ Usage: `!revert {game} {version}` (version must be a number)")
            return
            
        tournament = await self.bot.db.get_tournament_by_game(ctx.guild.id, game, status="live")
        if not tournament:
            await ctx.send(f"❌ No active `{game}` tournament found.")
            return
            
        if ctx.author.id not in tournament.owners and not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Only tournament owners can revert bracket states.")
            return

        snapshot = await self.bot.db.get_snapshot(tournament.id, version)
        if not snapshot:
            await ctx.send(f"❌ Could not find State {version} for `{game}`.")
            return

        # Restore from snapshot
        restored_matches = _deserialize_matches(snapshot.matches_json)
        
        await self.bot.db.delete_matches(tournament.id)
        await self.bot.db.insert_matches(restored_matches)
        
        await self.bot.db.update_tournament(tournament.id, version=version)
        await self.bot.db.delete_snapshots_after(tournament.id, version)
        
        tournament.version = version

        entrants = await self.bot.db.get_entrants(tournament.id)
        state = generate_bracket(tournament.id, [e.discord_id for e in entrants])
        state.matches = restored_matches

        await ctx.send(f"⏪ **[{game}] Bracket reverted to State {version}.**")
        image_file = self._get_bracket_image(ctx.guild, state)
        await ctx.send(content=f"**[{game}] Current Bracket:** (State: {version})", file=image_file)
        await self._post_matchboard(ctx.channel, tournament, state)

    @commands.command(name="dq")
    async def disqualify(self, ctx: commands.Context, *, args: str) -> None:
        args = args.strip()
        parts = args.split()
        if len(parts) < 2:
            await ctx.send("❌ Usage: `!dq {game} @Player`")
            return
            
        last_part = parts[-1]
        player_id = None
        game = " ".join(parts[:-1])
        
        if last_part.startswith('@') and last_part[1:].isdigit():
            player_id = int(last_part[1:])
        elif last_part.isdigit() and len(last_part) < 17:
            player_id = int(last_part)
        elif last_part.startswith('<@') and last_part.endswith('>'):
            try:
                player_id = int(last_part[2:-1].replace('!', ''))
            except ValueError:
                pass
                
        if not player_id:
            await ctx.send("❌ Could not resolve the player ping. Usage: `!dq {game} @Player`")
            return

        tournament = await self.bot.db.get_tournament_by_game(ctx.guild.id, game, status="live")
        if not tournament:
            await ctx.send(f"❌ No active `{game}` tournament found.")
            return

        if ctx.author.id not in tournament.owners and not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Only tournament owners can disqualify players.")
            return

        matches = await self.bot.db.get_matches(tournament.id)
        entrants = await self.bot.db.get_entrants(tournament.id)
        state = generate_bracket(tournament.id, [e.discord_id for e in entrants])
        state.matches = matches

        match = get_match_for_player(state, player_id)
        if not match:
            await ctx.send(f"❌ <@{player_id}> is not currently in an open match.")
            return

        # Snapshot before DQ
        snapshot = BracketSnapshot(
            tournament_id=tournament.id,
            version=tournament.version,
            matches_json=_serialize_matches(state.matches),
            created_at=datetime.now(ZoneInfo("UTC"))
        )
        await self.bot.db.insert_snapshot(snapshot)
        new_version = tournament.version + 1
        await self.bot.db.update_tournament(tournament.id, version=new_version)
        tournament.version = new_version

        winner_id = match.player1_id if match.player2_id == player_id else match.player2_id
        try:
            state, newly_opened = report_match_result(state, (match.round_num, match.match_number), winner_id, None)
        except Exception as e:
            await ctx.send(f"❌ Error applying DQ: {e}")
            return

        await self.bot.db.delete_matches(tournament.id)
        await self.bot.db.insert_matches(state.matches)

        p_ping = f"<@{player_id}>"
        w_ping = f"<@{winner_id}>"
        await ctx.send(f"🚨 **[{game}]** {p_ping} has been disqualified. {w_ping} advances.")
        
        if is_bracket_complete(state):
            await self._conclude_tournament(ctx.channel, tournament, state)
        else:
            await self._post_matchboard(ctx.channel, tournament, state)

    async def _conclude_tournament(self, channel, tournament: Tournament, state: BracketState) -> None:
        class FakeCtx:
            def __init__(self):
                self.guild = channel.guild
        ctx = FakeCtx()
        winner_id = get_winner(state)
        await self.bot.db.update_tournament(tournament.id, status="completed")
        
        w_ping = f"<@{winner_id}>"
        
        # Insert Champion
        from db.models import Champion
        champ = Champion(
            guild_id=tournament.guild_id,
            game=tournament.game,
            discord_id=winner_id,
            tournament_id=tournament.id,
            won_at=datetime.now(ZoneInfo("UTC"))
        )
        await self.bot.db.insert_champion(champ)

        embed = discord.Embed(
            title=f"🏆 [{tournament.game}] Tournament Completed! 🏆",
            description=f"**Congratulations to {w_ping} for winning it all!**",
            color=discord.Color.gold()
        )
        
        # Reschedule logic
        if tournament.frequency != "one-time":
            from dateutil.relativedelta import relativedelta
            
            delta_map = {
                "weekly": relativedelta(weeks=1),
                "monthly": relativedelta(months=1),
                "quarterly": relativedelta(months=3),
                "bi-annually": relativedelta(months=6),
                "annually": relativedelta(years=1)
            }
            delta = delta_map.get(tournament.frequency.lower(), relativedelta(months=1))
            next_date = tournament.scheduled_at + delta
            
            # Insert the next scheduled event
            new_t = Tournament(
                guild_id=tournament.guild_id,
                channel_id=tournament.channel_id,
                game=tournament.game,
                scheduled_at=next_date,
                frequency=tournament.frequency,
                status="scheduled",
                created_at=datetime.now(ZoneInfo("UTC")),
                rules=tournament.rules,
                owners=tournament.owners,
                version=1
            )
            await self.bot.db.insert_tournament(new_t)
            embed.add_field(name="🔄 Auto-Rescheduled", value=f"The next **{tournament.game}** event is scheduled for <t:{int(next_date.timestamp())}:F>!", inline=False)

        await channel.send(embed=embed)
        image_file = self._get_bracket_image(ctx.guild, state)
        await channel.send(content=f"**[{tournament.game}] Final Bracket:**", file=image_file)


    @commands.command(name="ping")
    @commands.has_permissions(administrator=True)
    async def ping_matches(self, ctx: commands.Context, *, game: str) -> None:
        '''Ping all players in open matches.'''
        tournament = await self.bot.db.get_tournament_by_game(ctx.guild.id, game, "live")
        if not tournament:
            await ctx.send(f"❌ No live tournament found for {game}.")
            return
            
        matches = await self.bot.db.get_matches(tournament.id)
        entrants = await self.bot.db.get_entrants(tournament.id)
        state = generate_bracket(tournament.id, [e.discord_id for e in entrants])
        state.matches = matches
        
        open_matches = get_open_matches(state)
        if not open_matches:
            await ctx.send(f"❌ No open matches currently in {game}.")
            return
            
        pings = set()
        for m in open_matches:
            if m.player1_id: pings.add(m.player1_id)
            if m.player2_id: pings.add(m.player2_id)
            
        if not pings:
            return
            
        ping_str = " ".join([f"<@{p}>" for p in pings])
        await ctx.send(f"🔔 **[{game}]** Your matches are ready to be played! Please report the winner using !win {game} @winner\n{ping_str}")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LiveCog(bot))
