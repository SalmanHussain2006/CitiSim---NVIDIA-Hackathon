import base64
import os
from dataclasses import dataclass

import requests
from dotenv import load_dotenv


load_dotenv()


ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "ABCDEFGXYZ")
ELEVENLABS_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"
ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
DEFAULT_STT_MODEL = os.getenv("ELEVENLABS_STT_MODEL", "scribe_v1")
DEFAULT_TTS_MODEL = os.getenv("ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2")


class VoiceAgentError(RuntimeError):
    pass


@dataclass
class VoiceResponse:
    text: str
    audio_base64: str = ""
    content_type: str = "audio/mpeg"
    warning: str = ""


def _headers():
    return {"xi-api-key": ELEVENLABS_API_KEY}


def transcribe_audio(audio_bytes, filename="voice.webm", content_type="audio/webm"):
    if not audio_bytes:
        raise VoiceAgentError("No audio was received.")

    files = {
        "file": (filename, audio_bytes, content_type or "application/octet-stream"),
    }
    data = {
        "model_id": DEFAULT_STT_MODEL,
    }

    try:
        response = requests.post(
            ELEVENLABS_STT_URL,
            headers=_headers(),
            data=data,
            files=files,
            timeout=45,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        raise VoiceAgentError(f"ElevenLabs speech-to-text failed: {error}") from error

    payload = response.json()
    transcript = payload.get("text") or payload.get("transcript") or ""
    transcript = transcript.strip()

    if not transcript:
        raise VoiceAgentError("ElevenLabs returned an empty transcript.")

    return transcript


def synthesize_speech(text, voice_id=DEFAULT_VOICE_ID):
    clean_text = " ".join(str(text or "").split())
    if not clean_text:
        raise VoiceAgentError("No response text was provided for speech.")

    payload = {
        "text": clean_text[:4500],
        "model_id": DEFAULT_TTS_MODEL,
        "voice_settings": {
            "stability": 0.45,
            "similarity_boost": 0.78,
            "style": 0.12,
            "use_speaker_boost": True,
        },
    }

    try:
        response = requests.post(
            ELEVENLABS_TTS_URL.format(voice_id=voice_id),
            headers={**_headers(), "Accept": "audio/mpeg"},
            json=payload,
            timeout=45,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        raise VoiceAgentError(f"ElevenLabs text-to-speech failed: {error}") from error

    return VoiceResponse(
        text=clean_text,
        audio_base64=base64.b64encode(response.content).decode("ascii"),
        content_type=response.headers.get("content-type", "audio/mpeg").split(";", 1)[0],
    )


def recommendation_script(simulation):
    location = simulation.get("location", "the selected area")
    summary = simulation.get("summary", "")
    recommendations = simulation.get("recommendations", [])[:3]

    actions = []
    for item in recommendations:
        if isinstance(item, str):
            actions.append(item)
        else:
            title = item.get("title") or "Recommended action"
            action = item.get("action") or ""
            actions.append(f"{title}. {action}".strip())

    action_text = " ".join(actions)
    return (
        f"Simulation complete for {location}. {summary} "
        f"Recommended response: {action_text}"
    ).strip()
