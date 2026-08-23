import re

with open('bracket/engine.py', 'r', encoding='utf-8') as f:
    code = f.read()

report_addition = """
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
"""

code = code.replace("    return state, newly_opened", report_addition + "\n    return state, newly_opened")

code = re.sub(r'def is_bracket_complete\(state: BracketState\) -> bool:.*?def get_winner', '''def is_bracket_complete(state: BracketState) -> bool:
    try:
        gf2 = _get_match(state.matches, 0, 2)
        return gf2.status == \\'complete\\'
    except ValueError:
        gf1 = _get_match(state.matches, 0, 1)
        if gf1.status == \\'complete\\' and gf1.winner_id == gf1.player1_id:
            return True
        return False

def get_winner'''.replace("\\'", "'"), code, flags=re.DOTALL)

code = re.sub(r'def get_winner\(state: BracketState\) -> Optional\[int\]:.*', '''def get_winner(state: BracketState) -> Optional[int]:
    try:
        gf2 = _get_match(state.matches, 0, 2)
        if gf2.status == 'complete':
            return gf2.winner_id
    except ValueError:
        gf1 = _get_match(state.matches, 0, 1)
        if gf1.status == 'complete' and gf1.winner_id == gf1.player1_id:
            return gf1.winner_id
    return None''', code, flags=re.DOTALL)

with open('bracket/engine.py', 'w', encoding='utf-8') as f:
    f.write(code)
