"""
Custom Help Cog — Provides detailed step-by-step instructions for bot usage.
"""

import discord
from discord.ext import commands


class HelpCog(commands.Cog, name="Help"):
    """Custom help command with detailed guides."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Remove the default help command if it exists
        self.bot.help_command = None

    @commands.group(name="help", invoke_without_command=True)
    async def custom_help(self, ctx: commands.Context, command_name: str = None) -> None:
        """
        Main help menu.

        Usage: !help [category]
        """
        # If they type `!help create` (an existing command), we can fall back to its docstring.
        if command_name:
            cmd = self.bot.get_command(command_name)
            if cmd and cmd.name != "help":
                embed = discord.Embed(title=f"Command: !{cmd.name}", description=cmd.help or "No description.", color=discord.Color.blue())
                await ctx.send(embed=embed)
                return
            else:
                await ctx.send(f"❌ Unknown category or command `{command_name}`. Use `!help` to see available guides.")
                return

        embed = discord.Embed(
            title="🏆 Tournies Bot Help Center",
            description="Welcome to Tournies Bot! Choose a guide below to learn how to set up and run tournaments.",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="🛠️ `!help setup`",
            value="How to set up the Discord channels and schedule your first tournament.",
            inline=False,
        )
        embed.add_field(
            name="🎮 `!help play`",
            value="For players: How to link your account, join, report scores, and drop.",
            inline=False,
        )
        embed.add_field(
            name="🔴 `!help live`",
            value="For admins: How to start the tournament, manage the bracket, and DQ players.",
            inline=False,
        )
        embed.add_field(
            name="🔗 `!help startgg`",
            value="Detailed guide on how to manually create a Start.gg bracket and link it to the bot.",
            inline=False,
        )
        embed.set_footer(text="Type !help <category> (e.g. !help startgg) to read a guide.")
        await ctx.send(embed=embed)

    @custom_help.command(name="setup")
    async def help_setup(self, ctx: commands.Context) -> None:
        """Guide on server setup and scheduling."""
        embed = discord.Embed(
            title="🛠️ Guide: Server Setup & Scheduling",
            color=discord.Color.green(),
        )
        embed.add_field(
            name="1. Discord Channel Setup",
            value=(
                "Create a dedicated channel named `#tournaments` in your server. "
                "Ensure the bot has permissions to **View Channel**, **Send Messages**, and **Embed Links** in this channel. "
                "Players should use all bot commands inside this channel to keep things organized."
            ),
            inline=False,
        )
        embed.add_field(
            name="2. Scheduling a Tournament",
            value=(
                "Use the `!create` command to schedule an event. The bot understands flexible dates and times.\n"
                "**Usage:** `!create {game} {date} {time} [frequency]`\n"
                "**Example:** `!create Smash 2026-10-31 7PM monthly`\n"
                "Frequencies: `monthly`, `quarterly`, `bi-annually`, `annually`. The bot will automatically schedule the next iteration when this one finishes."
            ),
            inline=False,
        )
        embed.add_field(
            name="3. Rescheduling & Viewing",
            value=(
                "Made a mistake? The creator can use `!move {game} {date} {time}` to change the date.\n"
                "Use `!upcoming` anytime to see all scheduled events and who has signed up so far."
            ),
            inline=False,
        )
        await ctx.send(embed=embed)

    @custom_help.command(name="play")
    async def help_play(self, ctx: commands.Context) -> None:
        """Guide for players signing up and reporting scores."""
        embed = discord.Embed(
            title="🎮 Guide: For Players",
            color=discord.Color.purple(),
        )
        embed.add_field(
            name="1. Linking Start.gg (Optional)",
            value=(
                "If the tournament uses a Start.gg bracket, you should link your account so you appear correctly.\n"
                "**Usage:** `!link {your_startgg_tag}` (e.g., `!link MkLeo`)\n"
                "If you don't link, you will participate as a local 'phantom' entrant."
            ),
            inline=False,
        )
        embed.add_field(
            name="2. Joining an Event",
            value=(
                "Once an admin schedules an event, use `!join {game}` (e.g., `!join Smash`) to enter the roster. "
                "If you need to back out before it starts, use `!leave {game}`."
            ),
            inline=False,
        )
        embed.add_field(
            name="3. Playing & Reporting Scores",
            value=(
                "When the tournament starts, the bot will ping you when your match is ready.\n"
                "After playing, the **winner** must report the score.\n"
                "**Usage:** `!win {your_wins}-{opponent_wins}` (e.g., `!win 2-1` or `!win 2-0`).\n"
                "The bot automatically knows who your opponent is. Matches are Best-of-3, Finals are Best-of-5."
            ),
            inline=False,
        )
        embed.add_field(
            name="4. Dropping Out",
            value="If you must leave mid-tournament, type `!drop`. The bot will forfeit your active match and automatically forfeit any future losers bracket matches.",
            inline=False,
        )
        await ctx.send(embed=embed)

    @custom_help.command(name="live")
    async def help_live(self, ctx: commands.Context) -> None:
        """Guide for running the live event."""
        embed = discord.Embed(
            title="🔴 Guide: Running a Live Tournament",
            color=discord.Color.red(),
        )
        embed.add_field(
            name="1. Starting the Bracket",
            value=(
                "When everyone is ready, the tournament creator runs `!start {game}`.\n"
                "This locks the roster, generates the double-elimination bracket, and pings players for the first round of open matches. "
                "You need at least 2 players to start."
            ),
            inline=False,
        )
        embed.add_field(
            name="2. Checking Bracket State",
            value=(
                "Anyone can use `!bracket {game}` to view a text summary of the current bracket state, "
                "including completed matches, open matches, and upcoming rounds."
            ),
            inline=False,
        )
        embed.add_field(
            name="3. Admin Controls",
            value=(
                "- **Disqualifications:** If a player is unresponsive, the creator can run `!dq @Player` to instantly forfeit their current match and drop them from the event.\n"
                "- **Start.gg Sync:** If a result was reported wrong, fix it on the Start.gg website, then run `!sync` (admin only) to pull the corrected bracket state back into the bot."
            ),
            inline=False,
        )
        embed.add_field(
            name="4. Conclusion",
            value="When Grand Finals finishes, the bot automatically crowns the champion on the `!leaderboard` and schedules the next event based on the recurring frequency.",
            inline=False,
        )
        await ctx.send(embed=embed)

    @custom_help.command(name="startgg")
    async def help_startgg(self, ctx: commands.Context) -> None:
        """Detailed guide on Start.gg integration."""
        embed = discord.Embed(
            title="🔗 Guide: Start.gg Integration",
            description=(
                "Because Start.gg does not allow bots to create tournaments automatically, "
                "you must create the bracket manually on their website and link it to the bot if you want Start.gg integration."
            ),
            color=discord.Color.orange(),
        )
        embed.add_field(
            name="Step 1: Create on Start.gg",
            value=(
                "1. Go to Start.gg and create a new Tournament.\n"
                "2. Make it **Unlisted** (in the Publishing settings) so it stays private to your Discord.\n"
                "3. Create an Event (e.g., 'Singles') and a Phase (e.g., 'Double Elimination Bracket')."
            ),
            inline=False,
        )
        embed.add_field(
            name="Step 2: Get the Event ID",
            value=(
                "You need the **Event ID** (a number like `123456`).\n"
                "Find this by going to your Tournament Settings -> Events -> click your event. The ID is in the URL or the settings page."
            ),
            inline=False,
        )
        embed.add_field(
            name="Step 3: Link to the Bot",
            value=(
                "In your Discord server, run:\n"
                "`!linkbracket {game} {event_id} {bracket_url_slug}`\n\n"
                "**Example:**\n"
                "`!linkbracket Smash 987654 my-tourney-name/events/singles`\n\n"
                "Once linked, when players run `!win`, the bot will automatically report the set results to Start.gg behind the scenes!"
            ),
            inline=False,
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Load the Custom Help cog."""
    await bot.add_cog(HelpCog(bot))
