#!/usr/bin/env python3
"""
VCP v1.1 Tamper Demonstration Script
=====================================

Edits one execution price in a PoC sample log targeting VCP v1.1.
The stored event hash, Merkle proof, and demo signature remain unchanged.

Expected verifier results for this edit:
- Layer 1: Recomputed event hash mismatch
- Layer 2: No new failure; paths use the unchanged stored event hash
- Layer 3: Demo prefix counts unchanged, no external proof verification
- VCP-XREF: Execution-price discrepancy

Usage:
    python tamper_demo.py

Document ID: VSO-POC-TAMPER-002
License: CC BY 4.0 International
VCP Version: 1.1
"""

import json
import hashlib
import sys
from pathlib import Path

# ANSI color codes
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    END = '\033[0m'


def tamper_event(event: dict, field_path: list, new_value) -> dict:
    """Modify a field in the event (simulating tampering)."""
    tampered = json.loads(json.dumps(event))  # Deep copy
    
    # Navigate to the field
    current = tampered
    for key in field_path[:-1]:
        current = current[key]
    
    # Modify the value
    current[field_path[-1]] = new_value
    
    return tampered


def main():
    print(f"""
{Colors.BOLD}{'='*70}
        VCP v1.1 TAMPER DEMONSTRATION
{'='*70}{Colors.END}

This PoC edits a sample execution price without updating its stored hash.

{Colors.CYAN}Expected results from the current PoC verifier:{Colors.END}
  • Layer 1: Recomputed EventHash differs
  • Layer 2: Stored-hash Merkle paths remain unchanged
  • Layer 3: Demo prefix counts unchanged; no external proof verification
  • VCP-XREF: Changed price differs from the trader sample

{Colors.YELLOW}Scenario: PropFirm changes execution price from 2658.20 to 2655.50
          to claim worse fill and reduce trader's profit by $2.70/oz.{Colors.END}
""")
    
    # Load original events
    source_file = Path(__file__).parent.parent / 'evidence' / 'propfirm_events.jsonl'
    output_file = Path(__file__).parent.parent / 'evidence' / 'propfirm_tampered.jsonl'
    
    if not source_file.exists():
        print(f"{Colors.RED}Error: Source file not found: {source_file}{Colors.END}")
        print(f"Please run 'python scripts/generate_events_v1_1.py' first.")
        sys.exit(1)
    
    events = []
    with open(source_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    
    print(f"{Colors.CYAN}Loaded {len(events)} events from prop firm log{Colors.END}")
    print()
    
    # Find the EXE event for order 002 (the profitable XAUUSD trade)
    tamper_index = None
    original_price = None
    
    for i, event in enumerate(events):
        header = event.get('header', {})
        payload = event.get('payload', {})
        trade_data = payload.get('trade_data', {})
        vcp_xref = event.get('vcp_xref', {})
        shared_key = vcp_xref.get('shared_event_key', {})
        
        if (header.get('event_type') == 'EXE' and 
            shared_key.get('order_id') == 'ORD-2025-001002'):
            tamper_index = i
            original_price = trade_data.get('execution_price')
            break
    
    if tamper_index is None:
        print(f"{Colors.RED}Error: Target event not found{Colors.END}")
        sys.exit(1)
    
    target_event = events[tamper_index]
    security = target_event['security']
    
    # Show original event details
    print(f"{Colors.BOLD}Original Event #{tamper_index + 1}:{Colors.END}")
    print(f"  Order ID:           ORD-2025-001002")
    print(f"  Event Type:         EXE (Execution)")
    print(f"  Symbol:             XAUUSD")
    print(f"  Execution Price:    {Colors.GREEN}{original_price}{Colors.END}")
    print()
    print(f"  {Colors.DIM}VCP v1.1 Security Layer:{Colors.END}")
    print(f"  Event Hash:         {security['event_hash'][:32]}...")
    print(f"  Merkle Root:        {security['merkle_root'][:32]}...")
    print(f"  Merkle Index:       {security['merkle_index']}")
    print(f"  Signature:          {security['signature'][:32]}...")
    print(f"  Anchor Reference:   {security['anchor_reference']}")
    print()
    
    # Perform tampering
    new_price = "2655.50"  # Changed from 2658.20
    
    print(f"{Colors.YELLOW}{Colors.BOLD}TAMPERING: Changing execution_price{Colors.END}")
    print(f"  From: {Colors.GREEN}{original_price}{Colors.END}")
    print(f"  To:   {Colors.RED}{new_price}{Colors.END}")
    print()
    
    events[tamper_index] = tamper_event(
        events[tamper_index],
        ['payload', 'trade_data', 'execution_price'],
        new_price
    )
    
    # Show Three-Layer impact
    print(f"{Colors.BOLD}{'='*70}")
    print(f"        THREE-LAYER ARCHITECTURE IMPACT")
    print(f"{'='*70}{Colors.END}")
    print()
    
    print(f"{Colors.MAGENTA}{Colors.BOLD}Layer 1: Event Integrity - BROKEN{Colors.END}")
    print(f"  {Colors.DIM}(EventHash, PrevHash){Colors.END}")
    print()
    print(f"  The EventHash was computed over the original content.")
    print(f"  After modification, recalculating the hash produces a different value.")
    print()
    print(f"    Stored hash:      {security['event_hash'][:40]}...")
    print(f"    {Colors.RED}Recalculated:     [DIFFERENT - Content modified]{Colors.END}")
    print()
    print(f"  {Colors.RED}→ Verifier detects: EVENT_HASH_MISMATCH{Colors.END}")
    print()
    
    print(f"{Colors.MAGENTA}{Colors.BOLD}Layer 2: PoC Merkle Checks - UNCHANGED{Colors.END}")
    print(f"  {Colors.DIM}(Padded-tree paths checked against stored event hashes){Colors.END}")
    print()
    print(f"  The stored EventHash and its Merkle proof were not changed.")
    print(f"  The verifier uses that stored hash, so this path still matches the root.")
    print()
    print(f"    Merkle Root:      {security['merkle_root'][:40]}...")
    print(f"    Proof Path:       {len(security['merkle_proof'])} steps")
    print(f"    {Colors.YELLOW}Expected result:  No new Merkle failure from this edit{Colors.END}")
    print()
    print(f"  {Colors.YELLOW}→ Recomputed content-hash failure is detected separately in Layer 1{Colors.END}")
    print()
    
    print(f"{Colors.MAGENTA}{Colors.BOLD}Layer 3: Demo Metadata - NO EXTERNAL VERIFICATION{Colors.END}")
    print(f"  {Colors.DIM}(SHA-512 demo prefix check and synthetic anchor metadata){Colors.END}")
    print()
    print(f"  The demo signature check uses the unchanged stored EventHash.")
    print(f"  It is not Ed25519 and does not authenticate event content.")
    print(f"  The committed samples report 0/23 prefix matches per party before and after this edit.")
    print()
    print(f"    Signature:        {security['signature'][:40]}...")
    print(f"    Public Key:       {security['public_key'][:40]}...")
    print(f"    {Colors.YELLOW}Verification:     No cryptographic signature authentication{Colors.END}")
    print()
    print(f"  Anchor metadata is synthetic; the verifier only compares stored roots.")
    print(f"  No OpenTimestamps submission or timestamp-proof validation occurs.")
    print()
    print(f"    Anchor ID:        {security['anchor_reference']}")
    print(f"    {Colors.YELLOW}→ No independent timestamp is established by this demo{Colors.END}")
    print()
    
    # Save tampered file
    with open(output_file, 'w') as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')
    
    print(f"{Colors.GREEN}Tampered log saved to: {output_file.name}{Colors.END}")
    print()
    
    # VCP-XREF impact
    print(f"{Colors.BOLD}{'='*70}")
    print(f"        VCP-XREF CROSS-REFERENCE IMPACT")
    print(f"{'='*70}{Colors.END}")
    print()
    print(f"  The separate trader sample still contains the ORIGINAL price.")
    print(f"  Cross-reference verification will detect the discrepancy:")
    print()
    print(f"    CrossReferenceID: {target_event['vcp_xref']['cross_reference_id']}")
    print(f"    Order ID:         ORD-2025-001002")
    print(f"    Field:            execution_price")
    print()
    print(f"    {Colors.GREEN}Trader logged:    {original_price}{Colors.END}")
    print(f"    {Colors.RED}PropFirm logged:  {new_price}{Colors.END}")
    print()
    print(f"  {Colors.RED}→ Verifier detects: CRITICAL DISCREPANCY{Colors.END}")
    print()
    
    # Instructions
    print(f"{Colors.BOLD}{'='*70}")
    print(f"                    VERIFICATION DEMO")
    print(f"{'='*70}{Colors.END}")
    print(f"""
Now run the verifier to detect the tampering:

{Colors.CYAN}python verifier/verify.py \\
    --trader evidence/trader_events.jsonl \\
    --propfirm evidence/propfirm_tampered.jsonl \\
    --anchor evidence/anchor_records.json{Colors.END}

The PoC verifier will report:

  {Colors.RED}Layer 1:{Colors.END} Recomputed event hash mismatch
  {Colors.YELLOW}Layer 2:{Colors.END} No new Merkle failure (stored hash unchanged)
  {Colors.RED}VCP-XREF:{Colors.END} execution_price discrepancy
     - Trader logged:   {original_price}
     - PropFirm logged: {new_price}

{Colors.BOLD}These sample-log inconsistencies are detected by the selected PoC checks.{Colors.END}
{Colors.BOLD}This demo does not establish authentic signatures, independent timestamps, or a dispute outcome.{Colors.END}
""")


if __name__ == '__main__':
    main()
