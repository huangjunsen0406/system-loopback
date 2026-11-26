# system-loopback (Go)

Zero-CGO Go binding for `libsystem_loopback` powered by `github.com/ebitengine/purego`.

Works on macOS (`arm64`/`amd64`), Windows (`amd64`), and Linux (`amd64`/`arm64`) with `CGO_ENABLED=0`.

## Usage

```go
package main

import (
	"fmt"
	"log"
	"time"

	systemloopback "github.com/huangjunsen0406/system-loopback/bindings/go"
)

func main() {
	stream, err := systemloopback.Open(systemloopback.Options{})
	if err != nil {
		log.Fatal(err)
	}
	defer stream.Close()

	time.Sleep(100 * time.Millisecond)
	buf := make([]float32, 4800)
	n, err := stream.ReadF32(buf)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("read %d frames @ %dHz (%s)\n", n, stream.SampleRate(), stream.Backend())
}
```
