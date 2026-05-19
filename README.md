# anime_search

애니메이션 프레임 CLIP 임베딩·벡터 검색 (Django + Qdrant). 검색(RAG)은 **Qdrant 벡터**만 사용하며, 프레임 JPG는 **스테이징**에만 둡니다.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env 편집 (GEMINI_API_KEY, QDRANT_URL 등) — 전체 목록은 .env.example 참고
python3 manage.py migrate
```

환경 변수는 프로젝트 루트 **`.env`** 한 곳에서 관리합니다 (`cp .env.example .env`). Django·Celery가 시작할 때 자동으로 읽습니다. `.env` 수정 후 **runserver·worker 재시작**이 필요합니다.

스키마·데이터를 처음부터 맞출 때:

```bash
rm -f db.sqlite3
rm -rf data/staging/jobs data/media
python3 manage.py migrate
```

필수 외부 프로세스: **Redis**(Celery), **Qdrant**(`QDRANT_URL`). 동영상 업로드 시 **ffmpeg** 권장.

| 변수 | 기본값 | 의미 |
|------|--------|------|
| `ANIME_DATA_ROOT` | `<프로젝트>/data` | 하위 `staging/`, `media/` |
| `CELERY_BROKER_URL` | `redis://127.0.0.1:6379/0` | Celery 큐 |
| `QDRANT_URL` | (없음) | 설정 시 임베딩 벡터 저장·검색 |
| `GEMINI_API_KEY` | (없음) | `/search/` 채팅 (Discovery) |

전체 키·설명: [`.env.example`](.env.example)

Redis 예: `brew install redis && brew services start redis`  
API·경로 상세: `GET /api/embed/path-help/` (DEBUG 또는 `X-Internal-Key`)

## Run

```bash
# .env 가 없으면: cp .env.example .env 후 GEMINI_API_KEY, QDRANT_URL 등 설정

# 터미널 1 — Redis (이미 떠 있으면 생략)
redis-server

# 터미널 2 — Celery worker (프로젝트 루트, venv; .env 와 동일 cwd)
celery -A anime_search worker -l info

# 터미널 3 — Django
python3 manage.py runserver
```

- 장면 검색: http://localhost:8000/search/
- 업로드: http://localhost:8000/upload/
- 잡 목록: http://localhost:8000/jobs/

업로드 → `EmbeddingJob` 생성 → 스테이징 `data/staging/jobs/<uuid>/` → (준비되면) 자동 enqueue → worker가 ffmpeg·CLIP·Qdrant 처리.

runserver와 worker는 **같은 `ANIME_DATA_ROOT`** 를 써야 합니다.

## Trade-offs

| 방식 | 장점 | 단점 |
|------|------|------|
| **스테이징만** (현재) | RAG에 충분, 재추출·동영상 미리보기 가능, 화별 media 덮어쓰기 없음 | `data/staging/jobs/` 용량 증가 — DONE 잡은 주기적 삭제 권장 |
| (과거) media 승격 | 화별 고정 캐논 경로 | 디스크 이중화, 승격 시 스테이징 삭제로 preview 소실 |

디스크 레이아웃: `data/staging/jobs/<job-uuid>/input/` (동영상), `.../frames/` (JPG). 잡 삭제 시 해당 UUID 폴더 전체 삭제.

macOS Celery·GPU 이슈: [docs/celery-macos-mps-agxmetal.md](docs/celery-macos-mps-agxmetal.md)
