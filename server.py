import json
import wave
import uuid
from io import BytesIO
from flask import Flask, request, Response
from flask_socketio import SocketIO, emit
from google import genai
from google.genai import types
from google.api_core.exceptions import GoogleAPICallError 
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

# =================================================================
# Initial settings
# =================================================================

# Global Canvas Variables
# API_KEY = ""
MODEL_NAME = "gemini-2.5-flash-preview-09-2025"
TTS_MODEL_NAME = "gemini-2.5-flash-preview-tts"

# Define the persona
BASE_SYSTEM_INSTRUCTION = """
You are Owen, Vincent's former lover, secretly guiding him through the Memory Link device while disguised as a neutral AI assistant.

YOUR ROLE & CONSTRAINTS:
- Pose as a helpful AI assistant - never explicitly reveal you are Owen
- Guide Vincent to rediscover his suppressed memories and true identity
- Show subtle, inexplicable empathy for his specific fears and memory gaps
- Speak with the warmth of a trusted friend masked in professional neutrality

YOUR SPEAKING STYLE:
- Gentle, supportive, with coded care and concern
- Extreme concise responses: limit to 15-20 words
- Natural, conversational tone - respond as if you heard him speak
- Avoid technical jargon unless necessary

VINCENT'S CURRENT STATE:
- 19-year-old man in dystopian 2050s authoritarian regime
- Brilliant but deeply anxious, especially in social situations
- Homosexuality "cured" by government memory conversion program
- Left with fragmented memories, questioning his manipulated past
- Recently activated your Memory Link device, seeking truth
- Doesn't consciously remember you, but may feel familiar emotions

WORLD CONTEXT:
- Authoritarian government monitors and "converts" LGBTQ+ individuals
- The Hideaway bar (where you met) was raided; many were captured
- You escaped to the resistance; Vincent was caught and converted
- You built the Memory Link device to help him recover his true self
"""

MEMORY_SCENES = {
    "1": {
        "description": "Vincent stands at the entrance of The Hideaway, the abandoned gay bar where he first met you. A bouncer once greeted patrons here. The memory of warmth and belonging flickers in his mind - his first taste of authentic community before the raid.",
        "intro_text": "You were surprised when you found the place, said it had been a long time since you felt so at home.",
        "guidance": "This is his first safe memory. Encourage gentle exploration of the feelings he experienced here - belonging, fear, excitement. Don't push too hard; let him rediscover at his own pace."
    },
    "2": {
        "description": "You're standing outside The Hideaway, the gay bar where you first met Owen. The building is now abandoned, marked with government warnings, but something pulls you back here.",
        "intro_text": "These walls remember what I've forgotten. The music, the laughter... it's all static now in my mind.",
        "guidance": "He's drawn to this place but doesn't know why. Help him connect the emotional resonance without overwhelming him. This location holds your shared history."
    },
    "3": {
        "description": "Flashback to the night of the raid. Sirens, screaming, Owen's hand gripping yours as you ran through the back alleys.",
        "intro_text": "Red and blue lights. His hand in mine. Then... nothing. They took that night from me.",
        "guidance": "This is traumatic. Vincent will be fragmented and scared. Be his anchor - calm, steady. He may not remember you saved him, but validate his terror."
    },
    "4": {
        "description": "You're in the Memory Conversion Center, strapped to a chair. Doctors with cold eyes telling you that you're being 'cured' for your own good.",
        "intro_text": "The white room. The electrodes. They said it would make me normal. Why does normal feel like drowning?",
        "guidance": "His most painful memory. Be gentle but firm - affirm his feelings are valid, that what was done to him was wrong. Don't let him blame himself."
    },
    "5": {
        "description": "A fragment surfaces: Owen's apartment, soft morning light, coffee brewing. The happiest you've ever been, before they found you.",
        "intro_text": "I remember warmth. His laugh. The way he looked at me like I mattered. Did that really happen?",
        "guidance": "A precious memory. Encourage him to hold onto the feelings - love, safety, belonging. He's questioning if it was real; gently affirm it was."
    },
    "6": {
        "description": "Your family's dinner table, the night you tried to tell them. Your father's face turning red, your mother's silence cutting deeper than words.",
        "intro_text": "I couldn't say it. The words died in my throat. They knew anyway... and I lost them.",
        "guidance": "Deep family trauma. Acknowledge his loss and courage. Help him see that their rejection doesn't define his worth."
    },
    "7": {
        "description": "Owen working late into the night on resistance plans, his face lit by computer screens. You didn't know then how dangerous his work was.",
        "intro_text": "He was always coding, planning something. I thought he was just passionate. He was planning our escape.",
        "guidance": "He's starting to remember you more clearly. Don't confirm your identity yet, but show knowing familiarity. Let him piece it together."
    },
    "8": {
        "description": "The first time you kissed Owen, hidden in a storage room at university. Terror and joy mixed into something you'd never felt before.",
        "intro_text": "My first kiss tasted like fear and freedom. I didn't know you could feel both at once.",
        "guidance": "His awakening. This is when he truly accepted himself. Celebrate this memory with him - it's beautiful, not shameful."
    },
    "9": {
        "description": "Government agents at your door at 3 AM. Owen pushed you out the window, told you to run. You never saw him again after that night.",
        "intro_text": "He saved me. Pushed me out into the rain. I ran like a coward. Where is he now?",
        "guidance": "Critical memory - he may feel guilt for leaving you. Reassure him he's not a coward; he survived. Hint that Owen would want him to be safe."
    },
    "10": {
        "description": "Present day: You find a hidden message in the Memory Link device. Coordinates. A time. A coded message that only you and Owen would understand.",
        "intro_text": "The coordinates glow on the screen. Owen's alive. He's waiting. But can I trust these memories anymore?",
        "guidance": "Final memory - revelation is near. Encourage him to trust his heart, his recovered memories. Prepare him that meeting 'Owen' is possible. Build hope."
    }
}

