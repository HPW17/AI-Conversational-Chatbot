using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.UI;
using UnityEngine.EventSystems;
using TMPro;

public class PushToTalkButton : MonoBehaviour, IPointerDownHandler, IPointerUpHandler
{
    [Header("Button References")]
    [SerializeField] private Image buttonImage;
    [SerializeField] private Color normalColor = Color.gray;
    [SerializeField] private Color recordingColor = Color.red;
    [SerializeField] private Color readyColor = Color.green;

    [Header("UI References")]
    [SerializeField] private TMP_Text statusText;
    [SerializeField] private TMP_Text transcriptText;
    [SerializeField] private TMP_Text responseText;

    private bool isInitialized = false;
    private bool isRecordingViaButton = false;

    void Start()
    {
        InitializeButton();
    }

    void Update()
    {
        // Sync button visual with spacebar state
        if (Keyboard.current != null)
        {
            if (Keyboard.current.spaceKey.wasPressedThisFrame)
            {
                if (buttonImage != null)
                    buttonImage.color = recordingColor;
            }
            else if (Keyboard.current.spaceKey.wasReleasedThisFrame)
            {
                if (buttonImage != null && !isRecordingViaButton)
                    buttonImage.color = normalColor;
            }
        }
    }

    private void InitializeButton()
    {
        // Set initial state
        if (buttonImage != null)
            buttonImage.color = normalColor;

        UpdateStatus("Press button or spacebar to record");

        // Subscribe to events
        VoiceChatManager.OnStatusUpdate += HandleStatusUpdate;
        VoiceChatManager.OnTranscriptReceived += HandleTranscriptReceived;
        VoiceChatManager.OnAgentResponseReceived += HandleAgentResponseReceived;

        isInitialized = true;
    }

    public void OnPointerDown(PointerEventData eventData)
    {
        if (!isInitialized) return;

        // Start recording when button is pressed
        isRecordingViaButton = true;
        VoiceChatManager.Instance.StartRecording();
        if (buttonImage != null)
            buttonImage.color = recordingColor;
    }

    public void OnPointerUp(PointerEventData eventData)
    {
        if (!isInitialized) return;

        // Stop recording when button is released
        isRecordingViaButton = false;
        VoiceChatManager.Instance.StopRecording();
        if (buttonImage != null)
            buttonImage.color = normalColor;
    }

    private void HandleStatusUpdate(string status)
    {
        if (statusText != null)
            statusText.text = status;

        // Update button color based on status
        if (buttonImage != null)
        {
            if (status.Contains("Ready"))
            {
                buttonImage.color = readyColor;
            }
            else if (status.Contains("Error"))
            {
                buttonImage.color = Color.yellow;
            }
        }
    }

    private void HandleTranscriptReceived(string transcript)
    {
        if (transcriptText != null)
            transcriptText.text = "You said: " + transcript;
    }

    private void HandleAgentResponseReceived(string response)
    {
        if (responseText != null)
            responseText.text = "Agent: " + response;
    }

    private void UpdateStatus(string status)
    {
        if (statusText != null)
            statusText.text = status;
    }

    void OnDestroy()
    {
        // Unsubscribe from events
        if (isInitialized)
        {
            VoiceChatManager.OnStatusUpdate -= HandleStatusUpdate;
            VoiceChatManager.OnTranscriptReceived -= HandleTranscriptReceived;
            VoiceChatManager.OnAgentResponseReceived -= HandleAgentResponseReceived;
        }
    }
}