import asyncio
import aiosqlite

async def migrate():
    async with aiosqlite.connect('db/tournies.db') as db:
        # Add columns to tournaments
        try:
            await db.execute("ALTER TABLE tournaments ADD COLUMN rules TEXT DEFAULT 'Standard rules apply.'")
        except aiosqlite.OperationalError:
            pass # column exists
            
        try:
            await db.execute("ALTER TABLE tournaments ADD COLUMN version INTEGER DEFAULT 1")
        except aiosqlite.OperationalError:
            pass

        # Create tournament_owners
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tournament_owners (
                tournament_id INTEGER NOT NULL,
                discord_id INTEGER NOT NULL,
                PRIMARY KEY (tournament_id, discord_id),
                FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE
            )
        """)
        
        # Migrate creator_id to owners
        # Check if creator_id exists
        cursor = await db.execute("PRAGMA table_info(tournaments)")
        columns = await cursor.fetchall()
        has_creator = any(col[1] == 'creator_id' for col in columns)
        
        if has_creator:
            await db.execute("""
                INSERT OR IGNORE INTO tournament_owners (tournament_id, discord_id)
                SELECT id, creator_id FROM tournaments
            """)
            
            # SQLite doesn't easily support dropping columns without recreating the table.
            # So we will leave creator_id as an orphaned column, or we can recreate the table.
            # Recreating is safer for long term.
            await db.execute("CREATE TABLE tournaments_new (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, game TEXT NOT NULL, scheduled_at TEXT NOT NULL, frequency TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, rules TEXT, version INTEGER)")
            await db.execute("INSERT INTO tournaments_new (id, guild_id, channel_id, game, scheduled_at, frequency, status, created_at, rules, version) SELECT id, guild_id, channel_id, game, scheduled_at, frequency, status, created_at, rules, version FROM tournaments")
            await db.execute("DROP TABLE tournaments")
            await db.execute("ALTER TABLE tournaments_new RENAME TO tournaments")

        # Create bracket_snapshots
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bracket_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id INTEGER NOT NULL,
                version INTEGER NOT NULL,
                matches_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE
            )
        """)
        
        await db.commit()

asyncio.run(migrate())
