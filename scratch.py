import re

with open('db/database.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Remove LinkedAccount from imports
code = code.replace(', LinkedAccount', '')

# Remove startgg columns from tables
code = re.sub(r'\s+startgg_slug TEXT,\n\s+startgg_event_id INTEGER,', '', code)
code = re.sub(r'\s+startgg_tag TEXT,\n\s+startgg_entrant_id INTEGER,', '', code)
code = re.sub(r'\s+startgg_set_id INTEGER,', '', code)

# Remove linked_accounts table
code = re.sub(r'\s+await self\._conn\.execute\(\"\"\"\s+CREATE TABLE IF NOT EXISTS linked_accounts.*?\"\"\"\)', '', code, flags=re.DOTALL)

# Remove linked_account methods
code = re.sub(r'\s+async def link_account.*?async def insert_match', '\n\n    async def insert_match', code, flags=re.DOTALL)

# Fix insert_tournament
code = re.sub(r'startgg_slug, startgg_event_id, ', '', code)
code = re.sub(r':startgg_slug, :startgg_event_id, ', '', code)
code = re.sub(r't\.startgg_slug,\n\s+t\.startgg_event_id,\n\s+', '', code)

# Fix map_tournament
code = re.sub(r'startgg_slug=row\["startgg_slug"\],\n\s+startgg_event_id=row\["startgg_event_id"\],\n\s+', '', code)

# Fix insert_entrant
code = re.sub(r'startgg_tag, startgg_entrant_id, ', '', code)
code = re.sub(r':startgg_tag, :startgg_entrant_id, ', '', code)
code = re.sub(r'e\.startgg_tag,\n\s+e\.startgg_entrant_id,\n\s+', '', code)

# Fix map_entrant
code = re.sub(r'startgg_tag=row\["startgg_tag"\],\n\s+startgg_entrant_id=row\["startgg_entrant_id"\],\n\s+', '', code)

# Fix insert_match / insert_matches
code = re.sub(r'startgg_set_id, ', '', code)
code = re.sub(r':startgg_set_id, ', '', code)
code = re.sub(r'm\.startgg_set_id,\n\s+', '', code)
code = re.sub(r'm\.startgg_set_id,\s+', '', code)

# Fix map_match
code = re.sub(r'startgg_set_id=row\["startgg_set_id"\],\n\s+', '', code)

with open('db/database.py', 'w', encoding='utf-8') as f:
    f.write(code)
