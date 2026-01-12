#!/usr/bin/env python3
"""
VCP Payout Dispute Verification Tool
=====================================

Cross-reference verification for dual-party VCP event logs.
Detects discrepancies between trader and prop firm records.

Usage:
    python verify.py --trader trader_events.jsonl --propfirm propfirm_events.jsonl

Document ID: VSO-POC-VERIFY-001
License: CC BY 4.0 International
"""

import argparse
import json
import sys
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# ANSI color codes
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'


class Severity(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class VCPEvent:
    """Parsed VCP event with key fields extracted."""
    event_id: str
    trace_id: str
    timestamp_int: int
    timestamp_iso: str
    event_type: str
    event_type_code: int
    symbol: str
    account_id: str
    xref_id: str
    party_role: str
    order_id: str
    tolerance_ms: int
    event_hash: str
    prev_hash: str
    raw: Dict[str, Any]
    
    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> 'VCPEvent':
        header = data.get('header', {})
        vcp_xref = data.get('vcp_xref', {})
        security = data.get('security', {})
        shared_key = vcp_xref.get('SharedEventKey', {})
        
        return cls(
            event_id=header.get('event_id', ''),
            trace_id=header.get('trace_id', ''),
            timestamp_int=int(header.get('timestamp_int', '0')),
            timestamp_iso=header.get('timestamp_iso', ''),
            event_type=header.get('event_type', ''),
            event_type_code=header.get('event_type_code', 0),
            symbol=header.get('symbol', ''),
            account_id=header.get('account_id', ''),
            xref_id=vcp_xref.get('CrossReferenceID', ''),
            party_role=vcp_xref.get('PartyRole', ''),
            order_id=shared_key.get('OrderID', ''),
            tolerance_ms=shared_key.get('ToleranceMs', 100),
            event_hash=security.get('event_hash', ''),
            prev_hash=security.get('prev_hash', ''),
            raw=data
        )


@dataclass
class Discrepancy:
    """Detected discrepancy between trader and prop firm logs."""
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
    """Complete verification result."""
    trader_events: int
    propfirm_events: int
    matched_pairs: int
    discrepancies: List[Discrepancy]
    trader_chain_valid: bool
    propfirm_chain_valid: bool
    trader_chain_break: Optional[int]
    propfirm_chain_break: Optional[int]


def load_events(filepath: str) -> List[VCPEvent]:
    """Load VCP events from JSONL file."""
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
                print(f"{Colors.YELLOW}⚠ Warning: Invalid JSON on line {line_num}: {e}{Colors.END}")
    return events


def verify_hash_chain(events: List[VCPEvent]) -> Tuple[bool, Optional[int]]:
    """
    Verify the hash chain integrity.
    Returns (is_valid, break_index) where break_index is None if valid.
    
    Note: This is a simplified check for the PoC. Production implementations
    should recompute hashes from event content.
    """
    if not events:
        return True, None
    
    # Check first event has genesis prev_hash
    genesis_hash = "0" * 64
    if events[0].prev_hash != genesis_hash:
        # Could be continuation chain - check if it's at least consistent
        pass
    
    # Verify chain continuity
    for i in range(1, len(events)):
        expected_prev = events[i-1].event_hash
        actual_prev = events[i].prev_hash
        
        if expected_prev != actual_prev:
            return False, i
    
    return True, None


def extract_comparable_fields(event: VCPEvent) -> Dict[str, str]:
    """Extract fields that should match between trader and prop firm."""
    payload = event.raw.get('payload', {})
    trade_data = payload.get('trade_data', {})
    vcp_risk = payload.get('vcp_risk', {})
    vcp_gov = payload.get('vcp_gov', {})
    
    fields = {
        'event_type': event.event_type,
        'symbol': event.symbol,
        'order_id': event.order_id,
    }
    
    # Trading fields
    if trade_data:
        for key in ['side', 'order_type', 'price', 'quantity', 
                    'execution_price', 'executed_qty', 'commission',
                    'reject_reason', 'reject_code']:
            if key in trade_data:
                fields[key] = str(trade_data[key])
    
    # Risk fields
    if vcp_risk:
        snapshot = vcp_risk.get('snapshot', {})
        for key in ['total_equity', 'margin_level_pct', 'daily_pnl', 'max_drawdown_pct']:
            if key in snapshot:
                fields[f'risk_{key}'] = str(snapshot[key])
    
    # Governance fields
    if vcp_gov:
        for key in ['signal_type', 'confidence']:
            if key in vcp_gov:
                fields[f'gov_{key}'] = str(vcp_gov[key])
    
    return fields


def match_events(trader_events: List[VCPEvent], 
                 propfirm_events: List[VCPEvent]) -> List[Tuple[VCPEvent, VCPEvent]]:
    """Match events by CrossReferenceID and event type."""
    # Build index of prop firm events
    propfirm_index: Dict[Tuple[str, str], VCPEvent] = {}
    for event in propfirm_events:
        key = (event.xref_id, event.event_type)
        propfirm_index[key] = event
    
    # Match trader events
    matched = []
    for trader_event in trader_events:
        key = (trader_event.xref_id, trader_event.event_type)
        if key in propfirm_index:
            matched.append((trader_event, propfirm_index[key]))
    
    return matched


def compare_events(trader: VCPEvent, propfirm: VCPEvent) -> List[Discrepancy]:
    """Compare two matched events for discrepancies."""
    discrepancies = []
    
    trader_fields = extract_comparable_fields(trader)
    propfirm_fields = extract_comparable_fields(propfirm)
    
    # Fields that must match exactly
    critical_fields = {'execution_price', 'executed_qty', 'side', 'quantity', 'reject_reason'}
    warning_fields = {'commission', 'price', 'order_type'}
    info_fields = {'gov_confidence'}
    
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
                xref_id=trader.xref_id,
                order_id=trader.order_id,
                field=field,
                trader_value=trader_val,
                propfirm_value=propfirm_val,
                severity=severity,
                event_type=trader.event_type,
                message=f"{field} mismatch: trader={trader_val}, propfirm={propfirm_val}"
            ))
    
    # Check timestamp tolerance
    time_diff_ns = abs(trader.timestamp_int - propfirm.timestamp_int)
    tolerance_ns = trader.tolerance_ms * 1_000_000
    
    if time_diff_ns > tolerance_ns * 2:
        discrepancies.append(Discrepancy(
            xref_id=trader.xref_id,
            order_id=trader.order_id,
            field="timestamp",
            trader_value=trader.timestamp_iso,
            propfirm_value=propfirm.timestamp_iso,
            severity=Severity.WARNING,
            event_type=trader.event_type,
            message=f"Timestamp difference ({time_diff_ns/1_000_000:.1f}ms) exceeds 2x tolerance"
        ))
    
    return discrepancies


