# system-loopback (Node.js & Electron)

Zero-`node-gyp` Node.js & Electron binding powered by `koffi` over `libsystem_loopback`.

## Usage

```ts
import { SystemLoopback } from 'system-loopback';

const lb = new SystemLoopback({ excludePid: process.pid });
const pcm = lb.readF32(4800); // Float32Array in [-1.0, 1.0]
lb.close();
```

## Electron Packaging Checklist

1. **Keep polling off the renderer UI thread**: run `SystemLoopback` inside a Node `worker_threads` worker or the Electron main process, and transfer `Float32Array.buffer` over IPC/MessagePort.
2. **Unpack native binaries from `app.asar`** (`electron-builder`):
   ```json
   {
     "build": {
       "asarUnpack": ["**/system-loopback/prebuilds/**"]
     }
   }
   ```
3. **macOS 14.2+ signing & privacy**:
   - Add `NSAudioCaptureUsageDescription` to your macOS `Info.plist`.
   - Ensure `libsystem_loopback.dylib` is codesigned along with your Electron `.app` bundle.
