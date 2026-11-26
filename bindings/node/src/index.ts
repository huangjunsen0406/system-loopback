import koffi from 'koffi';
import { resolveLibraryPath } from './loader.js';

export const EXPECTED_ABI_VERSION = 1;

export enum LoopbackStatus {
  OK = 0,
  UNSUPPORTED = -1,
  PERMISSION_DENIED = -2,
  DEVICE_NOT_FOUND = -3,
  INIT_FAILED = -4,
  DEVICE_LOST = -5,
  INVALID_ARG = -6,
}

export class LoopbackError extends Error {
  public readonly status: LoopbackStatus;
  constructor(status: LoopbackStatus, detail = '') {
    const label = LoopbackStatus[status] ?? 'UNKNOWN';
    super(detail ? `${label} (${status}): ${detail}` : `${label} (${status})`);
    this.name = 'LoopbackError';
    this.status = status;
  }
}

export interface LoopbackOptions {
  deviceName?: string;
  sampleRateHint?: number;
  excludePid?: number;
  autoStart?: boolean;
  libraryPath?: string;
}

const SlbConfig = koffi.struct('slb_config_t', {
  struct_size: 'uint32',
  device_name: 'str',
  sample_rate_hint: 'uint32',
  exclude_pid: 'uint32',
  flags: 'uint32',
});

interface NativeApi {
  slb_abi_version: () => number;
  slb_backend_name: () => string;
  slb_config_init: (cfg: Record<string, unknown>) => void;
  slb_create_ex: (
    cfg: Record<string, unknown> | null,
    outRate: Int32Array,
    outChannels: Int32Array,
    outHandle: unknown[],
  ) => number;
  slb_start: (handle: unknown) => number;
  slb_available_frames: (handle: unknown) => number;
  slb_read_f32: (handle: unknown, outBuf: Float32Array, maxFrames: number) => number;
  slb_last_error: (handle: unknown | null) => string;
  slb_stop: (handle: unknown) => void;
  slb_destroy: (handle: unknown) => void;
}

const apiCache = new Map<string, NativeApi>();

function loadApi(explicitPath?: string): NativeApi {
  const libPath = resolveLibraryPath(explicitPath);
  const cached = apiCache.get(libPath);
  if (cached) return cached;

  const lib = koffi.load(libPath);
  const api: NativeApi = {
    slb_abi_version: lib.func('uint32 slb_abi_version()'),
    slb_backend_name: lib.func('str slb_backend_name()'),
    slb_config_init: lib.func('void slb_config_init(_Out_ slb_config_t* cfg)'),
    slb_create_ex: lib.func(
      'int slb_create_ex(const slb_config_t* cfg, _Out_ int* out_sample_rate, _Out_ int* out_channels, _Out_ void** out_handle)',
    ),
    slb_start: lib.func('int slb_start(void* handle)'),
    slb_available_frames: lib.func('int slb_available_frames(void* handle)'),
    slb_read_f32: lib.func('int slb_read_f32(void* handle, _Out_ float* out_buf, int max_frames)'),
    slb_last_error: lib.func('str slb_last_error(void* handle)'),
    slb_stop: lib.func('void slb_stop(void* handle)'),
    slb_destroy: lib.func('void slb_destroy(void* handle)'),
  };

  const abi = api.slb_abi_version();
  if (abi !== EXPECTED_ABI_VERSION) {
    throw new Error(`Incompatible libsystem_loopback ABI: expected v${EXPECTED_ABI_VERSION}, got v${abi}`);
  }

  apiCache.set(libPath, api);
  return api;
}

export function abiVersion(libraryPath?: string): number {
  return loadApi(libraryPath).slb_abi_version();
}

export function backendName(libraryPath?: string): string {
  return loadApi(libraryPath).slb_backend_name();
}

export class SystemLoopback {
  private readonly api: NativeApi;
  private handle: unknown | null = null;
  private closed = false;
  public readonly sampleRate: number;
  public readonly channels: number;
  public readonly backend: string;

  constructor(options: LoopbackOptions = {}) {
    this.api = loadApi(options.libraryPath);
    this.backend = this.api.slb_backend_name();

    const cfg = {
      struct_size: koffi.sizeof(SlbConfig),
      device_name: options.deviceName ?? null,
      sample_rate_hint: options.sampleRateHint ?? 0,
      exclude_pid: options.excludePid ?? 0,
      flags: 0,
    };

    const rateOut = new Int32Array(1);
    const chOut = new Int32Array(1);
    const handleOut: unknown[] = [null];

    const rc = this.api.slb_create_ex(cfg, rateOut, chOut, handleOut);
    if (rc !== LoopbackStatus.OK || !handleOut[0]) {
      const msg = this.api.slb_last_error(null);
      throw new LoopbackError(rc as LoopbackStatus, msg);
    }

    this.handle = handleOut[0];
    this.sampleRate = rateOut[0] || 48000;
    this.channels = chOut[0] || 1;

    if (options.autoStart !== false) {
      try {
        this.start();
      } catch (err) {
        this.close();
        throw err;
      }
    }
  }

  start(): void {
    if (this.closed || !this.handle) {
      throw new LoopbackError(LoopbackStatus.INVALID_ARG, 'Stream is closed');
    }
    const rc = this.api.slb_start(this.handle);
    if (rc !== LoopbackStatus.OK) {
      throw new LoopbackError(rc as LoopbackStatus, this.api.slb_last_error(this.handle));
    }
  }

  stop(): void {
    if (!this.closed && this.handle) {
      this.api.slb_stop(this.handle);
    }
  }

  availableFrames(): number {
    if (this.closed || !this.handle) return 0;
    const n = this.api.slb_available_frames(this.handle);
    if (n < 0) {
      throw new LoopbackError(n as LoopbackStatus, this.api.slb_last_error(this.handle));
    }
    return n;
  }

  /** Non-blocking read of up to maxFrames mono float32 samples in [-1.0, 1.0]. */
  readF32(maxFrames = 4800): Float32Array {
    if (this.closed || !this.handle) return new Float32Array(0);
    const buf = new Float32Array(maxFrames);
    const n = this.api.slb_read_f32(this.handle, buf, maxFrames);
    if (n < 0) {
      throw new LoopbackError(n as LoopbackStatus, this.api.slb_last_error(this.handle));
    }
    return n === maxFrames ? buf : buf.subarray(0, n);
  }

  close(): void {
    if (this.closed) return;
    this.closed = true;
    if (this.handle) {
      const h = this.handle;
      this.handle = null;
      try {
        this.api.slb_stop(h);
      } finally {
        this.api.slb_destroy(h);
      }
    }
  }
}
