# VCP v1.1 Payout Dispute PoC - Architecture Document

**Document ID**: VSO-POC-ARCH-002  
**Version**: 1.1  
**Date**: 2025-01-12  
**Status**: PoC (status corrected 2026-10-25; see the README)

## 1. Executive Summary

This document describes the architecture of the VCP v1.1 Payout Dispute Resolution Proof of Concept. The PoC demonstrates how the VeritasChain Protocol v1.1 Three-Layer Architecture provides cryptographically verifiable records for resolving trading disputes between traders and prop firms.

## 2. VCP v1.1 Three-Layer Architecture

### 2.1 Architectural Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  LAYER 3: External Verifiability                                            │
│  ─────────────────────────────────────                                      │
│  Purpose: Third-party verification without trusting the producer            │
│                                                                             │
│  Components:                                                                │
│  ├─ Digital Signature (Ed25519): REQUIRED                                  │
│  ├─ Timestamp (dual format ISO+int64): REQUIRED                            │
│  └─ External Anchor (Blockchain/TSA): REQUIRED                             │
│                                                                             │
│  Frequency: Tier-dependent (10min / 1hr / 24hr)                            │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  LAYER 2: Collection Integrity    ← Core for external verifiability        │
│  ──────────────────────────────────                                         │
│  Purpose: Prove completeness of event batches                               │
│                                                                             │
│  Components:                                                                │
│  ├─ Merkle Tree (RFC 6962): REQUIRED                                       │
│  ├─ Merkle Root: REQUIRED                                                  │
│  └─ Audit Path (for verification): REQUIRED                                │
│                                                                             │
│  Note: Enables third-party verification of batch completeness              │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  LAYER 1: Event Integrity                                                   │
│  ──────────────────────────                                                 │
│  Purpose: Individual event completeness                                     │
│                                                                             │
│  Components:                                                                │
│  ├─ EventHash (SHA-256 of canonical event): REQUIRED                       │
│  └─ PrevHash (link to previous event): OPTIONAL                            │
│                                                                             │
│  Note: PrevHash provides real-time detection (OPTIONAL in v1.1)            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Layer Responsibilities

| Layer | Purpose | REQUIRED Components | OPTIONAL Components |
|-------|---------|---------------------|---------------------|
| **Layer 3** | External Verifiability | Signature, Timestamp, External Anchor | Dual signatures (PQC) |
| **Layer 2** | Collection Integrity | Merkle Tree, Merkle Root, Audit Path | - |
| **Layer 1** | Event Integrity | EventHash | PrevHash (hash chain) |

## 3. VCP-XREF Dual Logging Architecture

### 3.1 Concept

VCP-XREF enables **Dual Logging**—independent VCP event streams from multiple parties that can be cross-referenced to detect discrepancies.

```
┌──────────────────────┐          ┌──────────────────────┐
│  Trading Algorithm   │─────────▶│     Broker/PropFirm  │
└──────────┬───────────┘          └──────────┬───────────┘
           │                                  │
           ▼                                  ▼
┌──────────────────────┐          ┌──────────────────────┐
│   VCP Sidecar        │          │   PropFirm VCP       │
│  (Trader-side)       │          │  (PropFirm-side)     │
└──────────┬───────────┘          └──────────┬───────────┘
           │                                  │
           └───────────────┬──────────────────┘
                           ▼
                  ┌─────────────────────┐
                  │ Cross-Reference     │
                  │   Verification      │
                  └─────────────────────┘

Property:  Unless both parties collude, 
           omission or modification by one party 
           is detectable by the other.
```

### 3.2 Cross-Reference Protocol

**Step 1: Initiator Logs Event**
```json
{
  "vcp_xref": {
    "cross_reference_id": "550e8400-e29b-41d4-a716-446655440001",
    "party_role": "INITIATOR",
    "counterparty_id": "propfirm-alpha.com",
    "shared_event_key": {
      "order_id": "ORD-2025-001234",
      "timestamp": 1735689600000000000,
      "tolerance_ms": 100
    },
    "reconciliation_status": "PENDING"
  }
}
```