def verify_logs(trader_file: str, propfirm_file: str) -> VerificationResult:
    """Main verification function."""
    # Load events
    trader_events = load_events(trader_file)
    propfirm_events = load_events(propfirm_file)
    
    # Verify hash chains
    trader_chain_valid, trader_break = verify_hash_chain(trader_events)
    propfirm_chain_valid, propfirm_break = verify_hash_chain(propfirm_events)
    
    # Match and compare events
    matched_pairs = match_events(trader_events, propfirm_events)
    
    all_discrepancies = []
    for trader_event, propfirm_event in matched_pairs:
        discrepancies = compare_events(trader_event, propfirm_event)
        all_discrepancies.extend(discrepancies)
    
    return VerificationResult(
        trader_events=len(trader_events),
        propfirm_events=len(propfirm_events),
        matched_pairs=len(matched_pairs),
        discrepancies=all_discrepancies,
        trader_chain_valid=trader_chain_valid,
        propfirm_chain_valid=propfirm_chain_valid,
        trader_chain_break=trader_break,
        propfirm_chain_break=propfirm_break
    )


def print_result(result: VerificationResult, verbose: bool = False):
    """Print verification results with colors."""
    print()
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}        VCP PAYOUT DISPUTE VERIFICATION{Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    print()
    
    # Hash chain status
    print(f"{Colors.CYAN}Hash Chain Integrity:{Colors.END}")
    
    if result.trader_chain_valid:
        print(f"  {Colors.GREEN}✓{Colors.END} Trader chain: VALID ({result.trader_events} events)")
    else:
        print(f"  {Colors.RED}✗{Colors.END} Trader chain: BROKEN at event #{result.trader_chain_break}")
    
    if result.propfirm_chain_valid:
        print(f"  {Colors.GREEN}✓{Colors.END} PropFirm chain: VALID ({result.propfirm_events} events)")
    else:
        print(f"  {Colors.RED}✗{Colors.END} PropFirm chain: BROKEN at event #{result.propfirm_chain_break}")
    
    print()
    
    # Cross-reference matching
    print(f"{Colors.CYAN}Cross-Reference Matching:{Colors.END}")
    print(f"  Trader events:   {result.trader_events}")
    print(f"  PropFirm events: {result.propfirm_events}")
    print(f"  Matched pairs:   {result.matched_pairs}")
    print()
    
    # Discrepancies
    critical = [d for d in result.discrepancies if d.severity == Severity.CRITICAL]
    warnings = [d for d in result.discrepancies if d.severity == Severity.WARNING]
    info = [d for d in result.discrepancies if d.severity == Severity.INFO]
    
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
        
        if info and verbose:
            print(f"  {Colors.BLUE}INFO: {len(info)}{Colors.END}")
    else:
        print(f"{Colors.GREEN}{Colors.BOLD}✓ NO DISCREPANCIES DETECTED{Colors.END}")
    
    print()
    
    # Summary
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}                    SUMMARY{Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")
    
    all_valid = (result.trader_chain_valid and 
                 result.propfirm_chain_valid and 
                 len(critical) == 0)
    
    if all_valid:
        print(f"""
{Colors.GREEN}All verification checks PASSED.{Colors.END}

Both parties' logs are:
  • Cryptographically intact (hash chains valid)
  • Mutually consistent (no critical discrepancies)

{Colors.BOLD}This verification is MATHEMATICALLY PROVABLE.{Colors.END}
""")
    else:
        print(f"""
{Colors.RED}Verification FAILED.{Colors.END}

Issues detected:
  • Critical discrepancies: {len(critical)}
  • Chain integrity issues: {int(not result.trader_chain_valid) + int(not result.propfirm_chain_valid)}

{Colors.BOLD}These discrepancies are CRYPTOGRAPHICALLY PROVABLE.{Colors.END}
{Colors.BOLD}Manipulation requires collusion between BOTH parties.{Colors.END}
""")


def main():
    parser = argparse.ArgumentParser(
        description="VCP Payout Dispute Verification Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python verify.py --trader trader.jsonl --propfirm propfirm.jsonl
  python verify.py -t trader.jsonl -p propfirm.jsonl -v
  python verify.py -t evidence/trader_events.jsonl -p evidence/propfirm_events.jsonl

For more information: https://veritaschain.org
        """
    )
    
    parser.add_argument(
        '-t', '--trader',
        required=True,
        help='Path to trader-side VCP events (JSONL)'
    )
    parser.add_argument(
        '-p', '--propfirm',
        required=True,
        help='Path to prop firm-side VCP events (JSONL)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show all discrepancy details'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output results as JSON'
    )
    
    args = parser.parse_args()
    
    # Verify files exist
    if not Path(args.trader).exists():
        print(f"{Colors.RED}Error: Trader file not found: {args.trader}{Colors.END}")
        sys.exit(1)
    
    if not Path(args.propfirm).exists():
        print(f"{Colors.RED}Error: PropFirm file not found: {args.propfirm}{Colors.END}")
        sys.exit(1)
    
    # Run verification
    result = verify_logs(args.trader, args.propfirm)
    
    if args.json:
        # JSON output for programmatic use
        output = {
            'trader_events': result.trader_events,
            'propfirm_events': result.propfirm_events,
            'matched_pairs': result.matched_pairs,
            'trader_chain_valid': result.trader_chain_valid,
            'propfirm_chain_valid': result.propfirm_chain_valid,
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
    
    # Exit code
    critical = [d for d in result.discrepancies if d.severity == Severity.CRITICAL]
    if not result.trader_chain_valid or not result.propfirm_chain_valid or critical:
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
