import json
from packages.evidence_engine.builder import anonymize

# 1. test_anonymize_removes_identifiers_and_local_paths
def test_anonymize_removes_identifiers_and_local_paths():
    """脱敏函数清除姓名、学号、本地磁盘路径"""
    raw = {
        "studentName": "张三",
        "nested": {"student_id": "S001"},
        "sourceFiles": [{"name": "demo.mp4", "localPath": "E:/private/demo.mp4"}]
    }
    clean_data = anonymize(raw)
    assert "studentName" not in clean_data
    assert "student_id" not in clean_data["nested"]
    assert "localPath" not in clean_data["sourceFiles"][0]

# 2. test_showcase_windows_preserve_global_context
def test_showcase_windows_preserve_global_context():
    """时间切片窗口保留全局时间基准"""
    from packages.media_pipeline.showcase import build_windows
    windows = build_windows(timestamps=["00:02:00", "00:08:00"], clip_sec=30, offset_sec=15)
    assert windows[0]["globalStartSeconds"] == 105.0
    assert windows[0]["referenceSeconds"] == 120.0
    assert windows[1]["index"] == 2