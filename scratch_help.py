import re

with open('cogs/help.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Remove the Start.gg field from the main menu
code = re.sub(r'\s+embed\.add_field\(\n\s+name=\"🔗 `!help startgg`\",\n\s+value=\"Detailed guide on how to manually create a Start\.gg bracket and link it to the bot\.\",\n\s+inline=False,\n\s+\)', '', code, flags=re.DOTALL)

# Change footer
code = code.replace('e.g. !help startgg', 'e.g. !help live')

# Remove Startgg guide
code = re.sub(r'\s+@custom_help\.command\(name=\"startgg\"\).*?await ctx\.send\(embed=embed\)', '', code, flags=re.DOTALL)

with open('cogs/help.py', 'w', encoding='utf-8') as f:
    f.write(code)
