using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.Networking;
using SocketIOClient;
using SocketIOClient.Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using System.Threading.Tasks;
using System.IO;

public class VoiceChatManager : MonoBehaviour
{
    [Header("Server Settings")]
    [SerializeField] private string serverUrl = "http://127.0.0.1:5000";

    [Header("Audio Settings")]
    [SerializeField] private int recordingSampleRate = 48000;
    [SerializeField] private int maxRecordingSeconds = 30;

    private SocketIOUnity socket;
    private AudioClip recordingClip;
    private bool isRecording = false;
    private bool isConnected = false;

    // private int recordingStartPosition = 0;
    private int lastProcessedPosition = 0;
    private List<float> accumulatedSamples = new List<float>();

    public static event Action<string> OnStatusUpdate;
    public static event Action<string> OnTranscriptReceived;
    public static event Action<string> OnAgentResponseReceived;
    public static event Action<AudioClip> OnAudioResponseReceived;

    private static VoiceChatManager _instance;
    public static VoiceChatManager Instance => _instance;

    void Awake()
    {
        if (_instance != null && _instance != this)
        {
            Destroy(gameObject);
            return;
        }
        _instance = this;
        DontDestroyOnLoad(gameObject);
    }

    IEnumerator Start()
    {
        yield return Application.RequestUserAuthorization(UserAuthorization.Microphone);

        if (Application.HasUserAuthorization(UserAuthorization.Microphone))
        {
            Debug.Log("Microphone permission granted");
            InitializeSocketIO();
        }
        else
        {
            Debug.LogError("Microphone permission denied");
            OnStatusUpdate?.Invoke("Microphone access denied. Please allow microphone permissions.");
        }
    }

    void Update()
    {
        if (isRecording && Microphone.IsRecording(null))
        {
            CaptureAudioData();
        }

        // Handle spacebar for push-to-talk
        if (Keyboard.current != null)
        {
            if (Keyboard.current.spaceKey.wasPressedThisFrame)
            {
                StartRecording();
            }
            else if (Keyboard.current.spaceKey.wasReleasedThisFrame)
            {
                StopRecording();
            }
        }
    }

    async void OnDestroy()
    {
        if (socket != null && socket.Connected)
        {
            await socket.DisconnectAsync();
        }
        socket?.Dispose();
    }

    private void InitializeSocketIO()
    {
        try
        {
            var uri = new Uri(serverUrl);
            socket = new SocketIOUnity(uri, new SocketIOClient.SocketIOOptions
            {
                EIO = EngineIO.V4,
                Transport = SocketIOClient.Transport.TransportProtocol.WebSocket
            });

            socket.JsonSerializer = new NewtonsoftJsonSerializer();

            socket.OnConnected += (sender, e) =>
            {
                isConnected = true;
                OnStatusUpdate?.Invoke("Connected to server");
                UnityEngine.Debug.Log("Socket.IO connected");
            };

            socket.OnDisconnected += (sender, e) =>
            {
                isConnected = false;
                OnStatusUpdate?.Invoke("Disconnected from server");
                UnityEngine.Debug.Log("Socket.IO disconnected: " + e);
            };

            socket.OnError += (sender, e) =>
            {
                OnStatusUpdate?.Invoke("Connection error");
                UnityEngine.Debug.LogError($"Socket.IO error: {e}");
            };

            socket.OnUnityThread("status", OnStatusMessage);
            socket.OnUnityThread("transcript", OnTranscriptMessage);
            socket.OnUnityThread("response_text", OnResponseTextMessage);
            socket.OnUnityThread("audio_ready", OnAudioReadyMessage);

            socket.Connect();
            OnStatusUpdate?.Invoke("Connecting to server...");
        }
        catch (Exception e)
        {
            UnityEngine.Debug.LogError($"Failed to initialize Socket.IO: {e.Message}");
            OnStatusUpdate?.Invoke("Failed to initialize connection");
        }
    }

    private void OnStatusMessage(SocketIOClient.SocketIOResponse response)
    {
        try
        {
            string jsonText = response.GetValue().GetRawText();
            var json = JObject.Parse(jsonText);
            string message = json["message"]?.Value<string>() ?? "Unknown status";
            OnStatusUpdate?.Invoke(message);
        }
        catch (Exception ex)
        {
            UnityEngine.Debug.LogError($"Error parsing status message: {ex.Message}");
        }
    }

