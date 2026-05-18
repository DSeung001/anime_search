# anime_search

애니메이션 프레임 CLIP 임베딩·벡터 검색 (Django + Qdrant).

## 사전 준비

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python3 manage.py migrate
```

스키마를 Episode 정규화 이후로 **처음부터** 맞추려면 DB·로컬 데이터를 비운 뒤 migrate 하면 됩니다.

```bash
rm -f db.sqlite3
rm -rf data/staging/jobs data/media
python3 manage.py migrate
```

(Qdrant에 옛 벡터가 남아 있으면 컬렉션을 비우거나 `QDRANT_COLLECTION`을 새 이름으로 바꾸세요.)

## 로컬 실행 (웹 + 비동기 잡)

임베딩 잡은 **Celery**로 돌아가며, 기본 설정은 **Redis를 메시지 브로커 + 결과 저장소**로 씁니다.

| 구분 | 설명 |
|------|------|
| `pip install redis` | Python이 Redis에 **접속**하기 위한 라이브러리 |
| **Redis 서버** (`redis-server`) | 실제 큐가 쌓이는 **별도 프로세스** — 반드시 설치·실행 필요 |

Redis가 없거나 꺼져 있으면: Celery worker가 기동 실패하거나, `/jobs/`에서 “다음 잡 처리” 시 연결 오류가 납니다.

### 1) Redis 서버 설치 (macOS 예시)

**Homebrew**

```bash
brew install redis
brew services start redis   # 부팅 시 자동 시작 (선택)
# 또는 포그라운드만: redis-server
```

**Docker**

```bash
docker run -d --name anime-redis -p 6379:6379 redis:7-alpine
```

**동작 확인**

```bash
redis-cli ping
# PONG
```

기본 접속: `redis://127.0.0.1:6379/0` (settings의 `CELERY_BROKER_URL` 기본값과 동일)

### 2) 터미널 3개 (또는 tmux)

**터미널 A — Redis** (brew services로 이미 띄웠다면 생략 가능)

```bash
redis-server
```

**터미널 B — Celery worker** (프로젝트 루트, venv 활성화)

```bash
cd /path/to/anime_search
source .venv/bin/activate
celery -A anime_search worker -l info
```

**터미널 C — Django**

```bash
cd /path/to/anime_search
source .venv/bin/activate
python3 manage.py runserver
```

- 잡 UI: http://localhost:8000/jobs/
- “다음 잡 처리” / “이 잡 실행” → API가 Redis 큐에 넣음 → **B 터미널 worker**가 GPU 파이프라인 실행 → 브라우저는 폴링으로 DB 상태 갱신

### 웹 / Celery / 폴링 역할

| 구성요소 | 하는 일 | 잡 실행? |
|----------|---------|----------|
| Django `runserver` | `/jobs/` UI, `POST /api/jobs/<uuid>/run/` (큐 적재), `GET /api/jobs/` (상태 읽기) | POST는 enqueue만 |
| Celery worker | `run_embedding_job_task` → CLIP·Qdrant 파이프라인 | **실제 실행** |
| 브라우저 폴링 | `pending`/`processing` 잡이 있을 때 약 2초마다 **목록 API 1회** | **없음** (읽기 전용) |

폴링 중에 “이 잡 실행”을 눌러도 **충돌하지 않습니다**. 실행은 worker가 하고, 폴링은 DB 상태만 반영합니다.

`runserver` 로그에 `GET /api/jobs/` 가 반복되는 것은 위 폴링 때문이며, 활성 잡이 없으면 요청이 멈춥니다.

### 디스크 경로 (로컬)

환경변수는 **`ANIME_DATA_ROOT` 하나**만 쓰면 됩니다 (기본: 프로젝트 `data/`).

| 하위 경로 | 내용 |
|-----------|------|
| `data/staging/jobs/<job-uuid>/input/` | 업로드 동영상 (잡마다 UUID 폴더 1개) |
| `data/staging/jobs/<job-uuid>/frames/` | 추출·작업 중 JPG |
| `data/media/<anime-slug>/episodes/<n>/frames/` | 잡 완료 후 승격된 JPG (시리즈·화 단위) |

`/upload/` 한 번 = `EmbeddingJob` 1건 = `jobs/<public_id>/` 폴더 1개. 옛 `ANIME_STAGING_ROOT`·`anime_data` 등은 쓰지 않습니다.

### 스테이징 오류 (`스테이징 디렉터리가 없습니다`)

worker가 `data/staging/jobs/<public_id>/` 에 `input/` 동영상 또는 `frames/` JPG가 없을 때 실패합니다. runserver와 Celery worker가 **같은 `ANIME_DATA_ROOT`** 를 쓰는지 확인하세요.

### 환경 변수

| 변수 | 기본값 | 의미 |
|------|--------|------|
| `ANIME_DATA_ROOT` | `<프로젝트>/data` | 스테이징·미디어 상위 (하위 `staging/`, `media/` 고정) |
| `CELERY_BROKER_URL` | `redis://127.0.0.1:6379/0` | Celery 메시지 큐 |
| `CELERY_RESULT_BACKEND` | broker와 동일 | 태스크 결과 (이 프로젝트 UI는 DB 폴링 위주) |
| `CELERY_WORKER_CONCURRENCY` | `1` | GPU 1잡 순차 권장 |

원격 Redis 예:

```bash
export CELERY_BROKER_URL="redis://:비밀번호@호스트:6379/0"
export CELERY_RESULT_BACKEND="$CELERY_BROKER_URL"
```

### Redis 없이 잠깐 테스트만 (비권장)

테스트·단위 테스트용으로 Celery가 **같은 프로세스에서** 태스크를 즉시 실행하게 할 수 있습니다. **웹 UI + worker 분리 검증에는 쓰지 마세요.**

```bash
export CELERY_TASK_ALWAYS_EAGER=1
python3 manage.py runserver
```

`embeddings/tests_job_celery.py`도 이 모드로 동작합니다.

### 자주 나는 문제

| 증상 | 원인 | 조치 |
|------|------|------|
| `Error 61 connecting to 127.0.0.1:6379` | Redis 미실행 | `redis-server` 또는 `brew services start redis` |
| worker는 뜨는데 잡이 안 끝남 | worker 미기동 / 다른 venv | B 터미널에서 worker 로그 확인 |
| `processing`에서 멈춤 | worker 크래시·GPU 오류 | worker 로그, `last_error`, 필요 시 재큐 |
| `스테이징 디렉터리가 없습니다` | 스테이징 미생성·삭제·경로 불일치 | `data/staging/jobs/<public_id>/`·`ANIME_DATA_ROOT` 통일 |
| `AGXMetal` / `Failed to created pipeline state object` (macOS) | Celery prefork + MPS(Metal) | [docs/celery-macos-mps-agxmetal.md](docs/celery-macos-mps-agxmetal.md) |
