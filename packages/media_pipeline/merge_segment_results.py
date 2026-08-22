#!/usr/bin/env python3
"""Merge ordered video-segment observations into one classroom analysis input."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any


def parse_time(value: str) -> float:
    parts = [float(part) for part in value.split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    raise ValueError(f"Invalid timestamp: {value}")


def format_time(seconds: float) -> str:
    whole = max(0, round(seconds))
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def unique(items: list[Any]) -> list[Any]:
    result = []
    for item in items:
        if item not in result:
            result.append(item)
    return result


def weighted(values: list[tuple[float, float]]) -> float | None:
    valid = [(value, weight) for value, weight in values if weight > 0]
    if not valid:
        return None
    return sum(value * weight for value, weight in valid) / sum(weight for _, weight in valid)


def merge(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        raise ValueError("At least one segment result is required.")
    for item in results:
        if item.get("analysisMode") != "video" or not isinstance(item.get("segment"), dict):
            raise ValueError(
                "Every segment result must use video mode and contain segment metadata."
            )
    unique_by_index: dict[int, dict[str, Any]] = {}
    fingerprints: dict[int, str] = {}
    duplicate_count = 0
    for item in results:
        index = int(item["segment"]["index"])
        fingerprint = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if index in unique_by_index:
            if fingerprints[index] != fingerprint:
                raise ValueError("Conflicting duplicate segment index.")
            duplicate_count += 1
            continue
        unique_by_index[index] = item
        fingerprints[index] = fingerprint
    ordered = sorted(
        unique_by_index.values(),
        key=lambda item: (
            float(item["segment"]["startSeconds"]),
            int(item["segment"]["index"]),
        ),
    )
    indices = [int(item["segment"]["index"]) for item in ordered]
    expected_count = max(
        [int(item["segment"].get("expectedTotalSegments", max(indices))) for item in ordered]
    )
    if indices != list(range(1, expected_count + 1)):
        missing = sorted(set(range(1, expected_count + 1)) - set(indices))
        raise ValueError(f"Segment sequence is incomplete; missing indexes: {missing}.")
    previous_end = 0.0
    for item in ordered:
        start = float(item["segment"]["startSeconds"])
        duration = float(item["segment"]["durationSeconds"])
        if start + 0.5 < previous_end or duration <= 0:
            raise ValueError("Segments overlap or contain invalid durations.")
        previous_end = start + duration

    base = ordered[0]
    merged: dict[str, Any] = {
        "analysisMode": "video",
        "courseInfo": deepcopy(base["courseInfo"]),
        "observationGoal": base.get("observationGoal", "分段视频合并课堂观察"),
        "sourceFiles": [],
        "frames": [],
        "regionHeatmap": {},
        "asrSummary": {},
        "teacherBehaviorDurations": {},
        "teachingContent": {},
        "mergeMetadata": {
            "segmentCount": len(ordered),
            "orderedIndexes": indices,
            "duplicateInputsIgnored": duplicate_count,
        },
    }
    for item in ordered:
        segment = item["segment"]
        start = float(segment["startSeconds"])
        index = int(segment["index"])
        merged["sourceFiles"].extend(deepcopy(item.get("sourceFiles") or []))
        for frame in item.get("frames") or []:
            copy = deepcopy(frame)
            source_frame_id = copy.get("frame_id", len(merged["frames"]) + 1)
            copy["frame_id"] = f"segment_{index:02d}_{source_frame_id}"
            if segment.get("timeBasis", "relative") == "relative":
                copy["time"] = format_time(start + parse_time(str(copy.get("time", "00:00:00"))))
            copy["segment_index"] = index
            merged["frames"].append(copy)

    duration_weights = [float(item["segment"]["durationSeconds"]) for item in ordered]
    asr_sum_keys = (
        "teacherQuestionCount",
        "studentAnswerCount",
        "discussionSegments",
        "teacherTalkMinutes",
    )
    for key in asr_sum_keys:
        values = [float(item.get("asrSummary", {}).get(key, 0)) for item in ordered]
        if any(values):
            merged["asrSummary"][key] = sum(values)
    for key in ("teacherTalkRatio", "waitTimeSecondsAverage"):
        value = weighted(
            [
                (float(item.get("asrSummary", {}).get(key, 0)), weight)
                for item, weight in zip(ordered, duration_weights, strict=True)
                if key in item.get("asrSummary", {})
            ]
        )
        if value is not None:
            merged["asrSummary"][key] = value
    speech = weighted(
        [
            (
                float(item.get("asrSummary", {}).get("speechRateWpm", 0)),
                float(item.get("asrSummary", {}).get("teacherTalkMinutes", weight / 60)),
            )
            for item, weight in zip(ordered, duration_weights, strict=True)
            if "speechRateWpm" in item.get("asrSummary", {})
        ]
    )
    if speech is not None:
        merged["asrSummary"]["speechRateWpm"] = speech
    fillers: Counter[str] = Counter()
    quotes: list[str] = []
    for item in ordered:
        fillers.update(item.get("asrSummary", {}).get("fillerWords") or {})
        quotes.extend(str(value) for value in item.get("asrSummary", {}).get("notableQuotes") or [])
        for key, value in (item.get("teacherBehaviorDurations") or {}).items():
            current = merged["teacherBehaviorDurations"].get(key, 0)
            merged["teacherBehaviorDurations"][key] = current + float(value)
    if fillers:
        merged["asrSummary"]["fillerWords"] = dict(fillers)
    if quotes:
        merged["asrSummary"]["notableQuotes"] = unique(quotes)

    for region in ("front", "middle", "back"):
        samples = []
        for item, weight in zip(ordered, duration_weights, strict=True):
            value = (item.get("regionHeatmap") or {}).get(region) or {}
            if value.get("visibility") in {"visible", "partial"}:
                samples.append((value, weight))
        if not samples:
            merged["regionHeatmap"][region] = {
                "visibility": "not_visible",
                "focus": None,
                "interaction": None,
            }
        else:
            all_visible = all(value.get("visibility") == "visible" for value, _ in samples)
            visibility = "visible" if all_visible else "partial"
            focus = weighted(
                [
                    (float(value["focus"]), weight)
                    for value, weight in samples
                    if value.get("focus") is not None
                ]
            )
            interaction = weighted(
                [
                    (float(value["interaction"]), weight)
                    for value, weight in samples
                    if value.get("interaction") is not None
                ]
            )
            merged["regionHeatmap"][region] = {
                "visibility": visibility,
                "focus": focus,
                "interaction": interaction,
            }

    content_lists = (
        "knowledgePoints",
        "teachingMethods",
        "lessonSegments",
        "skillHighlights",
        "skillGaps",
        "skillRecommendations",
    )
    for key in content_lists:
        merged["teachingContent"][key] = unique(
            [
                value
                for item in ordered
                for value in (item.get("teachingContent", {}).get(key) or [])
            ]
        )
    summaries = unique(
        [
            str(item.get("teachingContent", {}).get("courseSummary"))
            for item in ordered
            if item.get("teachingContent", {}).get("courseSummary")
        ]
    )
    if summaries:
        merged["teachingContent"]["courseSummary"] = "；".join(summaries)
    for key in ("bloomQuestions", "fourWhatQuestions"):
        counts: Counter[str] = Counter()
        for item in ordered:
            counts.update(item.get("teachingContent", {}).get(key) or {})
        if counts:
            merged["teachingContent"][key] = dict(counts)
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge ordered segment observation JSON files.")
    parser.add_argument("results", nargs="+", type=Path, help="Segment observation JSON files.")
    parser.add_argument(
        "--output-json", type=Path, required=True, help="Merged video-mode input JSON."
    )
    args = parser.parse_args()
    try:
        payloads = [json.loads(path.read_text(encoding="utf-8-sig")) for path in args.results]
        merged = merge(payloads)
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        result: dict[str, Any] = {
            "mergedInput": str(args.output_json.resolve()),
            "segments": len(payloads),
            "frames": len(merged["frames"]),
        }
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
