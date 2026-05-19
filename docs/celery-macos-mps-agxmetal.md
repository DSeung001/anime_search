# macOS Celery 임베딩 실패: AGXMetal / MPS 파이프라인 오류

Celery worker(`prefork`)에서 CLIP 임베딩을 돌릴 때 macOS Metal(MPS) 관련 `RuntimeError`가 나는 경우의 재현·해결·원인 정리.

---

## 1. 에러 재현

### 환경

- macOS (Apple Silicon 또는 Metal 사용 가능한 Mac)
- Celery worker 기본 풀: **`prefork`** (`ForkPoolWorker-*` 로그)
- PyTorch CLIP 추론 디바이스가 **`mps`** 또는 **`auto`**(CUDA 없으면 MPS 선택)

### 재현 절차

1. Redis·Django·Celery worker를 평소와 같이 기동한다 (`.env`에 `QDRANT_URL` 등 설정).

   ```bash
   redis-server   # 또는 brew services start redis
   source .venv/bin/activate
   cp .env.example .env   # 최초 1회
   celery -A anime_search worker -l info
   # 다른 터미널
   python3 manage.py runserver
   ```

2. MPS를 쓰도록 `.env`를 맞춘다 (재현용).

   ```env
   ANIME_EMBED_DEVICE=mps
   ```

   worker를 재시작한다.

3. `/jobs/`에서 임베딩 잡을 큐에 넣거나 API로 실행한다.

4. worker 로그에서 아래와 유사한 스택이 나오고, DB/응답상 잡은 `failed`가 된다.

### 대표 로그

```
[ERROR/ForkPoolWorker-1] embedding job failed public_id=... anime=...
Traceback (most recent call last):
  File ".../embeddings/tasks.py", line 62, in run_embedding_job_task
    run_single_embedding_job(job)
  File ".../anime_indexing/embedding_job_runner/workflow.py", line 135, in run_single_embedding_job
    matrix, _, _ = worker.extract_features_from_paths(...)
  File ".../anime_indexing/clip/vision.py", line 140, in extract_features_from_paths
    features = self.model.encode_image(images)
  ...
RuntimeError: Failed to created pipeline state object, error: Error Domain=AGXMetal13_3 Code=2 "Compiler encountered XPC_ERROR_CONNECTION_INVALID (is the OS shutting down?)" ...
```

Celery는 예외를 태스크 안에서 잡아 DB만 실패 처리하므로, 아래처럼 **태스크 자체는 succeeded**로 보일 수 있다.

```
[INFO/ForkPoolWorker-1] Task embeddings.run_embedding_job[...] succeeded in ...: {'public_id': '...', 'status': 'failed'}
```

### 재현 확인 포인트

- worker 기동 직후: `[Worker Init] Loading ... on mps` (또는 `auto` → MPS)
- 로그에 `ForkPoolWorker-N` 표기
- `EmbeddingJob.last_error`에 동일 Metal 메시지

---

## 2. 에러 해결

우선순위: **CPU로 고정** → 필요 시 **fork 없는 worker 풀** → macOS에서는 **동시성 1** 유지.

### 2-1. 권장: CPU로 추론 (가장 단순)

이 프로젝트는 macOS에서 기본값을 `cpu`로 두도록 되어 있다 (`anime_indexing/clip/device.py`). `.env`에 다음을 넣고 worker를 재시작한다.

```env
ANIME_EMBED_DEVICE=cpu
```

기동 로그에 `on cpu`가 보이면 설정이 반영된 것이다.

### 2-2. prefork 회피: threads / solo

fork 이후 Metal을 쓰는 조합을 피하려면 풀을 바꾼다. **동시성은 1**을 권장한다 (`CELERY_WORKER_CONCURRENCY` 기본값도 1). `.env`에 `ANIME_EMBED_DEVICE=cpu`를 둔 뒤:

```bash
celery -A anime_search worker --pool=threads --concurrency=1 -l info
```

또는:

```bash
celery -A anime_search worker --pool=solo -l info
```

> `--pool=threads --concurrency=4`는 fork 문제는 줄일 수 있으나, `get_vision_worker()` 싱글톤 CLIP을 여러 스레드가 동시에 쓰면 MPS 사용 시 오히려 불안정해질 수 있다. macOS 로컬 worker에는 **concurrency=1**을 유지한다.

