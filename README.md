# Unpaid Advisor

A web application project.

## Overview

<!-- Describe what Unpaid Advisor does here -->

## Getting Started

### Prerequisites

<!-- List requirements, e.g. Node.js, Python, etc. -->

### Installation

```bash
git clone https://github.com/djcamp4/Unpaid-Advisor.git
cd Unpaid-Advisor
```

<!-- Add install steps, e.g. npm install -->

### Running Locally

```bash
# Add run command here
```

## Financial data

Prices, company details, and history use Polygon. Annual financial statements
use [FinDataEngine](https://asreported.io/) because Polygon's experimental
`/vX/reference/financials` endpoint has been retired.

Set `FINDATAENGINE_API_KEY` for local development. Cloud Build mounts Google
Secret Manager's `FinDataEngine-API` secret into that environment variable.
The Cloud Run service account must have Secret Accessor permission on it.
Never commit the key.

The adapter joins income, balance-sheet, and cash-flow records by period end,
retains up to five annual periods, and caches successful responses for 24 hours
per service instance. Financial figures are annual, not trailing twelve months;
individual fields can remain unavailable when the filing does not supply them.
Provider failures and missing latest-period statements stop individual analysis
with an explicit message. Congressional scans skip stocks with unavailable
statements and stop on account-wide access or quota failures.

Run backend checks with `python -m unittest discover -s backend/tests -v`
and frontend checks with `node --test frontend/selector.test.mjs`.

## Project Structure

```
Unpaid-Advisor/
├── frontend/       # Client-side code
├── backend/        # Server-side code
├── docs/           # Documentation
├── .github/        # GitHub Actions workflows
├── .gitignore
├── LICENSE
└── README.md
```

## Contributing

Pull requests are welcome. For major changes, please open an issue first.

## License

[MIT](LICENSE)
