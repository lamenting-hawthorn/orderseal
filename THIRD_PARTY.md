# Third-party software and sources

## Architectural reference

- BrowserTransactionBench, commit
  `9d01df42768b03e9cc08f5ff9e7beb09b29c6aa1`, MIT-licensed. Architectural
  concepts only; no source code or historical results copied.

## Runtime and development dependencies

- FastAPI — MIT
- Uvicorn — BSD-3-Clause
- HTTPX — BSD-3-Clause, test client only
- pytest — MIT, test runner only

Python's standard-library `sqlite3`, `secrets`, `hashlib`, and `urllib` modules
provide the initial database, capability-token, digest, and Gate Zero paths.
The exercised dependency lock is the version authority once generated.
