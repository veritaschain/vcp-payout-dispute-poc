#!/usr/bin/env python3
"""
VCP v1.1 PoC Event Generator
===================================

Generates illustrative sample events targeting VCP v1.1, not conformance evidence.
Uses a SHA-512 signature simulator, synthetic anchors, malformed UUID-like IDs,
simplified sorted-key JSON, and a padded Merkle tree. See README for limitations.

Features:
- Three-Layer Architecture (Event Integrity, Collection Integrity, External Verifiability)
- Policy Identification (Section 5.5)
- VCP-XREF Dual Logging (Section 5.6)
- Merkle tree with RFC 6962 hash prefixes and final-leaf padding
- SHA-512 demo signature fields (not Ed25519)
- Synthetic anchor metadata (no external submission)

Document ID: VSO-POC-GEN-002
License: CC BY 4.0 International
"""

import json
import hashlib
import base64
import os
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, asdict
import struct

# =============================================================================
# Cryptographic Primitives
# =============================================================================

class Ed25519Simulator:
    """
    Legacy-named SHA-512 signature simulator; not an Ed25519 implementation.
    In production, use a proper cryptographic library (e.g., PyNaCl, cryptography).
    """
    
    def __init__(self, seed: bytes = None):
        # For demo: deterministic "keys" derived from seed
        self.seed = seed or os.urandom(32)
        self.private_key = hashlib.sha512(self.seed).digest()[:32]
        self.public_key = hashlib.sha256(self.private_key).digest()
    
    def sign(self, message: bytes) -> bytes:
        """Simulate Ed25519 signature (NOT cryptographically secure - demo only)"""
        # Demo: HMAC-like construction for deterministic signatures
        sig_input = self.private_key + message
        return hashlib.sha512(sig_input).digest()
    
    def get_public_key_hex(self) -> str:
        return self.public_key.hex()
    
    def get_signature_base64(self, message: bytes) -> str:
        return base64.b64encode(self.sign(message)).decode('ascii')


class MerkleTree:
    """
    PoC Merkle tree with RFC 6962 hash prefixes and final-leaf padding.
    
    Uses domain separation:
    - Leaf nodes: SHA256(0x00 || data)
    - Internal nodes: SHA256(0x01 || left || right)
    """
    
    @staticmethod
    def leaf_hash(data: bytes) -> bytes:
        """Compute leaf hash with 0x00 prefix (RFC 6962)"""
        return hashlib.sha256(b'\x00' + data).digest()
    
    @staticmethod
    def node_hash(left: bytes, right: bytes) -> bytes:
        """Compute internal node hash with 0x01 prefix (RFC 6962)"""
        return hashlib.sha256(b'\x01' + left + right).digest()
    
    def __init__(self, leaves: List[bytes]):
        self.leaves = leaves
        self.levels = []
        self._build_tree()
    
    def _build_tree(self):
        """
        Build the Merkle tree from leaves.
        Pads to a power of two; this is not the RFC 6962 tree algorithm.
        """
        if not self.leaves:
            self.root = b'\x00' * 32
            return
        
        # Compute leaf hashes
        leaf_hashes = [self.leaf_hash(leaf) for leaf in self.leaves]
        
        # Pad to next power of 2 for consistent proof lengths
        n = len(leaf_hashes)
        next_pow2 = 1
        while next_pow2 < n:
            next_pow2 *= 2
        
        # Pad with duplicates of the last leaf hash
        while len(leaf_hashes) < next_pow2:
            leaf_hashes.append(leaf_hashes[-1])
        
        current_level = leaf_hashes
        self.levels.append(current_level)
        
        # Build internal levels
        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else current_level[i]
                next_level.append(self.node_hash(left, right))
            self.levels.append(next_level)
            current_level = next_level
        
        self.root = current_level[0] if current_level else b'\x00' * 32
    
    def get_root_hex(self) -> str:
        return self.root.hex()
    
    def get_proof(self, index: int) -> List[Dict[str, str]]:
        """Generate a path in this PoC padded tree."""
        proof = []
        idx = index
        
        for level in self.levels[:-1]:  # Exclude root level
            sibling_idx = idx ^ 1  # XOR to get sibling index
            
            if sibling_idx < len(level):
                # Sibling exists
                sibling_hash = level[sibling_idx].hex()
            else:
                # No sibling - this shouldn't happen in a properly padded tree
                # Use self-hash (duplicate)
                sibling_hash = level[idx].hex()
            
            # Position: 'left' means sibling is to the left of current node
            # 'right' means sibling is to the right
            position = "left" if sibling_idx < idx else "right"
            
            proof.append({
                "hash": sibling_hash,
                "position": position
            })
            
            idx //= 2
        
        return proof


