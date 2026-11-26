# system-loopback (Python)

Cross-platform, zero-driver system audio loopback capture for Python.

## Install

```bash
pip install system-loopback
# Optional: NumPy array output & AEC causal alignment helper
pip install "system-loopback[aec]"
```

## Usage

```python
import time
from system_loopback import SystemLoopback

with SystemLoopback() as lb:
    print(f"{lb.backend}: {lb.sample_rate}Hz, {lb.channels}ch")
    time.sleep(0.1)
    pcm = lb.read_f32(4800)  # numpy.ndarray(float32) if numpy installed, else array('f')
```

### Overriding Library Path

If you installed `libsystem_loopback` system-wide or built a custom binary, set:

```bash
export SLB_LIBRARY_PATH=/path/to/libsystem_loopback.dylib
```
