"""
Live Execution Cog — !start, !bracket, !win, !sync, !dq

Handles the full tournament lifecycle: bracket generation, match reporting,
result syncing with Start.gg, and disqualification.
"""

import logging
import json
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
    _get_match,
)

logger = logging.getLogger(__name__)

# In-memory bracket states keyed by tournament_id.
# Persisted to DB (matches table) and rebuilt on !sync or restart.
_bracket_states: dict[int, BracketState] = {}


def _frequency_delta(frequency: str) -> relativedelta:
    """Convert a frequency string to a relativedelta."""
    return {
        "monthly": relativedelta(months=1),
        "quarterly": relativedelta(months=3),
        "bi-annually": relativedelta(months=6),
        "annually": relativedelta(years=1),
    }.get(frequency, relativedelta(months=1))


def _format_bracket_text(state: BracketState) -> str:
    """Render the bracket as a compact text summary."""
    lines = []
    # Group matches by round
    rounds: dict[int, list[Match]] = {}
    for m in state.matches:
        rounds.setdefault(m.round_num, []).append(m)

    # Winners bracket
    for r in sorted(k for k in rounds if k > 0):
        label = f"Winners Round {r}"
        lines.append(f"**{label}**")
        for m in sorted(rounds[r], key=lambda x: x.match_number):
            p1 = f"<@{m.player1_id}>" if m.player1_id else "BYE"
            p2 = f"<@{m.player2_id}>" if m.player2_id else "BYE"
            status = ""
            if m.status == "complete":
                winner_tag = f"<@{m.winner_id}>" if m.winner_id else "?"
                status = f" → 🏆 {winner_tag} ({m.score or 'FF'})"
            elif m.status == "open":
                status = " ⚔️ _LIVE_"
            elif m.status == "bye":
                adv = f"<@{m.winner_id}>" if m.winner_id else "?"
                status = f" → {adv} (BYE)"
            lines.append(f"  {p1} vs {p2}{status}")
        lines.append("")

    # Losers bracket
    for r in sorted((k for k in rounds if k < 0), reverse=True):
        label = f"Losers Round {abs(r)}"
        lines.append(f"**{label}**")
        for m in sorted(rounds[r], key=lambda x: x.match_number):
            p1 = f"<@{m.player1_id}>" if m.player1_id else "TBD"
            p2 = f"<@{m.player2_id}>" if m.player2_id else "TBD"
            status = ""
            if m.status == "complete":
                winner_tag = f"<@{m.winner_id}>" if m.winner_id else "?"
                status = f" → 🏆 {winner_tag} ({m.score or 'FF'})"
            elif m.status == "open":
                status = " ⚔️ _LIVE_"
            lines.append(f"  {p1} vs {p2}{status}")
        lines.append("")

    # Grand Finals
    if 0 in rounds:
        lines.append("**🏆 Grand Finals**")
        for m in rounds[0]:
            p1 = f"<@{m.player1_id}>" if m.player1_id else "TBD"
            p2 = f"<@{m.player2_id}>" if m.player2_id else "TBD"
            status = ""
            if m.status == "complete":
                winner_tag = f"<@{m.winner_id}>" if m.winner_id else "?"
                status = f" → 👑 {winner_tag} ({m.score or 'W'})"
            elif m.status == "open":
                status = " ⚔️ _LIVE_"
            lines.append(f"  {p1} vs {p2}{status}")

    return "\n".join(lines) if lines else "_No bracket data_"


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
                engine_match.startgg_set_id = db_match.startgg_set_id
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
        await ctx.send(
            f"⚔️ <@{m.player1_id}> vs <@{m.player2_id}>!{gf_label}\n"
            f"_{best_of_label} — Report your win with `!win <score>` (e.g. `!win 2-1`)_"
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


class LiveCog(commands.Cog, name="Live"):
    """Commands for running live tournaments."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="start")
    async def start_tournament(self, ctx: commands.Context, *, game: str) -> None:
        """
        Lock the roster and generate the bracket. Creator only.

        Usage: !start {game}
        Example: !start Smash
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

        if tournament.startgg_slug:
            embed.add_field(
                name="Start.gg Bracket",
                value=f"[View on Start.gg](https://start.gg/{tournament.startgg_slug})",
                inline=True,
            )

        await ctx.send(embed=embed)

        # Announce initial open matches
        open_matches = get_open_matches(state)
        await _announce_open_matches(ctx, tournament, open_matches)

    @commands.command(name="bracket")
    async def show_bracket(self, ctx: commands.Context, *, game: str) -> None:
        """
        Display the current bracket.

        Usage: !bracket {game}
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

        bracket_text = _format_bracket_text(state)

        embed = discord.Embed(
            title=f"📊 Bracket: {game}",
            description=bracket_text[:4000],  # Discord embed limit
            color=discord.Color.purple(),
        )
        if tournament.startgg_slug:
            embed.add_field(
                name="🔗 Start.gg",
                value=f"[Full Bracket](https://start.gg/{tournament.startgg_slug})",
            )
        await ctx.send(embed=embed)

    @commands.command(name="win")
    async def report_win(self, ctx: commands.Context, score: str) -> None:
        """
        Report a match victory with the set score.

        Usage: !win {score}
        Example: !win 2-1
        """
        # Find the user's live tournament and open match
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

        # Validate score format
        try:
            parts = score.split("-")
            if len(parts) != 2:
                raise ValueError
            winner_games = int(parts[0])
            loser_games = int(parts[1])
            if winner_games <= loser_games:
                await ctx.send("❌ The first number (your wins) must be higher. Example: `!win 2-1`")
                return
            total_games = winner_games + loser_games
            needed = (match_found.best_of // 2) + 1
            if winner_games != needed:
                await ctx.send(
                    f"❌ This is a **Bo{match_found.best_of}** match. "
                    f"Winner must have exactly {needed} wins. Example: `!win {needed}-{needed-1}`"
                )
                return
        except ValueError:
            await ctx.send("❌ Invalid score format. Use `!win W-L` (e.g. `!win 2-1`)")
            return

        # Report the result
        state = _bracket_states[tournament_found.id]
        match_key = (match_found.round_num, match_found.match_number)
        opponent_id = (
            match_found.player2_id
            if match_found.player1_id == ctx.author.id
            else match_found.player1_id
        )

        try:
            state, newly_opened = report_match_result(
                state, match_key, ctx.author.id, score
            )
            _bracket_states[tournament_found.id] = state
        except ValueError as e:
            await ctx.send(f"❌ Error reporting result: {e}")
            return

        # Persist to DB
        await _persist_matches(self.bot, tournament_found.id, state)

        # Confirm the result
        round_label = ""
        if match_found.is_grand_finals:
            round_label = "Grand Finals"
        elif match_found.round_num > 0:
            round_label = f"Winners Round {match_found.round_num}"
        else:
            round_label = f"Losers Round {abs(match_found.round_num)}"

        await ctx.send(
            f"✅ **{round_label}** — <@{ctx.author.id}> defeats <@{opponent_id}> **{score}**!"
        )

        # Sync with Start.gg if linked
        if match_found.startgg_set_id and tournament_found.startgg_event_id:
            try:
                entrant = await self.bot.db.get_entrant(tournament_found.id, ctx.author.id)
                if entrant and entrant.startgg_entrant_id:
                    await self.bot.startgg.report_set(
                        match_found.startgg_set_id, entrant.startgg_entrant_id
                    )
                    logger.info("Synced set %d to Start.gg", match_found.startgg_set_id)
            except Exception as e:
                logger.warning("Failed to sync set to Start.gg: %s", e)

        # Check if tournament is complete
        if is_bracket_complete(state):
            winner = get_winner(state)
            if winner:
                await _conclude_tournament(ctx, self.bot, tournament_found, winner)
        else:
            # Announce newly opened matches
            await _announce_open_matches(ctx, tournament_found, newly_opened)

    @commands.command(name="sync")
    @commands.has_permissions(administrator=True)
    async def sync_bracket(self, ctx: commands.Context, *, game: str = "") -> None:
        """
        Sync the local bracket with Start.gg (admin only).

        Usage: !sync [game]
        If no game specified, syncs all live tournaments.
        """
        tournaments = await self.bot.db.get_upcoming_tournaments(ctx.guild.id)
        live = [t for t in tournaments if t.status == "live"]

        if game:
            live = [t for t in live if t.game.lower() == game.lower()]

        if not live:
            await ctx.send("❌ No live tournaments to sync.")
            return

        synced = 0
        for t in live:
            if not t.startgg_event_id:
                continue
            try:
                # Fetch sets from Start.gg
                sets_data = await self.bot.startgg.get_sets(t.startgg_event_id)
                nodes = sets_data.get("nodes", [])

                for sgg_set in nodes:
                    set_id = sgg_set.get("id")
                    state_val = sgg_set.get("state")
                    winner_id = sgg_set.get("winnerId")

                    # Find corresponding local match by startgg_set_id
                    matches = await self.bot.db.get_matches(t.id)
                    for m in matches:
                        if m.startgg_set_id == set_id:
                            if state_val == 3 and winner_id and m.status != "complete":
                                # Mark as complete locally
                                await self.bot.db.update_match(
                                    m.id, status="complete", winner_id=winner_id
                                )
                                synced += 1
                            break

                # Rebuild in-memory state
                await _rebuild_bracket_state(self.bot, t.id)
            except Exception as e:
                logger.error("Sync failed for tournament #%d: %s", t.id, e)
                await ctx.send(f"⚠️ Sync error for **{t.game}**: {e}")

        await ctx.send(f"🔄 Sync complete. Updated {synced} match(es).")

    @commands.command(name="dq")
    async def disqualify_player(self, ctx: commands.Context, player: discord.Member) -> None:
        """
        Disqualify a player from the active tournament (creator only).

        Usage: !dq @Player
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

            # Mark as dropped
            await self.bot.db.update_entrant(entrant.id, dropped=True)

            # Auto-forfeit any open match
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

                        # Check if complete
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
            await ctx.send("❌ Could not DQ that player. Are you the tournament creator and is there a live event?")


async def setup(bot: commands.Bot) -> None:
    """Load the Live Execution cog."""
    await bot.add_cog(LiveCog(bot))
