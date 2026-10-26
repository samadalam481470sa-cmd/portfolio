package brokerage

import "context"

// Intent is an out-of-consensus order intent. Production connectors are
// separately authorized and never mutate chain state directly.
type Intent struct {
	ClientOrderID string
	Symbol        string
	Side          string
	Quantity      string
	AccountRef    string
}

type Result struct {
	AttestationRef string
	ProviderID     string
}

type Connector interface {
	SubmitOrderIntent(ctx context.Context, intent Intent) (Result, error)
}

// Stub refuses live brokerage calls.
type Stub struct{}

func (Stub) SubmitOrderIntent(ctx context.Context, intent Intent) (Result, error) {
	return Result{}, ErrNotAuthorized
}

var ErrNotAuthorized = errNotAuth{}

type errNotAuth struct{}

func (errNotAuth) Error() string {
	return "brokerage connector not authorized in this environment (scaffold stub)"
}
