import tempfile
import unittest
from pathlib import Path

from character_visor.knowledge_wardrobe import (
    resolve_knowledge_directory,
    resolve_marker_knowledge_directories,
)


class KnowledgeDirectoryResolutionTests(unittest.TestCase):
    def test_uses_the_character_folder_name_and_album_prefix(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            year_dir = Path(temporary_directory) / "2026"
            character_folder = "23;Alter_Ego;Character_Name;2000-01-01;26"
            credential = (
                year_dir
                / "23. album"
                / character_folder
                / "__Character_Name__.json"
            )

            actual = resolve_knowledge_directory(credential, year=2026)

            self.assertEqual(
                actual,
                year_dir / "23. knowledge" / character_folder,
            )

    def test_preserves_a_zero_padded_album_prefix(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            year_dir = Path(temporary_directory) / "2003"
            character_folder = "00;Alter_Ego;Character_Name;2000-01-01;26"
            credential = (
                year_dir
                / "00. album"
                / character_folder
                / "__Character_Name__.json"
            )

            actual = resolve_knowledge_directory(credential, year=2003)

            self.assertEqual(
                actual,
                year_dir / "00. knowledge" / character_folder,
            )


    def test_resolves_every_matching_marker_folder_in_knowledge(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            year_dir = Path(temporary_directory) / "2026"
            knowledge_root = year_dir / "23. knowledge"
            first = knowledge_root / "23. _local_A"
            second = knowledge_root / "23. refs_local"
            ignored = knowledge_root / "23. album"
            first.mkdir(parents=True)
            second.mkdir()
            ignored.mkdir()

            root, matching = resolve_marker_knowledge_directories(
                Path(temporary_directory),
                2026,
                "_local",
            )

            self.assertEqual(root, knowledge_root)
            self.assertEqual(matching, [first, second])

    def test_missing_marker_folder_returns_knowledge_root_and_no_matches(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root, matching = resolve_marker_knowledge_directories(
                Path(temporary_directory),
                2026,
                "_ndomain",
            )

            self.assertEqual(
                root,
                Path(temporary_directory) / "2026" / "23. knowledge",
            )
            self.assertEqual(matching, [])

if __name__ == "__main__":
    unittest.main()
