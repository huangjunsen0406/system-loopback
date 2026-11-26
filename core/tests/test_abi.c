/*
 * test_abi.c - Unit tests for lock-free SPSC ring buffer and public C ABI contracts.
 */

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "system_loopback.h"
#include "ring_buffer.h"

static void test_ring_basic_and_wraparound(void) {
    slb_ring_t ring;
    slb_ring_init(&ring);
    assert(slb_ring_available(&ring) == 0u);

    float in[1024];
    float out[1024];
    for (int i = 0; i < 1024; ++i) in[i] = (float)i * 0.001f;

    /* Push past SLB_RING_CAPACITY to exercise wraparound. */
    for (int round = 0; round < 40; ++round) {
        uint32_t w = slb_ring_write(&ring, in, 1024);
        assert(w == 1024u);
        assert(slb_ring_available(&ring) == 1024u);
        uint32_t r = slb_ring_read_latest(&ring, out, 1024);
        assert(r == 1024u);
        assert(fabsf(out[0] - in[0]) < 1e-6f);
        assert(fabsf(out[1023] - in[1023]) < 1e-6f);
        assert(slb_ring_available(&ring) == 0u);
    }
}

static void test_ring_read_latest_skips_stale(void) {
    slb_ring_t ring;
    slb_ring_init(&ring);

    float a[100], b[100], out[50];
    for (int i = 0; i < 100; ++i) {
        a[i] = (float)i;
        b[i] = (float)(100 + i);
    }
    assert(slb_ring_write(&ring, a, 100) == 100u);
    assert(slb_ring_write(&ring, b, 100) == 100u);
    assert(slb_ring_available(&ring) == 200u);

    /* Asking for 50 frames must deliver frames [150..199] and drain queue. */
    uint32_t n = slb_ring_read_latest(&ring, out, 50);
    assert(n == 50u);
    assert(fabsf(out[0] - 150.0f) < 1e-6f);
    assert(fabsf(out[49] - 199.0f) < 1e-6f);
    assert(slb_ring_available(&ring) == 0u);
}

static void test_public_abi_guards(void) {
    assert(slb_abi_version() == SLB_ABI_VERSION);
    const char* backend = slb_backend_name();
    assert(backend != NULL && strlen(backend) > 0);
    printf("ABI v%u | backend=%s\n", slb_abi_version(), backend);

    slb_config_t cfg;
    slb_config_init(&cfg);
    assert(cfg.struct_size == sizeof(slb_config_t));

    /* NULL out_handle rejected. */
    assert(slb_create_ex(&cfg, NULL, NULL, NULL) == SLB_ERR_INVALID_ARG);

    /* Corrupt struct_size rejected. */
    SystemLoopback* handle = NULL;
    cfg.struct_size = 4;
    assert(slb_create_ex(&cfg, NULL, NULL, &handle) == SLB_ERR_INVALID_ARG);
    assert(handle == NULL);
    assert(slb_last_error(NULL) != NULL);

    /* NULL handle guards. */
    float buf[16];
    assert(slb_start(NULL) == SLB_ERR_INVALID_ARG);
    assert(slb_available_frames(NULL) == SLB_ERR_INVALID_ARG);
    assert(slb_read_f32(NULL, buf, 16) == SLB_ERR_INVALID_ARG);
    slb_stop(NULL);
    slb_destroy(NULL);
}

int main(void) {
    test_ring_basic_and_wraparound();
    test_ring_read_latest_skips_stale();
    test_public_abi_guards();
    printf("All C ABI tests passed.\n");
    return 0;
}