# =============================================================================
# VCP v1.1 Data Structures
# =============================================================================

@dataclass
class PolicyIdentification:
    """VCP v1.1 Section 5.5: Policy Identification"""
    version: str = "1.1"
    policy_id: str = ""
    conformance_tier: str = "SILVER"
    registration_policy: Dict[str, Any] = None
    verification_depth: Dict[str, bool] = None
    
    def __post_init__(self):
        if self.registration_policy is None:
            self.registration_policy = {
                "issuer": "VeritasChain Standards Organization",
                "policy_uri": "https://veritaschain.org/policies/poc-payout-dispute",
                "effective_date": 1735689600000000000
            }
        if self.verification_depth is None:
            self.verification_depth = {
                "hash_chain_validation": True,
                "merkle_proof_required": True,
                "external_anchor_required": True
            }


@dataclass 
class VCPXref:
    """VCP v1.1 Section 5.6: Cross-Reference and Dual Logging"""
    cross_reference_id: str
    party_role: str  # INITIATOR | COUNTERPARTY | OBSERVER
    counterparty_id: str
    shared_event_key: Dict[str, Any]
    reconciliation_status: str = "PENDING"
    expected_counterparty_hash: Optional[str] = None
    discrepancy_details: Optional[Dict[str, Any]] = None


@dataclass
class Security:
    """VCP v1.1 Section 6.4: Security Object"""
    version: str = "1.1"
    event_hash: str = ""
    prev_hash: str = ""  # OPTIONAL in v1.1
    hash_algo: str = "SHA256"
    signature: str = ""
    sign_algo: str = "ED25519"
    public_key: str = ""
    merkle_root: str = ""
    merkle_index: int = 0
    anchor_reference: str = ""


@dataclass
class AnchorRecord:
    """VCP v1.1 Section 6.3.3: Anchoring Record"""
    merkle_root: str
    signature: str
    sign_algo: str = "ED25519"
    timestamp: int = 0
    anchor_target: Dict[str, str] = None
    event_count: int = 0
    first_event_id: str = ""
    last_event_id: str = ""
    policy_id: str = ""


# =============================================================================
# Event Generation
# =============================================================================

