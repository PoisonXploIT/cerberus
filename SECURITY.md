# Security Policy

CERBERUS is a defensive evaluation framework. It does not contain model weights,
API keys, or execution results; datasets and run outputs stay local and are
gitignored by design.

The prompt templates in the code describe adversarial scenarios for
**authorized** security research only (red-team exercises with written
permission, defensive risk assessment). The tool is passive: it never executes
payloads.

If you discover a vulnerability in the framework itself, please open a private
security advisory instead of a public issue.
