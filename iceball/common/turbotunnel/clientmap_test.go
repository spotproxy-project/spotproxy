package turbotunnel

import (
	"testing"
	"time"
)

// Benchmark the ClientMap.SendQueue function. This is mainly measuring the cost
// of the mutex operations around the call to clientMapInner.SendQueue.
func BenchmarkSendQueue(b *testing.B) {
	m := NewClientMap(1 * time.Hour)
	id := NewClientID()
	m.SendQueue(id) // populate the entry for id
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		m.SendQueue(id)
	}
}
