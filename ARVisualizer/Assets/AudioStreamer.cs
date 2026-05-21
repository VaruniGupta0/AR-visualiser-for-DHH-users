using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.Android;
using System.Collections;

public class AudioStreamer : MonoBehaviour {
    public SubtitleManager subtitleManager;
    public string serverUrl = "http://192.168.1.104:5000"; // ← YOUR IP

    private AudioClip micClip;
    private bool isRecording = false;
    private int sampleRate = 16000;
    private float chunkDuration = 2.5f;
    
    private int lastMicPos = 0; // Tracks our exact read position

    void Start() {
        if (!Permission.HasUserAuthorizedPermission(Permission.Microphone)) {
            Permission.RequestUserPermission(Permission.Microphone);
        }

        StartCoroutine(SetConfig());
        StartMic();
    }

    void StartMic() {
        // 300 seconds = 5 minutes. When it hits 5 mins, it loops back to 0.
        micClip = Microphone.Start(null, true, 300, sampleRate);
        isRecording = true;
        lastMicPos = 0;
        StartCoroutine(ChunkRoutine());
    }

    // Using a Coroutine for chunking is cleaner than Update()
    IEnumerator ChunkRoutine() {
        int samplesToRead = (int)(sampleRate * chunkDuration);

        while (isRecording) {
            yield return new WaitForSeconds(chunkDuration);

            int currentMicPos = Microphone.GetPosition(null);
            int diff = currentMicPos - lastMicPos;

            // Handle the 5-minute wrap-around
            if (diff < 0) {
                diff += micClip.samples; 
            }

            // Only send if we actually have enough data
            if (diff >= samplesToRead) {
                float[] floatData = new float[samplesToRead];

                // Safely read the data, even if it splits across the loop boundary
                if (lastMicPos + samplesToRead > micClip.samples) {
                    int endLength = micClip.samples - lastMicPos;
                    float[] endData = new float[endLength];
                    micClip.GetData(endData, lastMicPos);

                    int startLength = samplesToRead - endLength;
                    float[] startData = new float[startLength];
                    micClip.GetData(startData, 0);

                    endData.CopyTo(floatData, 0);
                    startData.CopyTo(floatData, endLength);
                } else {
                    micClip.GetData(floatData, lastMicPos);
                }

                lastMicPos = (lastMicPos + samplesToRead) % micClip.samples;

                byte[] pcmBytes = FloatToPCM16(floatData);
                StartCoroutine(SendAudioChunk(pcmBytes));
            }
        }
    }

    IEnumerator SendAudioChunk(byte[] pcmBytes) {
        UnityWebRequest req = new UnityWebRequest(serverUrl + "/transcribe", "POST");
        req.uploadHandler = new UploadHandlerRaw(pcmBytes);
        req.downloadHandler = new DownloadHandlerBuffer();
        req.SetRequestHeader("Content-Type", "application/octet-stream");

        yield return req.SendWebRequest();

        if (req.result == UnityWebRequest.Result.Success) {
            var resp = JsonUtility.FromJson<TranscriptResponse>(req.downloadHandler.text);

            if (resp != null && !string.IsNullOrEmpty(resp.text)) {
                // Pass the direction to the manager
                subtitleManager.ShowSubtitle(resp.text, resp.is_priority, resp.source_direction);
            }
        }
    }

    IEnumerator SetConfig() {
        string json = "{\"mode\":\"hospital\",\"keywords\":[\"token 42\",\"sharma\",\"announcement\"]}";

        UnityWebRequest req = new UnityWebRequest(serverUrl + "/set_config", "POST");
        byte[] bodyRaw = System.Text.Encoding.UTF8.GetBytes(json);

        req.uploadHandler = new UploadHandlerRaw(bodyRaw);
        req.downloadHandler = new DownloadHandlerBuffer();
        req.SetRequestHeader("Content-Type", "application/json");

        yield return req.SendWebRequest();
    }

    byte[] FloatToPCM16(float[] samples) {
        byte[] bytes = new byte[samples.Length * 2];
        for (int i = 0; i < samples.Length; i++) {
            short s = (short)(Mathf.Clamp(samples[i], -1f, 1f) * 32767);
            bytes[i * 2] = (byte)(s & 0xFF);
            bytes[i * 2 + 1] = (byte)((s >> 8) & 0xFF);
        }
        return bytes;
    }

    [System.Serializable]
    class TranscriptResponse {
        public string text;
        public bool is_priority;
        public string matched_keyword;
        public string mode;
        public string source_direction; // Capturing the spatial data
    }
}