# VCP Payout Dispute Resolution - Architecture

## Overview

This document describes the architecture of the VCP (VeritasChain Protocol) Dual Logging system for resolving payout disputes between traders and prop firms.

## The Problem Space

### Current State: Trust-Based Systems

```
┌───────────────────────────────────────────────────────────────┐
│                    CURRENT SITUATION                          │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│  Trader                           Prop Firm                   │
│  ┌─────────┐                     ┌─────────┐                  │
│  │  MT4/5  │ ──── trades ────▶   │ Server  │                  │
│  │Terminal │                     │         │                  │
│  └────┬────┘                     └────┬────┘                  │
│       │                               │                       │
│       ▼                               ▼                       │
│  ┌─────────┐                     ┌─────────┐                  │
│  │  CSV    │                     │Database │                  │
│  │ Export  │                     │  Logs   │                  │
│  └─────────┘                     └─────────┘                  │
│       │                               │                       │
│       │        DISPUTE OCCURS         │                       │
│       │                               │                       │
│       ▼                               ▼                       │
│  "I executed                    "Our records                  │
│   at $2658.20"                   show $2655.50"               │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │              WHO IS TELLING THE TRUTH?                  │  │
│  │                                                         │  │
│  │  • CSV can be edited                                    │  │
│  │  • Database can be modified                             │  │
│  │  • Screenshots can be faked                             │  │
│  │  • No cryptographic proof                               │  │
│  │  • Months of email disputes                             │  │
│  │  • Legal costs exceed disputed amount                   │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

### Solution: Verification-Based System

```
┌───────────────────────────────────────────────────────────────┐
│                    VCP DUAL LOGGING                           │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│  Trader Side                      Prop Firm Side              │
│  ┌─────────────┐                  ┌─────────────┐             │
│  │  Trading    │ ── orders ──▶    │   Trading   │             │
│  │  Terminal   │ ◀── fills ───    │   Server    │             │
│  └──────┬──────┘                  └──────┬──────┘             │
│         │                                │                    │
│         ▼                                ▼                    │
│  ┌─────────────┐                  ┌─────────────┐             │
│  │VCP Sidecar  │                  │ VCP Logger  │             │
│  │             │                  │             │             │
│  │ • SHA-256   │                  │ • SHA-256   │             │
│  │ • Hash Chain│                  │ • Hash Chain│             │
│  │ • Merkle    │                  │ • Merkle    │             │
│  │ • XREF ID   │◀─── shared ───▶  │ • XREF ID   │             │
│  └──────┬──────┘                  └──────┬──────┘             │
│         │                                │                    │
│         ▼                                ▼                    │
│  ┌─────────────┐                  ┌─────────────┐             │
│  │External     │                  │External     │             │
│  │Anchor       │                  │Anchor       │             │
│  │(Blockchain/ │                  │(Blockchain/ │             │
│  │ TSA)        │                  │ TSA)        │             │
│  └─────────────┘                  └─────────────┘             │
│                                                               │
│                    DISPUTE OCCURS                             │
│                          │                                    │
│                          ▼                                    │
│              ┌─────────────────────┐                          │
│              │ Independent Verifier│                          │
│              │  (Auditor/Regulator/│                          │
│              │   Court/Third Party)│                          │
│              └──────────┬──────────┘                          │
│                         │                                     │
│                         ▼                                     │
│              ┌─────────────────────┐                          │
│              │  Cross-Reference    │                          │
│              │    Verification     │                          │
│              │                     │                          │
│              │  Match by XREF ID   │                          │
│              │  Compare fields     │                          │
│              │  Verify hash chains │                          │
│              └──────────┬──────────┘                          │
│                         │                                     │
│                         ▼                                     │
│              ┌─────────────────────┐                          │
│              │  MATHEMATICAL PROOF │                          │
│              │                     │                          │
│              │  Discrepancy is     │                          │
│              │  cryptographically  │                          │
│              │  provable           │                          │
│              └─────────────────────┘                          │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

## Data Flow

### Event Lifecycle

```
                    ┌────────────────────────────────────────┐
                    │         TRADING LIFECYCLE              │
                    └────────────────────────────────────────┘

Time ─────────────────────────────────────────────────────────▶

 T+0ms        T+50ms       T+120ms       T+180ms
   │            │            │             │
   ▼            ▼            ▼             ▼
┌──────┐    ┌──────┐    ┌──────┐     ┌──────┐
│ SIG  │───▶│ ORD  │───▶│ ACK  │────▶│ EXE  │
│      │    │      │    │      │     │      │
│Signal│    │Order │    │Broker│     │Fill  │
│Decide│    │Submit│    │  Ack │     │      │
└──────┘    └──────┘    └──────┘     └──────┘
   │            │            │             │
   │            │            │             │
   ▼            ▼            ▼             ▼
┌──────────────────────────────────────────────┐
│              HASH CHAIN                      │
│                                              │
│  GENESIS ─▶ H(SIG) ─▶ H(ORD) ─▶ H(ACK) ─▶   │
│                                              │
│  Each event contains:                        │
│  • event_hash: SHA-256 of this event         │
│  • prev_hash: hash of previous event         │
└──────────────────────────────────────────────┘
```

