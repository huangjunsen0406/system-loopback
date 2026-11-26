"""Low-level ctypes loader for libsystem_loopback."""

from __future__ import annotations

import ctypes
import os
import platform
from pathlib import Path

EXPECTED_ABI_VERSION = 1


class SlbConfig(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("device_name", ctypes.c_char_p),
        ("sample_rate_hint", ctypes.c_uint32),
        ("exclude_pid", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
    ]


def platform_tag() -> tuple[str, str]:
    """Return (platform_dir, library_filename) for the current host."""
    sys_name = platform.system().lower()
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        arch = "arm64"
    elif machine in ("x86_64", "amd64"):
        arch = "x64"
    else:
        arch = machine

    if sys_name == "darwin":
        return f"darwin-{arch}", "libsystem_loopback.dylib"
    if sys_name == "windows":
        return f"win32-{arch}", "system_loopback.dll"
    if sys_name == "linux":
        return f"linux-{arch}", "libsystem_loopback.so"
    raise RuntimeError(f"Unsupported platform: {sys_name}")


def resolve_library_path(explicit_path: str | os.PathLike[str] | None = None) -> str:
    """Resolve the native library via explicit path, env var, bundled wheel, repo dist, or system search."""
    if explicit_path:
        p = Path(explicit_path)
        if p.exists():
            return str(p)
        raise FileNotFoundError(f"Explicit system_loopback library not found: {p}")

    env_path = os.environ.get("SLB_LIBRARY_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return str(p)
        raise FileNotFoundError(f"SLB_LIBRARY_PATH does not exist: {p}")

    plat_dir, lib_name = platform_tag()
    pkg_root = Path(__file__).resolve().parent
    candidates = [
        pkg_root / "_libs" / plat_dir / lib_name,
        # Monorepo dev layout: bindings/python/src/system_loopback -> dist/native/<plat>/<lib>
        pkg_root.parents[3] / "dist" / "native" / plat_dir / lib_name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    # Fall back to OS dynamic loader (e.g. Homebrew / /usr/local/lib / PATH)
    return lib_name


_cached_lib: ctypes.CDLL | None = None


def load_native_library(explicit_path: str | os.PathLike[str] | None = None) -> ctypes.CDLL:
    global _cached_lib
    if _cached_lib is not None and explicit_path is None:
        return _cached_lib

    lib_path = resolve_library_path(explicit_path)
    try:
        lib = ctypes.CDLL(lib_path)
    except OSError as exc:
        raise FileNotFoundError(
            f"Unable to load {lib_path}. Build it via `python3 scripts/build_native.py --stage` "
            f"or set SLB_LIBRARY_PATH."
        ) from exc

    lib.slb_abi_version.argtypes = []
    lib.slb_abi_version.restype = ctypes.c_uint32

    abi = int(lib.slb_abi_version())
    if abi != EXPECTED_ABI_VERSION:
        raise RuntimeError(
            f"Incompatible libsystem_loopback ABI: expected v{EXPECTED_ABI_VERSION}, got v{abi}"
        )

    lib.slb_backend_name.argtypes = []
    lib.slb_backend_name.restype = ctypes.c_char_p

    lib.slb_config_init.argtypes = [ctypes.POINTER(SlbConfig)]
    lib.slb_config_init.restype = None

    lib.slb_create_ex.argtypes = [
        ctypes.POINTER(SlbConfig),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    lib.slb_create_ex.restype = ctypes.c_int

    lib.slb_start.argtypes = [ctypes.c_void_p]
    lib.slb_start.restype = ctypes.c_int

    lib.slb_available_frames.argtypes = [ctypes.c_void_p]
    lib.slb_available_frames.restype = ctypes.c_int

    lib.slb_read_f32.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_int,
    ]
    lib.slb_read_f32.restype = ctypes.c_int

    lib.slb_last_error.argtypes = [ctypes.c_void_p]
    lib.slb_last_error.restype = ctypes.c_char_p

    lib.slb_stop.argtypes = [ctypes.c_void_p]
    lib.slb_stop.restype = None

    lib.slb_destroy.argtypes = [ctypes.c_void_p]
    lib.slb_destroy.restype = None

    if explicit_path is None:
        _cached_lib = lib
    return lib