    private void OnTranscriptMessage(SocketIOClient.SocketIOResponse response)
    {
        try
        {
            string jsonText = response.GetValue().GetRawText();
            var json = JObject.Parse(jsonText);
            string transcript = json["transcript"]?.Value<string>() ?? "Could not transcribe";
            OnTranscriptReceived?.Invoke(transcript);
            UnityEngine.Debug.Log("Transcript: " + transcript);
        }
        catch (Exception ex)
        {
            UnityEngine.Debug.LogError($"Error parsing transcript message: {ex.Message}");
        }
    }

    private void OnResponseTextMessage(SocketIOClient.SocketIOResponse response)
    {
        try
        {
            string jsonText = response.GetValue().GetRawText();
            var json = JObject.Parse(jsonText);
            string text = json["text"]?.Value<string>() ?? "No response text";
            OnAgentResponseReceived?.Invoke(text);
            UnityEngine.Debug.Log("Response text: " + text);
        }
        catch (Exception ex)
        {
            UnityEngine.Debug.LogError($"Error parsing response text: {ex.Message}");
        }
    }

    private void OnAudioReadyMessage(SocketIOClient.SocketIOResponse response)
    {
        try
        {
            string jsonText = response.GetValue().GetRawText();
            var json = JObject.Parse(jsonText);
            string audioUrl = json["audio_url"]?.Value<string>();

            if (!string.IsNullOrEmpty(audioUrl))
            {
                UnityEngine.Debug.Log("Audio ready: " + audioUrl);
                StartCoroutine(DownloadAndPlayAudio(audioUrl));
            }
        }
        catch (Exception ex)
        {
            UnityEngine.Debug.LogError($"Error parsing audio ready message: {ex.Message}");
        }
    }

    public void StartRecording()
    {
        if (!isConnected)
        {
            OnStatusUpdate?.Invoke("Not connected to server");
            return;
        }

        try
        {
            if (Microphone.devices.Length == 0)
            {
                OnStatusUpdate?.Invoke("No microphone found");
                return;
            }

            // Clear previous recording data
            accumulatedSamples.Clear();
            lastProcessedPosition = 0;

            // Start microphone with buffer
            recordingClip = Microphone.Start(null, true, maxRecordingSeconds, recordingSampleRate);
            // recordingStartPosition = 0;
            isRecording = true;

            var data = new { format = "wav" };
            socket.Emit("start_stream", data);

            OnStatusUpdate?.Invoke("Recording...");
            UnityEngine.Debug.Log($"Started recording at {recordingSampleRate}Hz (max {maxRecordingSeconds}s)");
        }
        catch (Exception e)
        {
            UnityEngine.Debug.LogError($"Failed to start recording: {e.Message}");
            OnStatusUpdate?.Invoke("Recording failed");
        }
    }

    public void StopRecording()
    {
        if (!isRecording) return;

        try
        {
            CaptureAudioData();
            isRecording = false;
            Microphone.End(null);
            float[] allSamples = accumulatedSamples.ToArray();

            if (allSamples.Length > 0)
            {
                // Calculate actual duration
                float duration = (float)allSamples.Length / recordingSampleRate;
                UnityEngine.Debug.Log(
                    $"Recording stopped. Captured {allSamples.Length} samples ({duration:F2}s) at {recordingSampleRate}Hz");

                // Create WAV file
                byte[] wavData = CreateWAVFile(allSamples, recordingSampleRate);

                if (wavData != null && wavData.Length > 0)
                {
                    UnityEngine.Debug.Log(
                        $"Created WAV: {wavData.Length} bytes (44 byte header + {allSamples.Length * 2} bytes PCM)");
                    string header = System.Text.Encoding.ASCII.GetString(wavData, 0, 4);
                    UnityEngine.Debug.Log(
                        $"WAV header: '{header}' (should be 'RIFF')");
                    socket.Emit("message", wavData);
                }
            }
            else
            {
                UnityEngine.Debug.LogWarning("No audio samples captured!");
            }

            socket.Emit("stop_stream", new { });
            OnStatusUpdate?.Invoke("Processing...");
        }
        catch (Exception e)
        {
            UnityEngine.Debug.LogError($"Failed to stop recording: {e.Message}");
        }
    }

