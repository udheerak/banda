import json
import sys
from pathlib import Path

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR    = get_base_dir()
CONFIG_DIR  = BASE_DIR / "config"
CONFIG_FILE = CONFIG_DIR / "api_keys.json"

def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def config_exists() -> bool:
    return CONFIG_FILE.exists()

def save_api_keys(gemini_api_key: str) -> None:
    ensure_config_dir()

    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    data["gemini_api_key"] = gemini_api_key.strip()

    CONFIG_FILE.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8"
    )

def load_api_keys() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ Failed to load api_keys.json: {e}")
        return {}

def get_gemini_key() -> str | None:
    return load_api_keys().get("gemini_api_key")

def is_configured() -> bool:
    key = get_gemini_key()
    return bool(key and len(key) > 15)


def get_assistant_name() -> str:
    """Return the configured assistant name, or 'BANDA V3' if not set."""
    return load_api_keys().get("assistant_name", "BANDA V3") or "BANDA V3"


def get_user_name() -> str:
    """Return the configured user name for addressing."""
    return load_api_keys().get("user_name", "")


def save_assistant_config(assistant_name: str, user_name: str) -> None:
    """Persist assistant name and user name to config."""
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["assistant_name"] = assistant_name.strip() or "BANDA V3"
    data["user_name"] = user_name.strip()
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


# ── Assistant voice ──────────────────────────────────────────────────────────
# Gemini Live prebuilt voices. Names are proper nouns — identical in every
# language, so this list is safe to show verbatim in any locale.
# These are the voices the Live API accepts (the TTS-only names are left out
# on purpose — a saved voice the server rejects would break every connect).
AVAILABLE_VOICES = [
    "Umbriel", "Despina", "Callirrhoe", "Aoede",
    "Enceladus", "Leda", "Autonoe", "Erinome",
    "Zephyr", "Puck", "Gacrux", "Iapetus",
    "Orus", "Charon", "Kore", "Fenrir",
]
# One-word character of each voice, shown as a tooltip in the picker so the
# choice is by ear, not by guessing from a name.
VOICE_HINTS = {
    "Umbriel":    "Easy-going · natural",
    "Despina":    "Smooth",
    "Callirrhoe": "Easy-going",
    "Aoede":      "Breezy",
    "Enceladus":  "Breathy",
    "Leda":       "Youthful",
    "Autonoe":    "Bright",
    "Erinome":    "Clear",
    "Zephyr":     "Bright",
    "Puck":       "Upbeat",
    "Gacrux":     "Mature",
    "Iapetus":    "Clear",
    "Orus":       "Firm",
    "Charon":     "Informative",
    "Kore":       "Firm",
    "Fenrir":     "Excitable",
}
# Presenting gender per Google's voice catalogue — drives the Female / Male
# sections of the picker, nothing else. The assistant never sees this.
VOICE_GENDER = {
    "Umbriel": "female", "Despina": "female", "Callirrhoe": "female",
    "Aoede": "female", "Leda": "female", "Autonoe": "female",
    "Erinome": "female", "Zephyr": "female", "Kore": "female",
    "Gacrux": "female",
    "Enceladus": "male", "Iapetus": "male", "Puck": "male",
    "Orus": "male", "Charon": "male", "Fenrir": "male",
}
DEFAULT_VOICE    = "Umbriel"


# ── Live / AI model selection ────────────────────────────────────────────────
# Models are shown in Settings → Model so the user can pick without editing files.
# Keys that are not Gemini Live still go through the Live connection path but can
# be toggled to non-Live endpoints once multi-provider support is wired up.
AVAILABLE_LIVE_MODELS = [
    # Gemini Live (default, native audio dialog)
    "models/gemini-2.5-flash-native-audio-latest",
    "models/gemini-2.5-flash-native-audio-preview-12-2025",
    "models/gemini-3.8-live",
    "models/gemini-3.1-flash-live-preview",
    # Gemini text (non-live, via chat API)
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
    # Groq (ultra-fast inference via Groq Cloud API)
    "groq:llama-3.3-70b-versatile",
    "groq:llama-3.1-8b-instant",
    "groq:mixtral-8x7b-32768",
    "groq:gemma2-9b-it",
]