**Step 2: Counterparty Logs Event**
```json
{
  "vcp_xref": {
    "cross_reference_id": "550e8400-e29b-41d4-a716-446655440001",
    "party_role": "COUNTERPARTY",
    "counterparty_id": "trader-john-doe",
    "shared_event_key": {
      "order_id": "ORD-2025-001234",
      "timestamp": 1735689600005000000,
      "tolerance_ms": 100
    },
    "reconciliation_status": "MATCHED"
  }
}
```

**Step 3: Cross-Reference Verification**

Both parties' logs are compared by:
1. Matching events by `(cross_reference_id, event_type)` tuple
2. Comparing critical fields (execution_price, quantity, side)
3. Verifying timestamp within tolerance
4. Reporting any discrepancies

## 4. Event Data Model (VCP v1.1)

### 4.1 Complete Event Structure

```json
{
  "header": {
    "event_id": "019abc01-0001-7c82-9d1b-111111110001",
    "trace_id": "019abc01-0000-7000-8000-aaaaaaaaaaaa",
    "timestamp_int": "1735689600000000000",
    "timestamp_iso": "2025-01-01T08:00:00.000Z",
    "event_type": "EXE",
    "event_type_code": 4,
    "timestamp_precision": "MILLISECOND",
    "clock_sync_status": "BEST_EFFORT",
    "hash_algo": "SHA256",
    "venue_id": "MT5-PROPFIRM-ALPHA",
    "symbol": "XAUUSD",
    "account_id": "trader_john_doe_001",
    "operator_id": "EA_GOLD_SCALPER_V3"
  },
  "payload": {
    "trade_data": {
      "order_id": "ORD-2025-001001",
      "exec_id": "EXEC-001001",
      "execution_price": "2651.50",
      "executed_qty": "1.00",
      "commission": "7.50",
      "slippage": "0.00"
    }
  },
  "vcp_xref": {
    "version": "1.1",
    "cross_reference_id": "550e8400-e29b-41d4-a716-446655440001",
    "party_role": "INITIATOR",
    "counterparty_id": "propfirm-alpha.com",
    "shared_event_key": {
      "order_id": "ORD-2025-001001",
      "timestamp": 1735689600000000000,
      "tolerance_ms": 100
    },
    "reconciliation_status": "MATCHED"
  },
  "policy_identification": {
    "version": "1.1",
    "policy_id": "org.veritaschain.poc:trader-001",
    "conformance_tier": "SILVER",
    "registration_policy": {
      "issuer": "VeritasChain Standards Organization",
      "policy_uri": "https://veritaschain.org/policies/poc-payout-dispute",
      "effective_date": 1735689600000000000
    },
    "verification_depth": {
      "hash_chain_validation": true,
      "merkle_proof_required": true,
      "external_anchor_required": true
    }
  },
  "security": {
    "version": "1.1",
    "event_hash": "16351b5fc03b0ef191f1577a...",
    "prev_hash": "0000000000000000000000000000000000000000000000000000000000000000",
    "hash_algo": "SHA256",
    "signature": "W2A54vt+ftLFgA5bMN4TlLTSHC7x...",
    "sign_algo": "ED25519",
    "public_key": "c1f108292ff59cc023719e579f96c057...",
    "merkle_root": "2dfd9ee4bbdaeac4eb0daea6c66a630f...",
    "merkle_index": 0,
    "merkle_proof": [
      {"hash": "edcba8db8b19b049...", "position": "right"},
      {"hash": "7a3ea681754476...", "position": "right"}
    ],
    "anchor_reference": "anchor-12ddced20c534e02"
  }
}
```

### 4.2 Event Types

| EventType | Code | Description |
|-----------|------|-------------|
| **SIG** | 1 | Signal generated by trading algorithm |
| **ORD** | 2 | Order sent to broker |
| **ACK** | 3 | Order acknowledged by broker |
| **EXE** | 4 | Order executed (filled) |
| **REJ** | 5 | Order rejected |
| **RSK** | 6 | Risk event (limit breach, etc.) |

