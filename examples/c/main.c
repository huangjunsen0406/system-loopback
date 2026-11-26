/*
 * Minimal C example: capture 3 seconds of system audio loopback and print live RMS.
 */
#include <math.h>
#include <stdio.h>
#ifdef _WIN32
  #include <windows.h>
  static void sleep_ms(int ms) { Sleep((DWORD)ms); }
#else
  #include <unistd.h>
  static void sleep_ms(int ms) { usleep((useconds_t)ms * 1000u); }
#endif

#include "system_loopback.h"

int main(void) {
    slb_config_t cfg;
    slb_config_init(&cfg);

    int rate = 0, ch = 0;
    SystemLoopback* lb = NULL;
    slb_status_t rc = slb_create_ex(&cfg, &rate, &ch, &lb);
    if (rc != SLB_OK) {
        fprintf(stderr, "slb_create_ex failed (%d): %s\n", rc, slb_last_error(NULL));
        return 1;
    }
    if (slb_start(lb) != SLB_OK) {
        fprintf(stderr, "slb_start failed: %s\n", slb_last_error(lb));
        slb_destroy(lb);
        return 1;
    }

    printf("Capturing [%s] %dHz %dch for 3s...\n", slb_backend_name(), rate, ch);
    float buf[4800];
    for (int i = 0; i < 60; ++i) {
        sleep_ms(50);
        int n = slb_read_f32(lb, buf, 4800);
        if (n < 0) {
            fprintf(stderr, "read error (%d): %s\n", n, slb_last_error(lb));
            break;
        }
        if (n == 0) continue;
        double sum = 0.0;
        for (int k = 0; k < n; ++k) sum += (double)buf[k] * (double)buf[k];
        double rms = sqrt(sum / n);
        printf("frames=%4d  rms=%.4f\n", n, rms);
    }

    slb_destroy(lb);
    return 0;
}
