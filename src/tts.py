import os
import subprocess
import tempfile

import azure.cognitiveservices.speech as speechsdk

VOICE = "ur-PK-AsadNeural"  # Urdu (Pakistan) male neural voice; ur-PK-UzmaNeural is the female alternative


class Speaker:
    def __init__(self, api_key: str | None = None, region: str | None = None):
        self.speech_config = speechsdk.SpeechConfig(
            subscription=api_key or os.environ["AZURE_SPEECH_KEY"],
            region=region or os.environ["AZURE_SPEECH_REGION"],
        )
        self.speech_config.speech_synthesis_voice_name = VOICE

    def say(self, text: str):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            out_path = f.name

        audio_config = speechsdk.audio.AudioOutputConfig(filename=out_path)
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=self.speech_config, audio_config=audio_config
        )
        result = synthesizer.speak_text_async(text).get()

        if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
            details = result.cancellation_details
            raise RuntimeError(f"TTS failed: {details.reason} - {details.error_details}")

        subprocess.run(["aplay", "-q", out_path], check=True)
        os.unlink(out_path)
