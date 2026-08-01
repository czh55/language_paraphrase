#!/usr/bin/env python3
"""
从视频中按场景时间轴抽取关键帧，并处理视频封面，供单期场景英译 HTML 使用。

用法：
  python3 scripts/extract_frames.py --slug=crab-london --video=/tmp/crab-london.mp4 --thumb=/tmp/crab-london.jpg
  python3 scripts/extract_frames.py --slug=crab-london --video=/tmp/crab-london.mp4            # 仅场景帧
  python3 scripts/extract_frames.py --slug=crab-london --print-scenes                          # 仅打印场景时间轴

场景时间轴来源（按优先级）：
  1. docs/audio/{slug}/audio-input.json 的 scenes[].time（形如 "00:14–00:38"）
  2. docs/{slug}-场景英译.html 中 <span class="time"> 文本（存量内容走此路径）

输出到 docs/images/{slug}/：
  hero.jpg   视频封面（由 --thumb 复制/转换而来）
  s1.jpg..s{N}.jpg   各场景中点关键帧
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
IMAGES_DIR = DOCS / "images"

TIME_RE = re.compile(
    r"(?:(\d+):)?(\d{1,2}):(\d{2})\s*[–\-—~]\s*(?:(\d+):)?(\d{1,2}):(\d{2})"
)
TIME_PLAIN_RE = re.compile(
    r"(?:(\d+):)?(\d{1,2}):(\d{2})\s*[–\-—~]\s*(?:(\d+):)?(\d{1,2}):(\d{2})"
)


def parse_time_span(text: str) -> tuple[int, int] | None:
    """把 '00:14–00:38' / '1:02:00–1:02:30' 解析为 (start_sec, end_sec)。"""
    m = TIME_RE.search(text or "")
    if not m:
        return None
    parts = m.groups()

    def to_sec(h, m_, s):
        return (int(h or 0) * 3600) + (int(m_ or 0) * 60) + int(s)

    start = to_sec(parts[0], parts[1], parts[2])
    end = to_sec(parts[3], parts[4], parts[5])
    if end <= start:
        end = start
    return start, end


def format_ts(sec: int) -> str:
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def load_scene_times(slug: str) -> list[tuple[int, int]]:
    """按优先级解析场景时间轴，返回 (start, end) 列表（保持场景顺序）。"""
    # 1) audio-input.json
    audio_input = DOCS / "audio" / slug / "audio-input.json"
    if audio_input.exists():
        try:
            data = json.loads(audio_input.read_text("utf-8"))
            times = []
            for scene in data.get("scenes", []):
                span = parse_time_span(scene.get("time", ""))
                if span:
                    times.append(span)
            if times:
                return times
        except (json.JSONDecodeError, OSError) as e:
            print(f"[warn] 读取 {audio_input} 失败: {e}", file=sys.stderr)

    # 2) {slug}-场景英译.html
    html_file = DOCS / f"{slug}-场景英译.html"
    if html_file.exists():
        html = html_file.read_text("utf-8")
        spans = re.findall(r'<span class="time">([^<]+)</span>', html)
        times = []
        for text in spans:
            span = parse_time_span(text)
            if span:
                times.append(span)
        if times:
            return times

    return []


def extract_frame(video: Path, sec: int, out: Path) -> bool:
    """在指定秒抽取一帧，输出 720p 宽的 jpg。"""
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", str(sec), "-i", str(video),
        "-frames:v", "1",
        "-vf", "scale=-2:720",
        "-q:v", "2",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[error] ffmpeg 抽帧失败 {out} @ {sec}s: {proc.stderr.strip()}", file=sys.stderr)
        return False
    return out.exists() and out.stat().st_size > 0


def copy_thumb(thumb: Path, out: Path) -> bool:
    """把封面缩略图复制/转换为 hero.jpg。"""
    out.parent.mkdir(parents=True, exist_ok=True)
    if thumb.suffix.lower() in (".jpg", ".jpeg"):
        try:
            shutil.copyfile(thumb, out)
            return out.exists() and out.stat().st_size > 0
        except OSError as e:
            print(f"[error] 复制封面失败: {e}", file=sys.stderr)
            return False
    # 其他格式（webp/png）用 ffmpeg 转 jpg
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(thumb), str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[error] 封面转 jpg 失败: {proc.stderr.strip()}", file=sys.stderr)
        return False
    return out.exists() and out.stat().st_size > 0


def main() -> int:
    parser = argparse.ArgumentParser(description="按场景时间轴抽取视频关键帧")
    parser.add_argument("--slug", required=True, help="slug，如 crab-london")
    parser.add_argument("--video", help="视频文件路径（画面流）")
    parser.add_argument("--thumb", help="封面缩略图路径（可选）")
    parser.add_argument("--print-scenes", action="store_true", help="仅打印场景时间轴")
    args = parser.parse_args()

    slug = args.slug
    times = load_scene_times(slug)
    if not times:
        print(f"[error] 未找到 {slug} 的场景时间轴（audio-input.json / HTML time span）", file=sys.stderr)
        return 1

    if args.print_scenes:
        for i, (start, end) in enumerate(times, 1):
            print(f"s{i}: {format_ts(start)} - {format_ts(end)}")
        return 0

    video = Path(args.video) if args.video else None
    if not video or not video.exists():
        print("[error] 需要 --video 指向已下载的视频文件", file=sys.stderr)
        return 1

    out_dir = IMAGES_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) hero 封面
    if args.thumb and Path(args.thumb).exists():
        if copy_thumb(Path(args.thumb), out_dir / "hero.jpg"):
            print(f"[ok] hero.jpg <- {args.thumb}")
        else:
            print("[warn] 封面处理失败", file=sys.stderr)
    else:
        print("[warn] 未提供 --thumb，跳过 hero.jpg", file=sys.stderr)

    # 2) 场景关键帧
    failed = []
    for i, (start, end) in enumerate(times, 1):
        mid = (start + end) // 2
        out = out_dir / f"s{i}.jpg"
        if extract_frame(video, mid, out):
            print(f"[ok] s{i}.jpg <- {format_ts(mid)}")
        else:
            failed.append(f"s{i}")

    if failed:
        print(f"[warn] 抽帧失败 {len(failed)} 个场景: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