## 5. Cryptographic Mechanisms

### 5.1 Event Hash Calculation (Layer 1)

```python
def calculate_event_hash(header, payload, vcp_xref, policy_id, prev_hash=None):
    """
    Calculate event hash per VCP v1.1 Section 6.1.1
    """
    components = [
        canonicalize_json(header),
        canonicalize_json(payload),
        canonicalize_json(vcp_xref),
        canonicalize_json(policy_id)
    ]
    
    if prev_hash and prev_hash != "0" * 64:
        components.append(prev_hash)
    
    hash_input = ''.join(components).encode('utf-8')
    return hashlib.sha256(hash_input).hexdigest()
```

### 5.2 Merkle Tree (Layer 2 - RFC 6962)

```python
def merkle_leaf_hash(data: bytes) -> bytes:
    """RFC 6962 leaf hash: SHA256(0x00 || data)"""
    return hashlib.sha256(b'\x00' + data).digest()

def merkle_node_hash(left: bytes, right: bytes) -> bytes:
    """RFC 6962 internal node hash: SHA256(0x01 || left || right)"""
    return hashlib.sha256(b'\x01' + left + right).digest()
```

Domain separation (0x00 for leaves, 0x01 for internal nodes) prevents second preimage attacks.

### 5.3 External Anchor (Layer 3)

```json
{
  "anchor_id": "anchor-12ddced20c534e02",
  "merkle_root": "2dfd9ee4bbdaeac4eb0daea6c66a630f...",
  "signature": "...",
  "sign_algo": "ED25519",
  "public_key": "...",
  "timestamp": 1735689600000000000,
  "anchor_target": {
    "type": "PUBLIC_SERVICE",
    "identifier": "opentimestamps.org",
    "proof": "ots-..."
  },
  "event_count": 23,
  "first_event_id": "019abc01-0001-...",
  "last_event_id": "019abc01-0017-...",
  "policy_id": "org.veritaschain.poc:trader-001"
}
```

## 6. Verification Process

### 6.1 Three-Layer Verification

```
┌─────────────────────────────────────────────────────────────────────┐
│                    VERIFICATION PIPELINE                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  STEP 1: Layer 1 - Event Integrity                                 │
│  ─────────────────────────────────                                  │
│  For each event:                                                    │
│    1. Recalculate EventHash from (header, payload, vcp_xref, policy)│
│    2. Compare with stored event_hash                                │
│    3. Verify prev_hash chain (if enabled)                          │
│                                                                     │
│  Result: VALID | INVALID (hash mismatch = tampering detected)      │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  STEP 2: Layer 2 - Collection Integrity                            │
│  ───────────────────────────────────────                            │
│  For each event:                                                    │
│    1. Verify merkle_proof against merkle_root                       │
│    2. Check consistent merkle_root across batch                     │
│                                                                     │
│  Result: VALID | INVALID (proof failure = event added/removed)     │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  STEP 3: Layer 3 - External Verifiability                          │
│  ─────────────────────────────────────────                          │
│  For each event:                                                    │
│    1. Verify digital signature                                      │
│    2. Check anchor_reference exists                                 │
│  For batch:                                                         │
│    3. Verify anchor record merkle_root matches                      │
│                                                                     │
│  Result: VALID | INVALID (signature failure = unauthorized change) │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  STEP 4: VCP-XREF Cross-Reference                                  │
│  ─────────────────────────────────                                  │
│  For each (cross_reference_id, event_type) pair:                   │
│    1. Match trader event with propfirm event                        │
│    2. Compare critical fields (price, quantity, side)               │
│    3. Check timestamp within tolerance                              │
│                                                                     │
│  Result: MATCHED | DISCREPANCY (with field-level details)          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.2 Discrepancy Severity Classification

| Severity | Fields | Impact |
|----------|--------|--------|
| **CRITICAL** | execution_price, executed_qty, side, quantity, reject_reason | Direct financial impact |
| **WARNING** | commission, price, order_type | Potential compliance issue |
| **INFO** | Minor timestamp differences | For monitoring only |

## 7. Security Analysis

### 7.1 Threat Model

| Threat | Mitigation |
|--------|------------|
| **Single-party log modification** | Counterparty log provides independent evidence |
| **Hash collision attack** | SHA-256 provides 128-bit security |
| **Signature forgery** | Ed25519 provides 128-bit security |
| **Merkle proof manipulation** | RFC 6962 domain separation prevents attacks |
| **Post-hoc timestamp manipulation** | External anchor proves existence at specific time |
| **Collusion between parties** | External anchor remains independent |

### 7.2 Attack Scenarios and Defenses

**Scenario 1: PropFirm modifies execution price**
- Layer 1 detection: EventHash mismatch
- Layer 2 detection: Merkle proof invalid
- VCP-XREF detection: Price discrepancy with trader log

**Scenario 2: PropFirm deletes an event**
- Layer 2 detection: Merkle tree leaf count mismatch
- VCP-XREF detection: Missing cross-reference from one party

**Scenario 3: PropFirm creates fake event**
- Layer 3 detection: Signature cannot be created without private key
- VCP-XREF detection: No matching event in trader log

## 8. Implementation Notes

### 8.1 File Organization

```
evidence/
├── trader_events.jsonl       # JSONL format, one event per line
├── propfirm_events.jsonl     # JSONL format, one event per line
└── anchor_records.json       # Batch anchor records

