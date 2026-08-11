# Phase 5 acceptance record

Phase 5 turns authorized media into reproducible, globally timestamped ASR, OCR, and limited visual
observations before later Agent orchestration. Required acceptance uses real FFmpeg/FFprobe with
synthetic media and replaceable Fake model adapters. Optional local-model acceptance records real
faster-whisper and RapidOCR behavior separately. Generated media, model caches, and raw responses
remain ignored by Git.

## Step 5.1: safe media inspection

`SafeMediaProbe` passes a shell-free argument vector to `ffprobe -print_format json`. It extracts
duration, size, container, video codec/dimensions/frame rate/rotation, audio codec/channels/sample
rate, stream count, and bounded metadata size. Before model use it rejects:

- non-local, unresolved, out-of-authorized-root, or unsupported paths;
- empty/oversize files, excess duration/dimensions/frame rate/streams/metadata;
- missing video streams and unsupported codecs;
- text renamed as MP4, damaged containers, and streams that fail complete FFmpeg decode validation.

Executable fixtures cover a normal ten-second H.264/AAC video, a no-audio H.264 video, corrupted
MP4, text disguised as MP4, Chinese plus spaces in the path, and an oversized metadata tag.

## Step 5.2: reproducible sampling

`frame-sampling.v1` first implements center-of-bin uniform timestamps with integer millisecond
arithmetic and also exposes bounded scene-change sampling. Every sampled PNG contains system-owned
asset/camera IDs, local/global milliseconds, policy version, SHA-256, and object reference.

Acceptance samples the same source and policy twice and compares all timestamps and hashes. It
also samples two camera IDs with the same global offset and verifies equal global timepoints.
Visual occurrences stay frame observations; no code converts sampling frequency into whole-class
duration.

## Step 5.3: ASR

The path is `video -> 16 kHz mono PCM -> energy VAD -> <=30-second chunks -> AsrModel -> global
merge`. Without diarization, every segment role is `unknown` and role-ratio metrics are explicitly
unavailable. `FasterWhisperAdapter` is an optional local Protocol implementation with explicit
model selection, raw-response object references, audio-second usage, and zero external API cost.

Real local acceptance on 2026-08-11 used faster-whisper `tiny`, CPU int8, and an authorized original
300-second Chinese synthetic fixture. Four manually defined reference windows produced:

| Category | CER |
|---|---:|
| Clean | 13.16% |
| Added noise | 11.54% |
| Proper noun | 94.87% |
| Overlapping speech | 98.44% |
| Overall | 64.67% |

The fixed-seed result shows that `tiny` is unsuitable for the mixed proper-noun/overlap sections;
the next model comparison should evaluate a larger checkpoint and a dedicated overlap/diarization
strategy. This fixture result is not a classroom accuracy claim or a quality gate hidden behind a
single average.

## Step 5.4: OCR

`RapidOcrAdapter` is an optional local OCR implementation. `OcrPipeline` saves raw text, filtered
text, inclusion flag, confidence, normalized box, frame ID, global timestamp, provider/model
revision, threshold, and threshold-selection note. If every item is below threshold, raw items
remain present and `all_below_threshold=true`; nothing is silently erased.

Real local acceptance used three synthetic slides, three synthetic board images, and three
no-text geometric negatives. Slide and board CER were both 0%. Raw OCR mislabeled the rectangle in
all three negatives as `口` with confidence about 0.772, for a 100% raw negative false-positive
rate. The validation-selected threshold 0.8 preserved the six text positives and reduced the
negative false-positive rate to 0%. Both raw and filtered evaluations remain in the ignored report.

## Step 5.5: limited VLM observations

The first vocabulary is exactly `raise_hand`, `standing`, `reading_or_writing_visible`,
`group_discussion_visible`, `teacher_at_podium`, and `teacher_patrolling_visible`. Counts may be
null when visibility is insufficient. Pydantic validates the six-label set, count bounds, teacher
binary counts, regions, and confidence. Asset/frame/camera/time provenance is never model-authored.
The prompt prohibits identity, emotion, attention, motivation, ability, diagnosis, discipline,
speaker role, and whole-lesson quality inference.

Thirty versioned original diagrams and preassigned truth counts are rendered and compared by the
evaluation harness. The default observer is Fake, so `accuracy_claimed=false`. A real VLM run is
still not claimed: the available compatible endpoint remains HTTP 403 and the optional Qwen runtime
was not completed in phase 4. The structured VLM code path and evaluation gate are complete, while
this external model-effect evidence remains the one phase-5 model gap.

## Step 5.6: long-video stress semantics

MVP probe defaults stop at ten minutes. Separate `media-segments.v1` manifests preserve contiguous
global offsets for the later 46-minute dual-camera stress case. Merge acceptance deliberately:

- passes shuffled observations and verifies sorting;
- repeats a byte-equivalent segment and verifies idempotent de-duplication plus the same merge ID;
- provides conflicting duplicates and verifies rejection;
- omits a segment and verifies an explicit missing-ID error;
- checks count/duration sums, duration-weighted metrics, and local-to-global evidence timestamps.

## Commands

Required reproducible gate:

```powershell
.\scripts\setup-media-tools.ps1
.\scripts\accept-stage-5.ps1
```

Optional real local ASR/OCR gate:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,media-models]"
.\scripts\accept-stage-5.ps1 -RunRealMediaModels -WhisperModel tiny
```

If direct Hugging Face access is unavailable, an explicitly trusted mirror may be passed through
`-HfEndpoint`; model data is cached only below ignored `.media-runtime/`. No endpoint, model, or
mirror is silently selected by repository code.
