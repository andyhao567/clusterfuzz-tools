"""Tests the main module of the CI service."""
# Copyright 2016 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys
import tempfile
import yaml

import mock

from daemon import main
from error import error
from test_libs import helpers


class MainTest(helpers.ExtendedTestCase):
  """Test main."""

  def setUp(self):
    helpers.patch(self, ['daemon.main.load_sanity_check_testcase_ids',
                         'daemon.main.reset_and_run_testcase',
                         'daemon.main.update_auth_header',
                         'daemon.main.load_new_testcases',
                         'time.sleep'])
    self.setup_fake_filesystem()
    self.mock.load_sanity_check_testcase_ids.return_value = [1, 2]
    self.mock.load_new_testcases.side_effect = [
        [main.Testcase(3, 'job'), main.Testcase(4, 'job')],
        [main.Testcase(5, 'job')]
    ]
    self.mock.reset_and_run_testcase.side_effect = [None, None, None, None,
                                                    SystemExit]

  def test_correct_calls(self):
    """Ensure the main method makes the correct calls to reproduce."""

    with self.assertRaises(SystemExit):
      main.main()

    self.assert_exact_calls(self.mock.load_sanity_check_testcase_ids,
                            [mock.call()])
    self.assert_exact_calls(self.mock.load_new_testcases, [mock.call(),
                                                           mock.call()])
    self.assert_exact_calls(self.mock.reset_and_run_testcase, [
        mock.call(1, 'sanity', sys.argv[1]),
        mock.call(2, 'sanity', sys.argv[1]),
        mock.call(3, 'job', sys.argv[1]),
        mock.call(4, 'job', sys.argv[1]),
        mock.call(5, 'job', sys.argv[1])])
    self.assertEqual(2, self.mock.update_auth_header.call_count)


class RunTestcaseTest(helpers.ExtendedTestCase):
  """Test the run_testcase method."""

  def setUp(self):
    helpers.patch(self, ['daemon.process.call'])
    self.mock_os_environment({'PATH': 'test'})
    main.PROCESSED_TESTCASE_IDS.clear()

  def test_succeed(self):
    """Ensures testcases are run properly."""
    self.mock.call.return_value = (0, None)
    self.assertEqual(0, main.run_testcase(1234, '--current'))

    self.assert_exact_calls(self.mock.call, [
        mock.call(
            '/python-daemon-data/clusterfuzz reproduce 1234 --current',
            cwd=main.HOME,
            env={
                'CF_QUIET': '1',
                'USER': 'CI',
                'CHROMIUM_SRC': main.CHROMIUM_SRC,
                'PATH': 'test:%s' % main.DEPOT_TOOLS,
                'GOMA_GCE_SERVICE_ACCOUNT': 'default'},
            raise_on_error=False)
    ])
    self.assertEqual(set([1234]), main.PROCESSED_TESTCASE_IDS)

  def test_not_save_testcase_id(self):
    """Test not saving testcase id."""
    self.mock.call.return_value = (
        error.MinimizationNotFinishedError.EXIT_CODE, None)
    self.assertEqual(
        error.MinimizationNotFinishedError.EXIT_CODE,
        main.run_testcase(1234, ''))

    self.assert_exact_calls(self.mock.call, [
        mock.call(
            '/python-daemon-data/clusterfuzz reproduce 1234',
            cwd=main.HOME,
            env={
                'CF_QUIET': '1',
                'USER': 'CI',
                'CHROMIUM_SRC': main.CHROMIUM_SRC,
                'PATH': 'test:%s' % main.DEPOT_TOOLS,
                'GOMA_GCE_SERVICE_ACCOUNT': 'default'},
            raise_on_error=False)
    ])
    self.assertEqual(0, len(main.PROCESSED_TESTCASE_IDS))


class LoadSanityCheckTestcasesTest(helpers.ExtendedTestCase):
  """Tests the load_sanity_check_testcases method."""

  def setUp(self):
    self.setup_fake_filesystem()
    os.makedirs(os.path.dirname(main.SANITY_CHECKS))
    with open(main.SANITY_CHECKS, 'w') as f:
      f.write('testcase_ids:\n')
      f.write('#ignore\n')
      f.write('        - 5899279404367872')

  def test_reading_testcases(self):
    """Ensures that testcases are read properly."""

    result = main.load_sanity_check_testcase_ids()
    self.assertEqual(result, [5899279404367872])


