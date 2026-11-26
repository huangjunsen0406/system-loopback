#!/usr/bin/env python3
"""Capture 3 seconds of system audio loopback and display a live RMS meter."""

import math
import time

from system_loopback import SystemLoopback


def main() -> None:
    with SystemLoopback() as lb:
        print(f"Backend: {lb.backend} | {lb.sample_rate}Hz | {lb.channels}ch")
        end = time.monotonic() + 3.0
        while time.monotonic() < end:
            time.sleep(0.05)
            samples = lb.read_f32(4800, as_numpy=False)
            if not samples:
                continue
            rms = math.sqrt(sum(s * s for s in samples) / len(samples))
            bar = "#" * min(40, int(rms * 200))
            print(f"frames={len(samples):4d}  rms={rms:.4f}  |{bar}")


if __name__ == "__main__":
    main()
