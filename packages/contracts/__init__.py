"""Public import surface for contracts v0.1."""

from .artifacts import EvidenceArtifact, MetricResult, VideoShard
from .base import BaseContract
from .evidence import EvidenceItem
from .frame import BoundingBox, FrameObservation
from .ocr import OcrBlock
from .region import RegionObservation
from .request import AnalysisRequest, MetricSwitch, TimeWindowConfig, VisibleRegionRule
from .result import AnalysisResult, ArtifactManifest
from .rubric import EvaluationRubric, RubricTarget
from .transcript import TranscriptSegment

__all__ = [
    "BaseContract",
    "AnalysisRequest",
    "TimeWindowConfig",
    "VisibleRegionRule",
    "MetricSwitch",
    "BoundingBox",
    "FrameObservation",
    "TranscriptSegment",
    "OcrBlock",
    "RegionObservation",
    "EvaluationRubric",
    "RubricTarget",
    "EvidenceItem",
    "AnalysisResult",
    "ArtifactManifest",
    "VideoShard",
    "MetricResult",
    "EvidenceArtifact",
]
