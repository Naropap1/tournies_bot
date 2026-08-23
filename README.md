# Tournies Bot

A fully functional, native Discord tournament bot tailored for community hubs. This bot handles scheduling, bracket generation (double-elimination), match progression, and prestige tracking entirely within Discord—no external websites needed!

## Features

- **Discord Native Image Brackets**: Automatically generates and posts a visual image of the bracket directly in chat.
- **Spaces natively supported**: Game and tournament names support spaces out-of-the-box, no messy quotes needed (e.g. !win Test Game).
- **Streamlined Match Reporting**: Simple !win commands to instantly advance through the bracket without unnecessary score tracking.
- **Double-Elimination Bracket Engine**: Fully custom local bracket logic with BYE handling, cascading auto-advances, and Grand Finals reset integration.
- **Recurring Schedules**: Auto-schedules the next event in a series when a tournament concludes.
- **Robust Persistence**: Backed by a SQLite database (iosqlite) with WAL mode. Survives restarts and crashes by persisting bracket state and rebuilding in-memory maps upon reboot.
- **Background Alerts**: Notifies tournament creators 1 week prior and pings channels 24 hours prior. Auto-deletes events that fail to reach the minimum entrant threshold.

## Requirements

- Python 3.12+
- Packages: discord.py, pillow, iohttp, python-dotenv, iosqlite, python-dateutil

## Installation & Setup

1. **Clone the repository.**
2. **Install dependencies**:
   `powershell
   pip install -r requirements.txt
   `
3. **Configure Environment Variables**:
   Open .env and fill in your DISCORD_TOKEN. Here is how to get them:

   **How to get your DISCORD_TOKEN**:
   - Go to the [Discord Developer Portal](https://discord.com/developers/applications).
   - Click **New Application** and give your bot a name.
   - Navigate to the **Bot** tab on the left sidebar.
   - Under the "Build-A-Bot" section, click **Reset Token** (and copy the resulting token).
   - Paste this token into your .env file as DISCORD_TOKEN.

4. **Invite the Bot to Discord**:
   - Still in the [Discord Developer Portal](https://discord.com/developers/applications) for your bot application, navigate to the **Bot** tab on the left sidebar.
   - Make sure the **Public Bot** toggle is checked (turned ON) to avoid default authorization link errors.
   - Scroll down to the **Privileged Gateway Intents** section and toggle ON the **Message Content Intent** and **Server Members Intent**, then save your changes. (The bot needs these to read commands like !join and see user profiles).
   - Now navigate to the **OAuth2 > URL Generator** tab on the left sidebar.
   - Under **Scopes**, check the box for ot.
   - A new **Bot Permissions** grid will appear below. Check the boxes for: 
     - Read Messages/View Channels
     - Send Messages
     - Embed Links
     - Attach Files *(CRITICAL: Required to post the bracket images!)*
     - Read Message History
   - Scroll down to the very bottom, copy the **Generated URL**, and paste it into a new browser tab to invite the bot to your server!

5. **Run the Bot**:
   `powershell
   python bot.py
   `
   The bot will automatically initialize the database 	ournies.db on first run.

## Commands

### Scheduling (!create, !move, !upcoming, !co_owner)
- !create {game} {date} {time} [frequency] [rules...]: Schedule a new tournament (Times are EST).
  - *Example:* !create Smash Bros 2026-10-31 7PM monthly
- !move {game} {date} {time}: Reschedule a tournament.
  - *Example:* !move Smash Bros 2026-11-01 8PM
- !co_owner {game} @User: Grant admin permissions for an event.
  - *Example:* !co_owner Smash Bros @AdminSteve
- !upcoming: View all scheduled and live events.
  - *Example:* !upcoming

### Participation (!join, !leave, !drop, !rules)
- !join {game}: Sign up for the next tournament.
  - *Example:* !join Smash Bros
- !leave {game}: Remove yourself from a scheduled tournament.
  - *Example:* !leave Smash Bros
- !rules {game}: Read the custom rules for the event.
  - *Example:* !rules Smash Bros
- !drop {game}: Forfeit remaining matches in a live tournament.
  - *Example:* !drop Smash Bros

### Live Execution (!start, !bracket, !win, !ping, !dq, !revert)
- !start {game}: Lock the roster and generate the bracket.
  - *Example:* !start Smash Bros
- !bracket {game}: Display the current visual bracket image.
  - *Example:* !bracket Smash Bros
- !ping {game}: Ping all players currently waiting in open matches (admin only).
  - *Example:* !ping Smash Bros
- !win {game} [@Winner]: Report a match victory. Leave out the @ tag if you won your own match.
  - *Example:* !win Smash Bros @Player
- !dq {game} @Player: Disqualify an unresponsive player (admin only).
  - *Example:* !dq Smash Bros @LateGamer
- !revert {game} {state_id}: Roll back the bracket to a previous state if a match was misreported.
  - *Example:* !revert Smash Bros 4

### Testing
- !test_tourney [game]: Automatically create and start a dummy tournament with 5 players (admin only).
  - *Example:* !test_tourney Smash Bros
- !join_dummy {game} {dummy_id}: Inject a fake player account into the database for a scheduled tournament.
  - *Example:* !join_dummy Smash Bros 999123

### Prestige (!leaderboard)
- !leaderboard: View the reigning champion for every game.
  - *Example:* !leaderboard

## Architecture

- **bot.py**: Entry point and lifecycle management.
- **config.py**: Centralized configuration constants.
- **db/**: Asynchronous SQLite database layer (models.py and database.py).
- **bracket/**: Pure logic module for computing double-elimination routes, auto-byes, and drawing Pillow imagery.
- **cogs/**: Discord command groups representing different feature pillars (scheduling, participation, live, etc).
- **tasks/**: Background loop for alerts and auto-deletion.