class UpdateAuthHeadertest(helpers.ExtendedTestCase):
  """Tests the update_auth_header method."""

  def setUp(self):
    self.setup_fake_filesystem()
    helpers.patch(self, ['oauth2client.client.GoogleCredentials'])
    (self.mock.GoogleCredentials._get_implicit_credentials.return_value. #pylint: disable=protected-access
     get_access_token.return_value) = mock.Mock(access_token='Access token')

  def test_proper_update(self):
    """Ensures that the auth key is updated properly."""

    self.assertFalse(os.path.exists(main.CLUSTERFUZZ_CACHE_DIR))
    main.update_auth_header()

    with open(main.AUTH_FILE_LOCATION, 'r') as f:
      self.assertEqual(f.read(), 'Bearer Access token')


class GetBinaryVersionTest(helpers.ExtendedTestCase):
  """Tests the get_binary_version method."""

  def setUp(self):
    helpers.patch(self, ['daemon.process.call'])
    self.result = yaml.dump({
        'chromium': ['chrome_job', 'libfuzzer_job'],
        'standalone': ['pdf_job', 'v8_job'],
        'Version': '0.2.2rc11'})
    self.mock.call.return_value = (0, self.result)

  def test_get(self):
    result = main.get_binary_version()
    self.assertEqual(result, '0.2.2rc11')


class GetSupportedJobtypesTest(helpers.ExtendedTestCase):
  """Tests the get_supported_jobtypes method."""

  def setUp(self):
    helpers.patch(self, ['daemon.process.call'])
    self.result = yaml.dump({
        'chromium': ['chrome_job', 'libfuzzer_job'],
        'standalone': ['pdf_job', 'v8_job'],
        'Version': '0.2.2rc11'})
    self.mock.call.return_value = (0, self.result)

  def test_get_supported_jobtypes(self):
    """Tests get_supported_jobtypes."""

    result = main.get_supported_jobtypes()
    correct = yaml.load(self.result)
    correct.pop('Version')
    self.assertEqual(result, correct)


class LoadNewTestcasesTest(helpers.ExtendedTestCase):
  """Tests the load_new_testcases method."""

  def setUp(self):
    self.setup_fake_filesystem()
    os.makedirs(main.CLUSTERFUZZ_CACHE_DIR)
    with open(main.AUTH_FILE_LOCATION, 'w') as f:
      f.write('Bearer xyzabc')

    helpers.patch(self, ['daemon.main.get_supported_jobtypes',
                         'daemon.main.post',
                         'random.randint'])
    self.mock.randint.return_value = 6
    self.mock.get_supported_jobtypes.return_value = {'chromium': [
        'supported', 'support']}
    main.PROCESSED_TESTCASE_IDS.clear()

  def test_get_testcase(self):
    """Tests get testcase."""
    resp = mock.Mock()
    resp.json.side_effect = (
        [{
            'items': [
                {'jobType': 'supported', 'id': 12345},
                {'jobType': 'unsupported', 'id': 98765},
                {'jobType': 'support', 'id': 23456},
                {'jobType': 'supported', 'id': 23456},
                {'jobType': 'supported', 'id': 1337},
            ]
        }] * 15
        + [{'items': []}]
    )
    self.mock.post.return_value = resp
    main.PROCESSED_TESTCASE_IDS.add(1337)

    result = main.load_new_testcases()

    self.assertEqual(
        [main.Testcase(12345, 'supported'), main.Testcase(23456, 'support')],
        result)
    self.assert_exact_calls(self.mock.post, [
        mock.call(
            'https://clusterfuzz.com/v2/testcases/load',
            headers={'Authorization': 'Bearer xyzabc'},
            json={'page': page, 'reproducible': 'yes',
                  'q': 'platform:linux', 'open': 'yes'})
        for page in xrange(1, 17)
    ])


