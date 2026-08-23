# Tournies Bot

A fully functional, native Discord tournament bot tailored for community hubs. This bot handles scheduling, bracket generation (double-elimination), match progression,.

## Features

- **Discord Native Image Brackets**: Automatically generates and posts an image of the bracket directly in chat.
- **Interactive Score Reporting**: Uses Discord UI buttons for zero-friction match reporting.
- **Double-Elimination Bracket Engine**: Fully custom local bracket logic with BYE handling, cascading auto-advances, and Grand Finals integration.
- **Recurring Schedules**: Auto-schedules the next event in a series when a tournament concludes.
- **Robust Persistence**: Backed by a SQLite database (`aiosqlite`) with WAL mode. Survives restarts and crashes by persisting bracket state and rebuilding in-memory maps upon reboot.
- **Background Alerts**: Notifies tournament creators 1 week prior and pings channels 24 hours prior. Auto-deletes events that fail to reach the minimum entrant threshold.

## Requirements

- Python 3.12+
- Packages: `discord.py`, `aiohttp`, `python-dotenv`, `aiosqlite`, `python-dateutil`

## Installation & Setup

1. **Clone the repository.**
2. **Install dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```
3. **Configure Environment Variables**:
   Open `.env` and fill in your tokens. Here is how to get them:

   **How to get your `DISCORD_TOKEN`**:
   - Go to the [Discord Developer Portal](https://discord.com/developers/applications).
   - Click **New Application** and give your bot a name.
   - Navigate to the **Bot** tab on the left sidebar.
   - Under the "Build-A-Bot" section, click **Reset Token** (and copy the resulting token).
   - Paste this token into your `.env` file as `DISCORD_TOKEN`.

   ```env
   DISCORD_TOKEN=your_discord_bot_token_here
   ```

4. **Invite the Bot to Discord**:
   - Still in the [Discord Developer Portal](https://discord.com/developers/applications) for your bot application, go to the **Bot** tab.
   - Scroll down and enable the **Message Content Intent** and **Server Members Intent**.
   - Go to **OAuth2 > URL Generator**.
   - Select scopes: `bot`.
   - Select bot permissions: `Read Messages/View Channels`, `Send Messages`, `Embed Links`.
   - Copy the generated URL at the bottom and paste it into your browser to invite the bot to your server!

5. **Run the Bot**:
   ```powershell
   python bot.py
   ```
   The bot will automatically initialize the database `tournies.db` on first run.

## Commands

### Scheduling (!create, !move, !upcoming)
- !create {game} {date} {time} [frequency]: Schedule a new tournament (frequencies: monthly, quarterly, bi-annually, annually).
- !move {game} {date} {time}: Reschedule a tournament.
- !upcoming: View all scheduled and live events.

### Participation (!join, !leave, !drop)
- !join {game}: Sign up for the next tournament.
- !leave {game}: Remove yourself from a scheduled tournament.
- !drop: Forfeit remaining matches in a live tournament.

### Live Execution (!start, !bracket, !win, !dq)
- !start {game}: Lock the roster and generate the bracket.
- !bracket {game}: Display the current bracket.
- !win {score}: Report a match victory (e.g., !win 2-1).
- !dq @Player: Disqualify a player (creator only).
- Matches will also display interactive buttons for score reporting and forfeiting.

### Testing
- !test_tourney [game]: Automatically create and start a dummy tournament with 5 players (admin only).

### Prestige (!leaderboard)
- !leaderboard: View the reigning champion for every game.

## Architecture

- **`bot.py`**: Entry point and lifecycle management.
- **`config.py`**: Centralized configuration constants.
- **`db/`**: Asynchronous SQLite database layer (`models.py` and `database.py`).
- **`bracket/`**: Pure logic module for computing double-elimination routes and states.
- **`startgg/`**: GraphQL API client handling queries, mutations, and rate limiting.
- **`cogs/`**: Discord command groups representing different feature pillars.
- **`tasks/`**: Background loop for alerts and auto-deletion.