### 2-3. MPS를 꼭 써야 할 때

속도를 위해 Metal을 쓸 경우:

1. `ANIME_EMBED_DEVICE=mps` (또는 `auto`)
2. **`--pool=threads` 또는 `--pool=solo` + `--concurrency=1`**
3. 실패 시 다시 `cpu`로 되돌린다.

### 2-4. 실패 잡 재시도

1. worker를 위 설정으로 재기동
2. `/jobs/`에서 해당 잡을 다시 실행하거나 API로 재큐
3. `last_error`·worker 로그로 성공 여부 확인

### 환경 변수 요약

프로젝트 루트 `.env`에 설정 (템플릿: `.env.example`).

| 변수 | macOS 권장 | 설명 |
|------|------------|------|
| `ANIME_EMBED_DEVICE` | `cpu` | `auto` / `mps`는 Metal 사용 → 본 오류와 연관 |
| `CELERY_WORKER_CONCURRENCY` | `1` | GPU/CLIP 1잡 순차 (`settings.py` 기본 1) |

---

## 3. 에러 이유

### 3-1. 직접 원인: Metal(MPS) 파이프라인 실패

스택의 `AGXMetal13_3`, `Failed to created pipeline state object`는 PyTorch **MPS 백엔드**가 GPU용 Metal 파이프라인(셰이더 컴파일·실행 상태)을 만들지 못했다는 뜻이다.  
`encode_image` 단계에서 텐서가 MPS 디바이스에 있을 때 발생한다.

### 3-2. 촉발 조건: Celery `prefork` + fork 이후 GPU/Metal

기본 Celery worker는 **`prefork`** 풀이다. 부모 프로세스가 fork로 `ForkPoolWorker-*` 자식을 만든 뒤, 자식에서 PyTorch·Metal을 초기화/사용하면 macOS에서 다음 문제가 자주 난다.

- Metal 셰이더 컴파일러(XPC) 연결이 끊김 → `XPC_ERROR_CONNECTION_INVALID`
- fork 전후 GPU/Metal 컨텍스트 불일치

로그의 **`ForkPoolWorker-1`** 은 이 경로를 쓰고 있음을 나타낸다.  
(Linux CUDA + fork도 유사하게 문제가 많아, ML 워커는 보통 `solo` / `threads` / `spawn`을 쓴다.)

### 3-3. 프로젝트 코드와의 관계

| 위치 | 내용 |
|------|------|
| `anime_indexing/clip/device.py` | macOS 기본 `cpu`, 주석에 AGXMetal 회피 명시 |
| `anime_indexing/clip/vision.py` | `pick_device()`로 모델 로드 디바이스 결정 |
| `anime_indexing/frame_directory_embedding/runtime.py` | 프로세스당 CLIP 싱글톤 (`get_vision_worker`) |
| `embeddings/tasks.py` | 예외 시 DB `failed` + Celery 태스크는 정상 반환 |

`ANIME_EMBED_DEVICE`가 비어 있으면 macOS에서는 `cpu`가 기본이지만, **`auto` 또는 `mps`를 export한 worker**에서는 여전히 Metal을 타서 본 오류가 재현된다.

### 3-4. “Task succeeded인데 status failed”인 이유

`run_embedding_job_task`는 파이프라인 예외를 `except`로 잡아 `EmbeddingJob`만 `FAILED`로 저장하고, **예외를 다시 던지지 않는다**.  
그래서 Celery는 태스크 실행을 성공으로 기록하고, 비즈니스 상태만 `failed`인 것이다. worker 크래시와는 별개로 보면 된다.

### 3-5. 한 줄 요약

**macOS에서 Celery prefork worker가 MPS(Metal)로 CLIP을 돌리면, fork와 Metal 컴파일러/XPC 조합 때문에 파이프라인 생성이 실패할 수 있다.**  
해결은 **`ANIME_EMBED_DEVICE=cpu`** 또는 **fork 없는 풀 + concurrency 1**이다.

---

## 참고

- Celery 앱 이름: `anime_search` (`celery -A anime_search worker ...`)
- 로컬 실행 개요: [README.md](../README.md)
- 디바이스 선택 구현: `anime_indexing/clip/device.py`
