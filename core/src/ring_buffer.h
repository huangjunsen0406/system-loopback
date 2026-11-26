/*
 * ring_buffer.h - Internal lock-free SPSC float32 ring buffer.
 *
 * Capacity is a power of two (32768 samples = ~682ms @ 48kHz, ~2048ms @ 16kHz).
 * Uses acquire/release atomics so OS real-time audio callbacks never block or
 * take locks against host consumer threads.
 */

#ifndef SYSTEM_LOOPBACK_RING_BUFFER_H
#define SYSTEM_LOOPBACK_RING_BUFFER_H

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#ifdef __cplusplus
  #include <atomic>
  #define SLB_ATOMIC_UINT64 std::atomic<uint64_t>
  #define SLB_ATOMIC_INT std::atomic<int>
  #define SLB_LOAD_ACQ(x) ((x).load(std::memory_order_acquire))
  #define SLB_LOAD_RELX(x) ((x).load(std::memory_order_relaxed))
  #define SLB_STORE_REL(x, v) ((x).store((v), std::memory_order_release))
  #define SLB_STORE_RELX(x, v) ((x).store((v), std::memory_order_relaxed))
#else
  #include <stdatomic.h>
  #define SLB_ATOMIC_UINT64 _Atomic uint64_t
  #define SLB_ATOMIC_INT _Atomic int
  #define SLB_LOAD_ACQ(x) atomic_load_explicit(&(x), memory_order_acquire)
  #define SLB_LOAD_RELX(x) atomic_load_explicit(&(x), memory_order_relaxed)
  #define SLB_STORE_REL(x, v) atomic_store_explicit(&(x), (v), memory_order_release)
  #define SLB_STORE_RELX(x, v) atomic_store_explicit(&(x), (v), memory_order_relaxed)
#endif

#define SLB_RING_CAPACITY 32768u
#define SLB_RING_MASK (SLB_RING_CAPACITY - 1u)

typedef struct slb_ring_t {
    float data[SLB_RING_CAPACITY];
    SLB_ATOMIC_UINT64 write_pos;
    SLB_ATOMIC_UINT64 read_pos;
} slb_ring_t;

static inline void slb_ring_init(slb_ring_t* r) {
    SLB_STORE_RELX(r->write_pos, 0u);
    SLB_STORE_RELX(r->read_pos, 0u);
}

static inline uint32_t slb_ring_available(slb_ring_t* r) {
    uint64_t rd = SLB_LOAD_RELX(r->read_pos);
    uint64_t w = SLB_LOAD_ACQ(r->write_pos);
    uint64_t avail = w - rd;
    return avail > SLB_RING_CAPACITY ? SLB_RING_CAPACITY : (uint32_t)avail;
}

static inline uint32_t slb_ring_write(slb_ring_t* r, const float* src, uint32_t count) {
    if (!count || !src) return 0u;
    uint64_t w = SLB_LOAD_RELX(r->write_pos);
    uint64_t rd = SLB_LOAD_ACQ(r->read_pos);
    uint64_t used = w - rd;
    if (used >= SLB_RING_CAPACITY) return 0u;
    uint32_t free_space = (uint32_t)(SLB_RING_CAPACITY - used);
    uint32_t n = count < free_space ? count : free_space;
    uint32_t idx = (uint32_t)(w & SLB_RING_MASK);
    uint32_t first = SLB_RING_CAPACITY - idx;
    if (first >= n) {
        memcpy(&r->data[idx], src, (size_t)n * sizeof(float));
    } else {
        memcpy(&r->data[idx], src, (size_t)first * sizeof(float));
        memcpy(&r->data[0], src + first, (size_t)(n - first) * sizeof(float));
    }
    SLB_STORE_REL(r->write_pos, w + n);
    return n;
}

static inline uint32_t slb_ring_write_zeros(slb_ring_t* r, uint32_t count) {
    if (!count) return 0u;
    uint64_t w = SLB_LOAD_RELX(r->write_pos);
    uint64_t rd = SLB_LOAD_ACQ(r->read_pos);
    uint64_t used = w - rd;
    if (used >= SLB_RING_CAPACITY) return 0u;
    uint32_t free_space = (uint32_t)(SLB_RING_CAPACITY - used);
    uint32_t n = count < free_space ? count : free_space;
    uint32_t idx = (uint32_t)(w & SLB_RING_MASK);
    uint32_t first = SLB_RING_CAPACITY - idx;
    if (first >= n) {
        memset(&r->data[idx], 0, (size_t)n * sizeof(float));
    } else {
        memset(&r->data[idx], 0, (size_t)first * sizeof(float));
        memset(&r->data[0], 0, (size_t)(n - first) * sizeof(float));
    }
    SLB_STORE_REL(r->write_pos, w + n);
    return n;
}

/*
 * Read the freshest samples up to max_frames; if more are queued, skip oldest
 * frames so far-end latency never accumulates unboundedly.
 */
static inline uint32_t slb_ring_read_latest(slb_ring_t* r, float* dst, uint32_t max_frames) {
    if (!max_frames || !dst) return 0u;
    uint64_t rd = SLB_LOAD_RELX(r->read_pos);
    uint64_t w = SLB_LOAD_ACQ(r->write_pos);
    uint64_t avail = w - rd;
    if (avail == 0u) return 0u;
    uint64_t start = rd;
    uint32_t n;
    if (avail > (uint64_t)max_frames) {
        start = w - (uint64_t)max_frames;
        n = max_frames;
    } else {
        n = (uint32_t)avail;
    }
    uint32_t idx = (uint32_t)(start & SLB_RING_MASK);
    uint32_t first = SLB_RING_CAPACITY - idx;
    if (first >= n) {
        memcpy(dst, &r->data[idx], (size_t)n * sizeof(float));
    } else {
        memcpy(dst, &r->data[idx], (size_t)first * sizeof(float));
        memcpy(dst + first, &r->data[0], (size_t)(n - first) * sizeof(float));
    }
    SLB_STORE_REL(r->read_pos, w);
    return n;
}

#endif /* SYSTEM_LOOPBACK_RING_BUFFER_H */