LIVE_MODEL_LABELS = {
    "models/gemini-2.5-flash-native-audio-latest":          "Gemini 2.5 Flash Live ❖ recommended",
    "models/gemini-2.5-flash-native-audio-preview-12-2025": "Gemini 2.5 Flash Live (Dec 2025)",
    "models/gemini-3.8-live":                               "Gemini 3.8 Live",
    "models/gemini-3.1-flash-live-preview":                 "Gemini 3.1 Flash Live",
    "gemini-2.5-flash":                                     "Gemini 2.5 Flash  (text)",
    "gemini-2.0-flash":                                     "Gemini 2.0 Flash  (text)",
    "gemini-1.5-pro":                                       "Gemini 1.5 Pro  (text)",
    "gemini-1.5-flash":                                     "Gemini 1.5 Flash  (text)",
    # Groq
    "groq:llama-3.3-70b-versatile":  "Groq — Llama 3.3 70B  (fastest)",
    "groq:llama-3.1-8b-instant":     "Groq — Llama 3.1 8B  (ultra-fast)",
    "groq:mixtral-8x7b-32768":       "Groq — Mixtral 8x7B",
    "groq:gemma2-9b-it":             "Groq — Gemma 2 9B",
}

DEFAULT_LIVE_MODEL = "models/gemini-2.5-flash-native-audio-latest"


def get_live_model() -> str:
    """Return the user-selected Live model, falling back to the default."""
    v = load_api_keys().get("live_model", DEFAULT_LIVE_MODEL) or DEFAULT_LIVE_MODEL
    return v if v in AVAILABLE_LIVE_MODELS else DEFAULT_LIVE_MODEL


def save_live_model(model: str) -> None:
    """Persist the chosen Live model."""
    m = (model or "").strip()
    _save_flag("live_model", m if m in AVAILABLE_LIVE_MODELS else DEFAULT_LIVE_MODEL)


# ── Extra provider API keys ───────────────────────────────────────────────────
def get_openai_key() -> str:
    """OpenAI API key (sk-…) or '' if not configured."""
    return (load_api_keys().get("openai_api_key") or "").strip()


def save_openai_key(key: str) -> None:
    _save_flag("openai_api_key", (key or "").strip())


def get_anthropic_key() -> str:
    """Anthropic API key (sk-ant-…) or '' if not configured."""
    return (load_api_keys().get("anthropic_api_key") or "").strip()


def save_anthropic_key(key: str) -> None:
    _save_flag("anthropic_api_key", (key or "").strip())


def get_groq_key() -> str:
    """Groq Cloud API key (gsk_…) or '' if not configured."""
    return (load_api_keys().get("groq_api_key") or "").strip()


def save_groq_key(key: str) -> None:
    _save_flag("groq_api_key", (key or "").strip())


def get_voice() -> str:
    """Return the configured Live voice, falling back to the default if unset
    or if the stored value is not a voice we recognise."""
    v = load_api_keys().get("voice_name", DEFAULT_VOICE) or DEFAULT_VOICE
    return v if v in AVAILABLE_VOICES else DEFAULT_VOICE


def save_voice(voice_name: str) -> None:
    """Persist the chosen Live voice. Unknown names collapse to the default so a
    bad value can never reach the API and break the session."""
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    v = (voice_name or "").strip()
    data["voice_name"] = v if v in AVAILABLE_VOICES else DEFAULT_VOICE
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


def get_wake_word_enabled() -> bool:
    """Whether local wake-word gating is on (assistant sleeps until 'Hey Banda')."""
    return load_api_keys().get("wake_word_enabled", False)


def save_wake_word_enabled(enabled: bool) -> None:
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["wake_word_enabled"] = bool(enabled)
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


def get_push_to_talk_enabled() -> bool:
    """Hold-a-key-to-speak. When on, the mic is closed unless the chord is held."""
    return load_api_keys().get("push_to_talk_enabled", False)


def save_push_to_talk_enabled(enabled: bool) -> None:
    _save_flag("push_to_talk_enabled", enabled)