    private void CaptureAudioData()
    {
        int currentPosition = Microphone.GetPosition(null);

        if (currentPosition < 0 || recordingClip == null)
            return;

        if (currentPosition < lastProcessedPosition)
        {
            int samplesToEnd = recordingClip.samples - lastProcessedPosition;
            float[] endSamples = new float[samplesToEnd];
            recordingClip.GetData(endSamples, lastProcessedPosition);
            accumulatedSamples.AddRange(endSamples);

            float[] startSamples = new float[currentPosition];
            recordingClip.GetData(startSamples, 0);
            accumulatedSamples.AddRange(startSamples);
        }
        else if (currentPosition > lastProcessedPosition)
        {
            int newSampleCount = currentPosition - lastProcessedPosition;
            float[] newSamples = new float[newSampleCount];
            recordingClip.GetData(newSamples, lastProcessedPosition);
            accumulatedSamples.AddRange(newSamples);
        }

        lastProcessedPosition = currentPosition;
    }

    private byte[] CreateWAVFile(float[] samples, int sampleRate)
    {
        byte[] pcmData = new byte[samples.Length * 2];
        for (int i = 0; i < samples.Length; i++)
        {
            float sample = Mathf.Clamp(samples[i], -1.0f, 1.0f);
            short pcmSample = (short)(sample * 32767f);
            pcmData[i * 2] = (byte)(pcmSample & 0xFF);
            pcmData[i * 2 + 1] = (byte)((pcmSample >> 8) & 0xFF);
        }
        int channels = 1;
        int bitsPerSample = 16;
        int byteRate = sampleRate * channels * bitsPerSample / 8;
        int blockAlign = channels * bitsPerSample / 8;

        using (var ms = new MemoryStream())
        using (var writer = new BinaryWriter(ms))
        {
            // RIFF header
            writer.Write(System.Text.Encoding.ASCII.GetBytes("RIFF"));
            writer.Write(36 + pcmData.Length);
            writer.Write(System.Text.Encoding.ASCII.GetBytes("WAVE"));

            // fmt chunk
            writer.Write(System.Text.Encoding.ASCII.GetBytes("fmt "));
            writer.Write(16);
            writer.Write((short)1); // PCM
            writer.Write((short)channels);
            writer.Write(sampleRate);
            writer.Write(byteRate);
            writer.Write((short)blockAlign);
            writer.Write((short)bitsPerSample);

            // data chunk
            writer.Write(System.Text.Encoding.ASCII.GetBytes("data"));
            writer.Write(pcmData.Length);
            writer.Write(pcmData);

            return ms.ToArray();
        }
    }

    private IEnumerator DownloadAndPlayAudio(string audioUrl)
    {
        OnStatusUpdate?.Invoke("Downloading audio...");

        using (UnityWebRequest www = UnityWebRequestMultimedia.GetAudioClip(audioUrl, AudioType.WAV))
        {
            yield return www.SendWebRequest();

            if (www.result == UnityWebRequest.Result.Success)
            {
                AudioClip audioClip = DownloadHandlerAudioClip.GetContent(www);
                OnAudioResponseReceived?.Invoke(audioClip);

                AudioSource audioSource = GetComponent<AudioSource>();
                if (audioSource == null)
                    audioSource = gameObject.AddComponent<AudioSource>();

                audioSource.clip = audioClip;
                audioSource.Play();

                OnStatusUpdate?.Invoke("Agent speaking...");
                UnityEngine.Debug.Log($"Playing audio, duration: {audioClip.length:F2}s");

                yield return new WaitForSeconds(audioClip.length);

                OnStatusUpdate?.Invoke("Ready - Hold button to speak");
            }
            else
            {
                UnityEngine.Debug.LogError($"Failed to download audio: {www.error}");
                OnStatusUpdate?.Invoke("Error playing audio: " + www.error);
            }
        }
    }
}