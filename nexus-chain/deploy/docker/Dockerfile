FROM golang:1.22-bookworm AS build
WORKDIR /src
COPY go.mod go.sum* ./
COPY . .
RUN go test ./... && go build -o /nexusd ./chain/cmd/nexusd && go build -o /nexus-gateway ./gateway/cmd/nexus-gateway

FROM debian:bookworm-slim
COPY --from=build /nexusd /usr/local/bin/nexusd
COPY --from=build /nexus-gateway /usr/local/bin/nexus-gateway
EXPOSE 26657 8080
CMD ["nexusd", "start", "--home", "/data", "--faucet"]
