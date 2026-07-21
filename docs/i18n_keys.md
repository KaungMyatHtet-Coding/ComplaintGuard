# English/Myanmar Translation-Key Structure

This Day 4 draft defines namespaces and fallback behavior only. It does not implement internationalization or provide a complete Myanmar catalog.

## Locale policy

- Supported locale identifiers are `en` and `my`.
- English (`en`) is the canonical fallback locale.
- Resolution order is requested locale, English key, then a safe visible missing-key marker in development.
- Production must log missing keys without complaint text or personal data and display the English value when available.
- Locale preference belongs in the user profile; complaint `inputLocale` records the language selected for that submission.
- Translation keys describe UI copy only. They are unrelated to complaint-text translation or model processing.

## Namespace convention

Use dot-separated, semantic keys rather than English sentences:

```text
common.*
navigation.*
auth.*
privacy.*
complaint.form.*
complaint.status.*
ticket.list.*
ticket.detail.*
message.*
staff.queue.*
staff.actions.*
manager.dashboard.*
manager.actions.*
department.*
role.*
validation.*
state.loading.*
state.empty.*
error.*
```

Keys remain stable when wording changes. Variables use named placeholders such as `{ticketId}` or `{count}`. Code must not concatenate translated fragments; pluralization and dates should use locale-aware formatting.

## Representative English structure

```json
{
  "common": {
    "retry": "Try again",
    "cancel": "Cancel"
  },
  "privacy": {
    "sensitiveDataWarning": "Do not enter passwords, PINs, or full account or card numbers."
  },
  "complaint": {
    "form": {
      "title": "Submit a complaint",
      "textLabel": "Complaint",
      "submit": "Submit complaint"
    },
    "status": {
      "submitted": "Submitted",
      "triaged": "Triaged",
      "inProgress": "In progress",
      "awaitingCustomer": "Awaiting customer",
      "resolved": "Resolved",
      "closed": "Closed"
    }
  },
  "department": {
    "transfer_payment": "Transfer & Payment",
    "account_support": "Account & KYC Support",
    "card_atm": "Card & ATM Support",
    "fraud_security": "Fraud & Security",
    "loan_credit": "Loan & Credit",
    "general_support": "General Support"
  },
  "state": {
    "loading": { "tickets": "Loading tickets..." },
    "empty": { "tickets": "No tickets found." }
  },
  "error": {
    "permissionDenied": "You do not have permission to view this item.",
    "serviceUnavailable": "The service is unavailable. Try again."
  }
}
```

The future Myanmar catalog must mirror the same key tree and receive human review. Missing Myanmar entries fall back per key to English; a missing namespace must not break the page. User-submitted complaint text, department IDs, ticket IDs, status values stored in Firestore, and audit values are data rather than translated strings. The UI maps stable stored IDs to localized display keys.
