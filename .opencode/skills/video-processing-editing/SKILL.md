---
name: video-processing-editing
description: Implement safe FFmpeg media processing for validation, normalization, centered crops, and MP4 H.264/AAC exports. Use when changing video ingestion or export behavior.
---

# Video Processing and Editing

## MVP Contract

- Accept MP4 input up to 100 MB and 5 minutes.
- Produce MP4 output with H.264 video and AAC audio.
- Suggest the requested aspect ratio before processing.
- Use a centered crop for the MVP after explicit confirmation.

## Safety Rules

- Inspect media with `ffprobe` before processing.
- Use isolated temporary directories and unique filenames.
- Do not build shell commands by interpolating untrusted filenames or prompts.
- Avoid destructive `-y` behavior unless the destination is a controlled temporary path.
- Bound CPU, duration, output size, and concurrent jobs.
- Preserve the source file and delete temporary inputs, frames, audio, and outputs after completion.
- Report codec, dimensions, duration, and failure reason without leaking local paths or secrets.

## Validation

Use fixtures covering portrait, landscape, square, audio-present, audio-absent, corrupt, oversized, and over-duration videos. Validate dimensions, codec, duration, audio behavior, and cleanup.
