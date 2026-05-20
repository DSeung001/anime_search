from __future__ import annotations

from pathlib import Path
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from anime_indexing.paths import ensure_dir, staging_frames_leaf
from anime_indexing.video.extract import extract_frames_ffmpeg
from anime_indexing.video.pts_manifest import write_frames_pts_manifest

from embeddings.models import EmbeddingJob


class Command(BaseCommand):
    help = "ffmpeg으로 동영상에서 JPG 프레임을 추출한다 (--output-dir 또는 --staging-job-uuid)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("video", type=str, help="입력 동영상 파일 경로")
        parser.add_argument(
            "--output-dir",
            type=str,
            default="",
            help="프레임 JPG를 쓸 디렉터리(없으면 생성)",
        )
        parser.add_argument(
            "--staging-job-uuid",
            type=str,
            default="",
            help="EmbeddingJob.public_id — 해당 작업의 스테이징 frames leaf 로 출력",
        )

    def handle(self, *args, **options) -> None:
        video_path = Path(options["video"]).expanduser().resolve()
        out_arg = (options["output_dir"] or "").strip()
        job_arg = (options["staging_job_uuid"] or "").strip()

        if bool(out_arg) == bool(job_arg):
            raise CommandError("--output-dir 또는 --staging-job-uuid 중 하나만 지정하세요.")

        if out_arg:
            out_dir = Path(out_arg).expanduser().resolve()
        else:
            try:
                uid = UUID(job_arg)
            except ValueError as exc:
                raise CommandError("staging-job-uuid 가 유효한 UUID 가 아닙니다.") from exc
            job = EmbeddingJob.objects.filter(public_id=uid).first()
            if job is None:
                raise CommandError("해당 UUID 의 EmbeddingJob 이 없습니다.")
            out_dir = staging_frames_leaf(job.staging_rel_path)

        if not video_path.is_file():
            raise CommandError(f"동영상 파일이 없습니다: {video_path}")

        ensure_dir(out_dir)
        from django.conf import settings as dj_settings

        fps_setting = float(dj_settings.VIDEO_EXTRACT_FPS)
        fps_arg = None if fps_setting <= 0 else fps_setting
        n = extract_frames_ffmpeg(
            video_path=video_path,
            output_dir=out_dir,
            ffmpeg_bin=dj_settings.FFMPEG_BIN or None,
            fps=fps_arg,
            max_frames=None if dj_settings.VIDEO_EXTRACT_MAX_FRAMES <= 0 else dj_settings.VIDEO_EXTRACT_MAX_FRAMES,
            jpeg_quality=dj_settings.VIDEO_EXTRACT_JPEG_Q,
        )
        manifest = write_frames_pts_manifest(
            video_path=video_path,
            frames_leaf=out_dir,
            ffprobe_bin=dj_settings.FFPROBE_BIN or None,
        )
        extra = f", manifest={manifest.name}" if manifest else ", manifest=(skipped)"
        self.stdout.write(self.style.SUCCESS(f"추출 완료: {n} frames -> {out_dir}{extra}"))
