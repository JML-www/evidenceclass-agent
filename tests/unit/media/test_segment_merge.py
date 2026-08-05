from packages.media_pipeline.merge_segment_results import merge

def test_segment_merge_uses_global_time_and_weight_ratio():
    """分片合并基于全局时间、加权计算指标均值"""
    course_info = {
        "courseName": "test",
        "teacherName": "test",
        "className": "test"
    }
    frame_template = {
        "frame_id": "f1",
        "time": "00:00:10",
        "visibleStudents": [],
        "teacher_behaviors": {}
    }

    seg1 = {
        "analysisMode": "video",
        "courseInfo": course_info,
        "segment": {
            "index": 1,
            "startSeconds": 0.0,
            "durationSeconds": 100.0,
            "timeBasis": "relative"
        },
        "frames": [frame_template],
        "asrSummary": {
            "teacherQuestionCount": 2,
            "teacherTalkRatio": 0.6,
            "teacherTalkMinutes": 1.6,
            "teacherTalkMinutes": 1.6
        }
    }

    seg2 = {
        "analysisMode": "video",
        "courseInfo": course_info,
        "segment": {
            "index": 2,
            "startSeconds": 100.0,
            "durationSeconds": 300.0,
            "timeBasis": "relative"
        },
        "frames": [frame_template],
        "asrSummary": {
            "teacherQuestionCount": 3,
            "teacherTalkRatio": 0.4,
            "teacherTalkMinutes": 4.8
        }
    }

    merged_data = merge([seg2, seg1])

    assert merged_data["frames"][1]["time"] == "00:01:50"
    assert merged_data["asrSummary"]["teacherQuestionCount"] == 5
    assert abs(merged_data["asrSummary"]["teacherTalkRatio"] - 0.45) < 0.01