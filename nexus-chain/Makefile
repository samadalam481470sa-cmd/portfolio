.PHONY: test build solo gateway tidy

tidy:
	go mod tidy

test:
	go test ./...

build:
	go build -o bin/nexusd ./chain/cmd/nexusd
	go build -o bin/nexus-gateway ./gateway/cmd/nexus-gateway

solo:
	go run ./chain/cmd/nexusd solo --home /tmp/nexus-home

gateway:
	go run ./gateway/cmd/nexus-gateway --rpc http://127.0.0.1:26657 --listen :8080
