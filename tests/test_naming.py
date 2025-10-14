import unittest

from src.naming import apply_preferred_scene_name, prefer_radarr_scene_name


class ApplyPreferredSceneNameTest(unittest.TestCase):
    def test_leaves_name_unchanged_when_disabled(self):
        meta = {"name": "Original", "radarr": {"movieFile": {"sceneName": "SCENE"}}}
        config = {"NAMING": {"prefer_radarr_scene_name": False}}

        apply_preferred_scene_name(meta, config)

        self.assertEqual(meta["name"], "Original")

    def test_applies_scene_name_with_default_sanitization(self):
        meta = {
            "name": "Original",
            "filelist": ["/path/Example.mkv"],
            "radarr": {"movieFile": {"sceneName": "Scene Name (Test)"}},
        }
        config = {"NAMING": {"prefer_radarr_scene_name": True}}

        apply_preferred_scene_name(meta, config)

        self.assertEqual(meta["preferred_scene_name"], "Scene.Name.Test.mkv")
        self.assertEqual(meta["name"], "Original")

    def test_preserves_original_extension(self):
        meta = {
            "name": "Original.Release.Name.mkv",
            "radarr": {"movieFile": {"sceneName": "Scene Name"}},
        }
        config = {"NAMING": {"prefer_radarr_scene_name": True}}

        apply_preferred_scene_name(meta, config)

        self.assertEqual(meta["name"], "Original.Release.Name.mkv")

    def test_applies_normalization_when_enabled(self):
        meta = {
            "name": "Original",
            "filelist": ["/path/Example.mkv"],
            "radarr": {"movieFile": {"sceneName": "Release DD+ HDR."}},
        }
        config = {
            "NAMING": {
                "prefer_radarr_scene_name": True,
                "normalize_scene_tokens": True,
                "sanitize_filenames": True,
            }
        }

        apply_preferred_scene_name(meta, config)

        self.assertEqual(meta["preferred_scene_name"], "Release.DDP.HDR10.mkv")
        self.assertEqual(meta["name"], "Original")

    def test_strip_chars_accepts_string_configuration(self):
        meta = {
            "name": "Original",
            "filelist": ["/path/Example.mkv"],
            "radarr": {"movieFile": {"sceneName": "Scene Name {Test}"}},
        }
        config = {
            "NAMING": {
                "prefer_radarr_scene_name": True,
                "strip_chars": "{}[]()",
            }
        }

        apply_preferred_scene_name(meta, config)

        self.assertEqual(meta["name"], "Original")

    def test_strip_chars_accepts_comma_separated_string(self):
        meta = {
            "name": "Original",
            "filelist": ["/path/Example.mkv"],
            "radarr": {"movieFile": {"sceneName": "Scene Name [Test]"}},
        }
        config = {
            "NAMING": {
                "prefer_radarr_scene_name": True,
                "strip_chars": "{, },[, ],(, )",
            }
        }

        apply_preferred_scene_name(meta, config)

        self.assertEqual(meta["name"], "Original")


class PreferRadarrSceneNameTest(unittest.TestCase):
    def test_sets_scene_name_when_available(self):
        meta = {
            "name": "Original",
            "filelist": ["/path/Example.mkv"],
            "radarr": {"movieFile": {"sceneName": "Scene Name"}},
        }

        prefer_radarr_scene_name(meta)

        self.assertEqual(meta["name"], "Original")
        self.assertEqual(meta["preferred_scene_name"], "Scene Name.mkv")

    def test_applies_minimal_normalization(self):
        meta = {
            "name": "Original",
            "filelist": ["/path/Example.mkv"],
            "radarr": {"movieFile": {"sceneName": "Release DD+ HDR."}},
        }

        prefer_radarr_scene_name(meta)

        self.assertEqual(meta["name"], "Original")
        self.assertEqual(meta["preferred_scene_name"], "Release DD+ HDR.mkv")

    def test_strips_limited_characters(self):
        meta = {
            "name": "Original",
            "filelist": ["/path/Example.mkv"],
            "radarr": {"movieFile": {"sceneName": "Scene Name {Test}"}},
        }

        prefer_radarr_scene_name(meta)

        self.assertEqual(meta["name"], "Original")
        self.assertEqual(meta["preferred_scene_name"], "Scene Name {Test}.mkv")

    def test_preserves_extension_when_preferred(self):
        meta = {
            "name": "Original.Name.mkv",
            "radarr": {"movieFile": {"sceneName": "Scene Name"}},
        }

        prefer_radarr_scene_name(meta)

        self.assertEqual(meta["name"], "Original.Name.mkv")

    def test_leaves_name_when_missing_scene(self):
        meta = {"name": "Original", "radarr": {"movieFile": {}}}

        prefer_radarr_scene_name(meta)

        self.assertEqual(meta["name"], "Original")

    def test_sets_torrent_override_when_scene_available(self):
        meta = {"name": "Original.mkv", "radarr": {"movieFile": {"sceneName": "Scene.Name"}}}

        prefer_radarr_scene_name(meta)

        self.assertEqual(meta["torrent_name_override"], "Scene.Name.mkv")


if __name__ == "__main__":
    unittest.main()
