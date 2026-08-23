"""
Double-elimination bracket engine.

Pure computation module — generates and advances brackets without any I/O.
"""

import math
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple

from db.models import Match

# Sentinel value in player slots indicating "no opponent due to BYE".
# When a player arrives at a match where the opponent slot is _BYE_SENTINEL,
# they auto-advance without playing.
_BYE_SENTINEL = -1

@dataclass
class BracketRoute:
    winner_to: Optional[Tuple[int, int]]  # (round_num, match_number) of next match
    winner_slot: int  # 1 or 2 (which player slot)
    loser_to: Optional[Tuple[int, int]]   # for winners bracket matches
    loser_slot: Optional[int]

@dataclass 
class BracketState:
    matches: List[Match]
    routes: Dict[Tuple[int, int], BracketRoute]  # keyed by (round_num, match_number)


def _generate_standard_seeding(bracket_size: int) -> list[int]:
    '''Generates standard power-of-2 tournament seeding (e.g. 1v8, 4v5, 2v7, 3v6).'''
    if bracket_size < 2:
        return [1]
    seeding = [1, 2]
    current_size = 2
    while current_size < bracket_size:
        next_size = current_size * 2
        next_seeding = []
        for seed in seeding:
            next_seeding.append(seed)
            next_seeding.append(next_size - seed + 1)
        seeding = next_seeding
        current_size = next_size
    return seeding

def _next_power_of_2(x: int) -> int:
    return 1 if x == 0 else 2**(x - 1).bit_length()

