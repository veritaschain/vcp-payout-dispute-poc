#!/usr/bin/env python3
"""
VCP v1.1 Payout Dispute Verification Tool
==========================================

Selected consistency checks for dual-party PoC sample logs targeting VCP v1.1.
This is not a conformance, signature-authentication, or external-proof verifier.

Features:
- Layer 1: Event hash verification
- Layer 2: Supplied paths/root consistency for the PoC padded tree
- Layer 3: Publicly computable demo prefix checks and anchor-root metadata
- VCP-XREF: Cross-reference matching and discrepancy detection
- Policy Identification: Presence checks, not tier conformance

Exit status covers event-hash failures, Merkle-check failures, and critical
cross-reference discrepancies only. It excludes signature results, anchor
metadata, hash-chain flags, policy checks, and warnings. JSON result names
ending in _valid retain their legacy PoC meaning; they do not imply conformance.

Usage:
    python verify.py --trader trader_events.jsonl --propfirm propfirm_events.jsonl

Document ID: VSO-POC-VERIFY-002
License: CC BY 4.0 International
VCP Version: 1.1
"""

import argparse
import json
import sys
import hashlib
import base64
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


# =============================================================================
# ANSI Color Codes
# =============================================================================

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    END = '\033[0m'


# =============================================================================
# Enums and Data Classes
# =============================================================================

