import asyncio
from bracket.engine import generate_bracket
from bracket.draw import generate_bracket_image

state = generate_bracket(1, [101, 102, 103, 104, 105], 3, 5)
img_file = generate_bracket_image(state)
print("Generated image:", img_file.filename)
