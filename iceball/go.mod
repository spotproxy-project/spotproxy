module main

go 1.18

require (
	github.com/clarkduvall/hyperloglog v0.0.0-20171127014514-a0107a5d8004
	github.com/gorilla/websocket v1.5.0
	github.com/pion/ice/v2 v2.3.1
	github.com/pion/sdp/v3 v3.0.6
	github.com/pion/stun v0.4.0
	github.com/pion/webrtc/v3 v3.1.57
	github.com/prometheus/client_golang v1.10.0
	github.com/prometheus/client_model v0.2.0
	github.com/refraction-networking/utls v1.0.0
	github.com/smartystreets/goconvey v1.6.4
	github.com/stretchr/testify v1.8.1
	github.com/xtaci/kcp-go/v5 v5.6.1
	github.com/xtaci/smux v1.5.15
	gitlab.torproject.org/tpo/anti-censorship/geoip v0.0.0-20210928150955-7ce4b3d98d01
	gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/goptlib v1.4.0
	gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/v2 v2.0.0
	golang.org/x/crypto v0.6.0
	golang.org/x/net v0.7.0
	golang.org/x/sys v0.5.0
	google.golang.org/protobuf v1.26.0
)

require (
	github.com/beorn7/perks v1.0.1 // indirect
	github.com/cespare/xxhash/v2 v2.1.1 // indirect
	github.com/davecgh/go-spew v1.1.1 // indirect
	github.com/golang/protobuf v1.5.2 // indirect
	github.com/google/uuid v1.3.0 // indirect
	github.com/gopherjs/gopherjs v0.0.0-20181017120253-0766667cb4d1 // indirect
	github.com/jtolds/gls v4.20.0+incompatible // indirect
	github.com/klauspost/cpuid v1.3.1 // indirect
	github.com/klauspost/reedsolomon v1.9.9 // indirect
	github.com/matttproud/golang_protobuf_extensions v1.0.1 // indirect
	github.com/mmcloughlin/avo v0.0.0-20200803215136-443f81d77104 // indirect
	github.com/pion/datachannel v1.5.5 // indirect
	github.com/pion/dtls/v2 v2.2.6 // indirect
	github.com/pion/interceptor v0.1.12 // indirect
	github.com/pion/logging v0.2.2 // indirect
	github.com/pion/mdns v0.0.7 // indirect
	github.com/pion/randutil v0.1.0 // indirect
	github.com/pion/rtcp v1.2.10 // indirect
	github.com/pion/rtp v1.7.13 // indirect
	github.com/pion/sctp v1.8.6 // indirect
	github.com/pion/srtp/v2 v2.0.12 // indirect
	github.com/pion/transport/v2 v2.0.2 // indirect
	github.com/pion/turn/v2 v2.1.0 // indirect
	github.com/pion/udp/v2 v2.0.1 // indirect
	github.com/pkg/errors v0.9.1 // indirect
	github.com/pmezard/go-difflib v1.0.0 // indirect
	github.com/prometheus/common v0.18.0 // indirect
	github.com/prometheus/procfs v0.6.0 // indirect
	github.com/smartystreets/assertions v0.0.0-20180927180507-b2de0cb4f26d // indirect
	github.com/templexxx/cpu v0.0.7 // indirect
	github.com/templexxx/xorsimd v0.4.1 // indirect
	github.com/tjfoc/gmsm v1.3.2 // indirect
	golang.org/x/mod v0.6.0-dev.0.20220419223038-86c51ed26bb4 // indirect
	golang.org/x/text v0.7.0 // indirect
	golang.org/x/tools v0.1.12 // indirect
	gopkg.in/yaml.v3 v3.0.1 // indirect
)

//replace gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/v2 v2.0.0 => /home/ubuntu/iceball

replace gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/v2 v2.0.0 => /home/cstdio/Desktop/Rice/Research/iceball/iceball
