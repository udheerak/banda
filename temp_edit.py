import sys

with open('ui.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1
for i, line in enumerate(lines):
    if 'class C:' in line:
        start_idx = i
    if 'def apply_ui_accent(' in line:
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    replacement = [
        'class C:\n',
        '    BG        = "#0a0a0a"\n',
        '    PANEL     = "#111111"\n',
        '    PANEL2    = "#1a1a1a"\n',
        '    BORDER    = "#222222"\n',
        '    BORDER_B  = "#333333"\n',
        '    BORDER_A  = "#444444"\n',
        '    PRI       = "#00d4ff"\n',
        '    PRI_DIM   = "#007a99"\n',
        '    PRI_GHO   = "#001f2e"\n',
        '    ACC       = "#ff6b00"\n',
        '    ACC2      = "#ffcc00"\n',
        '    GREEN     = "#00ff88"\n',
        '    GREEN_D   = "#00aa55"\n',
        '    RED       = "#ff3355"\n',
        '    MUTED_C   = "#ff3366"\n',
        '    TEXT      = "#f0f0f0"\n',
        '    TEXT_DIM  = "#888888"\n',
        '    TEXT_MED  = "#aaaaaa"\n',
        '    WHITE     = "#ffffff"\n',
        '    DARK      = "#000000"\n',
        '    BAR_BG    = "#111111"\n',
        '\n',
        '_HUE_LINKED = (\n',
        '    "PRI", "PRI_DIM", "PRI_GHO",\n',
        ')\n',
        '_PALETTE_DEFAULTS: dict[str, str] = {k: getattr(C, k) for k in _HUE_LINKED}\n',
        'DEFAULT_UI_COLOR = _PALETTE_DEFAULTS["PRI"]\n',
        '\n\n'
    ]
    lines = lines[:start_idx] + replacement + lines[end_idx:]
    with open('ui.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print('Updated ui.py successfully')
else:
    print('Indices not found', start_idx, end_idx)