HUD_STYLES = ("face", "aria", "kael", "core")


def get_hud_style() -> str:
    """Which centrepiece the HUD draws: the hologram, a human face (Aria or
    Kael), or the reactor core.

    Taste, not capability — all render in the same software painter and cost
    about the same. Defaults to the hologram; anyone who prefers a human face
    or the older core can switch in the controls drawer and the choice
    survives a restart.
    """
    v = str(load_api_keys().get("hud_style", "face")).strip().lower()
    return v if v in HUD_STYLES else "face"


def save_hud_style(style: str) -> None:
    s = str(style or "").strip().lower()
    _save_flag("hud_style", s if s in HUD_STYLES else "face")


# ── Live-session tuning ──────────────────────────────────────────────────────
# Everything here is optional and has a working default, so an untouched
# config behaves exactly like a configured one. Each value is also a way out:
# if a future model dislikes one of these, set it back and nothing else changes.

def get_thinking_enabled() -> bool:
    """Whether the Live model may spend tokens thinking before it answers.

    Off by default. A voice assistant is judged on how fast it starts talking,
    and the reasoning that actually needs deliberation in this app is delegated
    to the planning tools, which run on a separate non-Live model.
    """
    return bool(load_api_keys().get("thinking_enabled", False))


def save_thinking_enabled(enabled: bool) -> None:
    _save_flag("thinking_enabled", enabled)


def get_turn_tuning() -> dict:
    """How eagerly the server decides you have stopped speaking.

    ON by default with a 400 ms pause: close to a human turn-taking gap, so
    replies start the moment you finish instead of a beat later. 400 ms is
    the middle ground — short enough to feel live, long enough that a breath
    mid-sentence does not cut your turn in half. If the assistant ever clips
    your sentences or answers a turn late, raise silence_ms toward 600-800
    (or set enabled false to return to the server default).

    Turn it off with "turn_tuning": {"enabled": false} if your microphone or
    speaking pace suits the cautious server default better.
    """
    cfg = load_api_keys().get("turn_tuning")
    cfg = cfg if isinstance(cfg, dict) else {}

    def _int(key, default, lo, hi):
        try:
            return max(lo, min(hi, int(cfg.get(key, default))))
        except (TypeError, ValueError):
            return default

    return {
        "enabled":    bool(cfg.get("enabled", True)),
        "silence_ms": _int("silence_ms", 400, 200, 3000),
        "prefix_ms":  _int("prefix_ms", 150, 0, 1000),
        # "high" = quicker to decide speech has ended.
        "end_sensitivity":   str(cfg.get("end_sensitivity", "high")).lower(),
        "start_sensitivity": str(cfg.get("start_sensitivity", "high")).lower(),
    }


def save_turn_tuning(values: dict) -> None:
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    cur = data.get("turn_tuning")
    cur = dict(cur) if isinstance(cur, dict) else {}
    cur.update(values or {})
    data["turn_tuning"] = cur
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


def get_proactive_audio_enabled() -> bool:
    """Whether the model gets to decide an utterance was not aimed at it and
    stay quiet.

    OFF by default — instant replies. With it off the server answers the
    moment a turn ends instead of deliberating over whether the speech was
    addressed to the assistant, which is the delay users feel most. The cost
    is that background chatter (TV, another conversation in the room) may get
    answered too. Turn it back on from the CONTROLS drawer if that happens.
    """
    return bool(load_api_keys().get("proactive_audio", False))


def save_proactive_audio_enabled(enabled: bool) -> None:
    _save_flag("proactive_audio", enabled)


def get_full_auto() -> bool:
    """Master switch: skip ALL approval gates (task-agent high-risk plans,
    shutdown/restart/wifi confirmation, home-directory file jail).

    OFF by default and that's deliberate — with it on, a spoken sentence can
    delete files, send messages, run shell commands or power the machine off
    with no further question. Turn it on from the CONTROLS drawer only when
    that is exactly what is wanted; turn it back off afterwards.
    """
    return bool(load_api_keys().get("full_auto", False))


def save_full_auto(enabled: bool) -> None:
    _save_flag("full_auto", enabled)


