package main

import (
	"fmt"
	"log"
	"math"
	"strings"
	"time"

	systemloopback "github.com/huangjunsen0406/system-loopback/bindings/go"
)

func main() {
	stream, err := systemloopback.Open(systemloopback.Options{})
	if err != nil {
		log.Fatalf("open loopback: %v", err)
	}
	defer stream.Close()

	fmt.Printf("Backend: %s | %dHz | %dch\n", stream.Backend(), stream.SampleRate(), stream.Channels())
	buf := make([]float32, 4800)
	ticker := time.NewTicker(50 * time.Millisecond)
	defer ticker.Stop()

	deadline := time.After(3 * time.Second)
	for {
		select {
		case <-deadline:
			return
		case <-ticker.C:
			n, err := stream.ReadF32(buf)
			if err != nil {
				log.Fatalf("read loopback: %v", err)
			}
			if n == 0 {
				continue
			}
			var sum float64
			for _, v := range buf[:n] {
				sum += float64(v) * float64(v)
			}
			rms := math.Sqrt(sum / float64(n))
			bar := strings.Repeat("#", min(40, int(rms*200)))
			fmt.Printf("frames=%4d  rms=%.4f  |%s\n", n, rms, bar)
		}
	}
}
