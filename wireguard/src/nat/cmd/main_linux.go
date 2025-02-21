package main

import (
    "log"
	"os"
//    "github.com/spotproxy-project/spotproxy/tree/main/wireguard/src/nat/internal"
	"nat/internal"
)

func main() {
	logFilePath := "/app/logs/nat.log"

    // Open or create the log file
    logFile, err := os.OpenFile(logFilePath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
    if err != nil {
        log.Fatalf("Failed to open log file: %v", err)
    }
    defer logFile.Close()

    // Redirect logs to the file
    log.SetOutput(logFile)
    log.Println("Starting NAT server...")
    s := internal.NewServer()
    s.Run()
    log.Println("NAT server exited successfully.")
}
