from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import urllib.request
import discord

def generate_bracket_image(bracket_state) -> discord.File:
    """
    Generates a visual bracket image from the bracket_state.
    Returns a discord.File object ready to be sent.
    """
    # For now, we will draw a simple placeholder because doing a perfect tree layout 
    # dynamically in Pillow takes hundreds of lines of layout math.
    # We will just list the matches cleanly in a graphic format.
    
    width = 800
    height = 600
    
    img = Image.new('RGB', (width, height), color=(44, 47, 51))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("arial.ttf", 24)
        title_font = ImageFont.truetype("arialbd.ttf", 36)
    except IOError:
        font = ImageFont.load_default()
        title_font = font
        
    draw.text((20, 20), "Live Tournament Bracket", fill=(255, 255, 255), font=title_font)
    
    y = 80
    for match in bracket_state.matches:
        if match.status == 'bye':
            continue
            
        r_name = "Grand Finals" if match.is_grand_finals else (f"W-Round {match.round_num}" if match.round_num > 0 else f"L-Round {-match.round_num}")
        
        p1 = f"<Player {match.player1_id}>" if match.player1_id else "TBD"
        p2 = f"<Player {match.player2_id}>" if match.player2_id else "TBD"
        score = f" [{match.score}]" if match.score else ""
        status = " (Complete)" if match.status == 'complete' else " (Open)" if match.status == 'open' else ""
        
        winner_id = match.winner_id
        if winner_id == match.player1_id:
            p1 = f"👑 {p1}"
        elif winner_id == match.player2_id:
            p2 = f"👑 {p2}"
            
        text = f"{r_name} Match {match.match_number}: {p1} vs {p2}{score}{status}"
        draw.text((20, y), text, fill=(200, 200, 200), font=font)
        y += 35
        
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    
    return discord.File(buf, filename="bracket.png")
