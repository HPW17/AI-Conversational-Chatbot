# AI Conversational Chatbot

## Introduction

This is part of a project aiming to explore the effects of affective interactions on player emotion in VR interactive narrative. This conversational AI chatbot system is engineered by integrating LLM and STT/TTS APIs with custom prompt engineering to generate context-aware dialogue, enhancing player immersion.

 ## Methodology

- A persistent challenge in Virtual Reality (VR) interactive digital narrative (IDN) is the conflict between the player's desire for interactivity and the author's need for narrative structure. Traditional controller-based interactions often lead to "ludonarrative dissonance," where players rushing through plot points without emotional engagement. 
- To resolve this conflict, we developed the LLM-driven context-aware conversational AI agent to bridge the ambiguity between the player's state and the required narrative emotion, and guide the player into the protagonist's headspace.

## System Architecture and Implementation

1. **Client-Server Architecture**:
    The system operates on a bidirectional communication model:
    - Client: Captures audio via microphone and handles scene management. It sends voice data and current game state (e.g., "Player near Memory #3") to the server via WebSockets (Socket.IO).
    - Server: Orchestrates the AI pipeline. It receives the audio, performs Speech-to-Text (STT) transcription, feeds the text and context into the Large Language Model (Gemini), receives the text response, converts it via Text-to-Speech (TTS), and streams the audio back to the client.

2. **Functions and Mechanics**:
    The chatbot operates in two distinct modes:
    - The Emotional Primer (The Hint): As the player approaches a memory fragment, the AI autonomously delivers a concise, evocative prompt to set the mood. For example, "This is where he left... the silence is so loud here."
    - Contextual Deep-Dive (The Chat): If the player fails the emotional check or expresses confusion, they can query the bot. The bot analyzes the lore and provides tailored clues. If the player asks, "Why can't I pick this up?", the bot might reply, "Vincent felt a heavy weight in his chest here. Can you feel that grief?"

3. **Affective Persona Design**:
    Prompt engineering was critical to maintaining immersion. We established a specific "System Prompt Design Strategy":
    - Tone: Gentle, supportive, showing "inexplicable empathy." The AI must sound like a machine masking a human soul (reflecting the narrative theme of lost humanity).
    - Constraints: Strict word-count restrictions were imposed to prevent the AI from monologuing, which would overload the player's cognitive load and break the pacing.
    - Narrative Guardrails: The AI is strictly forbidden from breaking character or discussing real-world topics (e.g., "I am a language model").

4. **Iterative Feedback Implementation**:
    During development, we encountered two main issues with the AI integration:
    - Insufficient Prompts: Initial prompts were too vague. We adjusted the system prompt to associate with the memory to trigger stronger emotional reactions.
    - Intrusiveness: An AI voice speaking from "nowhere" broke immersion. 

## Results

The results support our hypothesis: combining facial expression recognition with AI scaffolding enhances dramatic agency. By enforcing emotional conditions, we prevented players from "rushing" the content. The AI chatbot played a crucial role here, without it, the facial recognition mechanic could have become a source of frustration (a "guess the emotion" minigame). The AI provided the necessary context to make the interaction meaningful rather than mechanical.

This validates the application of Appraisal Theory in VR. Players did not just observe the story, they had to appraise it as the protagonist would to progress. This created a feedback loop: Narrative Event --> AI Context --> Player Appraisal (Emotion) --> System Feedback --> Increased Immersion.

## Limitations

  Despite the success, several technical limitations hindered the experience:
  - System Latency: The round-trip time for the AI (Speech --> Text --> LLM --> Text --> Speech) introduced delays. In a high-fidelity VR environment, even a 2-second delay can break the "illusion of non-mediation."
  - ASR Robustness: The Automatic Speech Recognition (STT) struggled with background noise, leading to transcription errors that confused the LLM.
  - Flow Interruption: The necessity of pressing a "record" button to talk to the AI created a mode-switching cost, momentarily pulling the player out of the narrative flow.
  - TTS Emotional Range: Current Text-to-Speech models, while clear, often lack the emotional subtlety to whisper, cry, or express trembling fear, which creates a tonal mismatch with the heavy narrative themes.

## Programs

- **server.py** (AI Orchestrator & Backend): The Python server that runs the Affective Pipeline. It receives audio/scene context from the VR client, handles the entire LLM workflow (STT, prompt engineering with memory context, and TTS response generation via Gemini API), and manages the WebSocket connection. It is the brain that generates the AI persona "Owen's" empathetic dialogue. 
- **client.html** (Web-based Client): A simple HTML/JavaScript file that mimics the VR environment's function by capturing microphone input and playing back the AI's TTS response, ensuring the core voice-to-voice communication loop is functional outside of the full Unity VR environment.
- **VoiceChatManager.cs** (VR Client Core Logic): The central C# script within the Unity VR client. It handles the low-level audio streaming (capturing microphone PCM data), manages the WebSocket connection to server.py, and is responsible for integrating the AI's audio response into the 3D VR environment (e.g., spatializing the sound). It requires to include websocket-sharp-standard.dll package in Unity.
- **PushToTalkButton.cs** (User Interaction Mechanic): A C# script attached to the "Memory Link" artifact in the VR scene. It manages the user experience of the conversation by handling the "hold-to-talk" input: starting and stopping the audio stream based on the player's button press and providing visual feedback (e.g., changing the device's color/texture) to manage player expectation during AI latency.




