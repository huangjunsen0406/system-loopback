// Package systemloopback provides zero-CGO cross-platform system audio loopback
// capture for Go using ebitengine/purego against libsystem_loopback.
package systemloopback

import (
	"errors"
	"fmt"
	"sync"
	"unsafe"

	"github.com/ebitengine/purego"
)

const ExpectedABIVersion = 1

type Status int32

const (
	StatusOK               Status = 0
	StatusUnsupported      Status = -1
	StatusPermissionDenied Status = -2
	StatusDeviceNotFound   Status = -3
	StatusInitFailed       Status = -4
	StatusDeviceLost       Status = -5
	StatusInvalidArg       Status = -6
)

var (
	ErrUnsupported      = errors.New("systemloopback: unsupported OS or audio runtime")
	ErrPermissionDenied = errors.New("systemloopback: system audio capture permission denied")
	ErrDeviceNotFound   = errors.New("systemloopback: no active output device found")
	ErrDeviceLost       = errors.New("systemloopback: output device lost or invalidated")
)

type Error struct {
	Status  Status
	Message string
}

func (e *Error) Error() string {
	if e.Message != "" {
		return fmt.Sprintf("systemloopback: status %d: %s", e.Status, e.Message)
	}
	return fmt.Sprintf("systemloopback: status %d", e.Status)
}

func (e *Error) Unwrap() error {
	switch e.Status {
	case StatusUnsupported:
		return ErrUnsupported
	case StatusPermissionDenied:
		return ErrPermissionDenied
	case StatusDeviceNotFound:
		return ErrDeviceNotFound
	case StatusDeviceLost:
		return ErrDeviceLost
	default:
		return nil
	}
}

type slbConfig struct {
	StructSize     uint32
	_              uint32 // 64-bit alignment padding before pointer
	DeviceName     *byte
	SampleRateHint uint32
	ExcludePID     uint32
	Flags          uint32
	_              uint32
}

type Options struct {
	DeviceName     string
	SampleRateHint uint32
	ExcludePID     uint32
	LibraryPath    string
}

type nativeFns struct {
	abiVersion      func() uint32
	backendName     func() string
	createEx        func(cfg *slbConfig, outRate *int32, outCh *int32, outHandle *uintptr) int32
	start           func(handle uintptr) int32
	availableFrames func(handle uintptr) int32
	readF32         func(handle uintptr, outBuf *float32, maxFrames int32) int32
	lastError       func(handle uintptr) string
	stop            func(handle uintptr)
	destroy         func(handle uintptr)
}

var (
	libMu    sync.Mutex
	libCache = map[string]*nativeFns{}
)

func loadNative(explicitPath string) (*nativeFns, error) {
	libPath, err := ResolveLibraryPath(explicitPath)
	if err != nil {
		return nil, err
	}

	libMu.Lock()
	defer libMu.Unlock()
	if fns, ok := libCache[libPath]; ok {
		return fns, nil
	}

	dl, err := openLibrary(libPath)
	if err != nil {
		return nil, fmt.Errorf("systemloopback: load %s: %w", libPath, err)
	}

	fns := &nativeFns{}
	purego.RegisterLibFunc(&fns.abiVersion, dl, "slb_abi_version")
	purego.RegisterLibFunc(&fns.backendName, dl, "slb_backend_name")
	purego.RegisterLibFunc(&fns.createEx, dl, "slb_create_ex")
	purego.RegisterLibFunc(&fns.start, dl, "slb_start")
	purego.RegisterLibFunc(&fns.availableFrames, dl, "slb_available_frames")
	purego.RegisterLibFunc(&fns.readF32, dl, "slb_read_f32")
	purego.RegisterLibFunc(&fns.lastError, dl, "slb_last_error")
	purego.RegisterLibFunc(&fns.stop, dl, "slb_stop")
	purego.RegisterLibFunc(&fns.destroy, dl, "slb_destroy")

	if v := fns.abiVersion(); v != ExpectedABIVersion {
		return nil, fmt.Errorf("systemloopback: ABI mismatch (expected %d, got %d)", ExpectedABIVersion, v)
	}
	libCache[libPath] = fns
	return fns, nil
}

// ABIVersion returns the C ABI version of the loaded native library.
func ABIVersion(libraryPath string) (uint32, error) {
	fns, err := loadNative(libraryPath)
	if err != nil {
		return 0, err
	}
	return fns.abiVersion(), nil
}

// BackendName returns the native backend identifier (e.g. "coreaudio-tap").
func BackendName(libraryPath string) (string, error) {
	fns, err := loadNative(libraryPath)
	if err != nil {
		return "", err
	}
	return fns.backendName(), nil
}

// Stream represents an active system audio loopback capture handle.
type Stream struct {
	fns        *nativeFns
	handle     uintptr
	sampleRate int
	channels   int
	backend    string
	closed     bool
	mu         sync.Mutex
}

// Open creates and starts a system audio loopback stream.
func Open(opts Options) (*Stream, error) {
	fns, err := loadNative(opts.LibraryPath)
	if err != nil {
		return nil, err
	}

	var devBytes []byte
	var devPtr *byte
	if opts.DeviceName != "" {
		devBytes = append([]byte(opts.DeviceName), 0)
		devPtr = &devBytes[0]
	}

	cfg := slbConfig{
		StructSize:     uint32(unsafe.Sizeof(slbConfig{})),
		DeviceName:     devPtr,
		SampleRateHint: opts.SampleRateHint,
		ExcludePID:     opts.ExcludePID,
	}

	var rate, ch int32
	var handle uintptr
	rc := Status(fns.createEx(&cfg, &rate, &ch, &handle))
	if rc != StatusOK || handle == 0 {
		return nil, &Error{Status: rc, Message: fns.lastError(0)}
	}

	if startRC := Status(fns.start(handle)); startRC != StatusOK {
		msg := fns.lastError(handle)
		fns.destroy(handle)
		return nil, &Error{Status: startRC, Message: msg}
	}

	if rate <= 0 {
		rate = 48000
	}
	if ch <= 0 {
		ch = 1
	}

	return &Stream{
		fns:        fns,
		handle:     handle,
		sampleRate: int(rate),
		channels:   int(ch),
		backend:    fns.backendName(),
	}, nil
}

func (s *Stream) SampleRate() int { return s.sampleRate }
func (s *Stream) Channels() int   { return s.channels }
func (s *Stream) Backend() string { return s.backend }

// AvailableFrames returns the number of mono float32 frames queued in the ring buffer.
func (s *Stream) AvailableFrames() (int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed || s.handle == 0 {
		return 0, nil
	}
	n := s.fns.availableFrames(s.handle)
	if n < 0 {
		return 0, &Error{Status: Status(n), Message: s.fns.lastError(s.handle)}
	}
	return int(n), nil
}

// ReadF32 performs a non-blocking read of up to len(dst) mono float32 samples into dst.
func (s *Stream) ReadF32(dst []float32) (int, error) {
	if len(dst) == 0 {
		return 0, nil
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed || s.handle == 0 {
		return 0, nil
	}
	n := s.fns.readF32(s.handle, &dst[0], int32(len(dst)))
	if n < 0 {
		return 0, &Error{Status: Status(n), Message: s.fns.lastError(s.handle)}
	}
	return int(n), nil
}

// Close stops capture and releases native resources.
func (s *Stream) Close() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return nil
	}
	s.closed = true
	if s.handle != 0 {
		s.fns.stop(s.handle)
		s.fns.destroy(s.handle)
		s.handle = 0
	}
	return nil
}
