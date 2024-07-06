package version

import "strings"

var detailBuilder strings.Builder

func AddVersionDetail(detail string) {
	detailBuilder.WriteString(detail)
}

func GetVersionDetail() string {
	return detailBuilder.String()
}
