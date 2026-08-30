# Changelog

## Unreleased
### Added
- **WebRTC DSP Preprocessor:** Active noise suppression filter (Noise Gate) added to the AudioWorklet to prevent ambient background noise from triggering Gemini Live translation sessions.
- **Active Listening Visualizer:** Canvas visualizer updated to establish a noise floor threshold, ensuring the UI waveform only reacts to active speech rather than ambient room static.
