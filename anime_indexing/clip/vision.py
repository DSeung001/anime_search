from __future__ import annotations

import os
import time
from typing import List, Optional, Tuple

import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset

from anime_indexing.constants import DEFAULT_CLIP_MODEL_NAME

from .clip_load import load_clip
from .device import pick_device, sync_device as _sync_device


class AnimeFrameDataset(Dataset):
    def __init__(self, frame_paths: List[str], preprocess):
        self.frame_paths = frame_paths
        self.preprocess = preprocess

    def __len__(self) -> int:
        return len(self.frame_paths)

    def __getitem__(self, idx: int):
        img = Image.open(self.frame_paths[idx])
        return self.preprocess(img)


def list_frame_jpgs(frames_dir: str) -> List[str]:
    return sorted(
        os.path.join(frames_dir, f)
        for f in os.listdir(frames_dir)
        if f.endswith(".jpg")
    )


class VisionPipelineWorker:
    def __init__(
        self,
        model_name: str = DEFAULT_CLIP_MODEL_NAME,
        *,
        clip_checkpoint: Optional[str] = None,
    ) -> None:
        self.device = pick_device()
        self.model_name = model_name
        print(f"[Worker Init] Loading {model_name} on {self.device}...")
        self.model, self.preprocess = load_clip(
            model_name,
            self.device,
            checkpoint_path=clip_checkpoint,
            ssl_no_verify=False,
        )
        self.model.eval()

    def _empty_features(self) -> np.ndarray:
        dim = int(self.model.visual.output_dim)
        return np.zeros((0, dim), dtype=np.float32)

    def extract_features(
        self,
        frames_dir: str,
        *,
        batch_size: int,
        num_workers: int,
        verbose: bool = True,
        log_batches_every: int = 10,
    ) -> Tuple[np.ndarray, float, float]:
        # jpg 목록 가져오기
        all_frame_files = list_frame_jpgs(frames_dir)
        if not all_frame_files:
            return self._empty_features(), 0.0, 0.0

        # dataset에서 인덱스마다 파일을 읽고 그 떄 self.preprocess를 적용하게 생성
        dataset = AnimeFrameDataset(all_frame_files, self.preprocess)
        pin = self.device == "cuda"
        # Dataloader로 배치, 병렬처리 지정
        dataloader = DataLoader(
            dataset,
            batch_size=batch_size,
            shuffle=False,
            num_workers=num_workers,
            pin_memory=pin,
        )

        all_features: List[np.ndarray] = []
        start_time = time.perf_counter()
        # 추론할 때 그래프/그래디언트 비활성화해서 속도 향상
        # 학습을 위해 켜지는 옵션을 비활성화해서 추론 비용을 가볍게 처리
        with torch.no_grad():
            # 프레임 파일을 배치 단위로 순회
            for batch_idx, images in enumerate(dataloader):
                images = images.to(self.device)
                # 모델로 벡터(임베딩) 추출
                features = self.model.encode_image(images)
                # L2 정규화
                features /= features.norm(dim=-1, keepdim=True)
                all_features.append(features.cpu().numpy())

                if verbose and log_batches_every > 0 and (batch_idx + 1) % log_batches_every == 0:
                    print(f"Processed batch {batch_idx + 1}/{len(dataloader)}...")

        _sync_device(self.device)
        # 배치 단위로 나뉜 임베딩을 “프레임 N개 × 차원 D”처럼 하나의 레이아웃으로 합침
        final_matrix = np.vstack(all_features)
        elapsed = time.perf_counter() - start_time
        frames_per_sec = len(all_frame_files) / elapsed if elapsed > 0 else 0.0

        if verbose:
            print(f"  >> Inference Time: {elapsed:.2f}s ({frames_per_sec:.2f} frames/sec)")
        return final_matrix, elapsed, frames_per_sec

    def extract_features_from_paths(
        self,
        frame_paths: List[str],
        *,
        batch_size: int,
        num_workers: int,
        verbose: bool = False,
        log_batches_every: int = 10,
    ) -> Tuple[np.ndarray, float, float]:
        """지정된 JPG 경로만 임베딩(순서 유지)."""
        if not frame_paths:
            return self._empty_features(), 0.0, 0.0
        dataset = AnimeFrameDataset(list(frame_paths), self.preprocess)
        pin = self.device == "cuda"
        dataloader = DataLoader(
            dataset,
            batch_size=batch_size,
            shuffle=False,
            num_workers=num_workers,
            pin_memory=pin,
        )
        all_features: List[np.ndarray] = []
        start_time = time.perf_counter()
        with torch.no_grad():
            for batch_idx, images in enumerate(dataloader):
                images = images.to(self.device)
                features = self.model.encode_image(images)
                features /= features.norm(dim=-1, keepdim=True)
                all_features.append(features.cpu().numpy())
                if verbose and log_batches_every > 0 and (batch_idx + 1) % log_batches_every == 0:
                    print(f"Processed batch {batch_idx + 1}/{len(dataloader)}...")
        _sync_device(self.device)
        final_matrix = np.vstack(all_features)
        elapsed = time.perf_counter() - start_time
        fps = len(frame_paths) / elapsed if elapsed > 0 else 0.0
        if verbose:
            print(f"  >> Segment inference: {elapsed:.2f}s ({fps:.2f} frames/sec)")
        return final_matrix, elapsed, fps

    def encode_text_query(self, text: str) -> np.ndarray:
        """CLIP 텍스트 임베딩 (L2 정규화 1벡터)."""
        import clip
        import torch

        t = (text or "").strip() or " "
        tokens = clip.tokenize([t[:500]], truncate=True).to(self.device)
        with torch.no_grad():
            emb = self.model.encode_text(tokens)
            emb = emb / emb.norm(dim=-1, keepdim=True)
        return emb.cpu().numpy().astype(np.float32)[0]