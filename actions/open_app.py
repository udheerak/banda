import time
import subprocess
import platform
import shutil
import os
import glob
from pathlib import Path

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

_SYSTEM = platform.system()

_APP_ALIASES: dict[str, dict[str, str]] = {

    "chrome":             {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "google chrome":      {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "firefox":            {"Windows": "firefox",                 "Darwin": "Firefox",              "Linux": "firefox"},
    "edge":               {"Windows": "msedge",                  "Darwin": "Microsoft Edge",       "Linux": "microsoft-edge"},
    "brave":              {"Windows": "brave",                   "Darwin": "Brave Browser",        "Linux": "brave-browser"},
    "safari":             {"Windows": "msedge",                  "Darwin": "Safari",               "Linux": "firefox"},
    "opera":              {"Windows": "opera",                   "Darwin": "Opera",                "Linux": "opera"},
    "whatsapp":           {"Windows": "WhatsApp",                "Darwin": "WhatsApp",             "Linux": "whatsapp"},
    "telegram":           {"Windows": "Telegram",                "Darwin": "Telegram",             "Linux": "telegram"},
    "discord":            {"Windows": "Discord",                 "Darwin": "Discord",              "Linux": "discord"},
    "slack":              {"Windows": "Slack",                   "Darwin": "Slack",                "Linux": "slack"},
    "zoom":               {"Windows": "Zoom",                    "Darwin": "zoom.us",              "Linux": "zoom"},
    "teams":              {"Windows": "msteams",                 "Darwin": "Microsoft Teams",      "Linux": "teams"},
    "skype":              {"Windows": "skype",                   "Darwin": "Skype",                "Linux": "skype"},
    "signal":             {"Windows": "signal",                  "Darwin": "Signal",               "Linux": "signal"},
    "spotify":            {"Windows": "Spotify",                 "Darwin": "Spotify",              "Linux": "spotify"},
    "vlc":                {"Windows": "vlc",                     "Darwin": "VLC",                  "Linux": "vlc"},
    "netflix":            {"Windows": "Netflix",                 "Darwin": "Netflix",              "Linux": "firefox"},
    "vscode":             {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "visual studio code": {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "code":               {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "terminal":           {"Windows": "wt",                      "Darwin": "Terminal",             "Linux": "x-terminal-emulator"},
    "cmd":                {"Windows": "cmd.exe",                 "Darwin": "Terminal",             "Linux": "bash"},
    "powershell":         {"Windows": "powershell.exe",          "Darwin": "Terminal",             "Linux": "bash"},
    "postman":            {"Windows": "Postman",                 "Darwin": "Postman",              "Linux": "postman"},
    "git":                {"Windows": "git-bash",                "Darwin": "Terminal",             "Linux": "bash"},
    "figma":              {"Windows": "Figma",                   "Darwin": "Figma",                "Linux": "figma"},
    "photoshop":          {"Windows": "Photoshop",               "Darwin": "Adobe Photoshop",      "Linux": "gimp"},
    "adobe photoshop":    {"Windows": "Photoshop",               "Darwin": "Adobe Photoshop",      "Linux": "gimp"},
    "illustrator":        {"Windows": "Illustrator",             "Darwin": "Adobe Illustrator",    "Linux": "inkscape"},
    "adobe illustrator":  {"Windows": "Illustrator",             "Darwin": "Adobe Illustrator",    "Linux": "inkscape"},
    "indesign":           {"Windows": "InDesign",                "Darwin": "Adobe InDesign",       "Linux": "scribus"},
    "adobe indesign":     {"Windows": "InDesign",                "Darwin": "Adobe InDesign",       "Linux": "scribus"},
    "premiere":           {"Windows": "Premiere",                "Darwin": "Adobe Premiere Pro",   "Linux": "kdenlive"},
    "adobe premiere":     {"Windows": "Premiere",                "Darwin": "Adobe Premiere Pro",   "Linux": "kdenlive"},
    "after effects":      {"Windows": "After Effects",           "Darwin": "Adobe After Effects",  "Linux": "natron"},
    "lightroom":          {"Windows": "Lightroom",               "Darwin": "Adobe Lightroom",      "Linux": "darktable"},
    "google input tools": {"Windows": "Google Input Tools",      "Darwin": "Google Input Tools",   "Linux": "ibus"},
    "sinhala keyboard":   {"Windows": "ms-settings:regionlanguage", "Darwin": "System Preferences", "Linux": "gnome-control-center"},
    "blender":            {"Windows": "blender",                 "Darwin": "Blender",              "Linux": "blender"},
    "word":               {"Windows": "winword",                 "Darwin": "Microsoft Word",       "Linux": "libreoffice --writer"},
    "excel":              {"Windows": "excel",                   "Darwin": "Microsoft Excel",      "Linux": "libreoffice --calc"},
    "powerpoint":         {"Windows": "powerpnt",                "Darwin": "Microsoft PowerPoint", "Linux": "libreoffice --impress"},
    "libreoffice":        {"Windows": "soffice",                 "Darwin": "LibreOffice",          "Linux": "libreoffice"},
    "notepad":            {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "textedit":           {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "explorer":           {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "file explorer":      {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "finder":             {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "task manager":       {"Windows": "taskmgr.exe",             "Darwin": "Activity Monitor",     "Linux": "gnome-system-monitor"},
    "settings":           {"Windows": "ms-settings:",            "Darwin": "System Preferences",   "Linux": "gnome-control-center"},
    "windows settings":   {"Windows": "ms-settings:",            "Darwin": "System Preferences",   "Linux": "gnome-control-center"},
    "devices":            {"Windows": "ms-settings:bluetooth",   "Darwin": "System Preferences",   "Linux": "gnome-control-center"},
    "bluetooth":          {"Windows": "ms-settings:bluetooth",   "Darwin": "System Preferences",   "Linux": "gnome-control-center"},
    "printers":           {"Windows": "ms-settings:printers",    "Darwin": "System Preferences",   "Linux": "gnome-control-center"},
    "display":            {"Windows": "ms-settings:display",     "Darwin": "System Preferences",   "Linux": "gnome-control-center"},
    "sound":              {"Windows": "ms-settings:sound",       "Darwin": "System Preferences",   "Linux": "gnome-control-center"},
    "network":            {"Windows": "ms-settings:network",     "Darwin": "System Preferences",   "Linux": "gnome-control-center"},
    "wifi":               {"Windows": "ms-settings:network-wifi","Darwin": "System Preferences",   "Linux": "gnome-control-center"},
    "calculator":         {"Windows": "calc.exe",                "Darwin": "Calculator",           "Linux": "gnome-calculator"},
    "paint":              {"Windows": "mspaint.exe",             "Darwin": "Preview",              "Linux": "gimp"},
    "instagram":          {"Windows": "Instagram",               "Darwin": "Instagram",            "Linux": "firefox"},
    "tiktok":             {"Windows": "TikTok",                  "Darwin": "TikTok",               "Linux": "firefox"},
    "notion":             {"Windows": "Notion",                  "Darwin": "Notion",               "Linux": "notion"},
    "obsidian":           {"Windows": "Obsidian",                "Darwin": "Obsidian",             "Linux": "obsidian"},
    "capcut":             {"Windows": "CapCut",                  "Darwin": "CapCut",               "Linux": "capcut"},
    "steam":              {"Windows": "steam",                   "Darwin": "Steam",                "Linux": "steam"},
    "epic":               {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
    "epic games":         {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
}

_PROCESS_MAP: dict[str, list[str]] = {
    "photoshop": ["photoshop.exe"],
    "adobe photoshop": ["photoshop.exe"],
    "illustrator": ["illustrator.exe"],
    "adobe illustrator": ["illustrator.exe"],
    "indesign": ["indesign.exe"],
    "premiere": ["premiere.exe"],
    "after effects": ["afterfx.exe"],
    "chrome": ["chrome.exe"],
    "google chrome": ["chrome.exe"],
    "edge": ["msedge.exe"],
    "firefox": ["firefox.exe"],
    "brave": ["brave.exe"],
    "vscode": ["code.exe"],
    "code": ["code.exe"],
    "visual studio code": ["code.exe"],
    "notepad": ["notepad.exe"],
    "calculator": ["calculatorapp.exe", "calc.exe"],
    "word": ["winword.exe"],
    "excel": ["excel.exe"],
    "powerpoint": ["powerpnt.exe"],
    "spotify": ["spotify.exe"],
    "discord": ["discord.exe"],
    "telegram": ["telegram.exe"],
    "whatsapp": ["whatsapp.exe"],
    "vlc": ["vlc.exe"],
    "blender": ["blender.exe"],
    "figma": ["figma.exe"],
    "steam": ["steam.exe"],
}


def _normalize(raw: str) -> str:
    key = raw.lower().strip()

    if key in _APP_ALIASES:
        return _APP_ALIASES[key].get(_SYSTEM, raw)

    for alias_key, os_map in _APP_ALIASES.items():
        if alias_key in key or key in alias_key:
            return os_map.get(_SYSTEM, raw)

    return raw


def _is_app_running(app_name: str) -> bool:
    if not _PSUTIL:
        return False
    clean = app_name.lower().strip()
    norm = _normalize(clean).lower().strip()
    targets = set(_PROCESS_MAP.get(clean, []) + _PROCESS_MAP.get(norm, []))
    if not clean.endswith(".exe"):
        targets.add(f"{clean}.exe")
    targets_lower = {t.lower() for t in targets}

    try:
        for p in psutil.process_iter(['name']):
            pname = (p.info.get('name') or "").lower()
            if not pname:
                continue
            if pname in targets_lower or any(t.replace(".exe", "") in pname for t in targets_lower if len(t) > 3):
                return True
    except Exception:
        pass
    return False


def _focus_existing_app(title_or_name: str) -> bool:
    if _SYSTEM == "Windows":
        try:
            import win32gui, win32con
            found_hwnd = None
            def enum_cb(h, _):
                nonlocal found_hwnd
                if win32gui.IsWindowVisible(h):
                    txt = win32gui.GetWindowText(h)
                    if title_or_name.lower() in txt.lower():
                        found_hwnd = h
                        return False
                return True
            win32gui.EnumWindows(enum_cb, None)
            if found_hwnd:
                win32gui.ShowWindow(found_hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(found_hwnd)
                time.sleep(0.3)
                return True
        except Exception:
            pass

        try:
            script = f'(New-Object -ComObject WScript.Shell).AppActivate("{title_or_name}")'
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if _SYSTEM == "Windows" else 0
            )
            time.sleep(0.3)
            return "True" in res.stdout
        except Exception:
            pass
    elif _SYSTEM == "Darwin":
        try:
            script = f'tell application "{title_or_name}" to activate'
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
            return True
        except Exception:
            pass
    return False


def _find_windows_app_path(app_name: str) -> str | None:
    exe = shutil.which(app_name) or shutil.which(f"{app_name}.exe")
    if exe:
        return exe

    clean = app_name.lower().strip()

    # 1. Check Windows Registry App Paths (Official Windows App Paths)
    try:
        import winreg
        candidates = [clean, f"{clean}.exe"]
        for cand in candidates:
            for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{cand}") as k:
                        val = winreg.QueryValue(k, None)
                        if val:
                            p = val.strip('"\t ')
                            if os.path.exists(p):
                                return p
                except Exception:
                    pass
    except Exception:
        pass

    adobe_root = Path("C:/Program Files/Adobe")
    if adobe_root.exists():
        if "photoshop" in clean:
            matches = list(adobe_root.glob("Adobe Photoshop*/**/Photoshop.exe"))
            if matches:
                return str(matches[0])
        if "illustrator" in clean:
            matches = list(adobe_root.glob("Adobe Illustrator*/**/Illustrator.exe"))
            if matches:
                return str(matches[0])
        if "indesign" in clean:
            matches = list(adobe_root.glob("Adobe InDesign*/**/InDesign.exe"))
            if matches:
                return str(matches[0])
        if "audition" in clean:
            matches = list(adobe_root.glob("Adobe Audition*/**/Adobe Audition.exe"))
            if matches:
                return str(matches[0])
        if "premiere" in clean:
            matches = list(adobe_root.glob("Adobe Premiere*/**/Adobe Premiere Pro.exe"))
            if matches:
                return str(matches[0])

    start_dirs = [
        Path(os.environ.get("ProgramData", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    ]
    for sdir in start_dirs:
        if sdir.exists():
            for lnk in sdir.rglob("*.lnk"):
                if clean in lnk.stem.lower():
                    return str(lnk)
    return None


def _launch_windows(app_name: str) -> bool:
    # 0. Protocol or URI (e.g. ms-settings:, https://, etc.)
    if ":" in app_name:
        try:
            if hasattr(os, "startfile"):
                os.startfile(app_name)
                return True
        except Exception:
            pass
        try:
            subprocess.Popen(f'start "" "{app_name}"', shell=True)
            return True
        except Exception:
            pass

    # 1. Registered App Paths or installed path
    target_path = _find_windows_app_path(app_name)
    if target_path:
        try:
            print(f"[open_app] Found installed path: {target_path}")
            if hasattr(os, "startfile"):
                os.startfile(target_path)
            else:
                subprocess.Popen(f'start "" "{target_path}"', shell=True)
            return True
        except Exception as e:
            print(f"[open_app] Launch via found path failed: {e}")

    # 2. Direct which or exact executable path
    if shutil.which(app_name) or shutil.which(app_name.split(".")[0]):
        try:
            subprocess.Popen(
                app_name,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception as e:
            print(f"[open_app] subprocess failed: {e}")

    # 3. Direct Windows 'start' for registered executables
    try:
        subprocess.Popen(f'start "" "{app_name}"', shell=True)
        return True
    except Exception:
        pass

    # 4. Fallback to Start Menu search ONLY if not found above
    try:
        import pyautogui
        pyautogui.PAUSE = 0.05
        pyautogui.press("win")
        time.sleep(0.4)
        pyautogui.write(app_name, interval=0.03)
        time.sleep(0.5)
        pyautogui.press("enter")
        return True
    except Exception as e:
        print(f"[open_app] Start Menu search failed: {e}")

    return False


def _launch_macos(app_name: str) -> bool:

    try:
        result = subprocess.run(
            ["open", "-a", app_name],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["open", "-a", f"{app_name}.app"],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    binary = shutil.which(app_name) or shutil.which(app_name.lower())
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            return True
        except Exception:
            pass

    try:
        import pyautogui
        pyautogui.hotkey("command", "space")
        time.sleep(0.6)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(0.8)
        pyautogui.press("enter")
        time.sleep(1.5)
        return True
    except Exception as e:
        print(f"[open_app] Spotlight failed: {e}")

    return False


_LINUX_TERMINAL_FALLBACKS = [
    "x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal",
    "xterm", "lxterminal", "mate-terminal", "tilix", "alacritty", "kitty",
]

def _launch_linux(app_name: str) -> bool:

    # terminal emulators: try common ones in order
    if app_name in ("x-terminal-emulator", "gnome-terminal", "terminal"):
        for term in _LINUX_TERMINAL_FALLBACKS:
            if shutil.which(term):
                try:
                    subprocess.Popen([term], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    time.sleep(1.0)
                    return True
                except Exception:
                    continue

    binary = (
        shutil.which(app_name) or
        shutil.which(app_name.lower()) or
        shutil.which(app_name.lower().replace(" ", "-")) or
        shutil.which(app_name.lower().replace(" ", "_"))
    )
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            return True
        except Exception:
            pass

    try:
        subprocess.run(
            ["xdg-open", app_name],
            capture_output=True, timeout=5
        )
        return True
    except Exception:
        pass

    for desktop_name in [
        app_name.lower(),
        app_name.lower().replace(" ", "-"),
        app_name.lower().replace(" ", ""),
    ]:
        try:
            result = subprocess.run(
                ["gtk-launch", desktop_name],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass

    return False


_OS_LAUNCHERS = {
    "Windows": _launch_windows,
    "Darwin":  _launch_macos,
    "Linux":   _launch_linux,
}

def open_app(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    app_name = (parameters or {}).get("app_name", "").strip()

    if not app_name:
        return "No application name provided."

    normalized = _normalize(app_name)


    launcher = _OS_LAUNCHERS.get(_SYSTEM)
    if launcher is None:
        return f"Unsupported operating system: {_SYSTEM}"

    print(f"[open_app] Launching: '{app_name}' → '{normalized}' ({_SYSTEM})")

    if player:
        player.write_log(f"[open_app] {app_name}")

    try:
        success = launcher(normalized)
        if not success and normalized.lower() != app_name.lower():
            success = launcher(app_name)

        if success:
            return f"Successfully opened {app_name}."
        return (
            f"Could not open {app_name}. The application did not start, "
            f"or it might not be installed on this computer."
        )
    except Exception as e:
        print(f"[open_app] Error: {e}")
        return f"Failed to open {app_name}: {e}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "open_app",
    "description": "Opens any application on the computer. Use this whenever the user asks to open, launch, or start any app, website, or program. Always call this tool — never just say you opened it.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "app_name": {
                "type": "STRING",
                "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
            }
        },
        "required": [
            "app_name"
        ]
    },
    "handler": open_app,
}