def canonicalize_json(obj: Any) -> str:
    """
    Simplified sorted-key JSON serialization, not a full RFC 8785 implementation.
    Sorts keys and uses minimal whitespace.
    """
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def calculate_event_hash(header: dict, payload: dict, vcp_xref: dict, 
                         policy_id: dict, prev_hash: str = None) -> str:
    """
    Calculate event hash per VCP v1.1 Section 6.1.1
    
    Hash = SHA256(canonical(header) || canonical(payload) || 
                  canonical(vcp_xref) || canonical(policy_id) || prev_hash)
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


def generate_uuid_v7(timestamp_ns: int, counter: int) -> str:
    """Generate a legacy demo identifier (not a valid UUID)."""
    timestamp_ms = timestamp_ns // 1_000_000
    
    # UUIDv7 format: timestamp_ms (48 bits) + version (4 bits) + random (12 bits) + 
    #               variant (2 bits) + random (62 bits)
    uuid_bytes = struct.pack('>Q', timestamp_ms)[2:]  # 48-bit timestamp
    uuid_bytes += bytes([0x70 | (counter >> 8 & 0x0F)])  # Version 7 + 4 bits
    uuid_bytes += bytes([counter & 0xFF])  # 8 bits counter
    uuid_bytes += struct.pack('>Q', hash(f"{timestamp_ns}-{counter}") & 0xFFFFFFFFFFFFFFFF)[:6]
    
    # Format as UUID string
    hex_str = uuid_bytes.hex()
    return f"{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:32]}"


class VCPEventGenerator:
    """
    VCP v1.1 PoC Event Generator
    """
    
    def __init__(self, party_role: str, party_id: str, counterparty_id: str,
                 policy_id: str = "org.veritaschain.poc:payout-dispute-001"):
        self.party_role = party_role
        self.party_id = party_id
        self.counterparty_id = counterparty_id
        self.policy_id = policy_id
        
        # Deterministic key for reproducibility
        seed = hashlib.sha256(f"{party_id}-{policy_id}".encode()).digest()
        self.signer = Ed25519Simulator(seed)
        
        self.events = []
        self.prev_hash = "0" * 64  # Genesis
        self.event_counter = 0
    
    def create_policy_identification(self) -> dict:
        """Create Policy Identification per v1.1 Section 5.5"""
        return {
            "version": "1.1",
            "policy_id": self.policy_id,
            "conformance_tier": "SILVER",
            "registration_policy": {
                "issuer": "VeritasChain Standards Organization",
                "policy_uri": "https://veritaschain.org/policies/poc-payout-dispute",
                "effective_date": 1735689600000000000
            },
            "verification_depth": {
                "hash_chain_validation": True,
                "merkle_proof_required": True,
                "external_anchor_required": True
            }
        }
    
    def create_event(self, timestamp_ns: int, event_type: str, event_type_code: int,
                     symbol: str, account_id: str, order_id: str,
                     xref_id: str, payload: dict,
                     reconciliation_status: str = "PENDING") -> dict:
        """Create an illustrative PoC event targeting VCP v1.1."""
        
        self.event_counter += 1
        event_id = generate_uuid_v7(timestamp_ns, self.event_counter)
        trace_id = generate_uuid_v7(timestamp_ns, 0)
        
        # Header
        header = {
            "event_id": event_id,
            "trace_id": trace_id,
            "timestamp_int": str(timestamp_ns),
            "timestamp_iso": datetime.fromtimestamp(
                timestamp_ns / 1e9, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "event_type": event_type,
            "event_type_code": event_type_code,
            "timestamp_precision": "MILLISECOND",
            "clock_sync_status": "BEST_EFFORT",
            "hash_algo": "SHA256",
            "venue_id": f"MT5-{self.counterparty_id.upper().replace('.', '-')[:20]}",
            "symbol": symbol,
            "account_id": account_id,
            "operator_id": "EA_GOLD_SCALPER_V3"
        }
        
        # VCP-XREF
        vcp_xref = {
            "version": "1.1",
            "cross_reference_id": xref_id,
            "party_role": self.party_role,
            "counterparty_id": self.counterparty_id,
            "shared_event_key": {
                "order_id": order_id,
                "timestamp": timestamp_ns,
                "tolerance_ms": 100
            },
            "reconciliation_status": reconciliation_status
        }
        
        # Policy Identification
        policy_identification = self.create_policy_identification()
        
        # Calculate event hash
        event_hash = calculate_event_hash(
            header, payload, vcp_xref, policy_identification, self.prev_hash
        )
        
        # Sign the event hash
        signature = self.signer.get_signature_base64(bytes.fromhex(event_hash))
        
        # Security object (MerkleRoot and AnchorReference will be filled during batch finalization)
        security = {
            "version": "1.1",
            "event_hash": event_hash,
            "prev_hash": self.prev_hash,
            "hash_algo": "SHA256",
            "signature": signature,
            "sign_algo": "ED25519",
            "public_key": self.signer.get_public_key_hex(),
            "merkle_root": "",  # Filled during batch finalization
            "merkle_index": len(self.events),
            "anchor_reference": ""  # Filled during batch finalization
        }
        
        # Complete event
        event = {
            "header": header,
            "payload": payload,
            "vcp_xref": vcp_xref,
            "policy_identification": policy_identification,
            "security": security
        }
        
        self.events.append(event)
        self.prev_hash = event_hash
        
        return event
    
    def finalize_batch(self) -> Tuple[List[dict], AnchorRecord]:
        """
        Finalize batch: build Merkle tree and create anchor record.
        VCP v1.1 Section 6.2 and 6.3.3
        """
        if not self.events:
            return [], None
        
        # Build Merkle tree from event hashes
        event_hashes = [bytes.fromhex(e["security"]["event_hash"]) for e in self.events]
        merkle_tree = MerkleTree(event_hashes)
        merkle_root = merkle_tree.get_root_hex()
        
        # Generate anchor reference ID
        anchor_timestamp = int(self.events[-1]["header"]["timestamp_int"])
        anchor_id = f"anchor-{hashlib.sha256(merkle_root.encode()).hexdigest()[:16]}"
        
        # Sign the merkle root for anchoring
        anchor_signature = self.signer.get_signature_base64(bytes.fromhex(merkle_root))
        
        # Create anchor record
        anchor_record = {
            "anchor_id": anchor_id,
            "merkle_root": merkle_root,
            "signature": anchor_signature,
            "sign_algo": "ED25519",
            "public_key": self.signer.get_public_key_hex(),
            "timestamp": anchor_timestamp,
            "anchor_target": {
                "type": "PUBLIC_SERVICE",
                "identifier": "opentimestamps.org",
                "proof": f"ots-{hashlib.sha256((merkle_root + str(anchor_timestamp)).encode()).hexdigest()[:32]}"
            },
            "event_count": len(self.events),
            "first_event_id": self.events[0]["header"]["event_id"],
            "last_event_id": self.events[-1]["header"]["event_id"],
            "policy_id": self.policy_id
        }
        
        # Update each event with Merkle info
        for i, event in enumerate(self.events):
            event["security"]["merkle_root"] = merkle_root
            event["security"]["merkle_index"] = i
            event["security"]["merkle_proof"] = merkle_tree.get_proof(i)
            event["security"]["anchor_reference"] = anchor_id
        
        return self.events, anchor_record


def generate_trading_scenario() -> Tuple[List[dict], List[dict], dict, dict]:
    """
    Generate a realistic trading scenario with 6 trades.
    Returns: (trader_events, propfirm_events, trader_anchor, propfirm_anchor)
    """
    
    # Initialize generators
    trader_gen = VCPEventGenerator(
        party_role="INITIATOR",
        party_id="trader-john-doe",
        counterparty_id="propfirm-alpha.com",
        policy_id="org.veritaschain.poc:trader-001"
    )
    
    propfirm_gen = VCPEventGenerator(
        party_role="COUNTERPARTY", 
        party_id="propfirm-alpha.com",
        counterparty_id="trader-john-doe",
        policy_id="org.veritaschain.poc:propfirm-001"
    )
    
    # Base timestamp: 2025-01-01 08:00:00 UTC
    base_ts = 1735689600000000000
    
    # Trade scenarios
    trades = [
        # Trade 1: XAUUSD BUY - Successful execution
        {
            "order_id": "ORD-2025-001001",
            "xref_id": "550e8400-e29b-41d4-a716-446655440001",
            "symbol": "XAUUSD",
            "side": "BUY",
            "quantity": "1.00",
            "price": "2651.50",
            "execution_price": "2651.50",
            "commission": "7.50",
            "signal_confidence": "0.87",
            "signal_factors": ["MA_CROSSOVER", "RSI_OVERSOLD", "SUPPORT_LEVEL"],
            "offset_minutes": 0
        },
        # Trade 2: XAUUSD SELL - Close position with profit
        {
            "order_id": "ORD-2025-001002",
            "xref_id": "550e8400-e29b-41d4-a716-446655440002",
            "symbol": "XAUUSD",
            "side": "SELL",
            "quantity": "1.00",
            "price": "2658.20",
            "execution_price": "2658.20",
            "commission": "7.50",
            "signal_confidence": "0.82",
            "signal_factors": ["RESISTANCE_HIT", "RSI_OVERBOUGHT"],
            "offset_minutes": 15
        },
        # Trade 3: EURUSD BUY - Partial fill then complete
        {
            "order_id": "ORD-2025-001003",
            "xref_id": "550e8400-e29b-41d4-a716-446655440003",
            "symbol": "EURUSD",
            "side": "BUY",
            "quantity": "2.00",
            "price": "1.0850",
            "execution_price": "1.0851",
            "commission": "4.00",
            "signal_confidence": "0.75",
            "signal_factors": ["TREND_FOLLOWING", "VOLUME_BREAKOUT"],
            "offset_minutes": 45
        },
        # Trade 4: EURUSD SELL - Close with small loss
        {
            "order_id": "ORD-2025-001004",
            "xref_id": "550e8400-e29b-41d4-a716-446655440004",
            "symbol": "EURUSD",
            "side": "SELL",
            "quantity": "2.00",
            "price": "1.0845",
            "execution_price": "1.0844",
            "commission": "4.00",
            "signal_confidence": "0.68",
            "signal_factors": ["STOP_LOSS_HIT"],
            "offset_minutes": 90
        },
        # Trade 5: USDJPY BUY - Rejected due to margin
        {
            "order_id": "ORD-2025-001005",
            "xref_id": "550e8400-e29b-41d4-a716-446655440005",
            "symbol": "USDJPY",
            "side": "BUY",
            "quantity": "5.00",
            "price": "157.50",
            "execution_price": None,  # Rejected
            "commission": "0.00",
            "signal_confidence": "0.91",
            "signal_factors": ["BREAKOUT", "NEWS_EVENT"],
            "reject_reason": "INSUFFICIENT_MARGIN",
            "reject_code": "E001",
            "offset_minutes": 120
        },
        # Trade 6: GBPUSD SELL - Successful
        {
            "order_id": "ORD-2025-001006",
            "xref_id": "550e8400-e29b-41d4-a716-446655440006",
            "symbol": "GBPUSD",
            "side": "SELL",
            "quantity": "1.50",
            "price": "1.2720",
            "execution_price": "1.2719",
            "commission": "5.25",
            "signal_confidence": "0.79",
            "signal_factors": ["MEAN_REVERSION", "OVERBOUGHT"],
            "offset_minutes": 180
        }
    ]
    
    account_id = "trader_john_doe_001"
    
    for trade in trades:
        ts_base = base_ts + trade["offset_minutes"] * 60 * 1_000_000_000
        is_rejected = trade.get("reject_reason") is not None
        
        # --- SIGNAL EVENT (SIG) ---
        sig_payload = {
            "vcp_gov": {
                "signal_type": trade["side"],
                "confidence": trade["signal_confidence"],
                "model_version": "v3.2.1",
                "decision_factors": trade["signal_factors"]
            }
        }
        
        trader_gen.create_event(
            timestamp_ns=ts_base,
            event_type="SIG",
            event_type_code=1,
            symbol=trade["symbol"],
            account_id=account_id,
            order_id=trade["order_id"],
            xref_id=trade["xref_id"],
            payload=sig_payload
        )
        
        # PropFirm also logs the signal (received from trader's EA)
        propfirm_gen.create_event(
            timestamp_ns=ts_base + 5_000_000,  # 5ms later
            event_type="SIG",
            event_type_code=1,
            symbol=trade["symbol"],
            account_id=account_id,
            order_id=trade["order_id"],
            xref_id=trade["xref_id"],
            payload=sig_payload
        )
        
        # --- ORDER EVENT (ORD) ---
        ord_payload = {
            "trade_data": {
                "order_id": trade["order_id"],
                "side": trade["side"],
                "order_type": "MARKET",
                "price": trade["price"],
                "quantity": trade["quantity"],
                "time_in_force": "IOC"
            }
        }
        
        trader_gen.create_event(
            timestamp_ns=ts_base + 50_000_000,  # 50ms
            event_type="ORD",
            event_type_code=2,
            symbol=trade["symbol"],
            account_id=account_id,
            order_id=trade["order_id"],
            xref_id=trade["xref_id"],
            payload=ord_payload
        )
        
        propfirm_gen.create_event(
            timestamp_ns=ts_base + 55_000_000,  # 55ms
            event_type="ORD",
            event_type_code=2,
            symbol=trade["symbol"],
            account_id=account_id,
            order_id=trade["order_id"],
            xref_id=trade["xref_id"],
            payload=ord_payload
        )
        
        if is_rejected:
            # --- REJECTION EVENT (REJ) ---
            rej_payload = {
                "trade_data": {
                    "order_id": trade["order_id"],
                    "reject_reason": trade["reject_reason"],
                    "reject_code": trade["reject_code"]
                }
            }
            
            trader_gen.create_event(
                timestamp_ns=ts_base + 120_000_000,
                event_type="REJ",
                event_type_code=5,
                symbol=trade["symbol"],
                account_id=account_id,
                order_id=trade["order_id"],
                xref_id=trade["xref_id"],
                payload=rej_payload,
                reconciliation_status="MATCHED"
            )
            
            propfirm_gen.create_event(
                timestamp_ns=ts_base + 118_000_000,
                event_type="REJ",
                event_type_code=5,
                symbol=trade["symbol"],
                account_id=account_id,
                order_id=trade["order_id"],
                xref_id=trade["xref_id"],
                payload=rej_payload,
                reconciliation_status="MATCHED"
            )
        else:
            # --- ACKNOWLEDGMENT EVENT (ACK) ---
            ack_payload = {
                "trade_data": {
                    "order_id": trade["order_id"],
                    "broker_order_id": f"BRK-{hash(trade['order_id']) % 100000000:08d}",
                    "status": "ACKNOWLEDGED"
                }
            }
            
            trader_gen.create_event(
                timestamp_ns=ts_base + 120_000_000,
                event_type="ACK",
                event_type_code=3,
                symbol=trade["symbol"],
                account_id=account_id,
                order_id=trade["order_id"],
                xref_id=trade["xref_id"],
                payload=ack_payload
            )
            
            propfirm_gen.create_event(
                timestamp_ns=ts_base + 118_000_000,
                event_type="ACK",
                event_type_code=3,
                symbol=trade["symbol"],
                account_id=account_id,
                order_id=trade["order_id"],
                xref_id=trade["xref_id"],
                payload=ack_payload
            )
            
            # --- EXECUTION EVENT (EXE) ---
            exe_payload = {
                "trade_data": {
                    "order_id": trade["order_id"],
                    "exec_id": f"EXEC-{trade['order_id'].split('-')[-1]}",
                    "execution_price": trade["execution_price"],
                    "executed_qty": trade["quantity"],
                    "commission": trade["commission"],
                    "slippage": str(round(float(trade["execution_price"]) - float(trade["price"]), 5))
                }
            }
            
            trader_gen.create_event(
                timestamp_ns=ts_base + 180_000_000,
                event_type="EXE",
                event_type_code=4,
                symbol=trade["symbol"],
                account_id=account_id,
                order_id=trade["order_id"],
                xref_id=trade["xref_id"],
                payload=exe_payload,
                reconciliation_status="MATCHED"
            )
            
            propfirm_gen.create_event(
                timestamp_ns=ts_base + 178_000_000,
                event_type="EXE",
                event_type_code=4,
                symbol=trade["symbol"],
                account_id=account_id,
                order_id=trade["order_id"],
                xref_id=trade["xref_id"],
                payload=exe_payload,
                reconciliation_status="MATCHED"
            )
    
    # Finalize batches (build Merkle trees and anchor records)
    trader_events, trader_anchor = trader_gen.finalize_batch()
    propfirm_events, propfirm_anchor = propfirm_gen.finalize_batch()
    
    return trader_events, propfirm_events, trader_anchor, propfirm_anchor


def main():
    """Generate PoC sample events; no conformance claim."""
    from pathlib import Path
    
    print("=" * 60)
    print("VCP v1.1 PoC Event Generator")
    print("=" * 60)
    print()
    
    # Generate events
    trader_events, propfirm_events, trader_anchor, propfirm_anchor = generate_trading_scenario()
    
    print(f"Generated {len(trader_events)} trader events")
    print(f"Generated {len(propfirm_events)} propfirm events")
    print()
    
    # Output paths
    evidence_dir = Path(__file__).parent.parent / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    
    # Write trader events
    trader_file = evidence_dir / "trader_events.jsonl"
    with open(trader_file, 'w') as f:
        for event in trader_events:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')
    print(f"Written: {trader_file}")
    
    # Write propfirm events
    propfirm_file = evidence_dir / "propfirm_events.jsonl"
    with open(propfirm_file, 'w') as f:
        for event in propfirm_events:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')
    print(f"Written: {propfirm_file}")
    
    # Write anchor records
    anchor_file = evidence_dir / "anchor_records.json"
    with open(anchor_file, 'w') as f:
        json.dump({
            "trader_anchor": trader_anchor,
            "propfirm_anchor": propfirm_anchor
        }, f, indent=2, ensure_ascii=False)
    print(f"Written: {anchor_file}")
    
    print()
    print("=" * 60)
    print("VCP v1.1 PoC Generation Summary (not conformance)")
    print("=" * 60)
    print()
    print("Layer 1 - Event Integrity:")
    print(f"  ✓ EventHash (SHA-256): All {len(trader_events) + len(propfirm_events)} events")
    print(f"  ✓ PrevHash (hash chain): Enabled")
    print()
    print("Layer 2 - Collection Integrity:")
    print(f"  ✓ PoC Merkle tree: RFC 6962 hash prefixes, final-leaf padding")
    print(f"  ✓ Merkle Root (Trader):   {trader_anchor['merkle_root'][:32]}...")
    print(f"  ✓ Merkle Root (PropFirm): {propfirm_anchor['merkle_root'][:32]}...")
    print(f"  ✓ Merkle Proofs: Included in each event")
    print()
    print("Layer 3 - Demo Signature / Anchor Metadata:")
    print(f"  • Signature fields: SHA-512 simulator, not Ed25519")
    print(f"  • Anchor fields: synthetic ots- string; no external submission")
    print(f"  ✓ Policy Identification: Included")
    print()
    print("VCP-XREF Dual Logging:")
    print(f"  ✓ CrossReferenceID: Shared between parties")
    print(f"  ✓ PartyRole: INITIATOR/COUNTERPARTY")
    print(f"  ✓ ReconciliationStatus: Tracked")
    print()
    print("Sample files written. Run the PoC checks; this is not a conformance result.")
    print("Demo signature generation and verification differ; the committed samples report 0/23 prefix matches per party.")
    print("Generated IDs are not valid UUIDs; no external signature or timestamp proof is established.")


if __name__ == "__main__":
    main()
