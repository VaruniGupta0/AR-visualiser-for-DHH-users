import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel
import queue
import threading
import sys

# -------------------- SETTINGS --------------------
MODEL_SIZE = "base"   # try "small" for better accuracy (slower)
DEVICE = "cpu"        # use "cuda" if you have GPU
COMPUTE_TYPE = "int8"

SAMPLE_RATE = 16000
BLOCK_DURATION = 2.5   # higher = better accuracy, more delay

# --------------------------------------------------

print("⏳ Loading Whisper model...")
try:
    model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
except Exception as e:
    print("❌ Error loading model:", e)
    sys.exit(1)

print("✅ Whisper loaded successfully!\n")

q = queue.Queue()

# Audio callback
def callback(indata, frames, time, status):
    if status:
        print("⚠️ Mic issue:", status, file=sys.stderr)
    q.put(indata.copy())

# Transcription worker
def transcribe_worker():
    while True:
        audio_chunks = []

        # Collect audio chunks
        num_chunks = int(SAMPLE_RATE / 1024 * BLOCK_DURATION)
        for _ in range(num_chunks):
            audio_chunks.append(q.get())

        # Combine and convert audio
        audio_np = np.concatenate(audio_chunks, axis=0)
        audio_np = audio_np.flatten().astype(np.float32) / 32768.0

        # 🔥 TRANSCRIBE (FIXED SETTINGS)
        segments, _ = model.transcribe(
            audio_np,
            beam_size=5,
            language="en",                      # ✅ force English
            condition_on_previous_text=False    # ✅ avoid weird mixing
        )

        for segment in segments:
            text = segment.text.strip()
            if text:
                print("📝", text)

# Start worker thread
threading.Thread(target=transcribe_worker, daemon=True).start()

print("🎤 Listening with Whisper... (Ctrl+C to stop)\n")

# Start mic stream
try:
    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype='int16',
        blocksize=1024,
        callback=callback
        # device=1  # 👈 uncomment if mic not detected
    ):
        while True:
            pass

except KeyboardInterrupt:
    print("\n🛑 Stopped")

except Exception as e:
    print("❌ Error:", e)