#!/usr/bin/env python3
"""Compile libsystem_loopback for the current host and optionally stage into language bindings.

Zero third-party build dependencies:
  - macOS:   Apple clang + CoreAudio / Foundation / AudioToolbox (-mmacosx-version-min=11.0)
  - Windows: MSVC cl.exe (or MinGW g++) + ole32 / avrt / uuid
  - Linux:   gcc / clang + libdl / pthread (loads libpulse.so.0 via dlopen at runtime)

Usage:
    python3 scripts/build_native.py
    python3 scripts/build_native.py --arch arm64 --stage
    python3 scripts/build_native.py --arch all --stage    # macOS: arm64 + x64
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE_INC = ROOT / "core" / "include"
CORE_SRC = ROOT / "core" / "src"
DIST_ROOT = ROOT / "dist" / "native"


def host_arch() -> str:
    m = platform.machine().lower()
    if m in ("arm64", "aarch64"):
        return "arm64"
    if m in ("x86_64", "amd64"):
        return "x64"
    return m


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def build_macos(arch: str) -> Path:
    clang = shutil.which("clang")
    if not clang:
        raise RuntimeError("clang not found (install Xcode Command Line Tools)")
    clang_arch = "arm64" if arch == "arm64" else "x86_64"
    out_dir = DIST_ROOT / f"darwin-{arch}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "libsystem_loopback.dylib"

    run(
        [
            clang,
            "-shared",
            "-O2",
            "-Wall",
            "-Wextra",
            "-fobjc-arc",
            "-fvisibility=hidden",
            "-arch",
            clang_arch,
            "-mmacosx-version-min=11.0",
            f"-I{CORE_INC}",
            f"-I{CORE_SRC}",
            str(CORE_SRC / "macos_tap.m"),
            "-framework",
            "CoreAudio",
            "-framework",
            "Foundation",
            "-framework",
            "AudioToolbox",
            "-install_name",
            "@rpath/libsystem_loopback.dylib",
            "-o",
            str(out_path),
        ]
    )
    return out_path


def build_linux(arch: str) -> Path:
    cc = shutil.which("gcc") or shutil.which("clang") or shutil.which("cc")
    if not cc:
        raise RuntimeError("gcc/clang not found")
    out_dir = DIST_ROOT / f"linux-{arch}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "libsystem_loopback.so"

    run(
        [
            cc,
            "-shared",
            "-fPIC",
            "-O2",
            "-Wall",
            "-Wextra",
            "-fvisibility=hidden",
            f"-I{CORE_INC}",
            f"-I{CORE_SRC}",
            str(CORE_SRC / "linux_pulse.c"),
            "-ldl",
            "-lpthread",
            "-o",
            str(out_path),
        ]
    )
    return out_path


def build_windows(arch: str) -> Path:
    out_dir = DIST_ROOT / f"win32-{arch}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "system_loopback.dll"
    src = CORE_SRC / "windows_wasapi.cpp"

    cl = shutil.which("cl") or shutil.which("cl.exe")
    if cl:
        obj_path = out_dir / "windows_wasapi.obj"
        run(
            [
                cl,
                "/nologo",
                "/LD",
                "/O2",
                "/EHsc",
                "/W3",
                "/std:c++17",
                "/DSLB_EXPORTS",
                f"/I{CORE_INC}",
                f"/I{CORE_SRC}",
                str(src),
                f"/Fo{obj_path}",
                f"/Fe{out_path}",
                "ole32.lib",
                "avrt.lib",
                "uuid.lib",
            ],
            cwd=out_dir,
        )
        for ext in (".obj", ".exp", ".lib"):
            junk = out_dir / f"system_loopback{ext}"
            if junk.exists():
                junk.unlink()
        if obj_path.exists():
            obj_path.unlink()
        return out_path

    gxx = shutil.which("g++") or shutil.which("clang++")
    if gxx:
        run(
            [
                gxx,
                "-shared",
                "-O2",
                "-std=c++17",
                "-DSLB_EXPORTS",
                f"-I{CORE_INC}",
                f"-I{CORE_SRC}",
                str(src),
                "-lole32",
                "-lavrt",
                "-luuid",
                "-o",
                str(out_path),
            ]
        )
        return out_path

    raise RuntimeError("No Windows C++ compiler found in PATH")


def stage_into_bindings(built_path: Path) -> None:
    """Copy compiled binary into python, node, and go prebuild directories."""
    plat_tag = built_path.parent.name  # e.g. darwin-arm64
    targets = [
        ROOT / "bindings" / "python" / "src" / "system_loopback" / "_libs" / plat_tag,
        ROOT / "bindings" / "node" / "prebuilds" / plat_tag,
        ROOT / "bindings" / "go" / "prebuilds" / plat_tag,
    ]
    for dst_dir in targets:
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(built_path, dst_dir / built_path.name)
        print(f"Staged -> {dst_dir / built_path.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", default=host_arch(), help="arm64, x64, or 'all' (macOS)")
    parser.add_argument(
        "--stage",
        action="store_true",
        help="Copy built artifacts into bindings/{python,node,go}",
    )
    args = parser.parse_args()

    system = platform.system().lower()
    if system == "darwin":
        arches = ["arm64", "x64"] if args.arch == "all" else [args.arch]
        built = [build_macos(a) for a in arches]
    elif system == "linux":
        built = [build_linux(args.arch)]
    elif system == "windows":
        built = [build_windows(args.arch)]
    else:
        raise RuntimeError(f"Unsupported platform: {system}")

    for path in built:
        print(f"Built: {path} ({path.stat().st_size} bytes)")
        if args.stage:
            stage_into_bindings(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