MEDIA_RESOLUTIONS = ("default", "low", "medium", "high")


def get_media_resolution() -> str:
    """How finely the model tokenises the screenshots and camera frames it is
    sent. 'medium' keeps on-screen text readable at a fraction of the tokens a
    full-resolution frame costs; 'low' is cheaper still but starts losing small
    text, which is most of what screen captures are for."""
    v = str(load_api_keys().get("media_resolution", "medium")).strip().lower()
    return v if v in MEDIA_RESOLUTIONS else "medium"


def save_media_resolution(value: str) -> None:
    v = str(value or "").strip().lower()
    _save_flag("media_resolution", v if v in MEDIA_RESOLUTIONS else "medium")


def _save_flag(key: str, value) -> None:
    """Read-modify-write one key without disturbing the rest of the config."""
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data[key] = bool(value) if isinstance(value, bool) else value
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


def get_brief_enabled() -> bool:
    return load_api_keys().get("morning_brief_enabled", True)


def save_brief_enabled(enabled: bool) -> None:
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["morning_brief_enabled"] = enabled
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


# ── Audio devices ────────────────────────────────────────────────────────────
# Stored as device NAMES, not sounddevice indices. Indices shift every time a
# USB device is plugged in or removed, so a saved index silently starts pointing
# at a different microphone. The empty string means "system default", which is
# both the factory setting and what an unresolvable saved device falls back to —
# so unplugging a headset degrades to the built-in speakers instead of crashing.

def _patch_config(**fields) -> None:
    """Read-modify-write one or more keys in api_keys.json.

    Every setter in this file open-coded this. Collapsing it here means a new
    setting is one line, and there is one place where a corrupt config file is
    handled instead of nine."""
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data.update(fields)
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


def get_input_device() -> str:
    """Microphone device name, or '' for the system default."""
    return (load_api_keys().get("input_device", "") or "").strip()


def save_input_device(name: str) -> None:
    _patch_config(input_device=(name or "").strip())


def get_output_device() -> str:
    """Speaker device name, or '' for the system default."""
    return (load_api_keys().get("output_device", "") or "").strip()


def save_output_device(name: str) -> None:
    _patch_config(output_device=(name or "").strip())


def get_plugin_enabled(plugin_name: str) -> bool:
    """Plugins are enabled by default the moment they're discovered (opt-out model)."""
    return load_api_keys().get("plugins_enabled", {}).get(plugin_name, True)


# ── Per-plugin settings ("tokens" / connection details) ───────────────────────
# Generic store so a plugin can declare its own config fields (PLUGIN_SETTINGS)
# and the settings UI renders + persists them WITHOUT any core edit — keeping the
# drop-in model intact. Values live under plugin_config[<namespace>][<key>].
# A namespace defaults to the plugin name, but a suite of plugins (e.g. the
# several printer plugins) can share ONE namespace.
def get_plugin_config(namespace: str) -> dict:
    """All stored values for a namespace (empty dict if none set yet)."""
    cfg = load_api_keys().get("plugin_config")
    val = cfg.get(namespace) if isinstance(cfg, dict) else None
    return dict(val) if isinstance(val, dict) else {}


def get_plugin_setting(namespace: str, key: str, default=None):
    """A single value from a namespace, or `default` if unset."""
    return get_plugin_config(namespace).get(key, default)


def save_plugin_config(namespace: str, values: dict) -> None:
    """Merge `values` into a namespace's stored config (read-modify-write, like
    every other helper here). Only the provided keys are touched."""
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    pc = data.get("plugin_config")
    if not isinstance(pc, dict):
        pc = {}
    cur = pc.get(namespace)
    if not isinstance(cur, dict):
        cur = {}
    cur.update(values)
    pc[namespace] = cur
    data["plugin_config"] = pc
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


def save_plugin_enabled(plugin_name: str, enabled: bool) -> None:
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    plugins_cfg = data.get("plugins_enabled")
    if not isinstance(plugins_cfg, dict):
        plugins_cfg = {}
    plugins_cfg[plugin_name] = enabled
    data["plugins_enabled"] = plugins_cfg
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")