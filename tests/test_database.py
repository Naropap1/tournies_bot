"""
Integration test for the database layer.

Tests table creation, CRUD operations, and data persistence.
"""

import asyncio
import os
import sys

sys.path.insert(0, '.')

from datetime import datetime
from db.database import Database
from db.models import Tournament, Entrant, Match, Champion


async def test_database():
    db_path = "test_tournies.db"
    # Clean up from previous runs
    if os.path.exists(db_path):
        os.remove(db_path)

    db = Database(db_path)
    await db.initialize()
    print("DB initialized OK")

    # -- Tournament CRUD --
    t = Tournament(
        guild_id=123456,
        channel_id=789012,
        game="Smash",
        creator_id=111,
        scheduled_at=datetime(2026, 10, 1, 19, 0),
        frequency="monthly",
        status="scheduled",
        created_at=datetime.now(),
    )
    tid = await db.insert_tournament(t)
    print(f"Inserted tournament ID: {tid}")
    assert tid is not None and tid > 0

    fetched = await db.get_tournament(tid)
    assert fetched is not None
    assert fetched.game == "Smash"
    assert fetched.creator_id == 111
    print(f"Fetched tournament: {fetched.game} (status={fetched.status})")

    await db.update_tournament(tid, status="live")
    live = await db.get_tournament(tid)
    assert live.status == "live"
    print("Updated tournament status to live")

    by_game = await db.get_tournament_by_game(123456, "Smash", status="live")
    assert by_game is not None
    print(f"Found by game: {by_game.game}")

    upcoming = await db.get_upcoming_tournaments(123456)
    assert len(upcoming) == 1
    print(f"Upcoming tournaments: {len(upcoming)}")

    # -- Entrant CRUD --
    e1 = Entrant(tournament_id=tid, discord_id=222, is_phantom=False, joined_at=datetime.now())
    e2 = Entrant(tournament_id=tid, discord_id=333, is_phantom=True, joined_at=datetime.now())
    eid1 = await db.insert_entrant(e1)
    eid2 = await db.insert_entrant(e2)
    print(f"Inserted entrants: {eid1}, {eid2}")

    entrants = await db.get_entrants(tid)
    assert len(entrants) == 2
    print(f"Entrants in tournament: {len(entrants)}")

    single = await db.get_entrant(tid, 222)
    assert single is not None and single.discord_id == 222
    print(f"Fetched entrant 222: phantom={single.is_phantom}")

    await db.remove_entrant(tid, 333)
    entrants2 = await db.get_entrants(tid)
    assert len(entrants2) == 1
    print("Removed entrant 333, remaining: 1")

    # -- Linked Accounts --
    await db.link_account(222, "MkLeo", 123456)
    linked = await db.get_linked_account(222, 123456)
    assert linked is not None and linked.startgg_tag == "MkLeo"
    print(f"Linked account: {linked.startgg_tag}")

    # Update link
    await db.link_account(222, "MkLeo2", 123456)
    linked2 = await db.get_linked_account(222, 123456)
    assert linked2.startgg_tag == "MkLeo2"
    print(f"Updated link: {linked2.startgg_tag}")

    # -- Match CRUD --
    m1 = Match(tournament_id=tid, round_num=1, match_number=1, player1_id=222, player2_id=333, status="open")
    mid = await db.insert_match(m1)
    print(f"Inserted match ID: {mid}")

    matches = await db.get_matches(tid)
    assert len(matches) == 1
    print(f"Matches in tournament: {len(matches)}")

    open_m = await db.get_open_matches(tid)
    assert len(open_m) == 1
    print(f"Open matches: {len(open_m)}")

    player_m = await db.get_player_open_match(tid, 222)
    assert player_m is not None
    print(f"Player 222's match: R{player_m.round_num} M{player_m.match_number}")

    await db.update_match(mid, winner_id=222, score="2-1", status="complete")
    completed = await db.get_open_matches(tid)
    assert len(completed) == 0
    print("Match completed, no more open matches")

    # Bulk insert
    bulk = [
        Match(tournament_id=tid, round_num=2, match_number=1, status="pending"),
        Match(tournament_id=tid, round_num=2, match_number=2, status="pending"),
    ]
    await db.insert_matches(bulk)
    all_matches = await db.get_matches(tid)
    assert len(all_matches) == 3
    print(f"Bulk insert: {len(all_matches)} total matches")

    # -- Champions --
    c = Champion(guild_id=123456, game="Smash", discord_id=222, tournament_id=tid, won_at=datetime.now())
    cid = await db.insert_champion(c)
    print(f"Inserted champion ID: {cid}")

    champs = await db.get_champions(123456)
    assert len(champs) == 1
    print(f"Champions: {len(champs)}")

    game_champ = await db.get_champion_for_game(123456, "Smash")
    assert game_champ is not None and game_champ.discord_id == 222
    print(f"Smash champion: user {game_champ.discord_id}")

    # -- Alert Logs --
    await db.log_alert(tid, "1_week")
    assert await db.has_alert_been_sent(tid, "1_week")
    assert not await db.has_alert_been_sent(tid, "24_hour")
    print("Alert logging works correctly")

    await db.close()
    os.remove(db_path)
    print("\n=== All database tests PASSED ===")


if __name__ == "__main__":
    asyncio.run(test_database())
