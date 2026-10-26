package main

import (
	"encoding/json"
	"flag"
	"io"
	"log"
	"net/http"
)

func main() {
	rpc := flag.String("rpc", "http://127.0.0.1:26657", "nexusd RPC")
	listen := flag.String("listen", ":8080", "gateway listen")
	flag.Parse()

	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok", "service": "nexus-gateway"})
	})
	mux.HandleFunc("/v1/", func(w http.ResponseWriter, r *http.Request) {
		path := r.URL.Path
		u := *rpc + path
		if r.URL.RawQuery != "" {
			u += "?" + r.URL.RawQuery
		}
		req, err := http.NewRequest(r.Method, u, r.Body)
		if err != nil {
			http.Error(w, err.Error(), 500)
			return
		}
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			http.Error(w, err.Error(), 502)
			return
		}
		defer resp.Body.Close()
		w.WriteHeader(resp.StatusCode)
		_, _ = io.Copy(w, resp.Body)
	})
	mux.HandleFunc("/v1/connectors/manifest", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"name":      "nexus-connectors",
			"synthetic": true,
			"disclaimer": "Authorized brokerage/banking connectors are out-of-consensus and require separate legal agreements. This scaffold exposes interfaces only.",
			"interfaces": []string{"brokerage", "banking", "marketdata"},
		})
	})

	log.Printf("gateway listening on %s -> %s", *listen, *rpc)
	log.Fatal(http.ListenAndServe(*listen, mux))
}
