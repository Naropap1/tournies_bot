"""
Participation Cog — !link, !join, !leave, !drop

Handles player account linking, tournament signup, and mid-tournament forfeits.
"""

import logging
from datetime import datetime

import discord
from discord.ext import commands

from db.models import Entrant

logger = logging.getLogger(__name__)


class ParticipationCog(commands.Cog, name="Participation"):
    """Commands for managing tournament signups and account linking."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="link")
    async def link_account(self, ctx: commands.Context, startgg_tag: str) -> None:
        """
        Link your Discord account to your Start.gg profile.

        Usage: !link {start.gg_tag}
        Example: !link MkLeo
        """
        # Attempt to validate the tag via Start.gg API
        try:
            user_data = await self.bot.startgg.resolve_user(startgg_tag)
            if user_data:
                display_name = user_data.get("name") or user_data.get("player", {}).get("gamerTag", startgg_tag)
                await self.bot.db.link_account(ctx.author.id, startgg_tag, ctx.guild.id)
                embed = discord.Embed(
                    title="🔗 Account Linked!",
                    description=f"Your Discord is now linked to Start.gg profile: **{display_name}** (`{startgg_tag}`)",
                    color=discord.Color.green(),
                )
                await ctx.send(embed=embed)
                logger.info("Linked %s -> Start.gg:%s", ctx.author, startgg_tag)
            else:
                # Tag not found on Start.gg, but still save it locally
                await self.bot.db.link_account(ctx.author.id, startgg_tag, ctx.guild.id)
                await ctx.send(
                    f"⚠️ Could not verify `{startgg_tag}` on Start.gg, but saved it locally. "
                    f"Double-check the tag spelling."
                )
        except Exception as e:
            # API might be down or token missing — save locally anyway
            await self.bot.db.link_account(ctx.author.id, startgg_tag, ctx.guild.id)
            await ctx.send(
                f"⚠️ Start.gg verification failed ({type(e).__name__}), but your tag `{startgg_tag}` has been saved locally."
            )
            logger.warning("Start.gg resolve_user failed for %s: %s", startgg_tag, e)

    @commands.command(name="join")
    async def join_tournament(self, ctx: commands.Context, *, game: str) -> None:
        """
        Sign up for the next upcoming tournament of a game.

        Usage: !join {game}
        Example: !join Smash
        """
        tournament = await self.bot.db.get_tournament_by_game(ctx.guild.id, game, status="scheduled")
        if not tournament:
            await ctx.send(f"❌ No scheduled `{game}` tournament found. Use `!upcoming` to see available events.")
            return

        # Check if already signed up
        existing = await self.bot.db.get_entrant(tournament.id, ctx.author.id)
        if existing:
            if existing.dropped:
                # Re-join after dropping (only if not live)
                await self.bot.db.update_entrant(existing.id, dropped=False)
                await ctx.send(f"✅ Welcome back! You've re-joined the **{game}** tournament.")
                return
            await ctx.send(f"ℹ️ You're already signed up for the **{game}** tournament!")
            return

        # Check for linked account
        linked = await self.bot.db.get_linked_account(ctx.author.id, ctx.guild.id)
        is_phantom = linked is None
        startgg_tag = linked.startgg_tag if linked else None

        entrant = Entrant(
            tournament_id=tournament.id,
            discord_id=ctx.author.id,
            is_phantom=is_phantom,
            joined_at=datetime.now(),
            startgg_tag=startgg_tag,
        )
        await self.bot.db.insert_entrant(entrant)

        # Get updated roster count
        entrants = await self.bot.db.get_entrants(tournament.id)
        roster_count = len(entrants)

        phantom_note = ""
        if is_phantom:
            phantom_note = "\n_💡 Tip: Use `!link {tag}` to connect your Start.gg profile._"

        embed = discord.Embed(
            title=f"✅ Joined: {game}",
            description=(
                f"{ctx.author.mention} has signed up for the **{game}** tournament!\n"
                f"**Roster:** {roster_count} player(s){phantom_note}"
            ),
            color=discord.Color.green(),
        )
        embed.add_field(
            name="📅 Event Date",
            value=f"<t:{int(tournament.scheduled_at.timestamp())}:F>",
            inline=True,
        )
        await ctx.send(embed=embed)
        logger.info(
            "%s joined tournament #%d (%s) [phantom=%s]",
            ctx.author, tournament.id, game, is_phantom,
        )

    @commands.command(name="leave")
    async def leave_tournament(self, ctx: commands.Context, *, game: str) -> None:
        """
        Remove yourself from a scheduled tournament.

        Usage: !leave {game}
        Example: !leave Smash
        """
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
        await ctx.send(
            f"👋 {ctx.author.mention} has left the **{game}** tournament. "
            f"**Roster:** {len(entrants)} player(s)"
        )
        logger.info("%s left tournament #%d (%s)", ctx.author, tournament.id, game)

    @commands.command(name="drop")
    async def drop_from_tournament(self, ctx: commands.Context) -> None:
        """
        Forfeit remaining matches in a live tournament.

        Usage: !drop
        """
        from cogs.live import (
            _bracket_states,
            _rebuild_bracket_state,
            _persist_matches,
            _announce_open_matches,
            _conclude_tournament,
        )
        from bracket.engine import (
            get_match_for_player,
            report_match_result,
            is_bracket_complete,
            get_winner,
        )

        # Find any live tournament this player is in
        tournaments = await self.bot.db.get_upcoming_tournaments(ctx.guild.id)
        live_tournaments = [t for t in tournaments if t.status == "live"]

        dropped_from = None
        for t in live_tournaments:
            entrant = await self.bot.db.get_entrant(t.id, ctx.author.id)
            if entrant and not entrant.dropped:
                await self.bot.db.update_entrant(entrant.id, dropped=True)

                # Advance the bracket via the engine
                state = _bracket_states.get(t.id)
                if not state:
                    state = await _rebuild_bracket_state(self.bot, t.id)

                if state:
                    player_match = get_match_for_player(state, ctx.author.id)
                    if player_match:
                        opponent_id = (
                            player_match.player2_id
                            if player_match.player1_id == ctx.author.id
                            else player_match.player1_id
                        )
                        if opponent_id:
                            match_key = (player_match.round_num, player_match.match_number)
                            state, newly_opened = report_match_result(
                                state, match_key, opponent_id, "FF"
                            )
                            _bracket_states[t.id] = state
                            await _persist_matches(self.bot, t.id, state)

                            await ctx.send(
                                f"🏳️ {ctx.author.mention} has forfeited from the **{t.game}** tournament. "
                                f"<@{opponent_id}> advances."
                            )

                            # Check if tournament is complete
                            if is_bracket_complete(state):
                                winner = get_winner(state)
                                if winner:
                                    await _conclude_tournament(ctx, self.bot, t, winner)
                            else:
                                await _announce_open_matches(ctx, t, newly_opened)
                        else:
                            await ctx.send(
                                f"🏳️ {ctx.author.mention} has forfeited from the **{t.game}** tournament."
                            )
                    else:
                        await ctx.send(
                            f"🏳️ {ctx.author.mention} has forfeited from the **{t.game}** tournament. "
                            f"(No active match to forfeit)"
                        )
                else:
                    await ctx.send(
                        f"🏳️ {ctx.author.mention} has forfeited from the **{t.game}** tournament."
                    )

                dropped_from = t
                logger.info("%s dropped from tournament #%d (%s)", ctx.author, t.id, t.game)
                break

        if not dropped_from:
            await ctx.send("❌ You're not currently in any live tournament.")


async def setup(bot: commands.Bot) -> None:
    """Load the Participation cog."""
    await bot.add_cog(ParticipationCog(bot))
