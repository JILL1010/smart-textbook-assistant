import json
from pathlib import Path

import edge_tts

VOICE = "zh-CN-XiaoxiaoNeural"

TICK_RATE = 10_000_000


async def generate_audio(text: str, output_path: str) -> tuple[str, list[dict]]:
    """Use one stream; edge-tts handles splitting and audio-based time offsets."""
    audio = Path(output_path)
    audio.parent.mkdir(parents=True, exist_ok=True)
    subtitle_file = audio.with_suffix(".json")
    audio_temp = audio.with_suffix(".mp3.tmp")
    subtitle_temp = subtitle_file.with_suffix(".json.tmp")
    subtitles = []
    audio_bytes = 0
    try:
        communicate = edge_tts.Communicate(text, VOICE, boundary="SentenceBoundary")
        with audio_temp.open("wb") as stream:
            async for message in communicate.stream():
                if message["type"] == "audio":
                    stream.write(message["data"])
                    audio_bytes += len(message["data"])
                elif message["type"] == "SentenceBoundary":
                    subtitles.append({
                        "start": message["offset"] / TICK_RATE,
                        "end": (message["offset"] + message["duration"]) / TICK_RATE,
                        "text": message["text"].strip(),
                    })
        if not audio_bytes or not subtitles:
            raise RuntimeError("配音服务未返回完整的音频和字幕，请重试")
        subtitle_temp.write_text(json.dumps(subtitles, ensure_ascii=False), encoding="utf-8")
        audio_temp.replace(audio)
        subtitle_temp.replace(subtitle_file)
    except Exception:
        for path in (audio_temp, subtitle_temp, audio, subtitle_file):
            path.unlink(missing_ok=True)
        raise
    return output_path, subtitles
