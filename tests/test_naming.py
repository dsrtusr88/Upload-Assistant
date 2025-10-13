import unittest

from src.naming import apply_preferred_scene_name


class ApplyPreferredSceneNameTest(unittest.TestCase):
    def test_leaves_name_unchanged_when_disabled(self):
        meta = {"name": "Original", "radarr": {"movieFile": {"sceneName": "SCENE"}}}
        config = {"NAMING": {"prefer_radarr_scene_name": False}}

        apply_preferred_scene_name(meta, config)

        self.assertEqual(meta["name"], "Original")

    def test_applies_scene_name_with_default_sanitization(self):
        meta = {"name": "Original", "radarr": {"movieFile": {"sceneName": "Scene Name (Test)"}}}
        config = {"NAMING": {"prefer_radarr_scene_name": True}}

        apply_preferred_scene_name(meta, config)

        self.assertEqual(meta["name"], "Scene.Name.Test")

    def test_applies_normalization_when_enabled(self):
        meta = {"name": "Original", "radarr": {"movieFile": {"sceneName": "Release DD+ HDR."}}}
        config = {
            "NAMING": {
                "prefer_radarr_scene_name": True,
                "normalize_scene_tokens": True,
                "sanitize_filenames": True,
            }
        }

        apply_preferred_scene_name(meta, config)

        self.assertEqual(meta["name"], "Release.DDP.HDR10.")

    def test_strip_chars_accepts_string_configuration(self):
        meta = {"name": "Original", "radarr": {"movieFile": {"sceneName": "Scene Name {Test}"}}}
        config = {
            "NAMING": {
                "prefer_radarr_scene_name": True,
                "strip_chars": "{}[]()",
            }
        }

        apply_preferred_scene_name(meta, config)

        self.assertEqual(meta["name"], "Scene.Name.Test")

    def test_strip_chars_accepts_comma_separated_string(self):
        meta = {"name": "Original", "radarr": {"movieFile": {"sceneName": "Scene Name [Test]"}}}
        config = {
            "NAMING": {
                "prefer_radarr_scene_name": True,
                "strip_chars": "{, },[, ],(, )",
            }
        }

        apply_preferred_scene_name(meta, config)

        self.assertEqual(meta["name"], "Scene.Name.Test")


if __name__ == "__main__":
    unittest.main()