### Cross-Reference Matching

```
┌─────────────────────────────────────────────────────────────┐
│                 CROSS-REFERENCE PROTOCOL                    │
└─────────────────────────────────────────────────────────────┘

         TRADER                           PROP FIRM
         ──────                           ─────────
           │                                  │
           │     CrossReferenceID             │
           │   ◀──────────────────────────▶   │
           │     (shared UUID)                │
           │                                  │
    ┌──────┴──────┐                    ┌──────┴──────┐
    │   Event 1   │                    │   Event 1   │
    ├─────────────┤                    ├─────────────┤
    │ xref_id: X  │       MATCH        │ xref_id: X  │
    │ order: 001  │◀─────────────────▶ │ order: 001  │
    │ price: 100  │       COMPARE      │ price: 100  │
    │ role: INIT  │                    │ role: CNTR  │
    └─────────────┘                    └─────────────┘
           │                                  │
           ▼                                  ▼
    ┌─────────────┐                    ┌─────────────┐
    │   Event 2   │                    │   Event 2   │
    ├─────────────┤                    ├─────────────┤
    │ xref_id: X  │       MATCH        │ xref_id: X  │
    │ type: EXE   │◀─────────────────▶ │ type: EXE   │
    │ price: 101  │       COMPARE      │ price: 99   │  ⚠️
    └─────────────┘                    └─────────────┘
           │                                  │
           │         DISCREPANCY              │
           └──────────────┬───────────────────┘
                          │
                          ▼
                ┌─────────────────┐
                │   CRITICAL:     │
                │ Price mismatch  │
                │ T: 101, PF: 99  │
                └─────────────────┘
```

## Security Model

### Three-Layer Integrity Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              VCP v1.1 THREE-LAYER ARCHITECTURE              │
└─────────────────────────────────────────────────────────────┘

Layer 3: EXTERNAL VERIFIABILITY
┌─────────────────────────────────────────────────────────────┐
│  • External timestamp authority (TSA)                       │
│  • Blockchain anchor (optional)                             │
│  • Third-party cannot deny event existence                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
Layer 2: COLLECTION INTEGRITY
┌─────────────────────────────────────────────────────────────┐
│  • RFC 6962 Merkle Tree                                     │
│  • MerkleRoot commits to entire collection                  │
│  • Audit paths prove inclusion                              │
│                                                             │
│       MerkleRoot                                            │
│           │                                                 │
│     ┌─────┴─────┐                                           │
│     │           │                                           │
│   ┌─┴─┐       ┌─┴─┐                                         │
│   │H01│       │H23│                                         │
│   └┬──┘       └┬──┘                                         │
│  ┌─┴─┐ ┌─┴─┐ ┌─┴─┐ ┌─┴─┐                                    │
│  │ E0│ │ E1│ │ E2│ │ E3│                                    │
│  └───┘ └───┘ └───┘ └───┘                                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
Layer 1: EVENT INTEGRITY
┌─────────────────────────────────────────────────────────────┐
│  • SHA-256 EventHash per event                              │
│  • PrevHash creates chain                                   │
│  • Ed25519 signature (Gold/Platinum)                        │
│                                                             │
│  ┌─────┐    ┌─────┐    ┌─────┐    ┌─────┐                   │
│  │ E0  │───▶│ E1  │───▶│ E2  │───▶│ E3  │                   │
│  │     │    │     │    │     │    │     │                   │
│  │ H0  │    │ H1  │    │ H2  │    │ H3  │                   │
│  │ P:G │    │P:H0 │    │P:H1 │    │P:H2 │                   │
│  └─────┘    └─────┘    └─────┘    └─────┘                   │
│                                                             │
│  H = EventHash, P = PrevHash, G = Genesis                   │
└─────────────────────────────────────────────────────────────┘
```

### Threat Model

| Threat | Mitigation | Guarantee Level |
|--------|------------|-----------------|
| Trader modifies own logs | Prop Firm's independent log provides evidence | Single-party tampering detectable |
| Prop Firm modifies logs | Trader's independent log provides evidence | Single-party tampering detectable |
| Both parties collude | External anchors provide third-party proof | Requires anchor compromise |
| Log omission | Cross-reference reveals missing events | Missing events provable |
| Replay attack | UUIDv7 + timestamp uniqueness | Duplicates detectable |

## Implementation Components

### Verifier Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    VERIFICATION FLOW                        │
└─────────────────────────────────────────────────────────────┘

         ┌─────────────┐      ┌─────────────┐
         │   Trader    │      │  PropFirm   │
         │   JSONL     │      │   JSONL     │
         └──────┬──────┘      └──────┬──────┘
                │                    │
                ▼                    ▼
         ┌──────────────────────────────────┐
         │        1. LOAD EVENTS            │
         │   Parse JSONL → VCPEvent[]       │
         └──────────────────┬───────────────┘
                            │
                            ▼
         ┌──────────────────────────────────┐
         │     2. VERIFY HASH CHAINS        │
         │                                  │
         │   For each event[i]:             │
         │     assert event[i].prev_hash    │
         │         == event[i-1].event_hash │
         └──────────────────┬───────────────┘
                            │
                            ▼
         ┌──────────────────────────────────┐
         │      3. MATCH BY XREF ID         │
         │                                  │
         │   trader_index[xref_id,type]     │
         │   propfirm_index[xref_id,type]   │
         │   matched = intersect(indexes)   │
         └──────────────────┬───────────────┘
                            │
                            ▼
         ┌──────────────────────────────────┐
         │     4. COMPARE FIELDS            │
         │                                  │
         │   For each matched pair:         │
         │     compare(trader, propfirm)    │
         │     detect discrepancies         │
         └──────────────────┬───────────────┘
                            │
                            ▼
         ┌──────────────────────────────────┐
         │      5. GENERATE REPORT          │
         │                                  │
         │   • Chain validity              │
         │   • Match statistics            │
         │   • Discrepancy list            │
         │   • Severity classification     │
         └──────────────────────────────────┘
```

