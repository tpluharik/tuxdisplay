#!/usr/bin/python3
"""Pure helpers for TuxDisplay's low-latency GStreamer pipeline."""

from __future__ import annotations

from collections.abc import Collection


ENCODER_AUTO = "auto"
ENCODER_SOFTWARE = "software"
HARDWARE_ELEMENTS = frozenset({"vah264enc", "vapostproc"})
STATIC_KEEPALIVE_MS = 1000


def encoder_candidates(preference: str, available_elements: Collection[str]) -> list[str]:
    """Return ordered encoder backends with a safe software fallback."""
    if preference == ENCODER_AUTO and HARDWARE_ELEMENTS.issubset(available_elements):
        return ["hardware", "software"]
    return ["software"]


def target_bitrate_kbps(width: int, height: int, frames_per_second: int) -> int:
    """Scale quality with pixel rate while staying practical for USB receivers."""
    estimated = round(width * height * frames_per_second * 0.08 / 1000)
    return min(20_000, max(4_000, estimated))


def keyframe_interval(frames_per_second: int) -> int:
    """Keep periodic IDRs rare; reconnects request an immediate keyframe."""
    return min(1024, max(1, frames_per_second) * 60)


def pipeline_description(
    node_id: int,
    width: int,
    height: int,
    frames_per_second: int,
    encoder: str,
) -> str:
    """Build a damage-driven, bounded-latency capture and encoding graph."""
    bitrate_kbps = target_bitrate_kbps(width, height, frames_per_second)
    key_int_max = keyframe_interval(frames_per_second)
    queue = "queue max-size-buffers=1 max-size-bytes=0 max-size-time=0 leaky=downstream"
    browser_branch = (
        f"displaytee. ! {queue} "
        "! valve name=jpeg_valve drop=false "
        "! videoconvert n-threads=2 "
        "! videoscale n-threads=2 add-borders=true "
        f"! video/x-raw,format=I420,width={width},height={height},pixel-aspect-ratio=1/1 "
        "! jpegenc quality=76 "
        "! appsink name=jpeg_sink emit-signals=true max-buffers=1 drop=true sync=false "
    )
    if encoder == "hardware":
        h264_branch = (
            f"displaytee. ! {queue} "
            "! vapostproc add-borders=true "
            f"! video/x-raw(memory:VAMemory),format=NV12,width={width},height={height},pixel-aspect-ratio=1/1 "
            "! vah264enc name=h264_encoder rate-control=vbr target-usage=7 target-percentage=80 "
            f"bitrate={bitrate_kbps} b-frames=0 ref-frames=1 cabac=false dct8x8=false "
            f"key-int-max={key_int_max} aud=true "
        )
    elif encoder == "software":
        h264_branch = (
            f"displaytee. ! {queue} "
            "! videoconvert n-threads=4 "
            "! videoscale n-threads=4 add-borders=true "
            f"! video/x-raw,format=I420,width={width},height={height},pixel-aspect-ratio=1/1 "
            "! x264enc name=h264_encoder tune=zerolatency speed-preset=ultrafast "
            f"threads=0 sliced-threads=true bitrate={bitrate_kbps} "
            "byte-stream=true bframes=0 cabac=false dct8x8=false "
            f"key-int-max={key_int_max} aud=true "
        )
    else:
        raise ValueError(f"unsupported video encoder: {encoder}")

    return (
        f"pipewiresrc path={node_id} do-timestamp=true keepalive-time={STATIC_KEEPALIVE_MS} "
        "min-buffers=2 max-buffers=8 "
        f"! {queue} name=capture_queue "
        "! identity name=capture_probe signal-handoffs=true silent=true "
        "! tee name=displaytee "
        + browser_branch
        + h264_branch
        + "! h264parse config-interval=-1 "
        "! video/x-h264,profile=constrained-baseline,stream-format=byte-stream,alignment=au "
        "! appsink name=h264_sink emit-signals=true max-buffers=1 drop=false sync=false"
    )
