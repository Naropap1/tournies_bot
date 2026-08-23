"""
Prestige Cog — !leaderboard

Display the reigning champion for every game played on the server.
"""

import logging

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


class PrestigeCog(commands.Cog, name="Prestige"):
    """Commands for viewing tournament prestige and champions."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="leaderboard")
    async def leaderboard(self, ctx: commands.Context) -> None:
        """
        View the reigning champion for every game.

        Usage: !leaderboard
        """
        champions = await self.bot.db.get_champions(ctx.guild.id)
        if not champions:
            await ctx.send("🏆 No champions yet! Schedule a tournament with `!create` to get started.")
            return

        # Group by game, keep only the most recent champion per game
        latest: dict[str, any] = {}
        for c in sorted(champions, key=lambda x: x.won_at, reverse=True):
            if c.game not in latest:
                latest[c.game] = c

        embed = discord.Embed(
            title="🏆 Champion Leaderboard",
            description="The reigning champions of this server:",
            color=discord.Color.gold(),
        )

        for game in sorted(latest.keys()):
            champ = latest[game]
            embed.add_field(
                name=f"🎮 {game}",
                value=(
                    f"👑 <@{champ.discord_id}>\n"
                    f"_Won <t:{int(champ.won_at.timestamp())}:R>_"
                ),
                inline=True,
            )

        embed.set_footer(text="Champions are crowned after each tournament concludes.")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Load the Prestige cog."""
    await bot.add_cog(PrestigeCog(bot))
