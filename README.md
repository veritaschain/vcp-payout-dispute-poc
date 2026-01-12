# VCP Payout Dispute Resolution PoC

> **"When payout disputes happen, CSV logs are not evidence. Dual cryptographic logs are."**

**This PoC does not judge which party is correct. It demonstrates that discrepancies can be independently proven.**

[![VCP Version](https://img.shields.io/badge/VCP-v1.1-blue)](https://github.com/veritaschain/vcp-spec)
[![License](https://img.shields.io/badge/license-CC--BY--4.0-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://python.org)

## The Problem

Every year, thousands of prop firm traders lose payouts to disputes they cannot win:

- "Our records show you violated the drawdown limit"
- "The execution price in our system differs from yours"  
- "We have no record of that trade"

**CSV logs can be edited. Screenshots can be faked. Your word against theirs is not evidence.**

## The Solution: Dual Cryptographic Logging

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
│ VCP Event Chain     │                    │ VCP Event Chain     │
│ SHA-256 + Merkle    │                    │ SHA-256 + Merkle    │
│ Externally Anchored │                    │ Externally Anchored │
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

**Guarantee**: Unless both parties collude AND compromise external anchors, any discrepancy is detectable and provable.

## 3-Minute Quick Start

### 1. Trader-Side Events (What You Log)

```bash
cat evidence/trader_events.jsonl | head -3
```

Each trade generates a cryptographic chain:
- **SIG** → Signal/decision generated
- **ORD** → Order sent to broker
- **ACK** → Acknowledgment received
- **EXE** → Execution confirmed
- **REJ** → Rejection (if any)

### 2. Prop Firm-Side Events (What They Log)

```bash
cat evidence/propfirm_events.jsonl | head -3
```

Same trades, same CrossReferenceID, but logged independently.

### 3. Cross-Reference Verification

```bash
python verifier/verify.py \
    --trader evidence/trader_events.jsonl \
    --propfirm evidence/propfirm_events.jsonl
```

Output:
```
✓ 48/48 events verified
✓ All hash chains valid
✓ All cross-references matched
✓ No discrepancies detected

=== VERIFICATION SUMMARY ===
Trader Events:    24 (chain integrity: VALID)
PropFirm Events:  24 (chain integrity: VALID)  
Matched Pairs:    24
Discrepancies:    0
```

### 4. Detect Manipulation

```bash
# Simulate prop firm editing a fill price
python scripts/tamper_demo.py

python verifier/verify.py \
    --trader evidence/trader_events.jsonl \
    --propfirm evidence/propfirm_tampered.jsonl
```

Output:
```
✗ CRITICAL DISCREPANCY DETECTED

Event: ORD-2025-001234
Field: execution_price
├─ Trader logged:    2651.50
└─ PropFirm logged:  2652.80

HASH CHAIN BROKEN at event #7
Expected: a3b4c5d6e7f8...
Found:    9x8y7z6w5v4u...

This discrepancy is CRYPTOGRAPHICALLY PROVABLE.
```

## Repository Structure

```
vcp-payout-dispute-poc/
├── README.md                    # This file
├── LICENSE                      # CC-BY-4.0
├── requirements.txt             # Dependencies (standard library only)
├── evidence/
│   ├── trader_events.jsonl      # 24 trader-side VCP events
│   └── propfirm_events.jsonl    # 24 prop firm-side VCP events
├── verifier/
│   └── verify.py                # Main verification CLI (all-in-one)
├── scripts/
│   └── tamper_demo.py           # Create tampered version for demo
└── docs/
    └── architecture.md          # Detailed architecture
```

## Why This Matters for Prop Firms

| Scenario | Without VCP | With VCP Dual Logging |
|----------|-------------|----------------------|
| Trader claims execution at $X | "Trust us, it was $Y" | Cryptographic proof shows $X |
| Drawdown dispute | CSV can be edited | Hash chain proves timeline |
| Missing trade | "No record in our system" | CrossReferenceID proves existence |
| Payout denial | Months of email disputes | Mathematical verification in seconds |

## Technical Specifications

This PoC implements:

- **VCP v1.1** event structure with 3-layer integrity
- **VCP-XREF** cross-reference extension for dual logging
- **SHA-256** hash chains for tamper evidence
- **RFC 6962** Merkle trees for collection integrity
- **UUIDv7** for time-ordered event IDs

## For Prop Firms: Why Adopt This?

1. **End disputes permanently** - Mathematical proof replaces "he said, she said"
2. **Reduce legal costs** - Disputes resolve in seconds, not months
3. **Build trader trust** - "VC-Certified" badge signals transparency
4. **Regulatory readiness** - MiFID II, EU AI Act compliance preparation

## For Traders: Protect Yourself

1. Run the VCP Sidecar alongside your trading
2. Your logs are YOUR evidence
3. Cross-reference verification catches manipulation
4. External anchoring proves your timeline

## Installation

```bash
# Clone repository
git clone https://github.com/veritaschain/vcp-payout-dispute-poc.git
cd vcp-payout-dispute-poc

# Install dependencies
pip install -r requirements.txt

# Run verification
python verifier/verify.py \
    --trader evidence/trader_events.jsonl \
    --propfirm evidence/propfirm_events.jsonl
```

## Requirements

- Python 3.9+
- No external dependencies for core verification

## Related Resources

- [VCP Specification v1.1](https://github.com/veritaschain/vcp-spec)
- [VCP-XREF Dual Logging Guide](https://veritaschain.org/docs/xref)
- [VeritasChain Standards Organization](https://veritaschain.org)

## License

This PoC is released under [CC-BY-4.0](LICENSE).

## Contact

- **Standards Questions**: standards@veritaschain.org
- **Technical Support**: technical@veritaschain.org
- **Partnership Inquiries**: partners@veritaschain.org

---

**Remember**: When payout disputes happen, CSV logs are not evidence. Dual cryptographic logs are.

---

*This repository is a technical demonstration. It does not constitute legal, trading, or compliance advice.*

*Built by [VeritasChain Standards Organization](https://veritaschain.org) — Verify, Don't Trust.*
