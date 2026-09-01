# Agent notes

This is a public repository. Treat every commit as world-readable.

- Never commit `.env`, credentials, tokens, API keys, or cloud project identifiers.
- Read secrets from the environment. `.env.example` lists names only.
- Optional graph fusion uses Application Default Credentials. Do not export service-account JSON keys. Do not disable `iam.disableServiceAccountKeyCreation`.
- Vertex stays off unless `GRAPH_AI=true` and `VERTEX_PROJECT` are set in the local environment.
- Do not print, paste, or rewrite secrets into source, tests, or docs.
