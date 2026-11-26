# system-loopback

**Zero-driver, cross-platform system audio loopback capture with a minimal C ABI (`libsystem_loopback`) and native bindings for Python, Node.js / Electron, and Go.**

Capture everything playing out of the computer's speakers (for system-level AEC far-end reference in Voice AI apps, meeting transcription, or live audio metering) without installing BlackHole, VB-Cable, or any virtual audio driver—and without breaking system volume keys or triggering macOS VoiceProcessingIO media ducking.

## Platform Backends

| Platform | Native API | Min OS | Key Properties |
| --- | --- | --- | --- |
| **macOS** | Core Audio Process Tap (`CATapDescription` + Private Aggregate Device) | macOS 14.2+ | Weak-linked (`-mmacosx-version-min=11.0`); private tap does not pollute audio device lists; supports `exclude_pid`; `TapAutoStart = @NO` guarantees continuous silence frames |
| **Windows** | WASAPI Shared-Mode `AUDCLNT_STREAMFLAGS_LOOPBACK` | Windows 10+ | Runs COM `MTA` on a dedicated worker thread (safe alongside Qt / PySide6 / Electron `STA` UI threads); pads 10ms silence when speaker is idle |
| **Linux** | PulseAudio / PipeWire-Pulse (`pa_threaded_mainloop`) | PipeWire or PulseAudio | Runtime `dlopen("libpulse.so.0")` with zero compile-time hard dependency; records `@DEFAULT_MONITOR@` asynchronously |

## Architecture

All platforms share one pull-based C ABI (`core/include/system_loopback.h`) backed by a lock-free SPSC `float32` ring buffer (`32768` samples):

- **No host callbacks from OS audio threads**: real-time OS audio callbacks only execute lock-free `memcpy` into the ring buffer, avoiding Python GIL deadlocks, V8 thread-safety issues in Electron, and Go CGO/GC stalls.
- **Bounded latency**: `slb_read_f32` always drains the freshest window (`slb_ring_read_latest`), skipping stale overflow frames so far-end latency never drifts unboundedly.
- **Clean multi-language distribution**: build one tiny shared library (~30–60 KB) per target and consume it from C/C++, Python (`ctypes`), Node.js / Electron (`koffi`), Go (`purego`, zero CGO), Rust, or C#.

```text
system-loopback/
├── core/                  # Single source of truth: C ABI header + macOS/Windows/Linux backends + CMake
├── bindings/
│   ├── python/            # Zero-dependency ctypes package + optional CausalAecAligner helper
│   ├── node/              # TypeScript + koffi binding (Node.js & Electron asarUnpack-aware)
│   └── go/                # Zero-CGO Go module via ebitengine/purego
├── examples/              # Runnable C, Python, Node/Electron, and Go RMS capture samples
├── scripts/build_native.py
└── .github/workflows/     # Cross-platform CI & multi-target Release pipelines
```

## Quick Start

### 1. Build Native Library for Your Host

Using Python (zero CMake required):

```bash
python3 scripts/build_native.py --stage
```

Or using CMake (also compiles and runs `test_abi`):

```bash
cmake -S core -B build
cmake --build build
ctest --test-dir build --output-on-failure
```

### 2. Python

```bash
pip install -e bindings/python
python3 examples/python/capture_rms.py
```

```python
from system_loopback import SystemLoopback

with SystemLoopback() as lb:
    print(lb.backend, lb.sample_rate, lb.channels)
    pcm = lb.read_f32(4800)  # mono float32 in [-1.0, 1.0]
```

For Voice AI apps feeding system loopback into WebRTC AEC3, see `system_loopback.aec_align.CausalAecAligner` (handles OS loopback non-causal negative delay via a near-end causal FIFO and 10ms 1:1 `far -> near` interleaving).

### 3. Node.js & Electron

```bash
cd bindings/node && npm install && npm run build
node ../../examples/node/capture_rms.mjs
```

```ts
import { SystemLoopback } from 'system-loopback';

const lb = new SystemLoopback();
const pcm = lb.readF32(4800); // Float32Array
lb.close();
```

In Electron, read from a `worker_threads` worker (or main-process timer) and unpack `prebuilds/` in `electron-builder` via `asarUnpack: ["**/system-loopback/prebuilds/**"]`. See [bindings/node/README.md](bindings/node/README.md).

### 4. Go (Zero CGO)

```bash
cd bindings/go && go test -v ./...
```

```go
stream, err := systemloopback.Open(systemloopback.Options{})
if err != nil {
    log.Fatal(err)
}
defer stream.Close()

buf := make([]float32, 4800)
n, err := stream.ReadF32(buf)
```

## macOS 14.2+ Permission Note

Core Audio Process Tap requires macOS **"System Audio Recording Only"** privacy permission:

- Running from a terminal: grant permission to your terminal app (Terminal, iTerm2, VS Code) under **System Settings → Privacy & Security → Screen & System Audio Recording → System Audio Recording Only**.
- Shipping an `.app` bundle (Electron / PyInstaller / Go): include `NSAudioCaptureUsageDescription` in `Info.plist` and codesign `libsystem_loopback.dylib` with your app identity.

## License

MIT
