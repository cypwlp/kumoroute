import io
import os
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str((Path(__file__).resolve().parents[1] / "client" / "tools")))

import fetch_core


class FetchCoreTests(unittest.TestCase):
    def test_asset_url_is_versioned(self):
        self.assertEqual(
            fetch_core.asset_url("v1.2.3", "mihomo-darwin-arm64-v1.2.3.gz"),
            "https://github.com/MetaCubeX/mihomo/releases/download/"
            "v1.2.3/mihomo-darwin-arm64-v1.2.3.gz",
        )

    def test_resolve_tag_prefers_pinned_version(self):
        with mock.patch.dict(os.environ, {"MIHOMO_VERSION": "v1.2.3"}):
            with mock.patch.object(fetch_core, "latest_tag") as latest:
                self.assertEqual(fetch_core.resolve_tag(), "v1.2.3")
                latest.assert_not_called()

    def test_resolve_tag_uses_latest_when_not_pinned(self):
        env = dict(os.environ)
        env.pop("MIHOMO_VERSION", None)
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch.object(fetch_core, "latest_tag", return_value="v9.9.9") as latest:
                self.assertEqual(fetch_core.resolve_tag(), "v9.9.9")
                latest.assert_called_once_with()

    def test_download_retries_transient_failure(self):
        responses = [urllib.error.URLError("temporary"), io.BytesIO(b"ok")]
        with mock.patch.object(fetch_core.urllib.request, "urlopen", side_effect=responses):
            with mock.patch.object(fetch_core.time, "sleep") as sleep:
                self.assertEqual(fetch_core.download("https://example.test/core"), b"ok")
                sleep.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