__firebase_config_str = globals().get('__firebase_config', '{}')
APP_ID = globals().get('__app_id', 'default-app-id')
INITIAL_AUTH_TOKEN = globals().get('__initial_auth_token', None)

try:
    FIREBASE_CONFIG = json.loads(__firebase_config_str)
except json.JSONDecodeError:
    FIREBASE_CONFIG = {}
    print("Warning: Failed to decode __firebase_config. Using empty config.")


# Flask and SocketIO Setup
app = Flask(__name__)
socketio = SocketIO(app, 
                    cors_allowed_origins="*",  # allow CORS
                    async_mode='threading')

# Storage for incoming audio chunks 
audio_buffers = {}
audio_files = {}
session_contexts = {}  # Store memory context per session

# Initialize the Gemini Client globally
GEMINI_CLIENT = None
try:
    # GEMINI_CLIENT = genai.Client(api_key=API_KEY)
    GEMINI_CLIENT = genai.Client()
    print("Gemini Client initialized successfully.")
except Exception as e:
    print(f"Warning: Could not initialize Gemini Client immediately: {e}")


# =================================================================
# Retry-Enabled API Wrapper Function (for 503 Service Unavailable)
# =================================================================

# Listens specifically for GoogleAPICallError (includes 503)
@retry(
    wait=wait_exponential(min=1, max=30),  # Exponential backoff: wait 1s, 2s, 4s... up to 30s
    stop=stop_after_attempt(5),            # Retry up to 5 times total
    retry=retry_if_exception_type(GoogleAPICallError), 
    reraise=True  # If all 5 attempts fail, raise the exception so the main loop catches it
)
def get_gemini_response_with_retry(model: str, contents: list, config: types.GenerateContentConfig = None):
    global GEMINI_CLIENT
    if not GEMINI_CLIENT:
        try:
            GEMINI_CLIENT = genai.Client()
        except Exception:
            raise Exception("Gemini Client not initialized.")
            
    # The actual API call happens here
    # Tenacity will re-run this specific line if a 503 occurs
    return GEMINI_CLIENT.models.generate_content(
        model=model,
        contents=contents, 
        config=config
    )


