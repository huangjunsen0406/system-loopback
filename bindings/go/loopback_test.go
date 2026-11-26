package systemloopback

import (
	"errors"
	"testing"
)

func TestABIAndBackend(t *testing.T) {
	v, err := ABIVersion("")
	if err != nil {
		t.Fatalf("ABIVersion failed: %v", err)
	}
	if v != ExpectedABIVersion {
		t.Fatalf("expected ABI %d, got %d", ExpectedABIVersion, v)
	}
	backend, err := BackendName("")
	if err != nil || backend == "" {
		t.Fatalf("BackendName failed: %q (%v)", backend, err)
	}
	t.Logf("ABI v%d | backend=%s", v, backend)
}

func TestOpenOrCleanError(t *testing.T) {
	stream, err := Open(Options{})
	if err != nil {
		if errors.Is(err, ErrPermissionDenied) || errors.Is(err, ErrUnsupported) {
			t.Logf("Expected environment limitation: %v", err)
			return
		}
		t.Fatalf("unexpected open error: %v", err)
	}
	defer stream.Close()

	if stream.SampleRate() < 8000 || stream.Channels() != 1 {
		t.Fatalf("unexpected format: %dHz %dch", stream.SampleRate(), stream.Channels())
	}
	buf := make([]float32, 256)
	if _, err := stream.ReadF32(buf); err != nil {
		t.Fatalf("ReadF32 failed: %v", err)
	}
}
