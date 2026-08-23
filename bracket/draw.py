from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import discord
from typing import Dict, Tuple

def generate_bracket_image(bracket_state) -> discord.File:
    """
    Generates a tree-like visual bracket image from the bracket_state using Pillow.
    """
    # Group matches by round
    rounds: Dict[int, list] = {}
    for m in bracket_state.matches:
        if m.status == 'bye':
            continue
        rounds.setdefault(m.round_num, []).append(m)

    winners_rounds = sorted([r for r in rounds.keys() if r > 0])
    losers_rounds = sorted([r for r in rounds.keys() if r < 0], reverse=True)
    
    # Calculate dimensions
    box_w = 200
    box_h = 50
    x_spacing = 50
    y_spacing = 30
    
    # Max depth
    w_depth = len(winners_rounds)
    l_depth = len(losers_rounds)
    
    # We will draw Winners Bracket on top, Losers below
    w_max_matches = len(rounds.get(1, [])) if winners_rounds else 0
    l_max_matches = len(rounds.get(-1, [])) if losers_rounds else 0
    
    total_w = max(w_depth + 1, l_depth + 1) * (box_w + x_spacing) + 100
    
    w_h = w_max_matches * (box_h + y_spacing) * 2
    l_h = l_max_matches * (box_h + y_spacing) * 2
    
    total_h = w_h + l_h + 200
    
    img = Image.new('RGB', (int(total_w), int(total_h)), color=(35, 39, 42))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("arial.ttf", 16)
        title_font = ImageFont.truetype("arialbd.ttf", 32)
    except IOError:
        font = ImageFont.load_default()
        title_font = font
        
    draw.text((20, 20), "Tournament Bracket", fill=(255, 255, 255), font=title_font)
    
    match_coords = {} # (round_num, match_num) -> (x, y_center)
    
    # Draw Winners Bracket
    y_offset = 100
    for i, r in enumerate(winners_rounds):
        matches = sorted(rounds[r], key=lambda x: x.match_number)
        x = 50 + i * (box_w + x_spacing)
        
        # Calculate Y positions. 
        # Round 1 is evenly spaced.
        # Round N is the average Y of the two feeding matches from Round N-1.
        for m_idx, match in enumerate(matches):
            if r == 1:
                y_center = y_offset + m_idx * (box_h + y_spacing) * 2
            else:
                # Find feeders
                feeders = []
                for prev_m in rounds[r-1]:
                    route = bracket_state.routes.get((prev_m.round_num, prev_m.match_number))
                    if route and route.winner_to == (match.round_num, match.match_number):
                        feeders.append(match_coords.get((prev_m.round_num, prev_m.match_number)))
                if len(feeders) == 2 and all(feeders):
                    y_center = (feeders[0][1] + feeders[1][1]) / 2
                else:
                    y_center = y_offset + m_idx * (box_h + y_spacing) * 2
            
            match_coords[(match.round_num, match.match_number)] = (x, y_center)
            _draw_match_box(draw, x, y_center - box_h/2, box_w, box_h, match, font)
            
            # Draw connecting lines from feeders
            if r > 1:
                feeders = []
                for prev_m in rounds[r-1]:
                    route = bracket_state.routes.get((prev_m.round_num, prev_m.match_number))
                    if route and route.winner_to == (match.round_num, match.match_number):
                        prev_coord = match_coords.get((prev_m.round_num, prev_m.match_number))
                        if prev_coord:
                            # Draw line from right edge of prev to left edge of current
                            px, py = prev_coord[0] + box_w, prev_coord[1]
                            cx, cy = x, y_center
                            draw.line([(px, py), (px + x_spacing/2, py), (px + x_spacing/2, cy), (cx, cy)], fill=(114, 137, 218), width=2)
                            
    # Draw Losers Bracket
    l_y_offset = y_offset + w_h + 50
    draw.text((20, l_y_offset - 40), "Losers Bracket", fill=(255, 255, 255), font=title_font)
    
    for i, r in enumerate(losers_rounds):
        matches = sorted(rounds[r], key=lambda x: x.match_number)
        x = 50 + i * (box_w + x_spacing)
        
        for m_idx, match in enumerate(matches):
            if i == 0:
                y_center = l_y_offset + m_idx * (box_h + y_spacing) * 1.5
            else:
                feeders = []
                for prev_m in rounds[losers_rounds[i-1]]:
                    route = bracket_state.routes.get((prev_m.round_num, prev_m.match_number))
                    if route and route.winner_to == (match.round_num, match.match_number):
                        feeders.append(match_coords.get((prev_m.round_num, prev_m.match_number)))
                if len(feeders) == 2 and all(feeders):
                    y_center = (feeders[0][1] + feeders[1][1]) / 2
                elif len(feeders) == 1 and all(feeders):
                    y_center = feeders[0][1]
                else:
                    y_center = l_y_offset + m_idx * (box_h + y_spacing) * 1.5
                    
            match_coords[(match.round_num, match.match_number)] = (x, y_center)
            _draw_match_box(draw, x, y_center - box_h/2, box_w, box_h, match, font)
            
            if i > 0:
                feeders = []
                for prev_m in rounds[losers_rounds[i-1]]:
                    route = bracket_state.routes.get((prev_m.round_num, prev_m.match_number))
                    if route and route.winner_to == (match.round_num, match.match_number):
                        prev_coord = match_coords.get((prev_m.round_num, prev_m.match_number))
                        if prev_coord:
                            px, py = prev_coord[0] + box_w, prev_coord[1]
                            cx, cy = x, y_center
                            draw.line([(px, py), (px + x_spacing/2, py), (px + x_spacing/2, cy), (cx, cy)], fill=(200, 100, 100), width=2)
                            
    # Grand Finals
    gf_matches = sorted(rounds.get(0, []), key=lambda x: x.match_number)
    for idx, gf in enumerate(gf_matches):
        x = 50 + max(w_depth, l_depth) * (box_w + x_spacing)
        y_center = y_offset + (w_h / 2) + idx * (box_h + y_spacing)
        match_coords[(gf.round_num, gf.match_number)] = (x, y_center)
        _draw_match_box(draw, x, y_center - box_h/2, box_w, box_h, gf, font, True)
        
        # Draw lines to GF from WF and LF
        if idx == 0:
            if winners_rounds:
                wf = rounds[winners_rounds[-1]][0]
                wf_coord = match_coords.get((wf.round_num, wf.match_number))
                if wf_coord:
                    px, py = wf_coord[0] + box_w, wf_coord[1]
                    draw.line([(px, py), (px + x_spacing/2, py), (px + x_spacing/2, y_center-10), (x, y_center-10)], fill=(255, 215, 0), width=3)
            if losers_rounds:
                lf = rounds[losers_rounds[-1]][0]
                lf_coord = match_coords.get((lf.round_num, lf.match_number))
                if lf_coord:
                    px, py = lf_coord[0] + box_w, lf_coord[1]
                    draw.line([(px, py), (px + x_spacing/2, py), (px + x_spacing/2, y_center+10), (x, y_center+10)], fill=(255, 215, 0), width=3)
        elif idx == 1:
            # Bracket reset line from GF1
            gf1_coord = match_coords.get((0, 1))
            if gf1_coord:
                px, py = gf1_coord[0] + box_w, gf1_coord[1]
                draw.line([(px, py), (px + x_spacing/2, py), (px + x_spacing/2, y_center), (x, y_center)], fill=(255, 215, 0), width=3)

    # Crop image to fit contents
    bbox = img.getbbox()
    if bbox:
        img = img.crop((0, 0, bbox[2] + 50, bbox[3] + 50))

    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return discord.File(buf, filename="bracket.png")


