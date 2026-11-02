"""A public prefix match must never be reported as signature verification."""
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / 'verifier' / 'verify.py'


class DemoTagCliTests(unittest.TestCase):
    def invoke(self, trader, propfirm, *, as_json=True):
        command = [sys.executable, str(VERIFIER), '--trader', str(trader),
                   '--propfirm', str(propfirm)]
        if as_json:
            command.append('--json')
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        output = json.loads(result.stdout) if as_json else re.sub(r'\x1b\[[0-9;]*m', '', result.stdout)
        return result.returncode, output

    def public_tag_copies(self, directory):
        paths = []
        for party in ('trader', 'propfirm'):
            source = ROOT / 'evidence' / f'{party}_events.jsonl'
            events = [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
            for event in events:
                security = event['security']
                # Anyone can produce a matching prefix without a private key.
                prefix = hashlib.sha512(
                    bytes.fromhex(security['public_key'])[:32] +
                    bytes.fromhex(security['event_hash'])
                ).digest()[:32]
                security['signature'] = base64.b64encode(prefix + b'\0' * 32).decode('ascii')
            destination = Path(directory) / source.name
            destination.write_text(''.join(json.dumps(event) + '\n' for event in events))
            paths.append(destination)
        return paths

    def assert_signature_unimplemented(self, report):
        self.assertEqual(report['layer3'].get('signature_verification'), 'NOT_IMPLEMENTED')
        self.assertEqual(report.get('result_scope'), 'SELECTED_POC_CONSISTENCY_CHECKS')
        self.assertNotIn('trader_signatures_valid', report['layer3'])
        self.assertNotIn('propfirm_signatures_valid', report['layer3'])

    def test_committed_samples_report_demo_counts_and_capability_limit(self):
        status, report = self.invoke(ROOT / 'evidence/trader_events.jsonl',
                                     ROOT / 'evidence/propfirm_events.jsonl')
        self.assertEqual(status, 0)
        self.assert_signature_unimplemented(report)
        self.assertEqual(report['layer3']['trader_demo_tag_matches'], 0)
        self.assertEqual(report['layer3']['propfirm_demo_tag_matches'], 0)

    def test_all_publicly_forged_matches_still_do_not_authenticate_signatures(self):
        with tempfile.TemporaryDirectory() as directory:
            trader, propfirm = self.public_tag_copies(directory)
            status, report = self.invoke(trader, propfirm)
        self.assertEqual(status, 0)  # Limited consistency checks, not authentication.
        self.assert_signature_unimplemented(report)
        self.assertGreater(report['trader_events'], 0)
        self.assertEqual(report['layer3']['trader_demo_tag_matches'], report['trader_events'])
        self.assertEqual(report['layer3']['propfirm_demo_tag_matches'], report['propfirm_events'])

    def test_human_output_keeps_matching_tags_separate_from_signature_status(self):
        with tempfile.TemporaryDirectory() as directory:
            trader, propfirm = self.public_tag_copies(directory)
            status, output = self.invoke(trader, propfirm, as_json=False)
        self.assertEqual(status, 0)
        self.assertIn('Signature verification: NOT_IMPLEMENTED', output)
        self.assertIn('prefix matches (not authentication)', output)
        self.assertNotIn('demo signatures:', output)
        self.assertIn('selected consistency checks only; no signature authentication', output)

    def test_payload_tampering_retains_nonzero_exit_and_unimplemented_signature_status(self):
        source = ROOT / 'evidence/propfirm_events.jsonl'
        events = [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
        events[0]['payload']['test_mutation'] = 'changed payload, original event hash'
        with tempfile.TemporaryDirectory() as directory:
            mutated = Path(directory) / 'mutated.jsonl'
            mutated.write_text(''.join(json.dumps(event) + '\n' for event in events))
            status, report = self.invoke(ROOT / 'evidence/trader_events.jsonl', mutated)
        self.assertEqual(status, 1)
        self.assertEqual(report['layer1']['propfirm_hashes_valid'], len(events) - 1)
        self.assert_signature_unimplemented(report)


if __name__ == '__main__':
    unittest.main()
