# AEGIS AI investigation improvements

## Included in this update
- LangGraph orchestration and LangChain Gemini integration from the AI-stack upgrade.
- Application-scoped historical retrieval with semantic embedding ranking when configured, plus deterministic fallback.
- Output validation for service names, confidence bounds, evidence arrays, and non-executable remediation suggestions.
- Idempotent service-validation warnings (prevents the same caveat being appended twice).
- Plain-text log parsing now accepts timestamps containing both date and time, including `2026-10-30 10:00:03`.
- Fractional seconds using comma separators are normalized before ISO timestamp parsing.
- Optional LangSmith environment configuration.

## Important limitations
- The current semantic retrieval computes embeddings on demand; it is not a persistent vector database.
- LangGraph currently provides a linear workflow; conditional retry/evidence-request loops and human approval are future enhancements.
- LangSmith requires a valid API key and outbound connectivity.
- Confidence is a heuristic/model-reported score, not a statistically calibrated probability.
- This archive has not been tested against your live PostgreSQL database or live Gemini/LangSmith credentials.