def generate_bracket(tournament_id: int, entrant_ids: List[int], best_of_standard: int = 3, best_of_finals: int = 5) -> BracketState:
    num_players = len(entrant_ids)
    bracket_size = _next_power_of_2(max(2, num_players))
    k = int(math.log2(bracket_size))
    
    seeding_order = _generate_standard_seeding(bracket_size)
    padded_entrants = []
    for seed in seeding_order:
        if seed <= num_players:
            padded_entrants.append(entrant_ids[seed - 1])
        else:
            padded_entrants.append(None)
        
    matches = []
    routes = {}
    
    # Generate Winners Bracket
    # round_num: 1 to k
    winners_matches_by_round = {}
    for r in range(1, k + 1):
        num_matches = bracket_size // (2 ** r)
        winners_matches_by_round[r] = []
        is_wf = (r == k)
        best_of = best_of_finals if is_wf else best_of_standard
        for m in range(1, num_matches + 1):
            match = Match(
                id=None,
                tournament_id=tournament_id,
                round_num=r,
                match_number=m,
                player1_id=None,
                player2_id=None,
                winner_id=None,
                score=None,
                status='pending',
                    is_grand_finals=False,
                best_of=best_of
            )
            matches.append(match)
            winners_matches_by_round[r].append(match)
            
    # Populate WR1
    for m in range(bracket_size // 2):
        p1 = padded_entrants[2*m]
        p2 = padded_entrants[2*m + 1]
        match = winners_matches_by_round[1][m]
        match.player1_id = p1
        match.player2_id = p2
        if p1 is None or p2 is None:
            match.status = 'bye'
            match.winner_id = p2 if p1 is None else p1
        else:
            match.status = 'open'

    # Generate Losers Bracket
    # round_num: -1 to -(2k - 2) (if k >= 2)
    losers_matches_by_round = {}
    total_losers_rounds = max(0, 2 * k - 2)
    for lr in range(1, total_losers_rounds + 1):
        # lr=1: 2^{k-2} matches. lr=2: 2^{k-2}. lr=3: 2^{k-3} ...
        if lr == 1:
            num_matches = bracket_size // 4
        else:
            i = (lr + 3) // 2
            num_matches = bracket_size // (2 ** i)
        
        losers_matches_by_round[-lr] = []
        is_lf = (lr == total_losers_rounds)
        best_of = best_of_finals if is_lf else best_of_standard
        
        # Avoid zero matches in Edge case k=1
        if num_matches == 0:
            num_matches = 1

        for m in range(1, num_matches + 1):
            match = Match(
                id=None,
                tournament_id=tournament_id,
                round_num=-lr,
                match_number=m,
                player1_id=None,
                player2_id=None,
                winner_id=None,
                score=None,
                status='pending',
                    is_grand_finals=False,
                best_of=best_of
            )
            matches.append(match)
            losers_matches_by_round[-lr].append(match)
            
    # Generate Grand Finals
    gf_match = Match(
        id=None,
        tournament_id=tournament_id,
        round_num=0,
        match_number=1,
        player1_id=None,
        player2_id=None,
        winner_id=None,
        score=None,
        status='pending',
        is_grand_finals=True,
        best_of=best_of_finals
    )
    matches.append(gf_match)

    # Setup routes
    for match in matches:
        routes[(match.round_num, match.match_number)] = BracketRoute(
            winner_to=None, winner_slot=1, loser_to=None, loser_slot=None
        )

    # Winners routing
    for r in range(1, k + 1):
        for m in range(1, len(winners_matches_by_round[r]) + 1):
            route = routes[(r, m)]
            # Winner routing
            if r < k:
                next_m = (m + 1) // 2
                route.winner_to = (r + 1, next_m)
                route.winner_slot = 1 if m % 2 != 0 else 2
            else:
                route.winner_to = (0, 1) # Grand Finals
                route.winner_slot = 1
                
            # Loser routing
            if total_losers_rounds > 0:
                if r == 1:
                    lr = -1
                    next_m = (m + 1) // 2
                    route.loser_to = (lr, next_m)
                    route.loser_slot = 1 if m % 2 != 0 else 2
                else:
                    lr = -(2 * r - 2)
                    next_m = m
                    route.loser_to = (lr, next_m)
                    route.loser_slot = 2

    # Losers routing
    for lr in range(1, total_losers_rounds + 1):
        for m in range(1, len(losers_matches_by_round[-lr]) + 1):
            route = routes[(-lr, m)]
            # Winner routing
            if lr < total_losers_rounds:
                next_lr = -(lr + 1)
                if lr % 2 != 0:
                    # Drop down round feeds straight across
                    next_m = m
                    route.winner_to = (next_lr, next_m)
                    route.winner_slot = 1
                else:
                    # Elimination round pairs up
                    next_m = (m + 1) // 2
                    route.winner_to = (next_lr, next_m)
                    route.winner_slot = 1 if m % 2 != 0 else 2
            else:
                route.winner_to = (0, 1) # Grand Finals
                route.winner_slot = 2
                
            route.loser_to = None
            route.loser_slot = None

    state = BracketState(matches=matches, routes=routes)
    
    # Propagate byes — mark losers bracket slots receiving a 'no loser' as BYE_SENTINEL
    changed = True
    propagated_byes = set()
    while changed:
        changed = False
        for match in state.matches:
            m_key = (match.round_num, match.match_number)
            if match.status == 'bye' and m_key not in propagated_byes:
                propagated_byes.add(m_key)
                
                route = state.routes[m_key]
                # Forward winner to next match
                if route.winner_to:
                    next_match = _get_match(state.matches, route.winner_to[0], route.winner_to[1])
                    win_forward = match.winner_id if match.winner_id is not None else _BYE_SENTINEL
                    
                    if route.winner_slot == 1 and next_match.player1_id is None:
                        next_match.player1_id = win_forward
                        changed = True
                    elif route.winner_slot == 2 and next_match.player2_id is None:
                        next_match.player2_id = win_forward
                        changed = True

                # Forward BYE sentinel to losers bracket (no actual loser exists)
                if route.loser_to:
                    next_loser_match = _get_match(state.matches, route.loser_to[0], route.loser_to[1])
                    if route.loser_slot == 1 and next_loser_match.player1_id is None:
                        next_loser_match.player1_id = _BYE_SENTINEL
                        changed = True
                    elif route.loser_slot == 2 and next_loser_match.player2_id is None:
                        next_loser_match.player2_id = _BYE_SENTINEL
                        changed = True

        # Auto-advance matches where one side is BYE_SENTINEL and the other has a real player
        for match in state.matches:
            if match.status in ('pending', 'open') and match.round_num != 0:
                p1_bye = (match.player1_id == _BYE_SENTINEL)
                p2_bye = (match.player2_id == _BYE_SENTINEL)

                if p1_bye and p2_bye:
                    # Both sides BYE — propagate as BYE
                    match.player1_id = _BYE_SENTINEL
                    match.player2_id = _BYE_SENTINEL
                    match.status = 'bye'
                    match.winner_id = None
                    changed = True
                elif p1_bye and match.player2_id is not None and match.player2_id != _BYE_SENTINEL:
                    # Player 2 auto-advances
                    match.status = 'bye'
                    match.winner_id = match.player2_id
                    changed = True
                elif p2_bye and match.player1_id is not None and match.player1_id != _BYE_SENTINEL:
                    # Player 1 auto-advances
                    match.status = 'bye'
                    match.winner_id = match.player1_id
                    changed = True

    # Update statuses: matches with both real players become 'open'
    for match in state.matches:
        if match.status == 'pending':
            if (match.player1_id is not None and match.player1_id != _BYE_SENTINEL and
                    match.player2_id is not None and match.player2_id != _BYE_SENTINEL):
                match.status = 'open'

    return state

def _get_match(matches: List[Match], round_num: int, match_number: int) -> Match:
    for m in matches:
        if m.round_num == round_num and m.match_number == match_number:
            return m
    raise ValueError(f"Match {round_num}-{match_number} not found")


def report_match_result(state: BracketState, match_id_or_number: Tuple[int, int], winner_id: int, score: str) -> Tuple[BracketState, List[Match]]:
    round_num, match_number = match_id_or_number
    match = _get_match(state.matches, round_num, match_number)
    
    if match.status != 'open':
        raise ValueError("Match is not open")
        
    match.winner_id = winner_id
    match.score = score
    match.status = 'complete'
    
    loser_id = match.player2_id if match.player1_id == winner_id else match.player1_id
    
    route = state.routes[(round_num, match_number)]
    newly_opened = []

    def _place_player_in_match(player_id: int, target: Tuple[int, int], slot: int) -> None:
        """Place a player into a match slot. If the opponent is a BYE sentinel, auto-advance."""
        next_match = _get_match(state.matches, target[0], target[1])
        if slot == 1:
            next_match.player1_id = player_id
        else:
            next_match.player2_id = player_id

        other_slot = next_match.player2_id if slot == 1 else next_match.player1_id

        if other_slot == _BYE_SENTINEL:
            # Auto-advance: opponent is a BYE
            next_match.status = 'bye'
            next_match.winner_id = player_id
            # Cascade: forward this auto-advanced player to their next match
            bye_route = state.routes[(next_match.round_num, next_match.match_number)]
            if bye_route.winner_to:
                _place_player_in_match(player_id, bye_route.winner_to, bye_route.winner_slot)
        elif other_slot is not None and next_match.status == 'pending':
            next_match.status = 'open'
            newly_opened.append(next_match)
    
    # Forward winner
    if route.winner_to:
        _place_player_in_match(winner_id, route.winner_to, route.winner_slot)
            
    # Forward loser
    if route.loser_to and loser_id is not None and loser_id != _BYE_SENTINEL:
        _place_player_in_match(loser_id, route.loser_to, route.loser_slot)
            

    # Bracket Reset Logic
    if round_num == 0 and match_number == 1 and winner_id == match.player2_id:
        # Losers bracket champion won GF1. We need a bracket reset (GF2).
        # Check if GF2 already exists (just in case)
        try:
            gf2 = _get_match(state.matches, 0, 2)
        except ValueError:
            gf2 = Match(
                id=None,
                tournament_id=match.tournament_id,
                round_num=0,
                match_number=2,
                player1_id=match.player1_id,
                player2_id=match.player2_id,
                winner_id=None,
                score=None,
                status='open',
                is_grand_finals=True,
                best_of=match.best_of
            )
            state.matches.append(gf2)
            state.routes[(0, 2)] = BracketRoute(winner_to=None, winner_slot=1, loser_to=None, loser_slot=None)
            newly_opened.append(gf2)

    return state, newly_opened

def get_open_matches(state: BracketState) -> List[Match]:
    return [m for m in state.matches if m.status == 'open']

def get_match_for_player(state: BracketState, player_id: int) -> Optional[Match]:
    for m in state.matches:
        if m.status == 'open' and (m.player1_id == player_id or m.player2_id == player_id):
            return m
    return None

def is_bracket_complete(state: BracketState) -> bool:
    try:
        gf2 = _get_match(state.matches, 0, 2)
        return gf2.status == 'complete'
    except ValueError:
        gf1 = _get_match(state.matches, 0, 1)
        if gf1.status == 'complete' and gf1.winner_id == gf1.player1_id:
            return True
        return False

def get_winner(state: BracketState) -> Optional[int]:
    try:
        gf2 = _get_match(state.matches, 0, 2)
        if gf2.status == 'complete':
            return gf2.winner_id
    except ValueError:
        gf1 = _get_match(state.matches, 0, 1)
        if gf1.status == 'complete' and gf1.winner_id == gf1.player1_id:
            return gf1.winner_id
    return None