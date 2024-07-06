package utls

import (
	"gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/v2/common/version"
	"strings"
)

func generateVersionOutput() string {
	var versionOutputBuilder strings.Builder

	versionOutputBuilder.WriteString(`Known utls-imitate values:
(empty)
`)

	for _, name := range ListAllNames() {
		versionOutputBuilder.WriteString(name)
		versionOutputBuilder.WriteRune('\n')
	}
	return versionOutputBuilder.String()
}

func init() {
	version.AddVersionDetail(generateVersionOutput())
}