def _draw_match_box(draw, x, y, w, h, match, font, is_gf=False):
    fill_color = (44, 47, 51)
    outline_color = (255, 215, 0) if is_gf else (114, 137, 218)
    
    if match.status == 'open':
        fill_color = (55, 60, 65)
        outline_color = (67, 181, 129)
        
    draw.rectangle([x, y, x+w, y+h], fill=fill_color, outline=outline_color, width=2)
    
    p1 = f"<Player {match.player1_id}>" if match.player1_id else "TBD"
    p2 = f"<Player {match.player2_id}>" if match.player2_id else "TBD"
    
    if match.winner_id == match.player1_id:
        p1 = f"👑 {p1}"
    elif match.winner_id == match.player2_id:
        p2 = f"👑 {p2}"
        
    p1_color = (255,255,255) if match.winner_id == match.player1_id or not match.winner_id else (150,150,150)
    p2_color = (255,255,255) if match.winner_id == match.player2_id or not match.winner_id else (150,150,150)
    
    draw.text((x + 10, y + 5), p1, fill=p1_color, font=font)
    draw.line([x, y + h/2, x + w, y + h/2], fill=(80, 80, 80), width=1)
    draw.text((x + 10, y + h/2 + 5), p2, fill=p2_color, font=font)
    
    if match.score:
        draw.text((x + w - 40, y + h/2 - 10), match.score, fill=(200, 200, 200), font=font)
