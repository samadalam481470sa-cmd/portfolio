package types

const ModuleName = "protocolguard"

type GuardState struct {
	PausedModules map[string]bool `json:"paused_modules"`
	UpdatedHeight int64           `json:"updated_height"`
	UpdatedBy     string          `json:"updated_by"`
}
