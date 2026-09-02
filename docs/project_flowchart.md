# ComplaintGuard Whole-Project Flowchart

This flowchart describes the current verified local-emulator prototype, the
offline model-training path, the live complaint lifecycle, role-specific
operations, and the boundary around deferred Cloud deployment. It does not
claim that Vercel, Hugging Face Spaces, or production Firebase is deployed.

```mermaid
flowchart TD
    Start([Start]) --> Mode{User or project activity}

    subgraph Offline[Offline data and model pipeline]
        Raw[Historical CFPB CSV or Parquet\nkept outside Firestore] --> Clean[Profile, clean, and privacy review]
        Clean --> Labels[Deterministic Product and Issue mapping]
        Labels --> Split[Stratified train, validation, and test split]
        Split --> Fit[Fit TF-IDF vectorizer\nand Multinomial Naive Bayes]
        Fit --> Tune[Select operational confidence threshold]
        Tune --> Eval[Evaluate accuracy, precision, recall,\nmacro-F1, and confusion matrix]
        Eval --> Frozen[Versioned frozen model artifacts]
    end

    Mode -->|Model preparation| Raw
    Mode -->|Local demonstration| Entry[Open local Next.js application]

    subgraph Runtime[Verified local runtime]
        Entry --> Language[Select English or Myanmar]
        Language --> Login[Register or sign in\nwith Firebase Auth Emulator]
        Login --> Role{Resolve active application role}
        Role -->|Customer| CustomerHome[Customer dashboard]
        Role -->|Staff| StaffHome[Department staff dashboard]
        Role -->|Manager| ManagerHome[Manager review and analytics dashboard]
        Role -->|Admin| AdminHome[Admin account directory and provisioning shell]

        CustomerHome --> Compose[Enter complaint\nwith optional service/date/reference]
        Compose --> Validate{Valid length and\nno sensitive-data warning?}
        Validate -->|No| Compose
        Validate -->|Yes| Submit[POST ticket with Firebase ID token]
        Submit --> AuthZ[FastAPI verifies token, role,\nand customer ownership]
        AuthZ --> Create[Create submitted ticket\nin Firestore Emulator]
        Create --> Detect{Detect input language}
        Detect -->|English| Normalize[Normalize and redact transient text]
        Detect -->|Myanmar or mixed| Translate[Open-source Myanmar-to-English translation]
        Translate --> Normalize
        Normalize --> Predict[Load frozen TF-IDF + NB artifacts]
        Frozen -. artifact copy .-> Predict
        Predict --> Confidence{Confidence meets\noperational threshold?}
        Confidence -->|Yes, accepted English| AutoRoute[Assign one department label]
        Confidence -->|No, or Myanmar/mixed| Manual[Manual Review\nroute remains unassigned]
        AutoRoute --> Persist[Persist routing, confidence,\nassignment, and audit event]
        Manual --> Persist
        Persist --> Notify[Return ticket ID and status\nfor dashboard refresh]
        Notify --> Lifecycle[Ticket lifecycle]

        Lifecycle --> Submitted[Submitted]
        Submitted --> Classified[Classified or Manual Review]
        Classified --> Assigned[Assigned]
        Assigned --> InProgress[In Progress]
        InProgress --> Waiting[Waiting for Customer\noptional]
        Waiting --> InProgress
        InProgress --> Resolved[Resolved]
        Resolved --> Closed[Closed]
        InProgress -. exception .-> Reassign[Reassigned or Escalated]
        Reassign --> Assigned
        Closed -. customer follow-up .-> Reopened[Reopened]
        Reopened --> InProgress

        CustomerHome --> History[View own complaint history\nand message thread]
        Notify --> History
        History --> Feedback[Optional resolution feedback]

        StaffHome --> Queue[Read tickets for assigned department]
        Queue --> StaffAction{Staff action}
        StaffAction --> Reply[Reply in ticket thread]
        StaffAction --> Status[Update allowed ticket status]
        StaffAction --> Escalate[Reassign or escalate when permitted]
        Reply --> Audit[Write message and lifecycle event]
        Status --> Audit
        Escalate --> Audit
        Audit --> CustomerView[Customer sees permitted updates]

        ManagerHome --> Review[Review manual-review and operational tickets]
        Review --> Override[Override department when justified]
        Override --> Audit
        ManagerHome --> Analytics[View aggregate workload, trends,\nmodel and dataset evidence]

        AdminHome --> Directory[Read safe all-role account directory]
        AdminHome --> Provision[Prepare pending Staff or Manager accounts]
        Provision --> AdminAuth[Trusted active-Admin authorization]
        AdminAuth --> Pending[Pending profile state\nactivation helper remains owner-only]
    end

    subgraph Data[Firestore Emulator and security boundary]
        Store[(users, departments,\ncomplaints, messages, events, feedback)]
        Rules[Firestore security rules\ncustomer ownership, staff department scope,\nmanager access, deny-by-default writes]
    end

    AuthZ --> Rules
    Create --> Store
    Persist --> Store
    Audit --> Store
    History --> Rules
    Queue --> Rules
    Review --> Rules
    Directory --> Rules
    Store --> Rules
    Rules --> CustomerView

    subgraph Deferred[Deferred and unverified boundary]
        Cloud[Cloud Firebase, Vercel,\nHugging Face Spaces]
        Gate[Separate approval required for\nbudget, billing, hosting, and keyless identity]
        Cloud -. blocked by .-> Gate
    end

    Raw -. never bulk-loaded .-> Store
    Frozen -. local ignored artifact .-> Runtime
    Runtime -. current source of truth .-> Demo([Local demo complete])
```

## Stable routing labels

The classifier routes to one of these labels. Low-confidence or unsupported
automatic cases use `general_support` or remain in `Manual Review` according to
the current runtime contract.

`transfer_payment` · `account_support` · `card_atm` · `fraud_security` ·
`loan_credit` · `general_support`

## Security and data notes

- Firebase Auth supplies the identity token; FastAPI performs trusted workflow
  authorization and Firestore rules enforce direct client access boundaries.
- Historical CFPB records and training data stay local and are never bulk-loaded
  into Firestore.
- Use synthetic identities and complaints for demonstrations. Do not submit
  passwords, PINs, or full account/card numbers.
