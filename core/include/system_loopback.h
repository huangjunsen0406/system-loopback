/*
 * system_loopback.h - Cross-platform system audio loopback capture C ABI (v1).
 *
 * Zero third-party audio drivers required:
 *   - macOS 14.2+: Core Audio Process Tap (CATapDescription + Private Aggregate Device)
 *   - Windows 10+: WASAPI shared-mode loopback on a dedicated MTA worker thread
 *   - Linux:       PulseAudio / PipeWire-Pulse async monitor via runtime dlopen
 *
 * Designed as a clean, pull-based C ABI for multi-language FFI (Python, Go,
 * Node.js / Electron, Rust, C/C++, C#):
 *   - OS real-time audio callbacks never invoke host-language callbacks.
 *   - Audio flows through an internal lock-free SPSC float32 ring buffer.
 *   - All functions use opaque handles and library-owned error buffers.
 */

#ifndef SYSTEM_LOOPBACK_H
#define SYSTEM_LOOPBACK_H

#include <stdint.h>

#define SLB_ABI_VERSION 1u

#if defined(_WIN32)
  #if defined(SLB_STATIC)
    #define SLB_API
  #elif defined(SLB_EXPORTS)
    #define SLB_API __declspec(dllexport)
  #else
    #define SLB_API __declspec(dllimport)
  #endif
#else
  #define SLB_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef struct SystemLoopback SystemLoopback;

typedef enum slb_status {
    SLB_OK = 0,
    SLB_ERR_UNSUPPORTED = -1,       /* OS/runtime does not support system loopback */
    SLB_ERR_PERMISSION_DENIED = -2, /* OS privacy permission denied */
    SLB_ERR_DEVICE_NOT_FOUND = -3,  /* No active output or monitor device found */
    SLB_ERR_INIT_FAILED = -4,       /* Backend initialization error */
    SLB_ERR_DEVICE_LOST = -5,       /* Output device invalidated/disconnected */
    SLB_ERR_INVALID_ARG = -6        /* Invalid argument or ABI struct_size */
} slb_status_t;

/*
 * Versioned creation configuration.
 * Always initialize with slb_config_init(&cfg) or set struct_size = sizeof(slb_config_t).
 */
typedef struct slb_config {
    uint32_t struct_size;        /* Must be sizeof(slb_config_t) */
    const char* device_name;     /* Optional UTF-8 output/monitor hint (NULL/"" = default) */
    uint32_t sample_rate_hint;   /* Optional hint (0 = backend default; honored on Linux) */
    uint32_t exclude_pid;        /* Optional PID to exclude from capture (0 = capture all; macOS 14.2+) */
    uint32_t flags;              /* Reserved for future use; must be 0 */
} slb_config_t;

/* Returns SLB_ABI_VERSION compiled into this shared library. */
SLB_API uint32_t slb_abi_version(void);

/* Returns static backend identifier ("coreaudio-tap", "wasapi-loopback", "pulseaudio-monitor"). */
SLB_API const char* slb_backend_name(void);

/* Populate slb_config_t with default values and struct_size. */
SLB_API void slb_config_init(slb_config_t* cfg);

/*
 * Create a system loopback capture handle with versioned config.
 *
 * cfg:             optional config (NULL uses defaults).
 * out_sample_rate: receives actual native capture sample rate in Hz (optional).
 * out_channels:    receives output channel count, currently always 1 (mono float32, optional).
 * out_handle:      receives opaque handle on SLB_OK; caller must call slb_destroy().
 */
SLB_API slb_status_t slb_create_ex(
    const slb_config_t* cfg,
    int* out_sample_rate,
    int* out_channels,
    SystemLoopback** out_handle
);

/*
 * Convenience wrapper over slb_create_ex() taking only an optional device hint.
 */
SLB_API slb_status_t slb_create(
    const char* target_device_name,
    int* out_sample_rate,
    int* out_channels,
    SystemLoopback** out_handle
);

/* Start streaming system loopback audio into the internal ring buffer (idempotent). */
SLB_API slb_status_t slb_start(SystemLoopback* handle);

/*
 * Return number of mono float32 frames currently buffered, or negative slb_status_t
 * (e.g. SLB_ERR_DEVICE_LOST / SLB_ERR_INVALID_ARG).
 */
SLB_API int slb_available_frames(SystemLoopback* handle);

/*
 * Non-blocking read of up to max_frames mono float32 samples in [-1.0, 1.0].
 * If more than max_frames are buffered, oldest stale frames are skipped so the
 * caller always receives the freshest time-aligned audio window.
 *
 * Returns >= 0 frames read, or a negative slb_status_t (e.g. SLB_ERR_DEVICE_LOST).
 */
SLB_API int slb_read_f32(SystemLoopback* handle, float* out_buf, int max_frames);

/*
 * Returns the last diagnostic error string (never NULL; "" when none).
 * Passing NULL returns the last creation failure message.
 * Pointer is library-owned; caller MUST NOT free it.
 */
SLB_API const char* slb_last_error(SystemLoopback* handle);

/* Stop capture (idempotent). */
SLB_API void slb_stop(SystemLoopback* handle);

/* Stop and release all resources (NULL-safe). */
SLB_API void slb_destroy(SystemLoopback* handle);

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* SYSTEM_LOOPBACK_H */
