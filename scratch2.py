import re
with open('db/models.py', 'r') as f: code = f.read()
code = code.replace('    is_phantom: bool\n', '')
with open('db/models.py', 'w') as f: f.write(code)

with open('db/database.py', 'r') as f: code = f.read()
code = code.replace('                is_phantom BOOLEAN NOT NULL,\n', '')
code = code.replace('is_phantom, ', '')
code = code.replace(':is_phantom, ', '')
code = re.sub(r'e\.is_phantom,\n\s+', '', code)
code = re.sub(r'is_phantom=bool\(row\["is_phantom"\]\),\n\s+', '', code)
with open('db/database.py', 'w') as f: f.write(code)
