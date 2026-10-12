import sys

with open('ui.py', 'r', encoding='utf-8') as f:
    text = f.read()

old = 'self._app.setStyle("Fusion")'
new = 'self._app.setStyle("Fusion")\n        self._app.setFont(QFont("Roboto", 10))'

if old in text:
    with open('ui.py', 'w', encoding='utf-8') as f:
        f.write(text.replace(old, new))
    print('Font set')
else:
    print('Could not set font')
