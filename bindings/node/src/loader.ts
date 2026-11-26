import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export function platformInfo(): { tag: string; filename: string } {
  const arch = process.arch === 'arm64' ? 'arm64' : 'x64';
  if (process.platform === 'darwin') {
    return { tag: `darwin-${arch}`, filename: 'libsystem_loopback.dylib' };
  }
  if (process.platform === 'win32') {
    return { tag: `win32-${arch}`, filename: 'system_loopback.dll' };
  }
  if (process.platform === 'linux') {
    return { tag: `linux-${arch}`, filename: 'libsystem_loopback.so' };
  }
  throw new Error(`Unsupported platform: ${process.platform}`);
}

/**
 * Resolve libsystem_loopback across:
 *   1. Explicit path or SLB_LIBRARY_PATH env override
 *   2. Electron asarUnpack path (app.asar.unpacked)
 *   3. Bundled prebuilds/<platform-arch>/
 *   4. Monorepo dist/native/<platform-arch>/
 *   5. System dynamic library search path
 */
export function resolveLibraryPath(explicitPath?: string): string {
  if (explicitPath) {
    if (fs.existsSync(explicitPath)) return explicitPath;
    throw new Error(`Explicit system_loopback library not found: ${explicitPath}`);
  }

  const envPath = process.env.SLB_LIBRARY_PATH;
  if (envPath) {
    if (fs.existsSync(envPath)) return envPath;
    throw new Error(`SLB_LIBRARY_PATH does not exist: ${envPath}`);
  }

  const { tag, filename } = platformInfo();
  const pkgRoot = path.resolve(__dirname, '..');
  const rawCandidates = [
    path.join(pkgRoot, 'prebuilds', tag, filename),
    path.resolve(pkgRoot, '..', '..', 'dist', 'native', tag, filename),
  ];

  for (const candidate of rawCandidates) {
    // When packaged inside Electron app.asar, OS dlopen must target app.asar.unpacked.
    const unpacked = candidate.replace(/app\.asar([/\\])/i, 'app.asar.unpacked$1');
    if (fs.existsSync(unpacked)) return unpacked;
    if (fs.existsSync(candidate)) return candidate;
  }

  return filename;
}
