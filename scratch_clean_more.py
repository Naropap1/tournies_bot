with open('cogs/help.py', 'r', encoding='utf-8') as f:
    code = f.read()

import re
code = re.sub(r'\"🔗 \*\*Account Linking\*\*.*?\" \+ \\', '', code, flags=re.DOTALL)
code = re.sub(r'\s+\"\*\*Usage:\*\* `\!link \{your_startgg_tag\}` \(e\.g\., `\!link MkLeo`\)\\n\"', '', code, flags=re.DOTALL)

with open('cogs/help.py', 'w', encoding='utf-8') as f:
    f.write(code)

with open('config.py', 'r', encoding='utf-8') as f:
    code = f.read()

code = re.sub(r'STARTGG_API_URL.*?\n', '', code)
code = re.sub(r'STARTGG_RATE_LIMIT.*?\n', '', code)
code = re.sub(r'STARTGG_RATE_WINDOW.*?\n', '', code)

with open('config.py', 'w', encoding='utf-8') as f:
    f.write(code)
