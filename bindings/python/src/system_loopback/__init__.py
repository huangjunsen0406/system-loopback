"""Cross-platform zero-driver system audio loopback capture for Python.

Example:
    >>> from system_loopback import SystemLoopback
    >>> with SystemLoopback() as lb:
    ...     pcm = lb.read_f32(4800)  # float32 mono samples (numpy array if installed, else array('f'))
"""

from __future__ import annotations

import array
import ctypes
import os
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from ._native import SlbConfig, load_native_library

try:
    import numpy as _np
except ImportError:  # pragma: no cover - numpy is optional
    _np = None


class Status(IntEnum):
    """Status codes matching ``slb_status_t`` in ``system_loopback.h``."""

    OK = 0
    UNSUPPORTED = -1
    PERMISSION_DENIED = -2
    DEVICE_NOT_FOUND = -3
    INIT_FAILED = -4
    DEVICE_LOST = -5
    INVALID_ARG = -6


class LoopbackError(RuntimeError):
    """Base error raised by system-loopback operations."""

    def __init__(self, status: Status, message: str = "") -> None:
        self.status = status
        detail = f": {message}" if message else ""
        super().__init__(f"{status.name} ({int(status)}){detail}")


class UnsupportedPlatformError(LoopbackError):
    """Raised when the host OS or audio daemon does not support system loopback."""


class PermissionDeniedError(LoopbackError):
    """Raised when OS privacy permissions block system audio capture (e.g. macOS 14.2+ Audio Capture)."""


class DeviceNotFoundError(LoopbackError):
    """Raised when no active output or monitor audio device is available."""


class DeviceLostError(LoopbackError):
    """Raised when the captured output device is unplugged or invalidated mid-stream."""


_ERROR_MAP: dict[Status, type[LoopbackError]] = {
    Status.UNSUPPORTED: UnsupportedPlatformError,
    Status.PERMISSION_DENIED: PermissionDeniedError,
    Status.DEVICE_NOT_FOUND: DeviceNotFoundError,
    Status.DEVICE_LOST: DeviceLostError,
}

_DEFAULT_HINTS: dict[Status, str] = {
    Status.UNSUPPORTED: "OS or audio runtime does not support system loopback (macOS 14.2+, Windows 10+, Linux PipeWire/PulseAudio)",
    Status.PERMISSION_DENIED: "System audio capture permission denied (on macOS, enable 'System Audio Recording Only' for your terminal/app)",
    Status.DEVICE_NOT_FOUND: "No active output or monitor audio device found",
    Status.DEVICE_LOST: "Output audio device was disconnected or invalidated",
}


def _raise_for_status(code: int, message: str = "") -> None:
    try:
        status = Status(code)
    except ValueError:
        status = Status.INIT_FAILED
    exc_cls = _ERROR_MAP.get(status, LoopbackError)
    raise exc_cls(status, message or _DEFAULT_HINTS.get(status, ""))


@dataclass(frozen=True)
class LoopbackConfig:
    """Configuration for opening a :class:`SystemLoopback` capture stream."""

    device_name: str | None = None
    sample_rate_hint: int = 0
    exclude_pid: int = 0
    auto_start: bool = True
    library_path: str | os.PathLike[str] | None = None


def abi_version(library_path: str | os.PathLike[str] | None = None) -> int:
    """Return the compiled C ABI version of the loaded native library."""
    lib = load_native_library(library_path)
    return int(lib.slb_abi_version())


def backend_name(library_path: str | os.PathLike[str] | None = None) -> str:
    """Return the active native backend name (e.g. ``coreaudio-tap``, ``wasapi-loopback``)."""
    lib = load_native_library(library_path)
    raw = lib.slb_backend_name()
    return raw.decode("utf-8", errors="replace") if raw else ""


