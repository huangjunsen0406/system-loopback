"""Unit tests for system_loopback Python bindings and AEC alignment helper."""

from __future__ import annotations

import unittest

from system_loopback import (
    LoopbackConfig,
    LoopbackError,
    PermissionDeniedError,
    Status,
    SystemLoopback,
    UnsupportedPlatformError,
    abi_version,
    backend_name,
)


class TestSystemLoopbackBinding(unittest.TestCase):
    def test_abi_and_backend(self) -> None:
        self.assertEqual(abi_version(), 1)
        name = backend_name()
        self.assertIn(name, {"coreaudio-tap", "wasapi-loopback", "pulseaudio-monitor"})

    def test_error_hierarchy(self) -> None:
        self.assertTrue(issubclass(PermissionDeniedError, LoopbackError))
        self.assertTrue(issubclass(UnsupportedPlatformError, LoopbackError))
        self.assertEqual(int(Status.OK), 0)

    def test_live_open_or_clean_platform_error(self) -> None:
        try:
            with SystemLoopback(config=LoopbackConfig()) as lb:
                self.assertGreaterEqual(lb.sample_rate, 8000)
                self.assertEqual(lb.channels, 1)
                _ = lb.available_frames()
                chunk = lb.read_f32(256, as_numpy=False)
                self.assertLessEqual(len(chunk), 256)
        except (PermissionDeniedError, UnsupportedPlatformError) as exc:
            # Headless CI or macOS without audio capture permission must fail cleanly.
            self.assertIn(exc.status, (Status.PERMISSION_DENIED, Status.UNSUPPORTED))


if __name__ == "__main__":
    unittest.main()