class ResetAndRunTestcaseTest(helpers.ExtendedTestCase):
  """Tests the reset_and_run_testcase method."""

  def setUp(self):
    self.setup_fake_filesystem()
    os.makedirs(main.CHROMIUM_OUT)
    os.makedirs(main.CLUSTERFUZZ_CACHE_DIR)

    helpers.patch(self, [
        'daemon.process.call',
        'daemon.stackdriver_logging.send_run',
        'daemon.main.update_auth_header',
        'daemon.main.run_testcase',
        'daemon.main.prepare_binary_and_get_version',
        'daemon.main.read_logs',
        'daemon.main.clean_third_party',
    ])
    self.mock.prepare_binary_and_get_version.return_value = '0.2.2rc10'
    self.mock.run_testcase.return_value = 'run_testcase'
    self.mock.read_logs.return_value = 'some logs'

  def test_reset_run_testcase(self):
    """Tests resetting a testcase properly prior to running."""

    self.assertTrue(os.path.exists(main.CHROMIUM_OUT))
    self.assertTrue(os.path.exists(main.CLUSTERFUZZ_CACHE_DIR))
    main.reset_and_run_testcase(1234, 'sanity', 'master')
    self.assertFalse(os.path.exists(main.CHROMIUM_OUT))
    self.assertFalse(os.path.exists(main.CLUSTERFUZZ_CACHE_DIR))

    self.assert_exact_calls(
        self.mock.update_auth_header, [mock.call()] * 2)
    self.assert_exact_calls(self.mock.send_run, [
        mock.call(1234, 'sanity', '0.2.2rc10', 'master', 'run_testcase',
                  'some logs', ''),
        mock.call(1234, 'sanity', '0.2.2rc10', 'master', 'run_testcase',
                  'some logs', '--current --skip-deps')
    ])
    self.assert_exact_calls(
        self.mock.prepare_binary_and_get_version, [mock.call('master')])
    self.assert_exact_calls(self.mock.call, [
        mock.call('git checkout -f HEAD', cwd=main.CHROMIUM_SRC),
        mock.call('git clean -ffdd', cwd=main.CHROMIUM_SRC),
    ])
    self.mock.clean_third_party.assert_called_once_with()


class BuildMasterAndGetVersionTest(helpers.ExtendedTestCase):
  """Tests the build_master_and_get_version method."""

  def setUp(self):
    helpers.patch(self, ['daemon.process.call',
                         'daemon.main.delete_if_exists',
                         'shutil.copy',
                         'os.path.exists'])
    self.mock.exists.return_value = False

  def test_run(self):
    """Tests checking out & building from master."""
    self.mock.call.return_value = (0, 'version')
    self.assertEqual('version', main.build_master_and_get_version())

    self.assert_exact_calls(self.mock.call, [
        mock.call('git clone https://github.com/google/clusterfuzz-tools.git',
                  cwd=main.HOME),
        mock.call('git fetch', cwd=main.TOOL_SOURCE),
        mock.call('git checkout origin/master -f', cwd=main.TOOL_SOURCE),
        mock.call('./pants binary tool:clusterfuzz-ci', cwd=main.TOOL_SOURCE,
                  env={'HOME': main.HOME}),
        mock.call('git rev-parse HEAD', capture=True, cwd=main.TOOL_SOURCE)
    ])
    self.assert_exact_calls(
        self.mock.delete_if_exists, [mock.call(main.BINARY_LOCATION)])
    self.assert_exact_calls(self.mock.copy, [
        mock.call(os.path.join(main.TOOL_SOURCE, 'dist', 'clusterfuzz-ci.pex'),
                  main.BINARY_LOCATION)
    ])


class DeleteIfExistsTest(helpers.ExtendedTestCase):
  """Tests delete_if_exists."""

  def setUp(self):
    self.setup_fake_filesystem()

  def test_not_exist(self):
    """test non-existing file."""
    main.delete_if_exists('/path/test')

  def test_dir(self):
    """Test deleting dir."""
    os.makedirs('/path/test')
    self.fs.CreateFile('/path/test/textfile', contents='yes')
    self.assertTrue(os.path.exists('/path/test'))
    self.assertTrue(os.path.exists('/path/test/textfile'))

    main.delete_if_exists('/path/test')
    self.assertFalse(os.path.exists('/path/test'))
    self.assertFalse(os.path.exists('/path/test/textfile'))

  def test_file(self):
    """Test deleting file."""
    self.fs.CreateFile('/path/test/textfile', contents='yes')
    self.assertTrue(os.path.exists('/path/test/textfile'))

    main.delete_if_exists('/path/test/textfile')
    self.assertFalse(os.path.exists('/path/test/textfile'))


