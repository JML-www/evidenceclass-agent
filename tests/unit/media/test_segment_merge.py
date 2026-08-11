from copy import deepcopy

import pytest

from packages.media_pipeline.merge_segment_results import merge


def test_segment_merge_converts_global_time_and_uses_duration_weights():
    course = {
        "courseName": "Synthetic lesson C",
        "className": "Synthetic class",
        "studentCount": 10,
    }
    frame = {
        "frame_id": "frame_001",
        "time": "00:00:10",
        "visible_student_count": 10,
        "student_behaviors": {},
        "teacher_behaviors": {},
    }
    first = {
        "analysisMode": "video",
        "courseInfo": course,
        "segment": {
            "index": 1,
            "startSeconds": 0.0,
            "durationSeconds": 100.0,
            "timeBasis": "relative",
        },
        "frames": [frame],
        "asrSummary": {"teacherQuestionCount": 2, "teacherTalkRatio": 0.8},
    }
    second = {
        "analysisMode": "video",
        "courseInfo": course,
        "segment": {
            "index": 2,
            "startSeconds": 100.0,
            "durationSeconds": 300.0,
            "timeBasis": "relative",
        },
        "frames": [frame],
        "asrSummary": {"teacherQuestionCount": 3, "teacherTalkRatio": 0.4},
    }
    original = deepcopy([second, first])

    merged = merge([second, first])

    assert merged["mergeMetadata"]["orderedIndexes"] == [1, 2]
    assert merged["frames"][1]["time"] == "00:01:50"
    assert merged["asrSummary"]["teacherQuestionCount"] == 5
    assert merged["asrSummary"]["teacherTalkRatio"] == 0.5
    assert [second, first] == original


def test_segment_merge_is_idempotent_for_identical_duplicates_and_rejects_gaps():
    item = {
        "analysisMode": "video",
        "courseInfo": {"courseName": "Synthetic", "className": "Class", "studentCount": 1},
        "segment": {
            "index": 1,
            "startSeconds": 0.0,
            "durationSeconds": 10.0,
            "expectedTotalSegments": 1,
        },
        "frames": [],
    }

    merged = merge([item, deepcopy(item)])

    assert merged["mergeMetadata"]["duplicateInputsIgnored"] == 1

    missing_middle = deepcopy(item)
    missing_middle["segment"] = {
        "index": 2,
        "startSeconds": 10.0,
        "durationSeconds": 10.0,
        "expectedTotalSegments": 2,
    }
    with pytest.raises(ValueError, match="missing indexes"):
        merge([missing_middle])
