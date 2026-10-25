> **Status correction — 25 October 2026**
>
> - This is first-party proof-of-concept code by VeritasChain Co., Ltd., which operates the VeritasChain Standards Organization (VSO). It targets VCP v1.1. VCP v1.1 has no tagged release and is superseded by VCP v1.2 (Released, tag `v1.2.0`).
> - Conformance to any VCP tier, or to VAP, has not been independently established. There are zero external implementations of VAP or any of its profiles, including VCP.
> - Not certified. VSO does not issue certificates. The certification scheme requires a Conformity Assessment Body (CAB) independent of the scheme owner; the only registered CAB, VeritasChain Co., Ltd., is not independent (VAP v1.2 ERRATA E-2026-10-21).
> - Known limitations: signatures come from an Ed25519 *simulator* in `scripts/generate_events_v1_1.py` (a SHA-512 construction its own docstring calls "NOT cryptographically secure - demo only"); `verify.py` re-checks that construction, not Ed25519. The anchor "proof" is a synthetic string (`ots-` plus a truncated SHA-256 of the root and timestamp); nothing is submitted to OpenTimestamps. `verify.py` checks the anchor by comparing the anchor record's `merkle_root` string with the events' `merkle_root`; it does not verify an anchor signature or proof. The Merkle tree pads to a power of two by duplicating the last leaf (RFC 6962 hash prefixes, not the RFC 6962 tree algorithm). The generated event IDs are not valid UUIDs.
> - The results below show internal consistency of the sample logs. They are not proof of what was traded, and they do not settle disputes on their own.

# VCP v1.1 Payout Dispute Resolution PoC

> **"When payout disputes happen, CSV logs are not evidence. Dual cryptographic logs are."**

**This PoC demonstrates VCP v1.1 Three-Layer Architecture for tamper-evident audit trails.**

