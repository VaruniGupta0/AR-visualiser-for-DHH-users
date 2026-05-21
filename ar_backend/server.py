from flask import Flask, request, jsonify
from flask_cors import CORS
from vosk import Model, KaldiRecognizer
from faster_whisper import WhisperModel
import noisereduce as nr
import numpy as np
import wave, tempfile, os, subprocess, json

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
CORS(app)

# ── Load models once at startup ──────────────────────────────
print("Loading Vosk model...")
vosk_model = Model("vosk-model-small-en-in-0.4")
print("Loading Whisper model...")
whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
print("All models loaded. Server ready.")

# ── Keywords & mode ───────────────────────────────────────────
current_keywords = []
current_mode = "none"
current_direction = "front" # This acts as our "Sticky Memory"

def is_webm(data):
    return len(data) > 4 and data[:4] == bytes([0x1A, 0x45, 0xDF, 0xA3])

def webm_to_pcm(audio_bytes):
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(audio_bytes)
        in_path = f.name
    out_path = in_path.replace(".webm", ".wav")
    subprocess.run([
        "ffmpeg", "-y", "-i", in_path,
        "-ar", "16000", "-ac", "1", "-f", "wav", out_path
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with open(out_path, "rb") as f:
        wav_bytes = f.read()
    os.unlink(in_path)
    os.unlink(out_path)
    return wav_bytes[44:]

def denoise(pcm_bytes, sr=16000):
    try:
        audio_np = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
        if len(audio_np) == 0:
            return pcm_bytes
        reduced = nr.reduce_noise(y=audio_np, sr=sr, stationary=False)
        return reduced.astype(np.int16).tobytes()
    except Exception as e:
        print(f"Denoise skipped: {e}")
        return pcm_bytes

def check_keywords(text):
    text_lower = text.lower()
    for kw in current_keywords:
        if kw.lower() in text_lower:
            return True, kw
    return False, None

def pcm_to_wav_file(pcm_bytes):
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    with wave.open(tmp.name, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(pcm_bytes)
    return tmp.name

@app.route("/")
def home():
    return "Server is running!"

@app.route("/set_config", methods=["POST"])
def set_config():
    global current_keywords, current_mode, current_direction
    data = request.json
    current_mode = data.get("mode", "none")
    current_keywords = data.get("keywords", [])
    current_direction = data.get("direction", "front")
    print(f"Config updated - Mode: {current_mode} | Dir: {current_direction} | Keywords: {current_keywords}")
    return jsonify({"status": "ok", "mode": current_mode, "direction": current_direction, "keywords": current_keywords})

@app.route("/transcribe", methods=["POST"])
def transcribe():
    global current_direction # Pull in our sticky memory variable
    
    audio_data = request.get_data()

    if not audio_data or len(audio_data) < 100:
        return jsonify({
            "text": "", "is_priority": False,
            "matched_keyword": "", "mode": current_mode,
            "source_direction": current_direction
        })

    if is_webm(audio_data):
        try:
            pcm_bytes = webm_to_pcm(audio_data)
        except Exception as e:
            return jsonify({"error": "Audio conversion failed"}), 400
    else:
        pcm_bytes = audio_data

    pcm_bytes = denoise(pcm_bytes)

    vosk_text = ""
    try:
        rec = KaldiRecognizer(vosk_model, 16000)
        rec.AcceptWaveform(pcm_bytes)
        result = json.loads(rec.FinalResult())
        vosk_text = result.get("text", "").strip()
    except Exception as e:
        pass

    final_text = vosk_text
    is_priority = False
    matched_keyword = None

    if vosk_text:
        is_priority, matched_keyword = check_keywords(vosk_text)

    if is_priority or not vosk_text:
        try:
            wav_path = pcm_to_wav_file(pcm_bytes)
            segments, _ = whisper_model.transcribe(
                wav_path, language="en", beam_size=5, condition_on_previous_text=False
            )
            whisper_text = " ".join([s.text for s in segments]).strip()
            os.unlink(wav_path)
            if whisper_text:
                final_text = whisper_text
                is_priority, matched_keyword = check_keywords(whisper_text)
        except Exception as e:
            pass

    # --- FIX 1: The Ghost Filter ---
    # Ignore Whisper hallucinating words when the room is silent
    ghost_phrases = ["you", "you.", "thank you", "thank you.", "okay", "okay.", "yeah", "yeah."]
    if final_text.strip().lower() in ghost_phrases:
        final_text = ""

    # --- FIX 2: Sticky Memory Logic ---
    text_lower = final_text.lower()
    
    # Only update the direction if a new command is explicitly spoken
    if "left" in text_lower:
        current_direction = "left"
    elif "right" in text_lower:
        current_direction = "right"
    elif "back" in text_lower or "behind" in text_lower:
        current_direction = "back"
    elif "front" in text_lower or "straight" in text_lower:
        current_direction = "front"

    if final_text:
        print(f"Final output - Text: '{final_text}' | Dir: {current_direction} | Priority: {is_priority}")

    return jsonify({
        "text": final_text,
        "is_priority": is_priority,
        "matched_keyword": matched_keyword if matched_keyword else "",
        "mode": current_mode,
        "source_direction": current_direction
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)