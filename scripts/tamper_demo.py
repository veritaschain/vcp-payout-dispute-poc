#!/usr/bin/env python3
"""
VCP Tamper Demonstration Script
================================

Demonstrates what happens when a prop firm attempts to modify 
execution records after the fact.

This script:
1. Loads the legitimate prop firm events
2. Modifies a key execution price
3. Shows how the hash chain is broken
4. Saves the tampered version for verification demo

Usage:
    python tamper_demo.py

Document ID: VSO-POC-TAMPER-001
License: CC BY 4.0 International
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
    BOLD = '\033[1m'
    END = '\033[0m'


def compute_hash(event: dict) -> str:
    """Compute SHA-256 hash of event content (simplified for demo)."""
    # In production, this would follow VCP canonical serialization
    header = event.get('header', {})
    payload = event.get('payload', {})
    
    content = json.dumps({
        'header': header,
        'payload': payload
    }, sort_keys=True, separators=(',', ':'))
    
    return hashlib.sha256(content.encode()).hexdigest()


def tamper_event(event: dict, field_path: list, new_value: str) -> dict:
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
{Colors.BOLD}{'='*60}
        VCP TAMPER DEMONSTRATION
{'='*60}{Colors.END}

This demonstration shows what happens when a prop firm 
attempts to modify execution records after the fact.

{Colors.YELLOW}Scenario: PropFirm changes execution price from 2658.20 to 2655.50
          to claim worse fill and reduce trader's profit.{Colors.END}
""")
    
    # Load original events
    source_file = Path(__file__).parent.parent / 'evidence' / 'propfirm_events.jsonl'
    output_file = Path(__file__).parent.parent / 'evidence' / 'propfirm_tampered.jsonl'
    
    if not source_file.exists():
        print(f"{Colors.RED}Error: Source file not found: {source_file}{Colors.END}")
        sys.exit(1)
    
    events = []
    with open(source_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    
    print(f"{Colors.CYAN}Loaded {len(events)} events from prop firm log{Colors.END}")
    print()
    
    # Find the event to tamper (EXE event for order 002 - the profitable XAUUSD trade)
    tamper_index = None
    original_price = None
    
    for i, event in enumerate(events):
        header = event.get('header', {})
        payload = event.get('payload', {})
        trade_data = payload.get('trade_data', {})
        
        if (header.get('event_type') == 'EXE' and 
            trade_data.get('order_id') == 'ORD-2025-001002'):
            tamper_index = i
            original_price = trade_data.get('execution_price')
            break
    
    if tamper_index is None:
        print(f"{Colors.RED}Error: Target event not found{Colors.END}")
        sys.exit(1)
    
    # Show original event
    print(f"{Colors.BOLD}Original Event #{tamper_index + 1}:{Colors.END}")
    print(f"  Order ID:        ORD-2025-001002")
    print(f"  Event Type:      EXE (Execution)")
    print(f"  Symbol:          XAUUSD")
    print(f"  Execution Price: {Colors.GREEN}{original_price}{Colors.END}")
    print(f"  Event Hash:      {events[tamper_index]['security']['event_hash'][:16]}...")
    print()
    
    # Perform tampering
    new_price = "2655.50"  # Changed from 2658.20 (trader loses $2.70 per oz)
    
    print(f"{Colors.YELLOW}Tampering: Changing execution_price{Colors.END}")
    print(f"  From: {Colors.GREEN}{original_price}{Colors.END}")
    print(f"  To:   {Colors.RED}{new_price}{Colors.END}")
    print()
    
    events[tamper_index] = tamper_event(
        events[tamper_index],
        ['payload', 'trade_data', 'execution_price'],
        new_price
    )
    
    # Show what happens to the hash chain
    print(f"{Colors.BOLD}Hash Chain Impact:{Colors.END}")
    print()
    
    # The hash of the tampered event would be different
    original_hash = events[tamper_index]['security']['event_hash']
    # In reality, the hash wouldn't match the stored hash
    # For demo, we'll leave the stored hash unchanged to show the mismatch
    
    print(f"  Event #{tamper_index + 1}:")
    print(f"    Stored hash:   {original_hash[:32]}...")
    print(f"    {Colors.RED}Content modified but hash NOT updated{Colors.END}")
    print(f"    {Colors.RED}→ Verifier will detect mismatch{Colors.END}")
    print()
    
    # Show chain break
    if tamper_index + 1 < len(events):
        next_event = events[tamper_index + 1]
        print(f"  Event #{tamper_index + 2}:")
        print(f"    prev_hash points to: {next_event['security']['prev_hash'][:32]}...")
        print(f"    {Colors.RED}→ Chain reference now invalid{Colors.END}")
    print()
    
    # Save tampered file
    with open(output_file, 'w') as f:
        for event in events:
            f.write(json.dumps(event) + '\n')
    
    print(f"{Colors.GREEN}Tampered log saved to: {output_file}{Colors.END}")
    print()
    
    # Instructions
    print(f"{Colors.BOLD}{'='*60}")
    print("              VERIFICATION DEMO")
    print(f"{'='*60}{Colors.END}")
    print(f"""
Now run the verifier to detect the tampering:

{Colors.CYAN}python verifier/verify.py \\
    --trader evidence/trader_events.jsonl \\
    --propfirm evidence/propfirm_tampered.jsonl{Colors.END}

The verifier will detect:
  1. {Colors.RED}CRITICAL{Colors.END}: execution_price mismatch
     - Trader logged: 2658.20
     - PropFirm logged: 2655.50

This discrepancy is {Colors.BOLD}CRYPTOGRAPHICALLY PROVABLE{Colors.END}.
The trader's log provides non-repudiable evidence.
""")


if __name__ == '__main__':
    main()
