import discord
from discord.ext import commands

class HelpCog(commands.Cog, name="Help"):
    """Custom help command with detailed guides."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.bot.help_command = None

    @commands.group(name="help", invoke_without_command=True)
    async def custom_help(self, ctx: commands.Context, command_name: str = None) -> None:
        """Main help menu."""
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
        embed.add_field(name="📅 `!help schedule`", value="How to schedule and manage your tournaments (!create, !move, !upcoming, !co_owner).", inline=False)
        embed.add_field(name="🎮 `!help play`", value="For players: How to join, report scores, and view rules.", inline=False)
        embed.add_field(name="🔴 `!help manage`", value="For admins: How to start, revert mistakes, and DQ players.", inline=False)
        embed.add_field(name="⚙️ `!help misc`", value="Other utilities like leaderboards and testing.", inline=False)
        embed.set_footer(text="Type !help <category> (e.g. !help manage) to read a guide.")
        await ctx.send(embed=embed)

    @custom_help.command(name="schedule")
    async def help_schedule(self, ctx: commands.Context) -> None:
        embed = discord.Embed(title="📅 Guide: Scheduling Tournaments", color=discord.Color.green())
        embed.add_field(
            name="1. Scheduling (`!create`)",
            value="`!create {game} {date} {time} [frequency] [rules...]`\nExample: `!create Smash 2026-10-31 7PM monthly Best of 3 only.`\n*Note: All times are parsed as EST!*\n\n**Supported Frequencies:** `one-time`, `monthly`, `quarterly`, `bi-annually`, `annually`.\n*Background Info:* When a tournament concludes, the bot automatically reads the frequency. If it is NOT `one-time`, it instantly clones the tournament (carrying over the owners and rules) and sets the new date based on the time interval. It will then automatically alert players to start signing up again!",
            inline=False,
        )
        embed.add_field(name="2. Rescheduling (`!move`)", value="`!move {game} {date} {time}`", inline=False)
        embed.add_field(name="3. Co-Owners (`!co_owner`)", value="`!co_owner {game} @User` to allow others to start/manage the event.", inline=False)
        embed.add_field(name="4. Viewing (`!upcoming`)", value="See all scheduled events and rosters.", inline=False)
        await ctx.send(embed=embed)

    @custom_help.command(name="play")
    async def help_play(self, ctx: commands.Context) -> None:
        embed = discord.Embed(title="🎮 Guide: For Players", color=discord.Color.purple())
        embed.add_field(name="1. Joining & Leaving", value="`!join {game}` to enter. `!leave {game}` to back out before it starts.", inline=False)
        embed.add_field(name="2. Rules", value="`!rules {game}` to view the custom rules set by the organizer.", inline=False)
        embed.add_field(
            name="3. Playing & Reporting",
            value="When the tournament starts, open matches are posted to the Matchboard.\nReport wins: `!win {game} {score}` (e.g. `!win Smash 2-1`).",
            inline=False,
        )
        embed.add_field(name="4. Dropping Out", value="`!drop` to forfeit mid-tournament.", inline=False)
        await ctx.send(embed=embed)

    @custom_help.command(name="manage")
    async def help_manage(self, ctx: commands.Context) -> None:
        embed = discord.Embed(title="🔴 Guide: Managing a Live Tournament", color=discord.Color.red())
        embed.add_field(name="1. Starting (`!start`)", value="`!start {game}` generates the double-elimination bracket image and posts the first Matchboard.", inline=False)
        embed.add_field(name="2. Brackets (`!bracket`)", value="`!bracket {game}` posts the latest visual tree image of the bracket.", inline=False)
        embed.add_field(
            name="3. Admin Controls",
            value="- `!dq {game} @Player`: Disqualifies an unresponsive player.\n- `!revert {game} {state_id}`: Undo a misreported score by reverting the bracket to a previous state. The State ID is printed with every bracket image.",
            inline=False,
        )
        await ctx.send(embed=embed)

    @custom_help.command(name="misc")
    async def help_misc(self, ctx: commands.Context) -> None:
        embed = discord.Embed(title="⚙️ Guide: Miscellaneous", color=discord.Color.light_grey())
        embed.add_field(name="1. Prestige (`!leaderboard`)", value="View the reigning champions for every game.", inline=False)
        embed.add_field(
            name="2. Testing (`!test_tourney`)",
            value="`!test_tourney [game]`\nInstantly generates a dummy tournament with 5 simulated players and starts it. Used by admins to rapidly test bracket flow.\n*Example:* `!test_tourney Smash`",
            inline=False,
        )
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpCog(bot))