## Event Schema

### VCP Event Structure

```json
{
  "header": {
    "event_id": "UUIDv7",
    "trace_id": "UUIDv7 (groups related events)",
    "timestamp_int": "nanoseconds since epoch",
    "timestamp_iso": "ISO 8601",
    "event_type": "SIG|ORD|ACK|EXE|REJ|...",
    "event_type_code": "integer 1-255",
    "symbol": "e.g., XAUUSD",
    "account_id": "trader identifier",
    "venue_id": "broker/prop firm ID"
  },
  "payload": {
    "trade_data": {
      "order_id": "string",
      "side": "BUY|SELL",
      "price": "string (decimal)",
      "quantity": "string (decimal)",
      "execution_price": "string (on EXE)",
      "...": "..."
    }
  },
  "vcp_xref": {
    "CrossReferenceID": "shared UUID",
    "PartyRole": "INITIATOR|COUNTERPARTY",
    "CounterpartyID": "other party's ID",
    "SharedEventKey": {
      "OrderID": "correlation key",
      "Timestamp": "event timestamp",
      "ToleranceMs": "matching tolerance"
    }
  },
  "security": {
    "event_hash": "SHA-256 hex (64 chars)",
    "prev_hash": "previous event's hash"
  }
}
```

## Deployment Scenarios

### Scenario 1: Prop Firm Challenge (Eval/Funded Account)

```
Trader: Uses VCP Sidecar with their EA
PropFirm: Adopts VCP logging on server side
Result: Both parties have cryptographic proof
        Disputes resolved in seconds, not months
```

### Scenario 2: Broker Execution Quality

```
Algo Provider: Logs all orders with VCP
Broker: Logs all executions with VCP
Result: Best execution can be verified
        Slippage disputes have proof
```

### Scenario 3: Regulatory Audit

```
Trading Firm: Maintains VCP audit trail
Regulator: Can verify completeness
Result: MiFID II / EU AI Act compliance
        Algorithmic decisions are auditable
```

## Next Steps

1. **For Traders**: Run the VCP Sidecar alongside your trading
2. **For Prop Firms**: Integrate VCP logging on your server
3. **For Brokers**: Adopt VCP for execution transparency
4. **For Regulators**: Use VCP verification tools

## References

- [VCP Specification v1.1](https://github.com/veritaschain/vcp-spec)
- [VCP-XREF Extension](https://veritaschain.org/docs/xref)
- [RFC 6962: Certificate Transparency](https://www.rfc-editor.org/rfc/rfc6962)
- [VeritasChain Standards Organization](https://veritaschain.org)

---

*Document ID: VSO-POC-ARCH-001*
*License: CC BY 4.0 International*