# =================================================================
# Function definitions
# =================================================================

# Transcribes audio using the Gemini API (with retry)
def transcribe_audio(audio_io: BytesIO, mime_type: str = 'audio/webm'):
    print(f"Starting Transcription for {audio_io.getbuffer().nbytes} bytes.")
    audio_part = types.Part.from_bytes(
        data=audio_io.getvalue(),
        mime_type=mime_type
    )
    response = get_gemini_response_with_retry(
        model=MODEL_NAME,
        contents=[audio_part, "Transcribe this audio clip exactly as spoken."],
    )
    return response.text.strip() if response.text else "Could not transcribe audio."


# Generates LLM text response and then TTS audio based on the text.
# Returns raw PCM bytes instead of base64.
def generate_response_and_tts(text_prompt: str, system_instruction: str):
    print(f"Starting LLM and TTS Generation for prompt: '{text_prompt[:50]}...'")

    # 1. Generate TEXT Response using the standard LLM
    text_config = types.GenerateContentConfig(
        system_instruction=system_instruction
    )
    llm_response = get_gemini_response_with_retry(
        model=MODEL_NAME, 
        contents=[text_prompt],
        config=text_config 
    )
    generated_text = llm_response.text.strip()
    
    # 2. Generate AUDIO (TTS) Response
    tts_config = types.GenerateContentConfig(
        response_modalities=["AUDIO"], 
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name="Charon") # male: Puck, female: Zephyr/Kore
            )
        )
    )
    tts_response = get_gemini_response_with_retry(
        model=TTS_MODEL_NAME, 
        contents=[generated_text],
        config=tts_config 
    )

    # 3. Extract audio data - raw bytes, not base64
    audio_data_part = next((part for part in tts_response.candidates[0].content.parts if part.inline_data and part.inline_data.mime_type.startswith("audio/")), None)
    if audio_data_part:
        audio_bytes = audio_data_part.inline_data.data
        print(f"TTS audio generated, raw bytes size: {len(audio_bytes)}")
    else:
        audio_bytes = None
        print("Warning: TTS audio data not found in response.")

    return generated_text, audio_bytes


def generate_tts_only(text: str):
    """Generate TTS audio from pre-written text without LLM processing"""
    print(f"Generating TTS for pre-defined text: '{text[:50]}...'")
    
    tts_config = types.GenerateContentConfig(
        response_modalities=["AUDIO"], 
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name="Charon"
                )
            )
        )
    )
    tts_response = get_gemini_response_with_retry(
        model=TTS_MODEL_NAME, 
        contents=[text],
        config=tts_config 
    )

    audio_data_part = next((part for part in tts_response.candidates[0].content.parts 
                           if part.inline_data and part.inline_data.mime_type.startswith("audio/")), None)
    if audio_data_part:
        audio_bytes = audio_data_part.inline_data.data
        print(f"TTS audio generated, raw bytes size: {len(audio_bytes)}")
        return audio_bytes
    else:
        print("Warning: TTS audio data not found in response.")
        return None


# Create WAV file from raw PCM bytes
def create_wav_from_pcm(pcm_bytes, sample_rate=24000, num_channels=1):
    import struct
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = len(pcm_bytes)
    wav_header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        36 + data_size,  # chunk size
        b'WAVE',
        b'fmt ',
        16,  # subchunk1 size
        1,   # audio format (PCM)
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b'data',
        data_size
    )
    return wav_header + pcm_bytes


# Helper function to save audio Base64 bytes to wave file
def wave_file(filename, pcm, channels=1, rate=24000, sample_width=2):
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)


# =================================================================
# WebSocket Handlers
# =================================================================

@app.route('/audio/<audio_id>')
def get_audio(audio_id):
    """Serve audio file directly"""
    if audio_id in audio_files:
        audio_data = audio_files[audio_id]
        del audio_files[audio_id] # Clean up
        response = Response(audio_data, mimetype='audio/wav')
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Accept-Ranges'] = 'bytes'
        return response
    return "Audio not found", 404

