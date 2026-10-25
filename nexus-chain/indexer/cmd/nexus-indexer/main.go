package main

import (
	"flag"
	"fmt"
	"log"
)

func main() {
	rpc := flag.String("rpc", "http://127.0.0.1:26657", "chain RPC")
	dsn := flag.String("dsn", "", "postgres DSN (optional in scaffold)")
	flag.Parse()
	fmt.Println("nexus-indexer scaffold")
	fmt.Println("  rpc:", *rpc)
	fmt.Println("  dsn set:", *dsn != "")
	fmt.Println("Apply indexer/sql/001_init.sql then stream NewBlock events into Postgres.")
	log.Println("exiting (wire poller in ops phase)")
}