verifier/
└── verify.py                 # Three-layer verification tool

scripts/
├── generate_events_v1_1.py   # Event generation with Merkle tree
└── tamper_demo.py            # Tamper demonstration
```

### 8.2 Key Dependencies

**None** - This implementation uses only Python standard library:
- `hashlib` - SHA-256 hash calculation
- `json` - JSON parsing and canonicalization
- `base64` - Signature encoding
- `dataclasses` - Data structures

### 8.3 Performance Characteristics

| Operation | Complexity | Notes |
|-----------|------------|-------|
| Event hash calculation | O(1) | Single SHA-256 |
| Merkle tree building | O(n log n) | n = events in batch |
| Merkle proof verification | O(log n) | Proof path length |
| Cross-reference matching | O(n) | Linear scan with index |

## 9. Compliance Mapping

### 9.1 VCP v1.1 Specification Compliance

| VCP Section | Requirement | Implementation |
|-------------|-------------|----------------|
| 5.5 | Policy Identification | `policy_identification` object in each event |
| 5.6 | VCP-XREF | `vcp_xref` object with cross-reference ID |
| 6.0 | Three-Layer Architecture | Separate verification for each layer |
| 6.1 | EventHash | SHA-256 of canonical JSON |
| 6.2 | Merkle Tree | RFC 6962 with domain separation |
| 6.3 | External Anchor | Anchor record with merkle_root |
| 6.4 | Security Object | All required fields present |

### 9.2 Standards References

- **RFC 6962**: Certificate Transparency (Merkle Tree)
- **RFC 8785**: JSON Canonicalization Scheme (JCS)
- **RFC 9562**: UUID v7 format
- **RFC 8032**: Ed25519 Digital Signatures

## 10. Future Extensions

### 10.1 Production Considerations

1. **Real Ed25519 signatures** - Replace demo with cryptographic library
2. **OpenTimestamps integration** - Real Bitcoin-backed anchoring
3. **Database storage** - Replace JSONL with indexed database
4. **REST API** - Web service for verification
5. **Real-time streaming** - Kafka/Redis for live event capture

### 10.2 Conformance Tier Upgrades

| Current (Silver) | Gold Upgrade | Platinum Upgrade |
|------------------|--------------|------------------|
| BEST_EFFORT clock | NTP_SYNCED | PTP_LOCKED |
| 24h anchor | 1h anchor | 10min anchor |
| JSON format | JSON format | SBE binary |
| Software signing | Software signing | HSM signing |

---

**Document Status**: PoC  
**Last Updated**: 2025-01-12  
**Maintainer**: VeritasChain Standards Organization

---

*This document is part of the VCP v1.1 Payout Dispute PoC. Licensed under CC-BY-4.0.*
