# Tournies Bot

A fully functional, native Discord tournament bot tailored for community hubs. This bot handles scheduling, bracket generation (double-elimination), match progression, and integration with the Start.gg API.

## Features

- **Double-Elimination Bracket Engine**: Fully custom local bracket logic with BYE handling, cascading auto-advances, and Grand Finals integration.
- **Start.gg Integration**: Links Discord users to their Start.gg profiles and optionally syncs tournament results back to Start.gg.
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
   Open `.env` and fill in your tokens:
   ```env
   DISCORD_TOKEN=your_discord_bot_token_here
   STARTGG_TOKEN=your_startgg_api_token_here
   ```
4. **Invite the Bot to Discord**:
   - Go to the [Discord Developer Portal](https://discord.com/developers/applications).
   - Create a New Application and go to the **Bot** tab to get your token (put this in `.env`).
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

### Scheduling (`!create`, `!move`, `!upcoming`)
- `!create {game} {date} {time} [frequency]`: Schedule a new tournament (frequencies: monthly, quarterly, bi-annually, annually).
- `!move {game} {date} {time}`: Reschedule a tournament.
- `!upcoming`: View all scheduled and live events.

### Participation (`!link`, `!join`, `!leave`, `!drop`)
- `!link {start.gg_tag}`: Link your Discord account to your Start.gg profile.
- `!join {game}`: Sign up for the next tournament.
- `!leave {game}`: Remove yourself from a scheduled tournament.
- `!drop`: Forfeit remaining matches in a live tournament.

### Live Execution (`!start`, `!bracket`, `!win`, `!sync`, `!dq`, `!linkbracket`)
- `!linkbracket {game} {event_id} [slug]`: Link a manually created Start.gg event (admin only).
- `!start {game}`: Lock the roster and generate the bracket.
- `!bracket {game}`: Display the current bracket.
- `!win {score}`: Report a match victory (e.g., `!win 2-1`).
- `!sync [game]`: Sync the local bracket with Start.gg (admin only).
- `!dq @Player`: Disqualify a player (creator only).

### Prestige (`!leaderboard`)
- `!leaderboard`: View the reigning champion for every game.

## Architecture

- **`bot.py`**: Entry point and lifecycle management.
- **`config.py`**: Centralized configuration constants.
- **`db/`**: Asynchronous SQLite database layer (`models.py` and `database.py`).
- **`bracket/`**: Pure logic module for computing double-elimination routes and states.
- **`startgg/`**: GraphQL API client handling queries, mutations, and rate limiting.
- **`cogs/`**: Discord command groups representing different feature pillars.
- **`tasks/`**: Background loop for alerts and auto-deletion.
