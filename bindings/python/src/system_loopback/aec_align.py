"""Optional DSP timing alignment helpers for feeding system loopback into AEC3 / WebRTC APM.

Why this exists:
    OS system loopback taps sit downstream of the OS mixer, so loopback frames often arrive
    20ms~65ms *after* the microphone callback (non-causal negative delay). Adaptive FIR echo
    cancellers (like WebRTC AEC3) diverge unless the near-end microphone stream is delayed into
    the positive causal window and fed in strict 10ms 1:1 far->near interleaved subframes.
"""

from __future__ import annotations

from collections import deque
from typing import Callable

import numpy as np


def recommended_near_delay_ms(frame_duration_ms: int) -> int:
    """Compute safe near-end causal alignment delay for system loopback AEC.

    - 20ms / 40ms frames -> 80ms
    - 60ms frames        -> 100ms
    """
    return max(80, int(frame_duration_ms) + 40)


class CausalAecAligner:
    """Near-end causal FIFO + 10ms 1:1 far->near interleaver for system-level AEC.

    Example:
        >>> aligner = CausalAecAligner(sample_rate=16000, frame_duration_ms=60)
        >>> clean = aligner.process_block(
        ...     near_f32,
        ...     far_f32,
        ...     feed_far_10ms=apm_process_reverse,
        ...     process_near_10ms=apm_process_stream,
        ... )
    """

    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        frame_duration_ms: int = 60,
        near_delay_ms: int | None = None,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.subframe_samples = self.sample_rate // 100  # 10ms
        delay_ms = (
            int(near_delay_ms)
            if near_delay_ms is not None
            else recommended_near_delay_ms(frame_duration_ms)
        )
        delay_samples = int(self.sample_rate * delay_ms / 1000)
        self._near_fifo = np.zeros(delay_samples, dtype=np.float32)
        self._far_queue: deque[float] = deque()
        self._primed = False

    def push_far(self, far_f32: np.ndarray, *, block_samples: int) -> None:
        if len(far_f32):
            self._far_queue.extend(far_f32.tolist())
        # Discard stale startup pre-roll on the very first near-end callback.
        if not self._primed:
            self._primed = True
            excess = len(self._far_queue) - block_samples
            for _ in range(max(0, excess)):
                self._far_queue.popleft()

    def _pop_far_subframe(self) -> np.ndarray:
        n = self.subframe_samples
        if len(self._far_queue) >= n:
            return np.fromiter((self._far_queue.popleft() for _ in range(n)), dtype=np.float32, count=n)
        return np.zeros(n, dtype=np.float32)

    def process_block(
        self,
        near_f32: np.ndarray,
        far_f32: np.ndarray,
        *,
        feed_far_10ms: Callable[[np.ndarray], None],
        process_near_10ms: Callable[[np.ndarray], np.ndarray],
    ) -> np.ndarray:
        """Align near_f32 with far_f32 and execute 1:1 10ms interleaved AEC callbacks."""
        n = len(near_f32)
        if n == 0:
            return np.empty(0, dtype=np.float32)

        self.push_far(far_f32, block_samples=n)

        if len(self._near_fifo) > 0:
            combined = np.concatenate((self._near_fifo, near_f32))
            aligned_near = combined[:n]
            self._near_fifo = combined[n:]
        else:
            aligned_near = near_f32

        out = np.empty(n, dtype=np.float32)
        step = self.subframe_samples
        for off in range(0, n, step):
            feed_far_10ms(self._pop_far_subframe())
            sub = aligned_near[off : off + step]
            out[off : off + len(sub)] = process_near_10ms(sub)

        # Smoothly drain 1 extra 10ms frame when cross-clock drift exceeds 40ms.
        if len(self._far_queue) >= max(n, step * 4):
            feed_far_10ms(self._pop_far_subframe())

        return out
