with open('README.md', 'r', encoding='utf-8') as f:
    readme = f.read()

import re

# Remove startgg token references
readme = re.sub(r'\s+\*\*How to get your `STARTGG_TOKEN`.*?\n\s+```env', '\n\n   ```env', readme, flags=re.DOTALL)
readme = readme.replace('\n   STARTGG_TOKEN=your_startgg_api_token_here', '')

# Remove Start.gg integration from Features
readme = re.sub(r'- \*\*Start\.gg Integration\*\*:.*?\n', '', readme)

# Add Discord native features
readme = readme.replace('- **Double-Elimination Bracket Engine**', '- **Discord Native Image Brackets**: Automatically generates and posts an image of the bracket directly in chat.\n- **Interactive Score Reporting**: Uses Discord UI buttons for zero-friction match reporting.\n- **Double-Elimination Bracket Engine**')

# Fix live execution commands
readme = readme.replace('- `!linkbracket {game} {event_id} [slug]`: Link a manually created Start.gg event (admin only).\n', '')
readme = readme.replace('- `!sync [game]`: Sync the local bracket with Start.gg (admin only).\n', '')

with open('README.md', 'w', encoding='utf-8') as f:
    f.write(readme)
