from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Tournament:
    guild_id: int
    channel_id: int
    game: str
    creator_id: int
    scheduled_at: datetime
    frequency: str
    status: str
    created_at: datetime
    id: Optional[int] = None
    startgg_slug: Optional[str] = None
    startgg_event_id: Optional[int] = None

@dataclass
class Entrant:
    tournament_id: int
    discord_id: int
    is_phantom: bool
    joined_at: datetime
    id: Optional[int] = None
    startgg_tag: Optional[str] = None
    startgg_entrant_id: Optional[int] = None
    dropped: bool = False

@dataclass
class LinkedAccount:
    discord_id: int
    startgg_tag: str
    guild_id: int

@dataclass
class Match:
    tournament_id: int
    round_num: int
    match_number: int
    id: Optional[int] = None
    player1_id: Optional[int] = None
    player2_id: Optional[int] = None
    winner_id: Optional[int] = None
    score: Optional[str] = None
    status: str = 'pending'
    startgg_set_id: Optional[int] = None
    is_grand_finals: bool = False
    best_of: int = 3

@dataclass
class Champion:
    guild_id: int
    game: str
    discord_id: int
    tournament_id: int
    won_at: datetime
    id: Optional[int] = None

@dataclass
class AlertLog:
    tournament_id: int
    alert_type: str
    sent_at: datetime
    id: Optional[int] = None