class SystemLoopback:
    """Non-blocking mono float32 system audio loopback stream."""

    def __init__(
        self,
        device_name: str | None = None,
        *,
        sample_rate_hint: int = 0,
        exclude_pid: int = 0,
        auto_start: bool = True,
        library_path: str | os.PathLike[str] | None = None,
        config: LoopbackConfig | None = None,
    ) -> None:
        if config is not None:
            device_name = config.device_name
            sample_rate_hint = config.sample_rate_hint
            exclude_pid = config.exclude_pid
            auto_start = config.auto_start
            library_path = config.library_path

        self._lib = load_native_library(library_path)
        self._handle = ctypes.c_void_p(0)
        self._closed = False
        self._sample_rate = 0
        self._channels = 1

        cfg = SlbConfig()
        self._lib.slb_config_init(ctypes.byref(cfg))
        self._device_bytes = device_name.encode("utf-8") if device_name else None
        cfg.device_name = self._device_bytes
        cfg.sample_rate_hint = int(sample_rate_hint)
        cfg.exclude_pid = int(exclude_pid)

        rate = ctypes.c_int(0)
        channels = ctypes.c_int(0)
        handle = ctypes.c_void_p(0)

        rc = self._lib.slb_create_ex(
            ctypes.byref(cfg),
            ctypes.byref(rate),
            ctypes.byref(channels),
            ctypes.byref(handle),
        )
        if rc != int(Status.OK) or not handle.value:
            raw_err = self._lib.slb_last_error(None)
            detail = raw_err.decode("utf-8", errors="replace") if raw_err else ""
            _raise_for_status(rc, detail)

        self._handle = handle
        self._sample_rate = int(rate.value) or 48000
        self._channels = int(channels.value) or 1

        if auto_start:
            try:
                self.start()
            except Exception:
                self.close()
                raise

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def channels(self) -> int:
        return self._channels

    @property
    def backend(self) -> str:
        raw = self._lib.slb_backend_name()
        return raw.decode("utf-8", errors="replace") if raw else ""

    def _last_error(self) -> str:
        if not self._handle or not self._handle.value:
            return ""
        raw = self._lib.slb_last_error(self._handle)
        return raw.decode("utf-8", errors="replace") if raw else ""

    def start(self) -> None:
        if self._closed or not self._handle.value:
            raise LoopbackError(Status.INVALID_ARG, "Stream is closed")
        rc = self._lib.slb_start(self._handle)
        if rc != int(Status.OK):
            _raise_for_status(rc, self._last_error())

    def stop(self) -> None:
        if not self._closed and self._handle and self._handle.value:
            self._lib.slb_stop(self._handle)

    def available_frames(self) -> int:
        if self._closed or not self._handle.value:
            return 0
        n = int(self._lib.slb_available_frames(self._handle))
        if n < 0:
            _raise_for_status(n, self._last_error())
        return n

    def read_f32(self, max_frames: int = 8192, *, as_numpy: bool = True) -> Any:
        """Non-blocking read of up to ``max_frames`` mono float32 samples in [-1.0, 1.0].

        Returns a ``numpy.ndarray`` if NumPy is installed and ``as_numpy=True``,
        otherwise returns a standard library ``array.array('f')``.
        """
        if self._closed or not self._handle.value:
            if as_numpy and _np is not None:
                return _np.empty(0, dtype=_np.float32)
            return array.array("f")

        if as_numpy and _np is not None:
            buf = _np.empty(max_frames, dtype=_np.float32)
            ptr = buf.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            n = int(self._lib.slb_read_f32(self._handle, ptr, int(max_frames)))
            if n < 0:
                _raise_for_status(n, self._last_error())
            return buf[:n]

        raw_buf = (ctypes.c_float * max_frames)()
        n = int(self._lib.slb_read_f32(self._handle, raw_buf, int(max_frames)))
        if n < 0:
            _raise_for_status(n, self._last_error())
        return array.array("f", raw_buf[:n])

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._handle and self._handle.value:
            try:
                self._lib.slb_stop(self._handle)
            finally:
                self._lib.slb_destroy(self._handle)
                self._handle = ctypes.c_void_p(0)

    def __enter__(self) -> SystemLoopback:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


__all__ = [
    "Status",
    "LoopbackConfig",
    "LoopbackError",
    "UnsupportedPlatformError",
    "PermissionDeniedError",
    "DeviceNotFoundError",
    "DeviceLostError",
    "SystemLoopback",
    "abi_version",
    "backend_name",
]
