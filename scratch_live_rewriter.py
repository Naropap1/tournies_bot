import os

code = '''"""
Live Execution Cog — !start, !bracket, !win, !dq

Handles the full tournament lifecycle: bracket generation, match reporting,
and disqualification.
"""

import logging
from datetime import datetime
from dateutil.relativedelta import relativedelta

import discord
from discord.ext import commands

from config import BEST_OF_STANDARD, BEST_OF_FINALS, MIN_ENTRANTS
from db.models import Tournament, Match, Champion
from bracket.engine import (
    BracketState,
    generate_bracket,
    report_match_result,
    get_open_matches,
    get_match_for_player,
    is_bracket_complete,
    get_winner,
)
from bracket.draw import generate_bracket_image

logger = logging.getLogger(__name__)

# In-memory bracket states keyed by tournament_id.
# Persisted to DB (matches table) and rebuilt on restart.
_bracket_states: dict[int, BracketState] = {}


def _frequency_delta(frequency: str) -> relativedelta:
    """Convert a frequency string to a relativedelta."""
    return {
        "monthly": relativedelta(months=1),
        "quarterly": relativedelta(months=3),
        "bi-annually": relativedelta(months=6),
        "annually": relativedelta(years=1),
    }.get(frequency, relativedelta(months=1))


async def _rebuild_bracket_state(bot: commands.Bot, tournament_id: int) -> BracketState | None:
    """Rebuild a BracketState from persisted DB matches."""
    matches = await bot.db.get_matches(tournament_id)
    if not matches:
        return None
    # We need entrants to regenerate routes
    entrants = await bot.db.get_entrants(tournament_id)
    entrant_ids = [e.discord_id for e in entrants]
    # Regenerate the bracket to get the routing table
    state = generate_bracket(tournament_id, entrant_ids, BEST_OF_STANDARD, BEST_OF_FINALS)
    # Overlay persisted match data onto the generated skeleton
    for db_match in matches:
        for engine_match in state.matches:
            if engine_match.round_num == db_match.round_num and engine_match.match_number == db_match.match_number:
                engine_match.id = db_match.id
                engine_match.player1_id = db_match.player1_id
                engine_match.player2_id = db_match.player2_id
                engine_match.winner_id = db_match.winner_id
                engine_match.score = db_match.score
                engine_match.status = db_match.status
                break
    _bracket_states[tournament_id] = state
    return state


async def _persist_matches(bot: commands.Bot, tournament_id: int, state: BracketState) -> None:
    """Save all match states to the database."""
    for m in state.matches:
        if m.id:
            await bot.db.update_match(
                m.id,
                player1_id=m.player1_id,
                player2_id=m.player2_id,
                winner_id=m.winner_id,
                score=m.score,
                status=m.status,
            )


async def _announce_open_matches(
    ctx: commands.Context, tournament: Tournament, open_matches: list[Match]
) -> None:
    """Ping players for newly opened matches."""
    for m in open_matches:
        best_of_label = f"Bo{m.best_of}"
        gf_label = " 🏆 **GRAND FINALS** 🏆" if m.is_grand_finals else ""
        view = MatchView(ctx.bot, tournament, m)
        await ctx.send(
            f"⚔️ <@{m.player1_id}> vs <@{m.player2_id}>!{gf_label}\\n"
            f"_{best_of_label} — Report your win with the button below or `!win <score>` (e.g. `!win 2-1`)_",
            view=view
        )


async def _conclude_tournament(
    ctx: commands.Context, bot: commands.Bot, tournament: Tournament, winner_id: int
) -> None:
    """Conclude a tournament: crown champion, schedule next event."""
    # Update tournament status
    await bot.db.update_tournament(tournament.id, status="completed")

    # Record champion
    champion = Champion(
        guild_id=tournament.guild_id,
        game=tournament.game,
        discord_id=winner_id,
        tournament_id=tournament.id,
        won_at=datetime.now(),
    )
    await bot.db.insert_champion(champion)

    # Announce winner
    embed = discord.Embed(
        title=f"👑 Tournament Complete: {tournament.game}",
        description=f"<@{winner_id}> is the **{tournament.game} Champion**! 🎉",
        color=discord.Color.gold(),
    )
    await ctx.send(embed=embed)
    logger.info("Tournament #%d (%s) won by user %d", tournament.id, tournament.game, winner_id)

    # Auto-schedule next tournament
    next_date = tournament.scheduled_at + _frequency_delta(tournament.frequency)
    next_tournament = Tournament(
        guild_id=tournament.guild_id,
        channel_id=tournament.channel_id,
        game=tournament.game,
        creator_id=tournament.creator_id,
        scheduled_at=next_date,
        frequency=tournament.frequency,
        status="scheduled",
        created_at=datetime.now(),
    )
    next_id = await bot.db.insert_tournament(next_tournament)
    await ctx.send(
        f"🔄 Next **{tournament.game}** tournament auto-scheduled for "
        f"<t:{int(next_date.timestamp())}:F> (ID: {next_id}). "
        f"Sign up with `!join {tournament.game}`!"
    )
    logger.info("Auto-scheduled tournament #%d (%s) for %s", next_id, tournament.game, next_date.isoformat())

    # Clean up in-memory state
    _bracket_states.pop(tournament.id, None)


async def _handle_win(ctx_or_interaction, bot, tournament, match_found, winner_id, score):
    """Shared logic for processing a win via command or button."""
    state = _bracket_states.get(tournament.id)
    if not state:
        state = await _rebuild_bracket_state(bot, tournament.id)
    
    match_key = (match_found.round_num, match_found.match_number)
    opponent_id = (
        match_found.player2_id
        if match_found.player1_id == winner_id
        else match_found.player1_id
    )

    try:
        state, newly_opened = report_match_result(
            state, match_key, winner_id, score
        )
        _bracket_states[tournament.id] = state
    except ValueError as e:
        return f"❌ Error reporting result: {e}"

    # Persist to DB
    await _persist_matches(bot, tournament.id, state)

    # Confirm the result
    round_label = "Grand Finals" if match_found.is_grand_finals else (f"Winners Round {match_found.round_num}" if match_found.round_num > 0 else f"Losers Round {abs(match_found.round_num)}")
    
    msg = f"✅ **{round_label}** — <@{winner_id}> defeats <@{opponent_id}> **{score}**!"
    
    return msg, state, newly_opened


class ScoreModal(discord.ui.Modal, title="Report Score"):
    score_input = discord.ui.TextInput(
        label="Score (e.g., 2-1 or 2-0)",
        placeholder="W-L",
        max_length=5,
        required=True
    )

    def __init__(self, bot, tournament, match_found, winner_id):
        super().__init__()
        self.bot = bot
        self.tournament = tournament
        self.match_found = match_found
        self.winner_id = winner_id

    async def on_submit(self, interaction: discord.Interaction):
        score = self.score_input.value
        try:
            parts = score.split("-")
            if len(parts) != 2:
                raise ValueError
            winner_games = int(parts[0])
            loser_games = int(parts[1])
            if winner_games <= loser_games:
                await interaction.response.send_message("❌ Your wins must be higher.", ephemeral=True)
                return
            needed = (self.match_found.best_of // 2) + 1
            if winner_games != needed:
                await interaction.response.send_message(
                    f"❌ This is a Bo{self.match_found.best_of} match. You need {needed} wins.", ephemeral=True
                )
                return
        except ValueError:
            await interaction.response.send_message("❌ Invalid score format (use W-L).", ephemeral=True)
            return

        result = await _handle_win(interaction, self.bot, self.tournament, self.match_found, self.winner_id, score)
        if isinstance(result, str):
            await interaction.response.send_message(result, ephemeral=True)
            return

        msg, state, newly_opened = result
        await interaction.response.send_message(msg)
        
        ctx = await self.bot.get_context(interaction.message) if interaction.message else None
        
        # We need a context-like object for announce and conclude if context is missing
        class FakeCtx:
            def __init__(self, inter):
                self.channel = inter.channel
            async def send(self, *args, **kwargs):
                return await self.channel.send(*args, **kwargs)
                
        send_ctx = ctx or FakeCtx(interaction)

        if is_bracket_complete(state):
            winner = get_winner(state)
            if winner:
                await _conclude_tournament(send_ctx, self.bot, self.tournament, winner)
        else:
            await _announce_open_matches(send_ctx, self.tournament, newly_opened)


class MatchView(discord.ui.View):
    def __init__(self, bot, tournament, match_found):
        super().__init__(timeout=None)
        self.bot = bot
        self.tournament = tournament
        self.match_found = match_found

    @discord.ui.button(label="🏆 I Won", style=discord.ButtonStyle.success)
    async def report_win(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in [self.match_found.player1_id, self.match_found.player2_id]:
            await interaction.response.send_message("You are not in this match!", ephemeral=True)
            return
            
        modal = ScoreModal(self.bot, self.tournament, self.match_found, interaction.user.id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🏳️ Forfeit", style=discord.ButtonStyle.danger)
    async def report_forfeit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in [self.match_found.player1_id, self.match_found.player2_id]:
            await interaction.response.send_message("You are not in this match!", ephemeral=True)
            return
            
        opponent_id = self.match_found.player2_id if self.match_found.player1_id == interaction.user.id else self.match_found.player1_id
        result = await _handle_win(interaction, self.bot, self.tournament, self.match_found, opponent_id, "FF")
        if isinstance(result, str):
            await interaction.response.send_message(result, ephemeral=True)
            return
            
        msg, state, newly_opened = result
        await interaction.response.send_message(f"🏳️ <@{interaction.user.id}> forfeited. " + msg)
        
        class FakeCtx:
            def __init__(self, inter):
                self.channel = inter.channel
            async def send(self, *args, **kwargs):
                return await self.channel.send(*args, **kwargs)
                
        send_ctx = FakeCtx(interaction)

        if is_bracket_complete(state):
            winner = get_winner(state)
            if winner:
                await _conclude_tournament(send_ctx, self.bot, self.tournament, winner)
        else:
            await _announce_open_matches(send_ctx, self.tournament, newly_opened)


class LiveCog(commands.Cog, name="Live"):
    """Commands for running live tournaments."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="start")
    async def start_tournament(self, ctx: commands.Context, *, game: str) -> None:
        """
        Lock the roster and generate the bracket. Creator only.
        """
        tournament = await self.bot.db.get_tournament_by_game(ctx.guild.id, game, status="scheduled")
        if not tournament:
            await ctx.send(f"❌ No scheduled `{game}` tournament found.")
            return

        if tournament.creator_id != ctx.author.id:
            await ctx.send("❌ Only the tournament creator can start the event.")
            return

        entrants = await self.bot.db.get_entrants(tournament.id)
        if len(entrants) < MIN_ENTRANTS:
            await ctx.send(
                f"❌ Need at least {MIN_ENTRANTS} players to start. "
                f"Currently have {len(entrants)}."
            )
            return

        # Generate bracket
        entrant_ids = [e.discord_id for e in entrants]
        state = generate_bracket(tournament.id, entrant_ids, BEST_OF_STANDARD, BEST_OF_FINALS)
        _bracket_states[tournament.id] = state

        # Persist matches to DB
        for m in state.matches:
            m.id = await self.bot.db.insert_match(m)

        # Update tournament status
        await self.bot.db.update_tournament(tournament.id, status="live")

        # Build announcement
        roster_mentions = " ".join(f"<@{eid}>" for eid in entrant_ids)
        embed = discord.Embed(
            title=f"🚀 Tournament Started: {game}",
            description=f"The bracket is LIVE with {len(entrant_ids)} players!",
            color=discord.Color.red(),
        )
        embed.add_field(name="Roster", value=roster_mentions, inline=False)
        embed.add_field(name="Format", value="Double Elimination (Bo3 → Bo5 Finals)", inline=True)

        await ctx.send(embed=embed)

        # Send image
        img_file = generate_bracket_image(state)
        await ctx.send(file=img_file)

        # Announce initial open matches
        open_matches = get_open_matches(state)
        await _announce_open_matches(ctx, tournament, open_matches)

    @commands.command(name="bracket")
    async def show_bracket(self, ctx: commands.Context, *, game: str) -> None:
        """
        Display the current bracket image.
        """
        tournament = await self.bot.db.get_tournament_by_game(ctx.guild.id, game, status="live")
        if not tournament:
            await ctx.send(f"❌ No live `{game}` tournament found.")
            return

        state = _bracket_states.get(tournament.id)
        if not state:
            state = await _rebuild_bracket_state(self.bot, tournament.id)
        if not state:
            await ctx.send("❌ Could not load bracket data.")
            return

        img_file = generate_bracket_image(state)
        await ctx.send(f"📊 **Current Bracket for {game}**:", file=img_file)

    @commands.command(name="win")
    async def report_win(self, ctx: commands.Context, score: str) -> None:
        """
        Report a match victory with the set score (fallback command).
        """
        tournaments = await self.bot.db.get_upcoming_tournaments(ctx.guild.id)
        live_tournaments = [t for t in tournaments if t.status == "live"]

        match_found = None
        tournament_found = None

        for t in live_tournaments:
            state = _bracket_states.get(t.id)
            if not state:
                state = await _rebuild_bracket_state(self.bot, t.id)
            if not state:
                continue
            player_match = get_match_for_player(state, ctx.author.id)
            if player_match:
                match_found = player_match
                tournament_found = t
                break

        if not match_found or not tournament_found:
            await ctx.send("❌ You don't have an active match right now.")
            return

        try:
            parts = score.split("-")
            if len(parts) != 2:
                raise ValueError
            winner_games = int(parts[0])
            loser_games = int(parts[1])
            if winner_games <= loser_games:
                await ctx.send("❌ The first number (your wins) must be higher. Example: `!win 2-1`")
                return
            needed = (match_found.best_of // 2) + 1
            if winner_games != needed:
                await ctx.send(
                    f"❌ This is a **Bo{match_found.best_of}** match. "
                    f"Winner must have exactly {needed} wins."
                )
                return
        except ValueError:
            await ctx.send("❌ Invalid score format. Use `!win W-L` (e.g. `!win 2-1`)")
            return

        result = await _handle_win(ctx, self.bot, tournament_found, match_found, ctx.author.id, score)
        if isinstance(result, str):
            await ctx.send(result)
            return
            
        msg, state, newly_opened = result
        await ctx.send(msg)
        
        if is_bracket_complete(state):
            winner = get_winner(state)
            if winner:
                await _conclude_tournament(ctx, self.bot, tournament_found, winner)
        else:
            await _announce_open_matches(ctx, tournament_found, newly_opened)

    @commands.command(name="dq")
    async def disqualify_player(self, ctx: commands.Context, player: discord.Member) -> None:
        """
        Disqualify a player from the active tournament.
        """
        tournaments = await self.bot.db.get_upcoming_tournaments(ctx.guild.id)
        live = [t for t in tournaments if t.status == "live"]

        dq_done = False
        for t in live:
            if t.creator_id != ctx.author.id:
                continue

            entrant = await self.bot.db.get_entrant(t.id, player.id)
            if not entrant or entrant.dropped:
                continue

            await self.bot.db.update_entrant(entrant.id, dropped=True)

            state = _bracket_states.get(t.id)
            if not state:
                state = await _rebuild_bracket_state(self.bot, t.id)

            if state:
                player_match = get_match_for_player(state, player.id)
                if player_match:
                    opponent_id = (
                        player_match.player2_id
                        if player_match.player1_id == player.id
                        else player_match.player1_id
                    )
                    if opponent_id:
                        match_key = (player_match.round_num, player_match.match_number)
                        state, newly_opened = report_match_result(
                            state, match_key, opponent_id, "DQ"
                        )
                        _bracket_states[t.id] = state
                        await _persist_matches(self.bot, t.id, state)

                        await ctx.send(
                            f"⛔ <@{player.id}> has been **disqualified** from the **{t.game}** tournament. "
                            f"<@{opponent_id}> advances."
                        )

                        if is_bracket_complete(state):
                            winner = get_winner(state)
                            if winner:
                                await _conclude_tournament(ctx, self.bot, t, winner)
                        else:
                            await _announce_open_matches(ctx, t, newly_opened)
                    else:
                        await ctx.send(f"⛔ <@{player.id}> has been **disqualified** from **{t.game}**.")
                else:
                    await ctx.send(f"⛔ <@{player.id}> has been **disqualified** from **{t.game}**. (No active match)")

            dq_done = True
            logger.info("DQ: %s from tournament #%d (%s)", player, t.id, t.game)
            break

        if not dq_done:
            await ctx.send("❌ Could not DQ that player.")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LiveCog(bot))
'''
with open('cogs/live.py', 'w', encoding='utf-8') as f:
    f.write(code)
