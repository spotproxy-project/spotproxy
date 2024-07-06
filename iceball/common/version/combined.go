package version

func ConstructResult() string {
	return GetVersion() + "\n" + GetVersionDetail()
}
