# Tournies Bot Design Document

## Overview
Tournies Bot is a native Discord application designed to seamlessly manage community tournaments. It handles scheduling, participation tracking, automatic bracket generation, live bracket visualization, and prestige tracking (leaderboards). It aims to be completely self-contained within Discord without requiring any third-party websites or external tools.

## Architecture

- **Language:** Python 3.12+
- **Library:** discord.py
- **Database:** SQLite (via aiosqlite) using WAL mode for concurrent, crash-resistant persistence.
- **Image Generation:** Pillow (PIL) for dynamically drawing custom bracket images directly to Discord.

## Core Features & Workflows

### 1. Scheduling and Lifecycle Management
Tournaments are created via !create with a specified game, start time (EST), rules, and an optional recurrence frequency (e.g., one-time, monthly, quarterly).
- Events exist in a scheduled state until their start time.
- Users !join or !leave during this phase.
- A background task alerts players 1 week and 24 hours prior. If minimum participation isn't met, the event auto-cancels.
- Upon calling !start, the tournament transitions to the live state, locking the roster.

### 2. Double-Elimination Bracket Engine
The bracket engine is purely mathematical and decoupled from the database, producing a strictly topological BracketState mapping.
- **Seeding:** Standard power-of-2 topological mapping is used. Initial seeding is randomized to prevent exploitation.
- **Auto-BYEs:** Missing players in non-power-of-2 brackets are replaced with a _BYE_SENTINEL (-1). Any player matched against a BYE is immediately auto-advanced, collapsing the empty branch of the tree.
- **Advanced Rematch Prevention:** The Losers Bracket cross-over routes utilize industry-standard "minor orderings" (
atural, everse, half_shift, everse_half_shift, and pair_flip). This mathematically optimal routing prevents players from the same quadrant of the Winners Bracket from rematching too early in the Losers Bracket.
- **Bracket Resets:** The Grand Finals consists of a primary match (GF1). If the player from the Losers Bracket wins GF1, the engine seamlessly spawns a Bracket Reset match (GF2) to preserve true double-elimination rules.

### 3. Native Image Rendering
Instead of relying on web-based HTML/CSS visualizers, the bot uses Python's Pillow library to draw brackets directly to a .png file.
- Calculates dynamic canvas dimensions based on the depth of the Winners and Losers brackets.
- Re-aligns matches strictly to their respective columns, preventing column-collapse bugs when early Loser rounds consist purely of invisible BYEs.
- Explicitly handles horizontal offsetting for the GF2 (Bracket Reset) match so it remains visible.

### 4. Live Match Progression
Players advance through the tournament using simple text commands like !win [game] [@player].
- The bot locates the current open match involving the reported winner, logs the result, and computes the cascading routes for both the winner (advancing) and the loser (dropping to the Losers Bracket or being eliminated).
- Matches are fully deleted and re-inserted into the SQLite database upon every update to maintain 100% state synchronization.
- A fresh, updated bracket image is posted to the channel immediately following any state change.
- Server admins can use !revert {state_id} to rollback to previous bracket configurations in case of accidental reports.

### 5. Conclusion & Prestige
When the final match concludes (either GF1 or GF2):
- The tournament status is marked as completed.
- A Champion record is inserted into the database to persist the winner's legacy.
- A final gold-trimmed embed and bracket image are posted.
- If the tournament frequency is recurring, the next event in the series is automatically generated and scheduled in the database.
- The !leaderboard command dynamically aggregates these Champions, displaying the most recent reigning champion for every game played on the server.
