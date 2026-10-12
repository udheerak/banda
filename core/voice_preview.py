"""Voice preview for the Customize overlay: hear a Live voice before applying it.

The sample is synthesised with the SAME prebuilt voice name the Live session
would use — so what you hear is what you get. Edge/Kokoro/ElevenLabs voices
are deliberately NOT used here: they are different voices entirely and
previewing with one would be a lie.

The preview NEVER touches the conversation: it is a separate throwaway call,
and the voice list adds zero tokens to the assistant's prompt. Each voice is
synthesised once ever and then kept in a disk cache, so re-playing is instant
and costs no second call. If the text quota pool is dry, synthesis falls back
to a throwaway Live session (a separate quota pool) instead of failing.
Playback goes through the saved output device, like the assistant's replies.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import re
import threading
from pathlib import Path

TTS_MODEL = "gemini-2.5-flash-preview-tts"
DEFAULT_RATE = 24000

_cache: dict[tuple[str, str], tuple[bytes, int]] = {}
_cache_lock = threading.Lock()

_state_lock = threading.Lock()
_playing = False
_cancelled = False


class _QuotaError(RuntimeError):
    """The text quota pool is dry — the caller should try the Live pool."""


def preview_text(assistant_name: str) -> str:
    """The line that is spoken. Short on purpose — a preview must arrive fast."""
    name = (assistant_name or "").strip() or "Banda V3"
    return f"Hi! I'm {name}. This is how my new voice sounds. Do you like it?"


def _extract_rate(mime: str) -> int | None:
    try:
        m = re.search(r"rate=(\d+)", mime or "")
        if m:
            return max(8000, min(48000, int(m.group(1))))
    except (TypeError, ValueError):
        pass
    return None


def _parse_rate(mime: str) -> int:
    return _extract_rate(mime) or DEFAULT_RATE


def _cache_dir() -> Path:
    from memory.config_manager import CONFIG_DIR
    return CONFIG_DIR / "voice_cache"


def _cache_tag(voice: str, text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:10] + f"_{voice}"


def _disk_load(voice: str, text: str) -> tuple[bytes, int] | None:
    """A preview synthesised on any earlier run — instant, zero quota."""
    try:
        tag = _cache_tag(voice, text)
        for p in _cache_dir().glob(f"{tag}_*.pcm"):
            try:
                rate = int(p.stem.rsplit("_", 1)[1])
            except (ValueError, IndexError):
                continue
            data = p.read_bytes()
            if len(data) >= 2:
                return data, rate
    except Exception:
        pass
    return None


def _disk_save(voice: str, text: str, pcm: bytes, rate: int) -> None:
    try:
        d = _cache_dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{_cache_tag(voice, text)}_{rate}.pcm").write_bytes(pcm)
    except Exception:
        pass


def _store(voice: str, text: str, pcm: bytes, rate: int) -> tuple[bytes, int]:
    with _cache_lock:
        _cache[(voice, text)] = (pcm, rate)
    _disk_save(voice, text, pcm, rate)
    return pcm, rate


def synthesize(voice: str, assistant_name: str = "Banda V3",
               timeout_s: int = 30, on_stage=None) -> tuple[bytes, int]:
    """Return (pcm_bytes, sample_rate) of 16-bit mono PCM for `voice`.

    RAM cache → disk cache → REST TTS → throwaway Live session. `on_stage`
    gets short progress lines (safe to pass a Qt signal emit). Raises
    RuntimeError with a short, UI-safe message when everything is dry.
    """
    from memory.config_manager import AVAILABLE_VOICES, load_api_keys

    voice = (voice or "").strip()
    if voice not in AVAILABLE_VOICES:
        raise RuntimeError(f"unknown voice '{voice}'")
    text = preview_text(assistant_name)
    key = (voice, text)

    with _cache_lock:
        if key in _cache:
            return _cache[key]
    hit = _disk_load(voice, text)
    if hit is not None:
        with _cache_lock:
            _cache[key] = hit
        return hit

    api_key = ""
    try:
        api_key = str((load_api_keys().get("gemini_api_key") or ""))
    except Exception:
        api_key = ""
    if not api_key:
        raise RuntimeError("no Gemini API key is configured")

    def _stage(msg: str) -> None:
        try:
            if on_stage is not None:
                on_stage(msg)
        except Exception:
            pass

    _stage(f"preparing {voice}…")
    try:
        return _store(voice, text, *_synthesize_rest(voice, text, api_key, timeout_s))
    except _QuotaError:
        _stage("text quota is dry — trying the live voice pool…")
    try:
        return _store(voice, text, *_synthesize_live(voice, text, api_key, timeout_s))
    except _QuotaError:
        raise RuntimeError("both voice pools are dry — try again in a minute")
    except Exception as e:
        raise RuntimeError(_short_error(e))


def _synthesize_rest(voice: str, text: str, api_key: str,
                     timeout_s: int) -> tuple[bytes, int]:
    """One short REST TTS call. Raises _QuotaError when the pool is dry."""
    from core.gemini import is_quota_error
    from google import genai
    from google.genai import types

    try:
        cl = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=max(10_000, timeout_s * 1000)),
        )
        resp = cl.models.generate_content(
            model=TTS_MODEL,
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice
                        )
                    )
                ),
            ),
        )
    except Exception as e:
        if is_quota_error(str(e)):
            raise _QuotaError(str(e))
        raise RuntimeError(_short_error(e))

    for cand in getattr(resp, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", None) or []:
            blob = getattr(part, "inline_data", None)
            data = getattr(blob, "data", None) if blob is not None else None
            if not data:
                continue
            if isinstance(data, str):
                try:
                    data = base64.b64decode(data)
                except Exception:
                    continue
            pcm = bytes(data)
            if len(pcm) < 2:
                continue
            return pcm, _parse_rate(getattr(blob, "mime_type", "") or "")
    raise RuntimeError("the preview came back empty — try again")


async def _live_synth_async(voice: str, text: str, api_key: str,
                            timeout_s: int) -> tuple[bytes, int]:
    """Throwaway Live session that speaks one line — the separate quota pool.

    Never touches the conversation session: its own client, its own session,
    audio bytes collected here, nothing played or heard by the assistant.
    """
    from google import genai
    from google.genai import types
    from core.gemini import _live_model

    cl = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
    cfg = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=(
            "You are a voice-test function, not an assistant. There is no "
            "person listening. Say exactly the sentence the user gives you — "
            "no greeting, no extra words, no explanation."),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))),
    )
    cm = cl.aio.live.connect(model=_live_model(), config=cfg)
    session = await asyncio.wait_for(cm.__aenter__(), 30)
    try:
        await session.send_client_content(
            turns={"role": "user",
                   "parts": [{"text": f"Say exactly this sentence: {text}"}]},
            turn_complete=True)
        chunks: list[bytes] = []
        rate = DEFAULT_RATE

        async def drain():
            nonlocal rate
            async for resp in session.receive():
                sc = getattr(resp, "server_content", None)
                if sc is None:
                    continue
                turn = getattr(sc, "model_turn", None)
                if turn is not None:
                    for part in getattr(turn, "parts", None) or []:
                        blob = getattr(part, "inline_data", None)
                        data = (getattr(blob, "data", None)
                                if blob is not None else None)
                        if not data:
                            continue
                        if isinstance(data, str):
                            try:
                                data = base64.b64decode(data)
                            except Exception:
                                continue
                        if len(bytes(data)) >= 2:
                            chunks.append(bytes(data))
                            r = _extract_rate(getattr(blob, "mime_type", "") or "")
                            if r is not None:
                                rate = r
                if getattr(sc, "turn_complete", False):
                    break

        await asyncio.wait_for(drain(), timeout=timeout_s)
        if not chunks:
            raise RuntimeError("the preview came back empty — try again")
        return b"".join(chunks), rate
    finally:
        try:
            await cm.__aexit__(None, None, None)
        except Exception:
            pass


def _synthesize_live(voice: str, text: str, api_key: str,
                     timeout_s: int) -> tuple[bytes, int]:
    """The Live-pool fallback on its own thread/loop (never the Qt thread,
    never the conversation's loop). Yields to the conversation for a slot —
    a preview must not steal the session the user is talking on."""
    from core.gemini import _LIVE_SLOTS, _LIVE_SLOT_WAIT, is_quota_error

    if not _LIVE_SLOTS.acquire(timeout=_LIVE_SLOT_WAIT):
        raise RuntimeError("the conversation is busy — try the preview in a moment")
    box: dict = {}

    def runner():
        try:
            box["out"] = asyncio.run(
                _live_synth_async(voice, text, api_key, timeout_s))
        except BaseException as e:                     # noqa: BLE001
            box["error"] = e

    try:
        th = threading.Thread(target=runner, daemon=True, name="voice-preview-live")
        th.start()
        th.join(timeout=timeout_s + 20.0)
    finally:
        _LIVE_SLOTS.release()
    if "error" in box:
        err = box["error"]
        if is_quota_error(str(err)):
            raise _QuotaError(str(err))
        raise err if isinstance(err, Exception) else RuntimeError(str(err))
    if "out" not in box:
        raise RuntimeError("preview timed out — try again")
    return box["out"]


def _short_error(e: BaseException) -> str:
    msg = str(e) or type(e).__name__
    low = msg.lower()
    if "429" in msg or "resource_exhausted" in low:
        return "quota exhausted — try again in a minute"
    if "api key" in low or "401" in msg or "403" in msg:
        return "the API key was rejected"
    return msg[:110]


def is_playing() -> bool:
    with _state_lock:
        return _playing


def stop() -> None:
    """Stop playback now; a queued synth result will not start playing after."""
    global _cancelled
    with _state_lock:
        _cancelled = True
    try:
        import sounddevice as sd
        sd.stop()
    except Exception:
        pass


def play(pcm: bytes, rate: int) -> bool:
    """Play PCM through the saved output device. False when cancelled first."""
    global _playing, _cancelled
    with _state_lock:
        if _cancelled:
            _cancelled = False
            return False
        _playing = True
    try:
        import numpy as np
        import sounddevice as sd
        from core.audio_devices import resolve
        from memory.config_manager import get_output_device

        arr = np.frombuffer(pcm, dtype=np.int16)
        if arr.size == 0:
            return False
        try:
            dev = resolve(get_output_device(), "output")  # None = system default
        except Exception:
            dev = None
        if dev is None:
            sd.play(arr, rate)
        else:
            sd.play(arr, rate, device=dev)
        sd.wait()
        return True
    finally:
        with _state_lock:
            _playing = False
            _cancelled = False
