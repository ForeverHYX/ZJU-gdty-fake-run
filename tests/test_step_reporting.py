"""Offline regression tests; no personal config, credentials, or network required."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[1] / 'forge2.py'

class StepReportingTests(unittest.TestCase):
    def test_interval_reports_sum_to_local_total(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copyfile(SOURCE, root / 'forge2.py')
            config = {'user_id': 'offline-user', 'brand': 'offline-brand', 'device_info': 'offline-device'}
            (root / 'config.json').write_text(json.dumps(config), encoding='utf-8')
            (root / 'token.txt').write_text('offline-placeholder', encoding='utf-8')
            (root / 'route_template.json').write_text(json.dumps([[30.30, 120.08], [30.31, 120.08], [30.32, 120.08]]), encoding='utf-8')
            spec = importlib.util.spec_from_file_location('forge_step_test', root / 'forge2.py')
            forge = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(forge)
            clock = [1700000000.0]
            reports = []
            output = io.StringIO()

            def sleep(seconds):
                clock[0] += seconds

            def request(method, path, body=None, extra=None):
                if path.endswith('/start_route'):
                    return {'route_id': 'offline-route'}
                if path.endswith('/create_route_gyroscope_steps'):
                    reports.append(dict(body))
                if path.endswith('/completes_route'):
                    return {'route_id': 1}
                return {'ok': True}

            def uniform(low, high):
                return 1.0 if (low, high) == (.94, 1.06) else (low + high) / 2

            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(forge, 'TARGET_M', 500))
                stack.enter_context(patch.object(forge, 'BASE_PACE', 300))
                stack.enter_context(patch.object(forge, 'call', side_effect=request))
                stack.enter_context(patch.object(forge.time, 'time', side_effect=lambda: clock[0]))
                stack.enter_context(patch.object(forge.time, 'sleep', side_effect=sleep))
                stack.enter_context(patch.object(forge.random, 'uniform', side_effect=uniform))
                stack.enter_context(patch.object(forge.random, 'gauss', return_value=0))
                stack.enter_context(patch.object(forge.tempfile, 'gettempdir', return_value=directory))
                stack.enter_context(patch.object(forge.subprocess, 'run', return_value=Mock(returncode=0)))
                network = stack.enter_context(patch.object(forge.urllib.request, 'urlopen', side_effect=AssertionError('Network forbidden')))
                stack.enter_context(contextlib.redirect_stdout(output))
                forge.run()
                network.assert_not_called()

            self.assertGreaterEqual(len(reports), 3)
            for report in reports:
                self.assertEqual(report['cur_steps'], int(report['dur'] * forge.CADENCE))
            total = int(re.search(r'步数(\d+)', output.getvalue()).group(1))
            self.assertEqual(sum(report['cur_steps'] for report in reports), total)

if __name__ == '__main__':
    unittest.main()
