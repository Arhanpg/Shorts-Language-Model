# Proposal 2 — ReelScope Upload-First Creator Copilot

## Original direction

Treat the project as a creator-facing short-video analyst rather than a large crawler. A user uploads an MP4 or supplies a link through an authorized integration. The system extracts visual, speech, text and audio signals, then produces structured feedback and practical editing recommendations.

## Product workflow

1. Upload a short video or select an authorized media source.
2. Validate container, duration, frame rate, dimensions and audio streams.
3. Extract keyframes, scene boundaries, audio and text.
4. Run ASR, OCR, motion/effect analysis and a pretrained multimodal model.
5. Produce a strict JSON report.
6. Show the timeline, evidence frames, transcript and suggestions in a review UI.
7. Save user-corrected annotations as prospective training data.

## Example analysis fields

- **Hook:** opening seconds, hook type, evidence and confidence.
- **Visual structure:** timestamped scenes and actions.
- **Editing events:** cuts, transitions, speed changes, zooms and overlays.
- **On-screen text:** timed OCR spans, placement and possible function.
- **Audio design:** speech language, music/sound presence, energy and silence.
- **Retention hypotheses:** curiosity, payoff, pacing and loopability hypotheses.
- **Improvement suggestions:** timestamp-linked edits and trade-offs.
- **Limitations:** missing evidence, uncertain detections and model caveats.

## Proposed stack

- Python, PyTorch and Transformers.
- FFmpeg and OpenCV.
- PySceneDetect.
- faster-whisper.
- PaddleOCR.
- librosa.
- Qwen-family VLM or VideoLLaMA model.
- PEFT/LoRA for task-specific SFT.
- FastAPI for inference API.
- Streamlit/Gradio for the first review UI.
- PostgreSQL or SQLite for metadata.

## Product extensions

1. **Creator copilot:** evaluate an unpublished draft's opening, pacing, caption readability and payoff timing.
2. **Version comparison:** compare two edits of the same idea and show measured differences.
3. **Editing-agent integration:** export timestamped edit instructions for FFmpeg, Premiere or DaVinci workflows.
4. **Feedback loop:** use creator-owned analytics and controlled variants to improve personalized suggestions.

## What the combined plan accepts

- Start with an upload-first CLI and a single-video analysis report.
- Make user/creator permissions a first-class part of ingestion.
- Build a human-review interface to turn drafts into gold labels.
- Prioritize actionable timestamped reports over a premature viral score.
- Build CLI first, then Gradio/Streamlit, then a polished web UI only after the analysis pipeline is reliable.

## What changes

- A public video link is not an automatic right to download or train on that media.
- Arbitrary Instagram/YouTube crawling is not an MVP feature.
- A 3B/7B model-size recommendation is not fixed until the exact checkpoint and runtime are benchmarked.
- A product UI should not precede the core media-processing and evidence schema.

## Final disposition

**Accepted as the product path.** The system's first working capability is a local authorized-video analyzer. Discovery and batch acquisition are separate later subsystems.