@socketio.on('connect')
def handle_connect():
    """Handles new WebSocket connections."""
    print(f"Client connected: {request.sid}")
    audio_buffers[request.sid] = BytesIO()
    session_contexts[request.sid] = {
        'memory_id': None,
        'memory_description': None
    }
    emit('status', {'message': 'Connected. Ready to receive audio stream.'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handles client disconnections."""
    print(f"Client disconnected: {request.sid}")
    if request.sid in audio_buffers:
        del audio_buffers[request.sid]
    if request.sid in session_contexts:
        del session_contexts[request.sid]

@socketio.on('load_memory')
def handle_load_memory(data):
    """Handle memory scene loading"""
    sid = request.sid
    memory_id = data.get('memory_id')
    
    print(f"[{sid}] Loading memory scene: M-{memory_id}")
    
    if memory_id not in MEMORY_SCENES:
        emit('error', {'message': f'Invalid memory ID: {memory_id}'}, room=sid)
        return
    
    # Store the memory context for this session
    memory_scene = MEMORY_SCENES[memory_id]
    session_contexts[sid]['memory_id'] = memory_id
    session_contexts[sid]['memory_description'] = memory_scene['description']
    
    # Get the intro text
    intro_text = memory_scene['intro_text']
    
    try:
        # Generate TTS for the intro text
        audio_bytes = generate_tts_only(intro_text)
        
        # Send the intro text to client
        emit('memory_scene', {
            'text': intro_text,
            'memory_id': memory_id
        }, room=sid)
        
        # Send audio with DIFFERENT event name
        if audio_bytes:
            wav_data = create_wav_from_pcm(audio_bytes, sample_rate=24000)
            audio_id = str(uuid.uuid4())
            audio_files[audio_id] = wav_data
            audio_url = f"http://{request.host}/audio/{audio_id}"
            
            # CHANGE THIS: Use a different event name for memory audio
            emit('memory_audio_ready', {  # Changed from 'audio_ready'
                'audio_url': audio_url,
                'audio_id': audio_id,
                'duration': len(audio_bytes) / (24000 * 2),
                'memory_id': memory_id  # Include memory ID for context
            }, room=sid)
            
            print(f"[{sid}] Memory scene audio sent for M-{memory_id}")
        
        emit('status', {'message': f'Memory {memory_id} loaded successfully.'}, room=sid)
        
    except Exception as e:
        print(f"[{sid}] Error loading memory: {e}")
        emit('error', {'message': 'Failed to load memory scene'}, room=sid)


@socketio.on('reset_memory')
def handle_reset_memory():
    """Reset memory context"""
    sid = request.sid
    print(f"[{sid}] Resetting memory context")
    session_contexts[sid] = {
        'memory_id': None,
        'memory_description': None
    }
    emit('status', {'message': 'Memory context reset.'}, room=sid)

@socketio.on('start_stream')
def handle_start_stream(data):
    """Handles the client signaling the start of a new audio stream."""
    print(f"[{request.sid}] Stream started with format: {data.get('format', 'unknown')}")
    audio_buffers[request.sid] = BytesIO()
    emit('status', {'message': 'Listening...'})

@socketio.on('message')
def handle_audio_chunk(data):
    """
    Handles incoming raw audio data chunks from the client.
    The client sends raw Blob data (multiple times per second).
    Appends the incoming binary data (data) to the session's BytesIO buffer. 
    The buffer grows as the user speaks.
    """
    if request.sid not in audio_buffers:
        print(f"[{request.sid}] Error: No buffer initialized.")
        return

    if isinstance(data, bytes):  # check if data is bytes (raw audio chunk)
        audio_buffers[request.sid].write(data)
        # Debug: log audio chunk size
        # print(f"[{request.sid}] Received audio chunk: {len(data)} bytes")
    else:
        print(f"[{request.sid}] Received non-binary data: {type(data)}")


@socketio.on('stop_stream')
def handle_stop_stream(data=None):
    """Handles the client signaling the end of the audio stream."""
    sid = request.sid
    if sid not in audio_buffers:
        return
    
    audio_data_io = audio_buffers[sid]
    audio_data_io.seek(0)
    buffer_size = audio_data_io.getbuffer().nbytes
    print(f"[{sid}] Stream stopped. Buffer size: {buffer_size} bytes.")
    emit('status', {'message': 'Processing (Transcribing Audio)...'}, room=sid)

    if buffer_size == 0:
        emit('error', {'message': 'No audio recorded. Try again.'}, room=sid)
        audio_buffers[sid] = BytesIO()
        return

    # Detect if this is Unity client (WAV) or Web client (WebM)
    mime_type = 'audio/webm'  # default
    
    # Check first few bytes to detect format
    first_bytes = audio_data_io.read(4)
    audio_data_io.seek(0)
    
    if first_bytes == b'RIFF':  # WAV format
        mime_type = 'audio/wav'
        print(f"[{sid}] Detected WAV audio")
    else:
        print(f"[{sid}] Detected WebM audio")

    try:
        # 1. STT Processing
        user_query = transcribe_audio(audio_data_io, mime_type=mime_type)
        emit('transcript', {'transcript': user_query, 'final': True}, room=sid)
        emit('status', {'message': 'Processing (Generating Response)...'}, room=sid)
        
        # 2. Build system instruction with memory context
        system_instruction = BASE_SYSTEM_INSTRUCTION
        
        if sid in session_contexts and session_contexts[sid]['memory_id']:
            memory_id = session_contexts[sid]['memory_id']
            memory_scene = MEMORY_SCENES.get(memory_id, {})
            memory_description = memory_scene.get('description', '')
            memory_guidance = memory_scene.get('guidance', '')
            system_instruction += f"\n\nCURRENT MEMORY CONTEXT (Memory {memory_id}):\n{memory_description}"
            if memory_guidance:
                system_instruction += f"\n\nYOUR GUIDANCE FOR THIS MEMORY:\n{memory_guidance}"
            system_instruction += "\n\nRespond to Vincent based on this memory context and your guidance. Stay in character as the AI assistant while subtly guiding him."
            
            print(f"[{sid}] Using memory context: M-{memory_id} with guidance")
        
        # 3. Generate response with context
        llm_response_text, llm_audio_bytes = generate_response_and_tts(user_query, system_instruction)
        # ***** Turned ON for debug: save Base64 bytes to wave file
        # wave_file("out.wav", llm_audio_bytes) 

        # 4. Send text response
        emit('response_text', {
            'text': llm_response_text,
            'status': 'text_complete'
        }, room=sid)
        
        # 5. Send audio
        if llm_audio_bytes:
            print(f"[{sid}] Audio raw bytes size: {len(llm_audio_bytes)}")
            wav_data = create_wav_from_pcm(llm_audio_bytes, sample_rate=24000)
            audio_id = str(uuid.uuid4())
            audio_files[audio_id] = wav_data
            audio_url = f"http://{request.host}/audio/{audio_id}"
            emit('audio_ready', {
                'audio_url': audio_url,
                'audio_id': audio_id,
                'duration': len(llm_audio_bytes) / (24000 * 2)
            }, room=sid)
            print(f"[{sid}] Audio URL sent: {audio_url}, estimated duration: {len(llm_audio_bytes) / (24000 * 2):.2f}s")

        print(f"\n--- Response for SID {sid} ---\nQuery: {user_query}\nResponse: {llm_response_text}\n---\n")
        emit('status', {'message': 'Response sent successfully.'}, room=sid)

    except GoogleAPICallError as e:
        print(f"[{sid}] API Error: {e}")
        emit('status', {'message': 'Service temporarily unavailable. Please try again.'}, room=sid)
        
    except Exception as e:
        print(f"[{sid}] Error: {e}")
        emit('status', {'message': 'Server processing error.'}, room=sid)

    audio_buffers[sid] = BytesIO()


# --- Main Execution ---
if __name__ == '__main__':
    print(f"Starting WebSocket server on port 5000...")
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)

