from shorts_intelligence.config import AnalyzerConfig
from shorts_intelligence.feature_bundle import build_feature_bundle
from shorts_intelligence.schemas import (
    AudioFeatures,
    CutCandidate,
    FrameEvidence,
    HookWindow,
    MotionSummary,
    OCRSpan,
    RightsDeclaration,
    TranscriptSegment,
    VideoMetadata,
)


def test_feature_bundle_separates_modalities_and_defers_semantic_models():
    video = VideoMetadata(
        file_name="clip.mp4", sha256="a" * 64, file_size_bytes=100,
        duration_seconds=5.0, width=100, height=200, fps=24, frame_count=120,
        aspect_ratio="1:2",
    )
    transcript = [TranscriptSegment(
        start_seconds=0.2, end_seconds=1.0, text="hello",
        text_normalized="hello", script="Latn", language="en",
    )]
    ocr = [OCRSpan(
        timestamp_seconds=0.3, text="SALE", text_normalized="SALE",
        script="Latn", confidence=0.9, bbox_xyxy=[1, 1, 20, 10],
        bbox_normalized_xyxy=[0.01, 0.005, 0.2, 0.05], track_id="ocr_00001",
        track_start_seconds=0.3, track_end_seconds=0.8,
        accepted_candidate=True, quality_status="accepted_candidate",
        engine="paddleocr-3-cpu", frame_index=1,
    )]
    bundle = build_feature_bundle(
        video=video,
        hook_window=HookWindow(end_seconds=3, frame_count=4, cut_candidate_count=0, mean_motion_score=1),
        frame_evidence=[FrameEvidence(timestamp_seconds=0.3, frame_index=1, motion_score=1)],
        cut_candidates=[CutCandidate(timestamp_seconds=1, visual_difference=0.3, confidence=0.7)],
        motion=MotionSummary(sample_count=0, mean_flow_magnitude=0, p95_flow_magnitude=0),
        transcript_segments=transcript, ocr_spans=ocr, audio=AudioFeatures(analyzed=True),
        stages={"asr": {"status": "complete", "engine": "whisper"}},
        warnings=[], rights=RightsDeclaration(basis="creator_owned"),
        config=AnalyzerConfig(),
    )
    assert bundle["bundle_version"] == "3.0.0"
    assert bundle["video_manifest"]["file_name"] == "clip.mp4"
    assert bundle["transcript"]["segment_count"] == 1
    assert bundle["ocr"]["raw_candidate_count"] == 1
    assert bundle["ocr"]["tracklets"][0]["track_id"] == "ocr_00001"
    assert bundle["audio_features"]["analyzed"] is True
    assert bundle["temporal_events"]
    assert bundle["semantic_features"]["person_pose"]["status"] == "NOT_YET_PROCESSED"
    assert bundle["provenance"]["rights_declaration"]["model_training_permitted"] is False
    assert bundle["training_readiness"]["ready"] is False
    assert bundle["training_readiness"]["status"] == "NOT_READY"
    assert bundle["training_readiness"]["model_training_permission"] == "UNKNOWN_OR_NOT_PERMITTED"
