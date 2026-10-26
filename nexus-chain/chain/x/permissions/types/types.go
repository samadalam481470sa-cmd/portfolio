package types

const (
	ModuleName = "permissions"

	RoleIssuer           = "ISSUER"
	RoleAttestor         = "ATTESTOR"
	RoleOracleReporter   = "ORACLE_REPORTER"
	RoleSettlementAgent  = "SETTLEMENT_AGENT"
	RoleGuardian         = "GUARDIAN"
	RoleValidatorOps     = "VALIDATOR_OPS"
)

type Binding struct {
	Address string   `json:"address"`
	Roles   []string `json:"roles"`
}
