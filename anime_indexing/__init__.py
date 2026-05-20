"""
애니메이션 프레임 색인·임베딩용 **Django 바깥 순수 파이썬 패키지** (`anime_indexing`).

- ``paths`` — 미디어·스테이징 루트와 캐논 경로 (``{series_slug}/frames``)
- ``video`` — 동영상 → JPG 프레임 (ffmpeg; 기본 초당 1장, ``VIDEO_EXTRACT_FPS=0`` 시 전 프레임)
- ``clip`` — CLIP 모델 로드·디바이스·배치 추론
- ``vectors`` — Qdrant 등 벡터 저장소 적재
- ``frame_directory_embedding`` — **이미 풀려 있는** 프레임 디렉터리만 CLIP에 태움 (DB 작업 행 없음)
- ``embedding_job_runner`` — **Django ``EmbeddingJob`` 한 건**을 끝까지 처리 (추출·승격·CLIP·Qdrant)

Django 앱 ``embeddings`` 는 HTTP·ORM·관리 커맨드만 두고, 실제 처리는 이 패키지를 호출한다.
"""
