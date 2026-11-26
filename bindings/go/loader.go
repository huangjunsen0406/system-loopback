package systemloopback

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
)

func platformTagAndLib() (string, string, error) {
	arch := runtime.GOARCH
	switch arch {
	case "amd64":
		arch = "x64"
	case "arm64":
		arch = "arm64"
	}

	switch runtime.GOOS {
	case "darwin":
		return "darwin-" + arch, "libsystem_loopback.dylib", nil
	case "windows":
		return "win32-" + arch, "system_loopback.dll", nil
	case "linux":
		return "linux-" + arch, "libsystem_loopback.so", nil
	default:
		return "", "", fmt.Errorf("systemloopback: unsupported OS %s", runtime.GOOS)
	}
}

// ResolveLibraryPath locates libsystem_loopback in priority order:
//  1. explicit path argument
//  2. SLB_LIBRARY_PATH environment variable
//  3. ./prebuilds/<os>-<arch>/ next to source or executable
//  4. monorepo ../../dist/native/<os>-<arch>/
//  5. OS dynamic loader search path
func ResolveLibraryPath(explicitPath string) (string, error) {
	if explicitPath != "" {
		if _, err := os.Stat(explicitPath); err == nil {
			return explicitPath, nil
		}
		return "", fmt.Errorf("systemloopback: explicit library not found: %s", explicitPath)
	}

	if envPath := os.Getenv("SLB_LIBRARY_PATH"); envPath != "" {
		if _, err := os.Stat(envPath); err == nil {
			return envPath, nil
		}
		return "", fmt.Errorf("systemloopback: SLB_LIBRARY_PATH does not exist: %s", envPath)
	}

	tag, filename, err := platformTagAndLib()
	if err != nil {
		return "", err
	}

	var candidates []string
	if _, srcFile, _, ok := runtime.Caller(0); ok {
		dir := filepath.Dir(srcFile)
		candidates = append(candidates,
			filepath.Join(dir, "prebuilds", tag, filename),
			filepath.Join(dir, "..", "..", "dist", "native", tag, filename),
		)
	}
	if exe, err := os.Executable(); err == nil {
		exeDir := filepath.Dir(exe)
		candidates = append(candidates,
			filepath.Join(exeDir, filename),
			filepath.Join(exeDir, "prebuilds", tag, filename),
		)
	}

	for _, c := range candidates {
		if _, err := os.Stat(c); err == nil {
			return c, nil
		}
	}
	return filename, nil
}