class Severity(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class VerificationLayer(Enum):
    LAYER1_EVENT = "Layer 1: Event Integrity"
    LAYER2_COLLECTION = "Layer 2: Collection Integrity"
    LAYER3_EXTERNAL = "Layer 3: External Verifiability"
    XREF = "VCP-XREF: Cross-Reference"


@dataclass
class VCPEvent:
    """Parsed VCP v1.1 event with all required fields"""
    # Header fields
    event_id: str
    trace_id: str
    timestamp_int: int
    timestamp_iso: str
    event_type: str
    event_type_code: int
    symbol: str
    account_id: str
    
    # VCP-XREF fields
    xref_id: str
    party_role: str
    counterparty_id: str
    order_id: str
    tolerance_ms: int
    reconciliation_status: str
    
    # Policy Identification
    policy_id: str
    conformance_tier: str
    policy_version: str
    
    # Security fields
    event_hash: str
    prev_hash: str
    hash_algo: str
    signature: str
    sign_algo: str
    public_key: str
    merkle_root: str
    merkle_index: int
    merkle_proof: List[Dict]
    anchor_reference: str
    
    # Raw data for hash recalculation
    raw: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> 'VCPEvent':
        header = data.get('header', {})
        vcp_xref = data.get('vcp_xref', {})
        policy = data.get('policy_identification', {})
        security = data.get('security', {})
        shared_key = vcp_xref.get('shared_event_key', {})
        
        return cls(
            event_id=header.get('event_id', ''),
            trace_id=header.get('trace_id', ''),
            timestamp_int=int(header.get('timestamp_int', '0')),
            timestamp_iso=header.get('timestamp_iso', ''),
            event_type=header.get('event_type', ''),
            event_type_code=header.get('event_type_code', 0),
            symbol=header.get('symbol', ''),
            account_id=header.get('account_id', ''),
            
            xref_id=vcp_xref.get('cross_reference_id', ''),
            party_role=vcp_xref.get('party_role', ''),
            counterparty_id=vcp_xref.get('counterparty_id', ''),
            order_id=shared_key.get('order_id', ''),
            tolerance_ms=shared_key.get('tolerance_ms', 100),
            reconciliation_status=vcp_xref.get('reconciliation_status', ''),
            
            policy_id=policy.get('policy_id', ''),
            conformance_tier=policy.get('conformance_tier', ''),
            policy_version=policy.get('version', ''),
            
            event_hash=security.get('event_hash', ''),
            prev_hash=security.get('prev_hash', ''),
            hash_algo=security.get('hash_algo', 'SHA256'),
            signature=security.get('signature', ''),
            sign_algo=security.get('sign_algo', 'ED25519'),
            public_key=security.get('public_key', ''),
            merkle_root=security.get('merkle_root', ''),
            merkle_index=security.get('merkle_index', 0),
            merkle_proof=security.get('merkle_proof', []),
            anchor_reference=security.get('anchor_reference', ''),
            
            raw=data
        )


@dataclass
class VerificationIssue:
    """Single verification issue"""
    layer: VerificationLayer
    severity: Severity
    event_id: str
    field: str
    message: str
    expected: str = ""
    actual: str = ""


@dataclass
class Discrepancy:
    """Cross-reference discrepancy between trader and prop firm"""
    xref_id: str
    order_id: str
    field: str
    trader_value: str
    propfirm_value: str
    severity: Severity
    event_type: str
    message: str


@dataclass
class VerificationResult:
    """Complete verification result"""
    # Event counts
    trader_events: int
    propfirm_events: int
    matched_pairs: int
    
    # Layer 1 results
    trader_hashes_valid: int
    trader_hashes_invalid: int
    propfirm_hashes_valid: int
    propfirm_hashes_invalid: int
    trader_chain_valid: bool
    propfirm_chain_valid: bool
    
    # Layer 2 results
    trader_merkle_valid: bool
    propfirm_merkle_valid: bool
    trader_merkle_root: str
    propfirm_merkle_root: str
    
    # Layer 3 results
    trader_signatures_valid: int
    propfirm_signatures_valid: int
    trader_anchor_valid: bool
    propfirm_anchor_valid: bool
    
    # Policy verification
    trader_policy_valid: bool
    propfirm_policy_valid: bool
    
    # Issues and discrepancies
    issues: List[VerificationIssue]
    discrepancies: List[Discrepancy]


# =============================================================================
# Cryptographic Verification Functions
# =============================================================================

def canonicalize_json(obj: Any) -> str:
    """Simplified sorted-key JSON, not a full RFC 8785 implementation."""
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def recalculate_event_hash(event: VCPEvent) -> str:
    """Recalculate event hash per VCP v1.1 specification"""
    header = event.raw.get('header', {})
    payload = event.raw.get('payload', {})
    vcp_xref = event.raw.get('vcp_xref', {})
    policy = event.raw.get('policy_identification', {})
    prev_hash = event.prev_hash
    
    components = [
        canonicalize_json(header),
        canonicalize_json(payload),
        canonicalize_json(vcp_xref),
        canonicalize_json(policy)
    ]
    
    if prev_hash and prev_hash != "0" * 64:
        components.append(prev_hash)
    
    hash_input = ''.join(components).encode('utf-8')
    return hashlib.sha256(hash_input).hexdigest()


def verify_signature_demo(event_hash: str, signature: str, public_key: str) -> bool:
    """
    Check a publicly computable SHA-512 prefix, not an Ed25519 signature.
    This differs from the generator and does not authenticate the event.
    """
    try:
        sig_bytes = base64.b64decode(signature)
        if len(sig_bytes) != 64:
            return False
        expected_prefix = hashlib.sha512(
            bytes.fromhex(public_key)[:32] + bytes.fromhex(event_hash)
        ).digest()[:32]
        return sig_bytes[:32] == expected_prefix
    except Exception:
        return False


def merkle_leaf_hash(data: bytes) -> bytes:
    """RFC 6962 leaf hash: SHA256(0x00 || data)"""
    return hashlib.sha256(b'\x00' + data).digest()


def merkle_node_hash(left: bytes, right: bytes) -> bytes:
    """RFC 6962 internal node hash: SHA256(0x01 || left || right)"""
    return hashlib.sha256(b'\x01' + left + right).digest()


def verify_merkle_proof(event_hash: str, merkle_root: str, 
                        merkle_index: int, proof: List[Dict]) -> bool:
    """Check a supplied path using the PoC leaf and node hash prefixes."""
    try:
        current = merkle_leaf_hash(bytes.fromhex(event_hash))
        for step in proof:
            sibling = bytes.fromhex(step['hash'])
            if step['position'] == 'left':
                current = merkle_node_hash(sibling, current)
            else:
                current = merkle_node_hash(current, sibling)
        return current.hex() == merkle_root
    except Exception:
        return False


# =============================================================================
# Verification Functions
# =============================================================================

def load_events(filepath: str) -> List[VCPEvent]:
    """Load VCP v1.1 events from JSONL file"""
    events = []
    with open(filepath, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                events.append(VCPEvent.from_json(data))
            except json.JSONDecodeError as e:
                print(f"{Colors.YELLOW}Warning: Invalid JSON line {line_num}: {e}{Colors.END}")
    return events


def load_anchor_records(filepath: str) -> Dict:
    """Load anchor records from JSON file"""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def verify_layer1_event_integrity(events: List[VCPEvent], party: str) -> Tuple[int, int, bool, List[VerificationIssue]]:
    """Layer 1: Verify event integrity"""
    issues = []
    valid_hashes = 0
    invalid_hashes = 0
    chain_valid = True
    
    for i, event in enumerate(events):
        recalculated = recalculate_event_hash(event)
        if recalculated == event.event_hash:
            valid_hashes += 1
        else:
            invalid_hashes += 1
            issues.append(VerificationIssue(
                layer=VerificationLayer.LAYER1_EVENT,
                severity=Severity.CRITICAL,
                event_id=event.event_id,
                field="event_hash",
                message="Event hash mismatch - content may have been tampered",
                expected=recalculated[:32] + "...",
                actual=event.event_hash[:32] + "..."
            ))
        
        if i > 0 and event.prev_hash != "0" * 64:
            expected_prev = events[i-1].event_hash
            if event.prev_hash != expected_prev:
                chain_valid = False
                issues.append(VerificationIssue(
                    layer=VerificationLayer.LAYER1_EVENT,
                    severity=Severity.WARNING,
                    event_id=event.event_id,
                    field="prev_hash",
                    message="Hash chain break detected",
                    expected=expected_prev[:32] + "...",
                    actual=event.prev_hash[:32] + "..."
                ))
    
    return valid_hashes, invalid_hashes, chain_valid, issues


def verify_layer2_collection_integrity(events: List[VCPEvent], party: str) -> Tuple[bool, str, List[VerificationIssue]]:
    """Layer 2: Verify collection integrity"""
    issues = []
    if not events:
        return True, "", issues
    
    merkle_root = events[0].merkle_root
    merkle_valid = True
    
    for event in events:
        if event.merkle_root != merkle_root:
            merkle_valid = False
            issues.append(VerificationIssue(
                layer=VerificationLayer.LAYER2_COLLECTION,
                severity=Severity.WARNING,
                event_id=event.event_id,
                field="merkle_root",
                message="Inconsistent Merkle root within batch",
                expected=merkle_root[:32] + "...",
                actual=event.merkle_root[:32] + "..."
            ))
        
        if event.merkle_proof:
            if not verify_merkle_proof(event.event_hash, merkle_root, 
                                       event.merkle_index, event.merkle_proof):
                merkle_valid = False
                issues.append(VerificationIssue(
                    layer=VerificationLayer.LAYER2_COLLECTION,
                    severity=Severity.CRITICAL,
                    event_id=event.event_id,
                    field="merkle_proof",
                    message="Merkle proof verification failed",
                    expected="Valid proof",
                    actual="Invalid proof"
                ))
    
    return merkle_valid, merkle_root, issues


def verify_layer3_external(events: List[VCPEvent], anchor: Dict, party: str) -> Tuple[int, bool, List[VerificationIssue]]:
    """Count demo prefix matches and compare optional anchor-root metadata."""
    issues = []
    valid_signatures = 0
    anchor_valid = True
    
    for event in events:
        if verify_signature_demo(event.event_hash, event.signature, event.public_key):
            valid_signatures += 1
        
        if not event.anchor_reference:
            issues.append(VerificationIssue(
                layer=VerificationLayer.LAYER3_EXTERNAL,
                severity=Severity.WARNING,
                event_id=event.event_id,
                field="anchor_reference",
                message="Missing anchor reference (required in v1.1)",
                expected="Anchor ID",
                actual="<empty>"
            ))
    
    if anchor and events:
        if anchor.get('merkle_root') != events[0].merkle_root:
            anchor_valid = False
            issues.append(VerificationIssue(
                layer=VerificationLayer.LAYER3_EXTERNAL,
                severity=Severity.CRITICAL,
                event_id="<batch>",
                field="anchor_merkle_root",
                message="Anchor record Merkle root mismatch",
                expected=events[0].merkle_root[:32] + "...",
                actual=anchor.get('merkle_root', '<missing>')[:32] + "..."
            ))
    
    return valid_signatures, anchor_valid, issues


def verify_policy_identification(events: List[VCPEvent], party: str) -> Tuple[bool, List[VerificationIssue]]:
    """Verify Policy Identification per VCP v1.1 Section 5.5"""
    issues = []
    policy_valid = True
    
    for event in events:
        if not event.policy_id:
            policy_valid = False
            issues.append(VerificationIssue(
                layer=VerificationLayer.LAYER3_EXTERNAL,
                severity=Severity.WARNING,
                event_id=event.event_id,
                field="policy_id",
                message="Missing Policy ID (required in v1.1)",
                expected="org.example:policy-id",
                actual="<empty>"
            ))
    
    return policy_valid, issues


def extract_comparable_fields(event: VCPEvent) -> Dict[str, str]:
    """Extract fields that should match between trader and prop firm"""
    payload = event.raw.get('payload', {})
    trade_data = payload.get('trade_data', {})
    
    fields = {
        'event_type': event.event_type,
        'symbol': event.symbol,
        'order_id': event.order_id,
    }
    
    if trade_data:
        for key in ['side', 'order_type', 'price', 'quantity', 
                    'execution_price', 'executed_qty', 'commission',
                    'reject_reason', 'reject_code']:
            if key in trade_data:
                fields[key] = str(trade_data[key])
    
    return fields


def match_and_compare_events(trader_events: List[VCPEvent], 
                             propfirm_events: List[VCPEvent]) -> Tuple[int, List[Discrepancy]]:
    """Match events by CrossReferenceID and compare for discrepancies"""
    propfirm_index: Dict[Tuple[str, str], VCPEvent] = {}
    for event in propfirm_events:
        key = (event.xref_id, event.event_type)
        propfirm_index[key] = event
    
    matched_count = 0
    discrepancies = []
    critical_fields = {'execution_price', 'executed_qty', 'side', 'quantity', 'reject_reason'}
    warning_fields = {'commission', 'price', 'order_type'}
    
    for trader_event in trader_events:
        key = (trader_event.xref_id, trader_event.event_type)
        if key not in propfirm_index:
            continue
        
        propfirm_event = propfirm_index[key]
        matched_count += 1
        
        trader_fields = extract_comparable_fields(trader_event)
        propfirm_fields = extract_comparable_fields(propfirm_event)
        all_fields = set(trader_fields.keys()) | set(propfirm_fields.keys())
        
        for field in all_fields:
            trader_val = trader_fields.get(field, '<missing>')
            propfirm_val = propfirm_fields.get(field, '<missing>')
            
            if trader_val != propfirm_val:
                if field in critical_fields:
                    severity = Severity.CRITICAL
                elif field in warning_fields:
                    severity = Severity.WARNING
                else:
                    severity = Severity.INFO
                
                discrepancies.append(Discrepancy(
                    xref_id=trader_event.xref_id,
                    order_id=trader_event.order_id,
                    field=field,
                    trader_value=trader_val,
                    propfirm_value=propfirm_val,
                    severity=severity,
                    event_type=trader_event.event_type,
                    message=f"{field} mismatch"
                ))
        
        time_diff_ns = abs(trader_event.timestamp_int - propfirm_event.timestamp_int)
        tolerance_ns = trader_event.tolerance_ms * 1_000_000
        if time_diff_ns > tolerance_ns * 2:
            discrepancies.append(Discrepancy(
                xref_id=trader_event.xref_id,
                order_id=trader_event.order_id,
                field="timestamp",
                trader_value=trader_event.timestamp_iso,
                propfirm_value=propfirm_event.timestamp_iso,
                severity=Severity.WARNING,
                event_type=trader_event.event_type,
                message=f"Timestamp diff ({time_diff_ns/1_000_000:.1f}ms) exceeds 2x tolerance"
            ))
    
    return matched_count, discrepancies


def verify_logs(trader_file: str, propfirm_file: str, 
                anchor_file: Optional[str] = None) -> VerificationResult:
    """Main verification function for VCP v1.1 logs"""
    
    trader_events = load_events(trader_file)
    propfirm_events = load_events(propfirm_file)
    
    anchors = {}
    if anchor_file and Path(anchor_file).exists():
        anchors = load_anchor_records(anchor_file)
    
    all_issues = []
    
    t_valid, t_invalid, t_chain, t_issues = verify_layer1_event_integrity(trader_events, "trader")
    p_valid, p_invalid, p_chain, p_issues = verify_layer1_event_integrity(propfirm_events, "propfirm")
    all_issues.extend(t_issues)
    all_issues.extend(p_issues)
    
    t_merkle_valid, t_merkle_root, t_m_issues = verify_layer2_collection_integrity(trader_events, "trader")
    p_merkle_valid, p_merkle_root, p_m_issues = verify_layer2_collection_integrity(propfirm_events, "propfirm")
    all_issues.extend(t_m_issues)
    all_issues.extend(p_m_issues)
    
    t_sigs, t_anchor, t_e_issues = verify_layer3_external(
        trader_events, anchors.get('trader_anchor', {}), "trader")
    p_sigs, p_anchor, p_e_issues = verify_layer3_external(
        propfirm_events, anchors.get('propfirm_anchor', {}), "propfirm")
    all_issues.extend(t_e_issues)
    all_issues.extend(p_e_issues)
    
    t_policy, t_p_issues = verify_policy_identification(trader_events, "trader")
    p_policy, p_p_issues = verify_policy_identification(propfirm_events, "propfirm")
    all_issues.extend(t_p_issues)
    all_issues.extend(p_p_issues)
    
    matched_count, discrepancies = match_and_compare_events(trader_events, propfirm_events)
    
    return VerificationResult(
        trader_events=len(trader_events),
        propfirm_events=len(propfirm_events),
        matched_pairs=matched_count,
        trader_hashes_valid=t_valid,
        trader_hashes_invalid=t_invalid,
        propfirm_hashes_valid=p_valid,
        propfirm_hashes_invalid=p_invalid,
        trader_chain_valid=t_chain,
        propfirm_chain_valid=p_chain,
        trader_merkle_valid=t_merkle_valid,
        propfirm_merkle_valid=p_merkle_valid,
        trader_merkle_root=t_merkle_root,
        propfirm_merkle_root=p_merkle_root,
        trader_signatures_valid=t_sigs,
        propfirm_signatures_valid=p_sigs,
        trader_anchor_valid=t_anchor,
        propfirm_anchor_valid=p_anchor,
        trader_policy_valid=t_policy,
        propfirm_policy_valid=p_policy,
        issues=all_issues,
        discrepancies=discrepancies
    )


def print_result(result: VerificationResult, verbose: bool = False):
    """Print verification results with colors"""
    
    print()
    print(f"{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}        VCP v1.1 PAYOUT DISPUTE PoC CHECKS{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}")
    print()
    
    # Layer 1
    print(f"{Colors.CYAN}{Colors.BOLD}Layer 1: Event Integrity{Colors.END}")
    print(f"  {Colors.DIM}(EventHash, PrevHash){Colors.END}")
    print()
    
    t_hash_ok = result.trader_hashes_invalid == 0
    p_hash_ok = result.propfirm_hashes_invalid == 0
    
    icon = f"{Colors.GREEN}✓{Colors.END}" if t_hash_ok else f"{Colors.RED}✗{Colors.END}"
    print(f"  {icon} Trader event hashes:   {result.trader_hashes_valid}/{result.trader_events} valid")
    icon = f"{Colors.GREEN}✓{Colors.END}" if p_hash_ok else f"{Colors.RED}✗{Colors.END}"
    print(f"  {icon} PropFirm event hashes: {result.propfirm_hashes_valid}/{result.propfirm_events} valid")
    icon = f"{Colors.GREEN}✓{Colors.END}" if result.trader_chain_valid else f"{Colors.YELLOW}⚠{Colors.END}"
    print(f"  {icon} Trader hash chain:     {'VALID' if result.trader_chain_valid else 'BROKEN'}")
    icon = f"{Colors.GREEN}✓{Colors.END}" if result.propfirm_chain_valid else f"{Colors.YELLOW}⚠{Colors.END}"
    print(f"  {icon} PropFirm hash chain:   {'VALID' if result.propfirm_chain_valid else 'BROKEN'}")
    print()
    
    # Layer 2
    print(f"{Colors.CYAN}{Colors.BOLD}Layer 2: PoC Merkle Checks{Colors.END}")
    print(f"  {Colors.DIM}(Supplied padded-tree paths and stored roots; missing proofs are skipped){Colors.END}")
    print()
    icon = f"{Colors.GREEN}✓{Colors.END}" if result.trader_merkle_valid else f"{Colors.RED}✗{Colors.END}"
    print(f"  {icon} Trader Merkle checks:    {'NO FAILURE REPORTED' if result.trader_merkle_valid else 'FAILED'}")
    if result.trader_merkle_root:
        print(f"      Root: {result.trader_merkle_root[:48]}...")
    icon = f"{Colors.GREEN}✓{Colors.END}" if result.propfirm_merkle_valid else f"{Colors.RED}✗{Colors.END}"
    print(f"  {icon} PropFirm Merkle checks:  {'NO FAILURE REPORTED' if result.propfirm_merkle_valid else 'FAILED'}")
    if result.propfirm_merkle_root:
        print(f"      Root: {result.propfirm_merkle_root[:48]}...")
    print()
    
    # Layer 3
    print(f"{Colors.CYAN}{Colors.BOLD}Layer 3: Demo Signature / Anchor Metadata Checks{Colors.END}")
    print(f"  {Colors.DIM}(Publicly computable prefix check; optional anchor-root comparison only){Colors.END}")
    print()
    t_sig_ok = result.trader_signatures_valid == result.trader_events
    p_sig_ok = result.propfirm_signatures_valid == result.propfirm_events
    icon = f"{Colors.GREEN}✓{Colors.END}" if t_sig_ok else f"{Colors.YELLOW}⚠{Colors.END}"
    print(f"  {icon} Trader demo signatures:     {result.trader_signatures_valid}/{result.trader_events} prefix matches")
    icon = f"{Colors.GREEN}✓{Colors.END}" if p_sig_ok else f"{Colors.YELLOW}⚠{Colors.END}"
    print(f"  {icon} PropFirm demo signatures:   {result.propfirm_signatures_valid}/{result.propfirm_events} prefix matches")
    icon = f"{Colors.GREEN}✓{Colors.END}" if result.trader_anchor_valid else f"{Colors.YELLOW}⚠{Colors.END}"
    print(f"  {icon} Trader anchor-root mismatch:   {'NOT DETECTED' if result.trader_anchor_valid else 'DETECTED'}")
    icon = f"{Colors.GREEN}✓{Colors.END}" if result.propfirm_anchor_valid else f"{Colors.YELLOW}⚠{Colors.END}"
    print(f"  {icon} PropFirm anchor-root mismatch: {'NOT DETECTED' if result.propfirm_anchor_valid else 'DETECTED'}")
    print("  Missing anchor records also leave the mismatch flag unset.")
    print("  No external signature or timestamp proof is verified.")
    print()
    
    # VCP-XREF
    print(f"{Colors.CYAN}{Colors.BOLD}VCP-XREF: Cross-Reference Verification{Colors.END}")
    print(f"  {Colors.DIM}(Dual Logging, Discrepancy Detection){Colors.END}")
    print()
    print(f"  Trader events:    {result.trader_events}")
    print(f"  PropFirm events:  {result.propfirm_events}")
    print(f"  Matched pairs:    {result.matched_pairs}")
    print()
    
    # Discrepancies
    critical = [d for d in result.discrepancies if d.severity == Severity.CRITICAL]
    warnings = [d for d in result.discrepancies if d.severity == Severity.WARNING]
    
    if result.discrepancies:
        print(f"{Colors.RED}{Colors.BOLD}✗ DISCREPANCIES DETECTED{Colors.END}")
        print()
        if critical:
            print(f"  {Colors.RED}CRITICAL: {len(critical)}{Colors.END}")
            for d in critical:
                print(f"    • [{d.event_type}] {d.order_id}: {d.field}")
                print(f"      ├─ Trader:   {d.trader_value}")
                print(f"      └─ PropFirm: {d.propfirm_value}")
        if warnings:
            print(f"  {Colors.YELLOW}WARNING: {len(warnings)}{Colors.END}")
            for d in warnings:
                print(f"    • [{d.event_type}] {d.order_id}: {d.field}")
                if verbose:
                    print(f"      ├─ Trader:   {d.trader_value}")
                    print(f"      └─ PropFirm: {d.propfirm_value}")
    else:
        print(f"{Colors.GREEN}{Colors.BOLD}✓ NO DISCREPANCIES DETECTED{Colors.END}")
    print()
    
    # Summary
    print(f"{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}                         SUMMARY{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}")
    
    all_valid = (
        result.trader_hashes_invalid == 0 and
        result.propfirm_hashes_invalid == 0 and
        result.trader_merkle_valid and
        result.propfirm_merkle_valid and
        len(critical) == 0
    )
    
    if all_valid:
        print(f"""
{Colors.GREEN}No failures reported by the PoC exit-status checks.{Colors.END}

These checks cover event hashes, supplied Merkle paths/root consistency,
and critical cross-reference discrepancies.
Signature results, anchor metadata, hash-chain flags, policy checks, and warnings
do not determine the exit status. Review the individual results above.

{Colors.BOLD}PoC result: selected consistency checks only; no signature authentication or external proof verification.{Colors.END}
""")
    else:
        print(f"""
{Colors.RED}Selected PoC checks FAILED.{Colors.END}

Issues detected:
  • Event hash failures:    {result.trader_hashes_invalid + result.propfirm_hashes_invalid}
  • Merkle check failures:  {int(not result.trader_merkle_valid) + int(not result.propfirm_merkle_valid)}
  • Critical discrepancies: {len(critical)}

{Colors.BOLD}These sample-log inconsistencies are detected by the selected PoC checks.{Colors.END}
Signature results, anchor metadata, hash-chain flags, policy checks, and warnings
do not determine the exit status. No attribution or non-repudiation is established.
""")


def main():
    parser = argparse.ArgumentParser(
        description="Selected checks for VCP v1.1 PoC sample logs (not conformance)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
PoC check scope:
  - Event hashes and supplied paths in the padded Merkle tree
  - Policy metadata presence and selected cross-reference fields
  - Demo signature-prefix counts and optional anchor-root comparison
  - No Ed25519 authentication or external timestamp-proof verification
  - Exit status excludes signature, anchor, hash-chain, policy, and warning results

Examples:
  python verify.py --trader trader.jsonl --propfirm propfirm.jsonl
  python verify.py -t trader.jsonl -p propfirm.jsonl -a anchor_records.json -v

For more information: https://veritaschain.org
        """
    )
    
    parser.add_argument('-t', '--trader', required=True, help='Trader events (JSONL)')
    parser.add_argument('-p', '--propfirm', required=True, help='PropFirm events (JSONL)')
    parser.add_argument('-a', '--anchor', help='Synthetic anchor metadata (JSON, optional; root comparison only)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Show all details')
    parser.add_argument('--json', action='store_true', help='Output legacy PoC result fields as JSON (not conformance)')
    
    args = parser.parse_args()
    
    if not Path(args.trader).exists():
        print(f"{Colors.RED}Error: Trader file not found: {args.trader}{Colors.END}")
        sys.exit(1)
    if not Path(args.propfirm).exists():
        print(f"{Colors.RED}Error: PropFirm file not found: {args.propfirm}{Colors.END}")
        sys.exit(1)
    
    result = verify_logs(args.trader, args.propfirm, args.anchor)
    
    if args.json:
        output = {
            'vcp_version': '1.1',
            'trader_events': result.trader_events,
            'propfirm_events': result.propfirm_events,
            'matched_pairs': result.matched_pairs,
            'layer1': {
                'trader_hashes_valid': result.trader_hashes_valid,
                'propfirm_hashes_valid': result.propfirm_hashes_valid,
                'trader_chain_valid': result.trader_chain_valid,
                'propfirm_chain_valid': result.propfirm_chain_valid
            },
            'layer2': {
                'trader_merkle_valid': result.trader_merkle_valid,
                'propfirm_merkle_valid': result.propfirm_merkle_valid
            },
            'layer3': {
                'trader_signatures_valid': result.trader_signatures_valid,
                'propfirm_signatures_valid': result.propfirm_signatures_valid
            },
            'discrepancies': [
                {
                    'xref_id': d.xref_id,
                    'order_id': d.order_id,
                    'field': d.field,
                    'trader_value': d.trader_value,
                    'propfirm_value': d.propfirm_value,
                    'severity': d.severity.value,
                    'event_type': d.event_type
                }
                for d in result.discrepancies
            ]
        }
        print(json.dumps(output, indent=2))
    else:
        print_result(result, args.verbose)
    
    critical = [d for d in result.discrepancies if d.severity == Severity.CRITICAL]
    has_failures = (
        result.trader_hashes_invalid > 0 or
        result.propfirm_hashes_invalid > 0 or
        not result.trader_merkle_valid or
        not result.propfirm_merkle_valid or
        len(critical) > 0
    )
    sys.exit(1 if has_failures else 0)


if __name__ == '__main__':
    main()