class PrepareBinaryAndGetVersionTest(helpers.ExtendedTestCase):
  """Prepare binary and get version."""

  def setUp(self):
    helpers.patch(self, [
        'daemon.main.build_master_and_get_version',
        'daemon.main.get_binary_version'
    ])
    self.mock.build_master_and_get_version.return_value = 'vmaster'
    self.mock.get_binary_version.return_value = 'vbinary'

  def test_master(self):
    """Get version from master."""
    self.assertEqual('vmaster', main.prepare_binary_and_get_version('master'))

  def test_release(self):
    """Get version from release."""
    self.assertEqual(
        'vbinary', main.prepare_binary_and_get_version('release'))
    self.assertEqual(
        'vbinary', main.prepare_binary_and_get_version('release-candidate'))


class ReadLogsTest(helpers.ExtendedTestCase):
  """Test read_logs."""

  def setUp(self):
    # We can't use pyfakefs. Because pyfakefs' f.seek() results in a
    # different behaviour. See:
    # https://github.com/google/clusterfuzz-tools/issues/367
    self.tempfile = tempfile.NamedTemporaryFile(delete=False)
    self.tempfile.close()

  def tearDown(self):
    os.remove(self.tempfile.name)

  def test_file_not_exist(self):
    """Test file not exist."""
    self.another_tempfile = tempfile.NamedTemporaryFile(delete=True)
    self.another_tempfile.close()
    self.assertEqual(
        "%s doesn't exist." % self.another_tempfile.name,
        main.read_logs(self.another_tempfile.name))

  def test_small_file(self):
    """Test small file."""
    with open(self.tempfile.name, 'w') as f:
      f.write('some logs')
    self.assertIn('some logs', main.read_logs(self.tempfile.name))

  def test_large_file(self):
    """Test previewing a large file."""
    with open(self.tempfile.name, 'w') as f:
      f.write('a' * (main.MAX_PREVIEW_LOG_BYTE_COUNT + 10))
    self.assertIn(
        'a' * main.MAX_PREVIEW_LOG_BYTE_COUNT,
        main.read_logs(self.tempfile.name))
    self.assertNotIn(
        'a' * (main.MAX_PREVIEW_LOG_BYTE_COUNT + 1),
        main.read_logs(self.tempfile.name))


class CleanThirdPartyTest(helpers.ExtendedTestCase):
  """Test clean_third_party."""

  def setUp(self):
    self.setup_fake_filesystem()
    helpers.patch(self, ['daemon.process.call'])

  def test_clean(self):
    """Test clean every git repo."""
    third_party_path = os.path.join(main.CHROMIUM_SRC, 'third_party')
    os.makedirs(third_party_path)
    os.makedirs(os.path.join(third_party_path, 'one_git'))
    os.makedirs(os.path.join(third_party_path, 'one_git', '.git'))
    os.makedirs(os.path.join(third_party_path, 'another_git'))
    os.makedirs(os.path.join(third_party_path, 'another_git', '.git'))
    os.makedirs(os.path.join(third_party_path, 'not_git'))
    os.makedirs(os.path.join(third_party_path, 'not_another_git'))
    os.makedirs(os.path.join(third_party_path, 'not_git', 'sub_git'))
    os.makedirs(os.path.join(third_party_path, 'not_git', 'sub_git', '.git'))
    os.makedirs(os.path.join(third_party_path, 'not_git', 'not_sub_git'))

    main.clean_third_party()

    self.assert_exact_calls(self.mock.call, [
        mock.call('git checkout HEAD -f',
                  cwd=os.path.join(third_party_path, 'not_git', 'sub_git', '')),
        mock.call('git clean -ffdd',
                  cwd=os.path.join(third_party_path, 'not_git', 'sub_git', '')),
        mock.call('git checkout HEAD -f',
                  cwd=os.path.join(third_party_path, 'one_git', '')),
        mock.call('git clean -ffdd',
                  cwd=os.path.join(third_party_path, 'one_git', '')),
        mock.call('git checkout HEAD -f',
                  cwd=os.path.join(third_party_path, 'another_git', '')),
        mock.call('git clean -ffdd',
                  cwd=os.path.join(third_party_path, 'another_git', '')),
    ])