[![VCP Version](https://img.shields.io/badge/VCP-v1.1-blue)](https://github.com/veritaschain/vcp-spec)
[![License](https://img.shields.io/badge/license-CC--BY--4.0-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://python.org)

## The Problem

Every year, thousands of prop firm traders lose payouts to disputes they cannot win:

- "Our records show you violated the drawdown limit"
- "The execution price in our system differs from yours"  
- "We have no record of that trade"

**CSV logs can be edited. Screenshots can be faked. Your word against theirs is not evidence.**

## The Solution: VCP v1.1 Three-Layer Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 3: External Verifiability                                    │
│  ─────────────────────────────────                                  │
│  • Digital Signatures (Ed25519)                                     │
│  • External Anchoring (OpenTimestamps/Blockchain)                   │
│  • Third-party verification without trusting the producer           │
├─────────────────────────────────────────────────────────────────────┤
│  LAYER 2: Collection Integrity                                      │
│  ────────────────────────────────                                   │
│  • Merkle Tree (RFC 6962 compliant)                                │
│  • Batch completeness proof                                         │
│  • Audit path for each event                                        │
├─────────────────────────────────────────────────────────────────────┤
│  LAYER 1: Event Integrity                                           │
│  ───────────────────────────                                        │
│  • EventHash (SHA-256 of canonical event)                          │
│  • PrevHash (optional hash chain)                                   │
│  • Individual event completeness                                    │
└─────────────────────────────────────────────────────────────────────┘
```

## VCP-XREF: Dual Logging for Dispute Resolution

```
┌─────────────────────┐                    ┌─────────────────────┐
│   TRADER SIDECAR    │                    │   PROP FIRM SYSTEM  │
│  (Your Evidence)    │                    │  (Their Evidence)   │
└─────────┬───────────┘                    └─────────┬───────────┘
          │                                          │
          │    CrossReferenceID: shared-uuid         │
          │    OrderID: ORD-2025-001234              │
          │                                          │
          ▼                                          ▼
┌─────────────────────┐                    ┌─────────────────────┐
│ VCP v1.1 Event Log  │                    │ VCP v1.1 Event Log  │
│ • EventHash         │                    │ • EventHash         │
│ • Merkle Tree       │                    │ • Merkle Tree       │
│ • Digital Signature │                    │ • Digital Signature │
│ • External Anchor   │                    │ • External Anchor   │
└─────────┬───────────┘                    └─────────┬───────────┘
          │                                          │
          └──────────────────┬───────────────────────┘
                             ▼
                  ┌─────────────────────┐
                  │ Independent Verifier│
                  │  (Auditor/Regulator/│
                  │   Third Party)      │
                  └──────────┬──────────┘
                             ▼
                  ┌─────────────────────┐
                  │  CROSS-REFERENCE    │
                  │    VERIFICATION     │
                  │                     │
                  │  ✓ Both logs match  │
                  │  ✗ Discrepancy alert│
                  └─────────────────────┘
```

**Property (design goal)**: Unless both parties collude AND compromise external anchors, a discrepancy between the two logs is detectable. In this PoC the anchors are simulated (see the status correction above).

## 3-Minute Quick Start

### 1. Generate VCP v1.1 PoC Events

```bash
python scripts/generate_events_v1_1.py
```

This creates:
- `evidence/trader_events.jsonl` - 23 trader-side events
- `evidence/propfirm_events.jsonl` - 23 prop firm-side events
- `evidence/anchor_records.json` - External anchor records

### 2. Verify Both Logs Match

```bash
python verifier/verify.py \
    --trader evidence/trader_events.jsonl \
    --propfirm evidence/propfirm_events.jsonl \
    --anchor evidence/anchor_records.json
```

Output:
```
Layer 1: Event Integrity
  ✓ Trader event hashes:   23/23 valid
  ✓ PropFirm event hashes: 23/23 valid

Layer 2: Collection Integrity
  ✓ Trader Merkle tree:    VALID
  ✓ PropFirm Merkle tree:  VALID

Layer 3: External Verifiability
  ✓ Trader anchor:         VALID
  ✓ PropFirm anchor:       VALID

VCP-XREF: Cross-Reference Verification
  ✓ NO DISCREPANCIES DETECTED

PoC check: internal consistency only (demo signatures, synthetic anchor proof).
```

### 3. Demonstrate Tamper Detection

```bash
# Simulate prop firm editing an execution price
python scripts/tamper_demo.py

# Verify and detect the tampering
python verifier/verify.py \
    --trader evidence/trader_events.jsonl \
    --propfirm evidence/propfirm_tampered.jsonl
```

Output:
```
Layer 1: Event Integrity
  ✗ PropFirm event hashes: 22/23 valid

✗ DISCREPANCIES DETECTED

  CRITICAL: 1
    • [EXE] ORD-2025-001002: execution_price
      ├─ Trader:   2658.20
      └─ PropFirm: 2655.50

These issues are detectable by the checks above (PoC; demo signatures).
```

## Repository Structure

```
vcp-payout-dispute-poc/
├── README.md                           # This file
├── LICENSE                             # CC-BY-4.0
├── requirements.txt                    # Dependencies (standard library only)
├── evidence/
│   ├── trader_events.jsonl             # 23 trader-side VCP v1.1 events
│   ├── propfirm_events.jsonl           # 23 prop firm-side VCP v1.1 events
│   └── anchor_records.json             # External anchor records
├── verifier/
│   └── verify.py                       # VCP v1.1 Three-Layer verification
├── scripts/
│   ├── generate_events_v1_1.py         # Generate VCP v1.1 PoC events
│   └── tamper_demo.py                  # Demonstrate tamper detection
└── docs/
    └── architecture.md                 # Detailed architecture
```

## VCP v1.1 Design Targets (not conformance results)

This PoC addresses the following VCP v1.1 requirements. See the status correction above for limitations:

| Requirement | Status | Reference |
|-------------|--------|-----------|
| **Three-Layer Architecture** | ✅ | Section 6.0 |
| **EventHash (SHA-256)** | ✅ | Section 6.1.1 |
| **PrevHash (optional)** | ✅ | Section 6.1.2 |
| **Merkle Tree (RFC 6962)** | Partial: RFC 6962 hash prefixes; pads by duplicating the last leaf | Section 6.2.1 |
| **Merkle Proof** | ✅ | Section 6.2.3 |
| **Digital Signatures** | Simulated (not Ed25519; demo only) | Section 6.3.1 |
| **External Anchor** | Simulated (synthetic proof string; not submitted) | Section 6.3.3 |
| **Policy Identification** | ✅ | Section 5.5 |
| **VCP-XREF Dual Logging** | ✅ | Section 5.6 |
| **UUIDv7 Event IDs** | ✗ Generated IDs are not valid UUIDs (last group has 8 hex digits, not 12) | RFC 9562 |
| **JSON Canonicalization** | Simplified (sorted-key JSON; not a full RFC 8785 implementation) | RFC 8785 |

### Event Structure (VCP v1.1)

```json
{
  "header": {
    "event_id": "UUIDv7",
    "timestamp_int": "nanoseconds",
    "timestamp_iso": "ISO 8601",
    "event_type": "SIG|ORD|ACK|EXE|REJ",
    "...": "..."
  },
  "payload": {
    "trade_data": { "...": "..." },
    "vcp_gov": { "...": "..." }
  },
  "vcp_xref": {
    "version": "1.1",
    "cross_reference_id": "shared UUID",
    "party_role": "INITIATOR|COUNTERPARTY",
    "shared_event_key": { "order_id": "...", "..." }
  },
  "policy_identification": {
    "version": "1.1",
    "policy_id": "org.example:policy-001",
    "conformance_tier": "SILVER|GOLD|PLATINUM",
    "verification_depth": { "..." }
  },
  "security": {
    "version": "1.1",
    "event_hash": "SHA-256 hex",
    "prev_hash": "previous event hash",
    "signature": "Ed25519 base64",
    "merkle_root": "batch root",
    "merkle_index": 0,
    "merkle_proof": [{ "hash": "...", "position": "left|right" }],
    "anchor_reference": "anchor-id"
  }
}
```

## Why This Matters for Prop Firms

| Scenario | Without VCP | With VCP v1.1 Dual Logging |
|----------|-------------|---------------------------|
| Trader claims execution at $X | "Trust us, it was $Y" | Three-layer cryptographic proof shows $X |
| Drawdown dispute | CSV can be edited | Merkle tree proves timeline integrity |
| Missing trade | "No record in our system" | CrossReferenceID + anchor proves existence |
| Payout denial | Months of email disputes | Record verification in seconds |

## For Prop Firms: Why Adopt This?

1. **Shorten disputes** - Verifiable records replace "he said, she said"
2. **Reduce legal costs** - Record checks take seconds, not months
3. **Regulatory readiness** - MiFID II, EU AI Act preparation (compliance not determined)

## For Traders: Protect Yourself

1. Run the VCP Sidecar alongside your trading
2. Your logs are YOUR evidence (independently anchored)
3. Cross-reference verification catches manipulation
4. External anchoring proves your timeline

## Installation

```bash
# Clone repository
git clone https://github.com/veritaschain/vcp-payout-dispute-poc.git
cd vcp-payout-dispute-poc

# No dependencies required - uses Python standard library only
python --version  # Requires Python 3.9+

# Generate events and run verification
python scripts/generate_events_v1_1.py
python verifier/verify.py -t evidence/trader_events.jsonl -p evidence/propfirm_events.jsonl
```

## Requirements

- Python 3.9+
- No external dependencies (standard library only)

## Related Resources

- [VCP Specification v1.1](https://github.com/veritaschain/vcp-spec)
- [VCP-XREF Dual Logging Guide](https://veritaschain.org/docs/xref)
- [VeritasChain Standards Organization](https://veritaschain.org)
- [IETF Draft: draft-kamimura-scitt-vcp](https://datatracker.ietf.org/doc/draft-kamimura-scitt-vcp/)

## License

This PoC is released under [CC-BY-4.0](LICENSE).

## Contact

- **Standards Questions**: standards@veritaschain.org
- **Technical Support**: technical@veritaschain.org
- **Partnership Inquiries**: partners@veritaschain.org

---

**Remember**: When payout disputes happen, CSV logs are not evidence. VCP v1.1 Three-Layer cryptographic logs are.

---

*This repository is a technical demonstration. It does not constitute legal, trading, or compliance advice.*

*Built by [VeritasChain Standards Organization](https://veritaschain.org) — Verify, Don't Trust.*
