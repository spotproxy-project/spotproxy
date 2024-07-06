package snowflake_proxy

import (
	"gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/v2/common/task"
	"io"
	"log"
	"time"

	"gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/v2/common/event"
)

func NewProxyEventLogger(logPeriod time.Duration, output io.Writer) event.SnowflakeEventReceiver {
	logger := log.New(output, "", log.LstdFlags|log.LUTC)
	el := &logEventLogger{logPeriod: logPeriod, logger: logger}
	el.task = &task.Periodic{Interval: logPeriod, Execute: el.logTick}
	el.task.WaitThenStart()
	return el
}

type logEventLogger struct {
	inboundSum      int64
	outboundSum     int64
	connectionCount int
	logPeriod       time.Duration
	task            *task.Periodic
	logger          *log.Logger
}

func (p *logEventLogger) OnNewSnowflakeEvent(e event.SnowflakeEvent) {
	switch e.(type) {
	case event.EventOnProxyConnectionOver:
		e := e.(event.EventOnProxyConnectionOver)
		p.inboundSum += e.InboundTraffic
		p.outboundSum += e.OutboundTraffic
		p.connectionCount += 1
	default:
		p.logger.Println(e.String())
	}
}

func (p *logEventLogger) logTick() error {
	inbound, inboundUnit := formatTraffic(p.inboundSum)
	outbound, outboundUnit := formatTraffic(p.outboundSum)
	p.logger.Printf("In the last %v, there were %v connections. Traffic Relayed ↓ %v %v, ↑ %v %v.\n",
		p.logPeriod.String(), p.connectionCount, inbound, inboundUnit, outbound, outboundUnit)
	p.outboundSum = 0
	p.inboundSum = 0
	p.connectionCount = 0
	return nil
}

func (p *logEventLogger) Close() error {
	return p.task.Close()
}
