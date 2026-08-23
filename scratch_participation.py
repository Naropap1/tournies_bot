with open('cogs/participation.py', 'r', encoding='utf-8') as f:
    code = f.read()

import re

# Remove !link command
code = re.sub(r'    @commands\.command\(name=\"link\"\)\n.*?async def join_tournament', '    @commands.command(name=\"join\")\n    async def join_tournament', code, flags=re.DOTALL)

# Simplify !join
code = re.sub(r'\s+# Check for linked account.*?\)', '''
        entrant = Entrant(
            tournament_id=tournament.id,
            discord_id=ctx.author.id,
            joined_at=datetime.now(),
        )''', code, flags=re.DOTALL)

code = re.sub(r'\s+phantom_note = "".*?phantom_note = "\\n_💡 Tip: Use `!link \{tag\}` to connect your Start\.gg profile\._"', '', code, flags=re.DOTALL)
code = code.replace('{phantom_note}', '')
code = code.replace('Participation Cog — !link, !join, !leave, !drop', 'Participation Cog — !join, !leave, !drop')
code = code.replace('tournament signups and account linking.', 'tournament signups.')

with open('cogs/participation.py', 'w', encoding='utf-8') as f:
    f.write(code)
