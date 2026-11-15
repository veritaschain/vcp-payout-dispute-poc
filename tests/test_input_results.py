"""Ordinary input failures and incomplete comparisons are not successful checks."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / 'verifier/verify.py'
SPEC = importlib.util.spec_from_file_location('payout_verifier', VERIFIER)
verifier = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verifier
SPEC.loader.exec_module(verifier)


class InputResultTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.source = {party: (ROOT / 'evidence' / f'{party}_events.jsonl').read_bytes()
                       for party in ('trader', 'propfirm')}
        self.events = {party: [json.loads(line) for line in raw.splitlines() if line.strip()]
                       for party, raw in self.source.items()}

    def invoke(self, trader=None, propfirm=None, *, human=False, anchor=None):
        paths = []
        for party, value in (('trader', trader), ('propfirm', propfirm)):
            path = self.directory / f'{party}.jsonl'
            if value is None:
                value = self.source[party]
            if type(value) is list:
                value = b''.join(json.dumps(event).encode() + b'\n' for event in value)
            path.write_bytes(value)
            paths.append(path)
        original = [path.read_bytes() for path in paths]
        command = [sys.executable, '-I', '-B', str(VERIFIER), '-t', str(paths[0]), '-p', str(paths[1])]
        if not human:
            command.append('--json')
        if anchor is not None:
            command.extend(['--anchor', str(anchor)])
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertNotIn('Traceback', result.stderr)
        self.assertEqual([path.read_bytes() for path in paths], original)
        output = re.sub(r'\x1b\[[0-9;]*m', '', result.stdout) if human else json.loads(result.stdout)
        if not human:
            self.assertEqual(output['result_scope'], 'SELECTED_POC_CONSISTENCY_CHECKS')
            self.assertEqual(output['layer3']['signature_verification'], 'NOT_IMPLEMENTED')
        return result, output

    def test_empty_and_blank_logs_are_unresolved_not_successful(self):
        for raw in (b'', b' \n\t\r\n'):
            with self.subTest(raw=raw):
                result, output = self.invoke(raw, raw)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(output['comparison_status'], 'INDETERMINATE')
                self.assertFalse(output['comparison_completed'])
                self.assertIsNone(output['layer1']['trader_chain_valid'])
                self.assertIsNone(output['layer2']['trader_merkle_valid'])
                self.assertEqual(output['matched_pairs'], 0)

    def test_one_empty_party_cannot_produce_a_successful_comparison(self):
        for trader, propfirm in ((b'', None), (None, b'')):
            with self.subTest(trader_empty=trader == b''):
                result, output = self.invoke(trader, propfirm)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(output['comparison_status'], 'INDETERMINATE')
                self.assertEqual(output['matched_pairs'], 0)

    def test_empty_human_report_does_not_display_a_success_summary(self):
        result, output = self.invoke(b'', b'', human=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('PoC comparison: INDETERMINATE', output)
        self.assertIn('COMPARISON INCOMPLETE', output)
        self.assertNotIn('✓', output)
        self.assertNotIn('NO DISCREPANCIES DETECTED', output)

    def test_malformed_json_utf8_duplicates_and_nonfinite_values_are_not_skipped(self):
        first = json.dumps(self.events['trader'][0], separators=(',', ':'))
        malformed = [b'{\n', b'\xff\n', b'[' * 10000 + b'0' + b']' * 10000,
                     first.replace('"payload":', '"payload":{},"payload":', 1).encode(),
                     first.replace('"event_type":', '"event_type":"discarded","event_type":', 1).encode()]
        malformed += [(first[:-1] + ',"extra":' + value + '}').encode()
                      for value in ('NaN', 'Infinity', '-Infinity', '1e999')]
        for raw in malformed:
            with self.subTest(raw=raw[:16]):
                result, output = self.invoke(raw)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(output['comparison_status'], 'INVALID_INPUT')
                self.assertFalse(output['comparison_completed'])
                self.assertEqual(result.stderr, 'EVENT_INPUT_INVALID\n')
                self.assertNotIn('Warning:', result.stdout)

    def test_invalid_record_shapes_have_fixed_structured_errors(self):
        records = [None, [], {}, {'header': None}]
        for field in ('header', 'payload', 'vcp_xref', 'security'):
            record = copy.deepcopy(self.events['trader'][0])
            record[field] = None
            records.append(record)
        record = copy.deepcopy(self.events['trader'][0])
        record['vcp_xref']['shared_event_key']['tolerance_ms'] = 'invalid'
        records.append(record)
        for record in records:
            with self.subTest(record=record):
                result, output = self.invoke([record])
                self.assertEqual(result.returncode, 1)
                self.assertEqual(output['input_error']['code'], 'EVENT_INPUT_INVALID')
                self.assertEqual(output['input_error']['party'], 'trader')

    def test_invalid_trailing_line_cannot_disappear_from_a_valid_log(self):
        result, output = self.invoke(self.source['trader'] + b'\n{\n')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(output['comparison_status'], 'INVALID_INPUT')
        self.assertNotIn('matched_pairs', output)

    def test_missing_file_or_directory_is_unavailable_without_a_traceback(self):
        for path in (self.directory / 'missing', self.directory):
            with self.subTest(path=path.name):
                result = subprocess.run([sys.executable, '-I', '-B', str(VERIFIER),
                    '-t', str(path), '-p', str(ROOT / 'evidence/propfirm_events.jsonl'), '--json'],
                    capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 2)
                output = json.loads(result.stdout)
                self.assertEqual(output['comparison_status'], 'INDETERMINATE')
                self.assertEqual(output['input_error']['code'], 'EVENT_INPUT_UNAVAILABLE')
                self.assertEqual(result.stderr, 'EVENT_INPUT_UNAVAILABLE\n')

    def test_missing_counterpart_in_either_direction_is_incomplete(self):
        for party in ('trader', 'propfirm'):
            values = {party: self.events[party][:-1]}
            result, output = self.invoke(**values)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(output['comparison_status'], 'INDETERMINATE')
            self.assertFalse(output['comparison_completed'])
            self.assertEqual(output['matched_pairs'], 22)
            self.assertEqual(sum(output['unmatched_or_ambiguous'].values()), 1)

    def test_duplicate_cross_references_are_not_silently_overwritten_or_reused(self):
        for party in ('trader', 'propfirm'):
            values = {party: self.events[party] + [copy.deepcopy(self.events[party][0])]}
            result, output = self.invoke(**values)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(output['comparison_status'], 'INDETERMINATE')
            self.assertEqual(output['matched_pairs'], 22)
            self.assertEqual(sum(output['unmatched_or_ambiguous'].values()), 3)

    def test_missing_merkle_material_remains_unknown(self):
        for field in ('merkle_proof', 'merkle_root'):
            events = copy.deepcopy(self.events['trader'])
            del events[0]['security'][field]
            result, output = self.invoke(trader=events)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(output['comparison_status'], 'INDETERMINATE')
            self.assertIsNone(output['layer2']['trader_merkle_valid'])

    def test_empty_supplied_merkle_path_is_checked_as_a_single_leaf_path(self):
        values = {party: [copy.deepcopy(events[0])] for party, events in self.events.items()}
        for events in values.values():
            security = events[0]['security']
            security['merkle_proof'] = []
            security['merkle_root'] = hashlib.sha256(b'\0' + bytes.fromhex(security['event_hash'])).hexdigest()
        result, output = self.invoke(**values)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(output['comparison_status'], 'MATCH')
        values['trader'][0]['security']['merkle_root'] = 'f' * 64
        result, output = self.invoke(**values)
        self.assertEqual(result.returncode, 1)
        self.assertIs(output['layer2']['trader_merkle_valid'], False)

    def test_known_hash_contradiction_survives_missing_counterparts_and_proofs(self):
        events = copy.deepcopy(self.events['trader'])
        events[0]['payload']['test_change'] = 'ordinary local test mutation'
        del events[0]['security']['merkle_proof']
        result, output = self.invoke(trader=events, propfirm=self.events['propfirm'][:-1])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(output['comparison_status'], 'MISMATCH')
        self.assertFalse(output['comparison_completed'])
        self.assertIsNone(output['layer2']['trader_merkle_valid'])
        result, output = self.invoke(trader=events, propfirm=self.events['propfirm'][:-1], human=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('PoC comparison: MISMATCH', output)
        self.assertIn('COMPARISON INCOMPLETE', output)
        self.assertNotIn('NO DISCREPANCIES DETECTED', output)

    def test_optional_anchor_metadata_is_unknown_when_absent_or_unreadable(self):
        malformed = self.directory / 'bad-anchor.json'
        malformed.write_text('{')
        for anchor in (None, self.directory / 'missing-anchor.json', malformed):
            result, output = self.invoke(anchor=anchor)
            self.assertEqual(result.returncode, 0)  # Optional metadata is outside exit scope.
            self.assertEqual(output['comparison_status'], 'MATCH')
            self.assertIsNone(output['layer3']['trader_anchor_root_match'])
            self.assertIsNone(output['layer3']['propfirm_anchor_root_match'])
            if anchor is not None:
                self.assertIn(output['layer3']['anchor_input_error'],
                              ('ANCHOR_INPUT_UNAVAILABLE', 'ANCHOR_INPUT_INVALID'))
        result, output = self.invoke(anchor=ROOT / 'evidence/anchor_records.json')
        self.assertEqual(result.returncode, 0)
        self.assertIs(output['layer3']['trader_anchor_root_match'], True)
        self.assertIsNone(output['layer3']['anchor_input_error'])

    def test_historical_inputs_and_report_bytes_are_preserved(self):
        expected = {
            'evidence/trader_events.jsonl': '48879bc0f1e985ec5df9319915119aa77994438f5e72f2169db56750c77d6c04',
            'evidence/propfirm_events.jsonl': 'c376c94cbea330a1705fdc5a6dcdb85657bf3f992d86ac7d0fc87db75e998405',
            'evidence/anchor_records.json': '9d7ab4476f236a9c8df0d3c373ee7b79b8d64cf3529c4415c671c7d93436fb13',
            'VCP_WorldFirst_Final_Report.md': 'c11e58fbad9a1f6a0c53761b5320e2a1fbb3741ac9da6b3b2c3d817c02c22076',
        }
        for name, digest in expected.items():
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest)
        parsed = verifier.load_events(str(ROOT / 'evidence/trader_events.jsonl'))
        self.assertTrue(all(verifier.recalculate_event_hash(event) == event.event_hash for event in parsed))


if __name__ == '__main__':
    unittest.main()
