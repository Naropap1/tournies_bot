# Design Document: Tournies Bot 2.0 🏆

## 1. Overview
**Tournies Bot** is a fully automated, 100% native Discord tournament manager. Designed for community hubs and gaming servers, it completely eliminates the need for external websites. It manages the entire tournament lifecycle—from scheduling, rulesets, and signups to visually stunning bracket generation, optimal double-elimination rematch prevention, state-reversions, and prestige tracking—entirely within Discord.

---

## 2. The User Experience (How it Works)

### Phase 1: Scheduling & Setup
- **Creation:** A tournament organizer (TO) uses !create to schedule an upcoming tournament. They set a date, time (defaulted strictly to EST), frequency, and a custom rules block.
- **Delegation:** The organizer can use !co_owner @User to instantly grant trusted community members full administrative access over that specific event.
- **Discovery & Rules:** Players use !upcoming to see a formatted list of all upcoming events. They can use !rules {game} at any time to read the specific ruleset configured by the TO.
- **Alerts:** The bot automatically pings the channel 1 week and 24 hours before the event to drive signups.

### Phase 2: Sign-ups & Participation
- **Joining:** Players type !join Smash. The bot instantly confirms their registration and updates the live roster count.
- **Backing Out:** Players can use !leave Smash prior to the event starting.
- **Auto-Pruning:** If a tournament fails to reach the minimum player threshold (2) by start time, the bot automatically cancels it.

### Phase 3: The Live Tournament
- **Starting:** A TO types !start Smash. The bot locks the roster and dynamically generates the Double-Elimination Bracket. Seeding is completely randomized to prevent exploitation.
- **Visual Brackets:** The bot generates a custom .png image of a true bracket tree and posts it directly in the chat.
- **Auto-BYEs:** Missing players in non-power-of-2 brackets are mapped dynamically. Players matched against a BYE are instantly auto-advanced.
- **Reporting:** When a player wins, they type !win Smash (or a TO types !win Smash @Winner). The bot computationally routes the winner forward and drops the loser to the Losers Bracket using industry-standard optimal rematch-prevention math (everse_half_shift, pair_flip, etc.).
- **Progress Tracking:** The bot posts an updated visual bracket instantly upon every match conclusion. TOs can use !ping Smash to alert any players who are currently holding up open matches.
- **State Reversion:** A TO can instantly roll back the tournament using !revert {game} {state_id} if a match is misreported.
- **Grand Finals Reset:** If the champion of the Losers Bracket defeats the champion of the Winners Bracket in the Grand Finals, the bot automatically generates and visualizes a "Bracket Reset" (GF2) match to preserve true double-elimination rules.

### Phase 4: Glory & Prestige
- **Crowning the Champion:** The bot announces the winner and records the victory in the database Hall of Fame.
- **Auto-Scheduling:** Recurring events are automatically rescheduled for their next iteration.
- **The Leaderboard:** Players can use !leaderboard to view server-wide champions for every game.

---

## 3. Comprehensive Command Reference

### 📅 Scheduling Commands (Organizers)
- !create {game} {date} {time} [frequency] [rules...] — Schedules a new tournament (EST).
- !move {game} {date} {time} — Reschedules an upcoming tournament.
- !co_owner {game} @User — Grants admin permissions for a specific event.
- !upcoming — Displays active and scheduled events.

### 🎮 Participation Commands (Players)
- !join {game} — Signs you up for an upcoming tournament.
- !leave {game} — Removes you from the roster.
- !rules {game} — View the tournament ruleset.
- !drop {game} — Forfeits remaining matches in a live event.

### 🔴 Live Execution Commands (During the Event)
- !start {game} — Locks roster and starts the bracket (TO only).
- !bracket {game} — Posts the latest bracket image.
- !ping {game} — Pings all players currently waiting in open matches (TO only).
- !win {game} [@Winner] — Reports a win for your active match (TOs can tag others).
- !revert {game} {state_id} — Rolls back bracket to a previous state (TO only).
- !dq {game} @Player — Forcibly disqualifies an unresponsive player (TO only).

### 🏆 Prestige & Testing
- !leaderboard — Displays server champions.
- !test_tourney [game] — Generates a dummy one-time tournament with 5 placeholder players for testing.
- !join_dummy {game} {dummy_id} — Injects a fake player account into a scheduled tournament.

---

## 4. Technical Architecture

### Internal Modules
- **ot.py** — Main entry point; handles DB initialization and loads Cogs.
- **config.py** — Centralized configuration variables.
- **racket/engine.py** — Pure computation module handling advanced double-elimination routing topology.
- **racket/draw.py** — Uses Python Pillow (PIL) to natively render and offset visual bracket trees.
- **cogs/** — Modularized Discord features (live, participation, scheduling, prestige, help, 	esting).
- **	asks/** — Background loops driving the 1-week/24-hour alerting system.

### Database Schema (SQLite WAL)
- **	ournaments**: Tracks metadata (rules, version, scheduling).
- **	ournament_owners**: Maps tournaments to multiple Discord owners.
- **entrants**: Tracks tournament rosters.
- **matches**: Tracks individual sets and status natively.
- **racket_snapshots**: JSON dumps generated upon every state change for instantaneous rollbacks.
- **champions**: Hall of Fame tracking for the leaderboard.
- **lert_logs**: Ensures background alerts are only sent once per threshold.
