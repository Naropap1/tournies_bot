import aiosqlite
from datetime import datetime
from typing import Optional, List, Any, Dict
import json

from .models import Tournament, Entrant, Match, Champion, AlertLog, BracketSnapshot

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def initialize(self):
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._create_tables()

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def _create_tables(self):
        if not self._conn:
            raise RuntimeError("Database not initialized")
        
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS tournaments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                game TEXT NOT NULL,
                scheduled_at TEXT NOT NULL,
                frequency TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                rules TEXT DEFAULT 'Standard rules apply.',
                version INTEGER DEFAULT 1
            )
        """)

        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS tournament_owners (
                tournament_id INTEGER NOT NULL,
                discord_id INTEGER NOT NULL,
                PRIMARY KEY (tournament_id, discord_id),
                FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE
            )
        """)
        
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS entrants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id INTEGER NOT NULL,
                discord_id INTEGER NOT NULL,
                joined_at TEXT NOT NULL,
                dropped BOOLEAN NOT NULL DEFAULT 0,
                FOREIGN KEY (tournament_id) REFERENCES tournaments (id) ON DELETE CASCADE
            )
        """)

        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id INTEGER NOT NULL,
                round_num INTEGER NOT NULL,
                match_number INTEGER NOT NULL,
                player1_id INTEGER,
                player2_id INTEGER,
                winner_id INTEGER,
                score TEXT,
                status TEXT NOT NULL,
                is_grand_finals BOOLEAN NOT NULL DEFAULT 0,
                best_of INTEGER NOT NULL DEFAULT 3,
                FOREIGN KEY (tournament_id) REFERENCES tournaments (id) ON DELETE CASCADE
            )
        """)

        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS bracket_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id INTEGER NOT NULL,
                version INTEGER NOT NULL,
                matches_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE
            )
        """)

        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS champions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                game TEXT NOT NULL,
                discord_id INTEGER NOT NULL,
                tournament_id INTEGER NOT NULL,
                won_at TEXT NOT NULL,
                FOREIGN KEY (tournament_id) REFERENCES tournaments (id) ON DELETE CASCADE
            )
        """)

        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS alert_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id INTEGER NOT NULL,
                alert_type TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                FOREIGN KEY (tournament_id) REFERENCES tournaments (id) ON DELETE CASCADE
            )
        """)
        await self._conn.commit()

    async def _row_to_tournament(self, row: aiosqlite.Row) -> Tournament:
        t_id = row['id']
        async with self._conn.execute("SELECT discord_id FROM tournament_owners WHERE tournament_id = ?", (t_id,)) as cursor:
            owners_rows = await cursor.fetchall()
            owners = [r['discord_id'] for r in owners_rows]

        return Tournament(
            id=t_id,
            guild_id=row['guild_id'],
            channel_id=row['channel_id'],
            game=row['game'],
            scheduled_at=datetime.fromisoformat(row['scheduled_at']),
            frequency=row['frequency'],
            status=row['status'],
            created_at=datetime.fromisoformat(row['created_at']),
            rules=row['rules'],
            version=row['version'],
            owners=owners
        )

    async def insert_tournament(self, t: Tournament) -> int:
        if not self._conn:
            raise RuntimeError("Database not initialized")
        cursor = await self._conn.execute(
            """
            INSERT INTO tournaments 
            (guild_id, channel_id, game, scheduled_at, frequency, status, created_at, rules, version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (t.guild_id, t.channel_id, t.game, t.scheduled_at.isoformat(), t.frequency, t.status, t.created_at.isoformat(), t.rules, t.version)
        )
        t_id = cursor.lastrowid
        
        for owner_id in t.owners:
            await self.add_owner(t_id, owner_id)
            
        await self._conn.commit()
        return t_id

    async def add_owner(self, tournament_id: int, discord_id: int):
        await self._conn.execute(
            "INSERT OR IGNORE INTO tournament_owners (tournament_id, discord_id) VALUES (?, ?)",
            (tournament_id, discord_id)
        )
        await self._conn.commit()

    async def get_tournament(self, tournament_id: int) -> Optional[Tournament]:
        if not self._conn:
            raise RuntimeError("Database not initialized")
        async with self._conn.execute("SELECT * FROM tournaments WHERE id = ?", (tournament_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return await self._row_to_tournament(row)
        return None

    async def get_tournament_by_game(self, guild_id: int, game: str, status: str = 'scheduled') -> Optional[Tournament]:
        if not self._conn:
            raise RuntimeError("Database not initialized")
        async with self._conn.execute(
            "SELECT * FROM tournaments WHERE guild_id = ? AND LOWER(game) = LOWER(?) AND status = ? ORDER BY scheduled_at ASC LIMIT 1",
            (guild_id, game, status)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return await self._row_to_tournament(row)
        return None

    async def get_upcoming_tournaments(self, guild_id: int) -> List[Tournament]:
        if not self._conn:
            raise RuntimeError("Database not initialized")
        tournaments = []
        async with self._conn.execute(
            "SELECT * FROM tournaments WHERE guild_id = ? AND status IN ('scheduled', 'live') ORDER BY scheduled_at ASC",
            (guild_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                tournaments.append(await self._row_to_tournament(row))
        return tournaments

    async def update_tournament(self, tournament_id: int, **kwargs):
        if not self._conn:
            raise RuntimeError("Database not initialized")
        if not kwargs:
            return
        
        if 'scheduled_at' in kwargs and isinstance(kwargs['scheduled_at'], datetime):
            kwargs['scheduled_at'] = kwargs['scheduled_at'].isoformat()
            
        set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values())
        values.append(tournament_id)
        
        await self._conn.execute(f"UPDATE tournaments SET {set_clause} WHERE id = ?", values)
        await self._conn.commit()

    async def delete_tournament(self, tournament_id: int):
        await self._conn.execute("DELETE FROM tournaments WHERE id = ?", (tournament_id,))
        await self._conn.commit()

    # --- Snapshots ---
    async def insert_snapshot(self, snapshot: BracketSnapshot):
        await self._conn.execute(
            "INSERT INTO bracket_snapshots (tournament_id, version, matches_json, created_at) VALUES (?, ?, ?, ?)",
            (snapshot.tournament_id, snapshot.version, snapshot.matches_json, snapshot.created_at.isoformat())
        )
        await self._conn.commit()

    async def get_snapshot(self, tournament_id: int, version: int) -> Optional[BracketSnapshot]:
        async with self._conn.execute("SELECT * FROM bracket_snapshots WHERE tournament_id = ? AND version = ?", (tournament_id, version)) as cursor:
            row = await cursor.fetchone()
            if row:
                return BracketSnapshot(
                    id=row['id'],
                    tournament_id=row['tournament_id'],
                    version=row['version'],
                    matches_json=row['matches_json'],
                    created_at=datetime.fromisoformat(row['created_at'])
                )
        return None
        
    async def delete_snapshots_after(self, tournament_id: int, version: int):
        await self._conn.execute("DELETE FROM bracket_snapshots WHERE tournament_id = ? AND version >= ?", (tournament_id, version))
        await self._conn.commit()

    # --- Entrants ---
    def _row_to_entrant(self, row: aiosqlite.Row) -> Entrant:
        return Entrant(
            id=row['id'],
            tournament_id=row['tournament_id'],
            discord_id=row['discord_id'],
            joined_at=datetime.fromisoformat(row['joined_at']),
            dropped=bool(row['dropped'])
        )

    async def insert_entrant(self, e: Entrant) -> int:
        if not self._conn:
            raise RuntimeError("Database not initialized")
        cursor = await self._conn.execute(
            "INSERT INTO entrants (tournament_id, discord_id, joined_at, dropped) VALUES (?, ?, ?, ?)",
            (e.tournament_id, e.discord_id, e.joined_at.isoformat(), e.dropped)
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def get_entrants(self, tournament_id: int) -> List[Entrant]:
        if not self._conn:
            raise RuntimeError("Database not initialized")
        entrants = []
        async with self._conn.execute(
            "SELECT * FROM entrants WHERE tournament_id = ? ORDER BY joined_at ASC",
            (tournament_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                entrants.append(self._row_to_entrant(row))
        return entrants

    async def get_entrant(self, tournament_id: int, discord_id: int) -> Optional[Entrant]:
        if not self._conn:
            raise RuntimeError("Database not initialized")
        async with self._conn.execute(
            "SELECT * FROM entrants WHERE tournament_id = ? AND discord_id = ?",
            (tournament_id, discord_id)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_entrant(row)
        return None

    async def remove_entrant(self, tournament_id: int, discord_id: int):
        if not self._conn:
            raise RuntimeError("Database not initialized")
        await self._conn.execute(
            "DELETE FROM entrants WHERE tournament_id = ? AND discord_id = ?",
            (tournament_id, discord_id)
        )
        await self._conn.commit()

    async def update_entrant(self, entrant_id: int, **kwargs):
        if not self._conn:
            raise RuntimeError("Database not initialized")
        if not kwargs:
            return
        set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values())
        values.append(entrant_id)
        await self._conn.execute(f"UPDATE entrants SET {set_clause} WHERE id = ?", values)
        await self._conn.commit()

    # --- Matches ---
    def _row_to_match(self, row: aiosqlite.Row) -> Match:
        return Match(
            id=row['id'],
            tournament_id=row['tournament_id'],
            round_num=row['round_num'],
            match_number=row['match_number'],
            player1_id=row['player1_id'],
            player2_id=row['player2_id'],
            winner_id=row['winner_id'],
            score=row['score'],
            status=row['status'],
            is_grand_finals=bool(row['is_grand_finals']),
            best_of=row['best_of']
        )

    async def insert_match(self, m: Match) -> int:
        if not self._conn:
            raise RuntimeError("Database not initialized")
        cursor = await self._conn.execute(
            """
            INSERT INTO matches 
            (tournament_id, round_num, match_number, player1_id, player2_id, winner_id, score, status, is_grand_finals, best_of)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (m.tournament_id, m.round_num, m.match_number, m.player1_id, m.player2_id, m.winner_id, m.score, m.status, m.is_grand_finals, m.best_of)
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def insert_matches(self, matches: List[Match]):
        if not self._conn:
            raise RuntimeError("Database not initialized")
        data = [
            (m.tournament_id, m.round_num, m.match_number, m.player1_id, m.player2_id, m.winner_id, m.score, m.status, m.is_grand_finals, m.best_of)
            for m in matches
        ]
        await self._conn.executemany(
            """
            INSERT INTO matches 
            (tournament_id, round_num, match_number, player1_id, player2_id, winner_id, score, status, is_grand_finals, best_of)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            data
        )
        await self._conn.commit()
        
    async def delete_matches(self, tournament_id: int):
        await self._conn.execute("DELETE FROM matches WHERE tournament_id = ?", (tournament_id,))
        await self._conn.commit()

    async def get_matches(self, tournament_id: int) -> List[Match]:
        if not self._conn:
            raise RuntimeError("Database not initialized")
        matches = []
        async with self._conn.execute(
            "SELECT * FROM matches WHERE tournament_id = ?",
            (tournament_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                matches.append(self._row_to_match(row))
        return matches

    async def get_open_matches(self, tournament_id: int) -> List[Match]:
        if not self._conn:
            raise RuntimeError("Database not initialized")
        matches = []
        async with self._conn.execute(
            "SELECT * FROM matches WHERE tournament_id = ? AND status = 'open' AND player1_id IS NOT NULL AND player2_id IS NOT NULL",
            (tournament_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                matches.append(self._row_to_match(row))
        return matches

    async def get_player_open_match(self, tournament_id: int, discord_id: int) -> Optional[Match]:
        if not self._conn:
            raise RuntimeError("Database not initialized")
        async with self._conn.execute(
            "SELECT * FROM matches WHERE tournament_id = ? AND status = 'open' AND (player1_id = ? OR player2_id = ?)",
            (tournament_id, discord_id, discord_id)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_match(row)
        return None

    async def update_match(self, match_id: int, **kwargs):
        if not self._conn:
            raise RuntimeError("Database not initialized")
        if not kwargs:
            return
        set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values())
        values.append(match_id)
        await self._conn.execute(f"UPDATE matches SET {set_clause} WHERE id = ?", values)
        await self._conn.commit()

    # --- Champions ---
    def _row_to_champion(self, row: aiosqlite.Row) -> Champion:
        return Champion(
            id=row['id'],
            guild_id=row['guild_id'],
            game=row['game'],
            discord_id=row['discord_id'],
            tournament_id=row['tournament_id'],
            won_at=datetime.fromisoformat(row['won_at'])
        )

    async def insert_champion(self, c: Champion) -> int:
        if not self._conn:
            raise RuntimeError("Database not initialized")
        cursor = await self._conn.execute(
            "INSERT INTO champions (guild_id, game, discord_id, tournament_id, won_at) VALUES (?, ?, ?, ?, ?)",
            (c.guild_id, c.game, c.discord_id, c.tournament_id, c.won_at.isoformat())
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def get_champions(self, guild_id: int) -> List[Champion]:
        if not self._conn:
            raise RuntimeError("Database not initialized")
        champions = []
        async with self._conn.execute(
            "SELECT * FROM champions WHERE guild_id = ? ORDER BY won_at DESC",
            (guild_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                champions.append(self._row_to_champion(row))
        return champions

    async def get_champion_for_game(self, guild_id: int, game: str) -> Optional[Champion]:
        if not self._conn:
            raise RuntimeError("Database not initialized")
        async with self._conn.execute(
            "SELECT * FROM champions WHERE guild_id = ? AND LOWER(game) = LOWER(?) ORDER BY won_at DESC LIMIT 1",
            (guild_id, game)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_champion(row)
        return None

    # --- Alerts ---
    async def log_alert(self, tournament_id: int, alert_type: str):
        if not self._conn:
            raise RuntimeError("Database not initialized")
        await self._conn.execute(
            "INSERT INTO alert_logs (tournament_id, alert_type, sent_at) VALUES (?, ?, ?)",
            (tournament_id, alert_type, datetime.now().isoformat())
        )
        await self._conn.commit()

    async def has_alert_been_sent(self, tournament_id: int, alert_type: str) -> bool:
        if not self._conn:
            raise RuntimeError("Database not initialized")
        async with self._conn.execute(
            "SELECT 1 FROM alert_logs WHERE tournament_id = ? AND alert_type = ?",
            (tournament_id, alert_type)
        ) as cursor:
            row = await cursor.fetchone()
            return bool(row)
