# Media Handbook

## M01 Probe Before Model

M01 probe before model uses bounded FFprobe metadata and full decode validation before any expensive AI capability runs.

## M02 Unicode Path Safety

M02 Unicode path safety passes executable arguments without a shell so Chinese names, spaces, and special characters are not concatenated into commands.

## M03 Uniform Sampling

M03 uniform sampling chooses integer millisecond bin centers and records a PNG SHA-256 for reproducible frames.

## M04 Global Timeline

M04 global timeline adds the trusted segment offset to local milliseconds and aligns multiple cameras without model-authored time.

## M05 Audio Normalization

M05 audio normalization verifies 16 kHz mono PCM16 headers before VAD and ASR processing.

## M06 Speech Chunk Limit

M06 speech chunk limit caps each VAD speech chunk at thirty seconds before model transcription and global merge.

## M07 OCR Threshold

M07 OCR threshold is selected with positive and no-text negative fixtures while preserving both raw and filtered results.

## M08 Limited Visual Labels

M08 limited visual labels allow only six directly observable classroom labels and reject psychological or quality fields.

## M09 Segment Idempotency

M09 segment idempotency ignores byte-equivalent retries, rejects conflicting duplicates, and preserves the same merge identifier.

## M10 Missing Segment

M10 missing segment causes an explicit failure listing absent segment identifiers instead of publishing an incomplete aggregate.
