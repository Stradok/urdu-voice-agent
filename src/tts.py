import os
import subprocess
import tempfile
from xml.sax.saxutils import escape

import azure.cognitiveservices.speech as speechsdk

from . import settings as app_settings

VOICE = "ur-PK-UzmaNeural"  # Urdu (Pakistan) female neural voice; ur-PK-AsadNeural is the male alternative

SSML_TEMPLATE = """<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="ur-PK">
    <voice name="{voice}">
        <prosody rate="{rate}">{text}</prosody>
    </voice>
</speak>"""


class Speaker:
    def __init__(self, api_key: str | None = None, region: str | None = None):
        self.speech_config = speechsdk.SpeechConfig(
            subscription=api_key or os.environ["AZURE_SPEECH_KEY"],
            region=region or os.environ["AZURE_SPEECH_REGION"],
        )
        self.speech_config.speech_synthesis_voice_name = VOICE

    def say(self, text: str):
        rate = f"+{app_settings.load_settings()['tts_rate_percent']}%"
        ssml = SSML_TEMPLATE.format(voice=VOICE, rate=rate, text=escape(text))

        last_error = None
        for attempt in range(2):  # RTF timeouts are usually transient system-load hiccups
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                out_path = f.name

            audio_config = speechsdk.audio.AudioOutputConfig(filename=out_path)
            synthesizer = speechsdk.SpeechSynthesizer(
                speech_config=self.speech_config, audio_config=audio_config
            )
            result = synthesizer.speak_ssml_async(ssml).get()

            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                subprocess.run(["aplay", "-q", out_path], check=True)
                os.unlink(out_path)
                return

            details = result.cancellation_details
            last_error = f"TTS failed: {details.reason} - {details.error_details}"
            os.unlink(out_path)

        raise RuntimeError(last_error)
