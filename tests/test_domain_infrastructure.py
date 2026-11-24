import json
import tempfile
import unittest
from pathlib import Path

from engines.domain_infrastructure import (
    read_domain_property,
    update_domain_property,
)


class DomainInfrastructurePropertyTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.infrastructure_path = (
            Path(self.temporary_directory.name) / "infrastructure.json"
        )
        self.data = [
            {
                "superdomain": "first",
                "domains": [
                    {
                        "id": 0,
                        "domain": "first_domain",
                        "norm_BaaS": "BootOTE [3.0 - 5.4]",
                    },
                    {
                        "id": 1,
                        "domain": "second_domain",
                        "norm_BaaS": "BootMGR [0.5 - 2.9]",
                    },
                ],
            }
        ]
        self._write_data()

    def _write_data(self):
        with self.infrastructure_path.open("w", encoding="utf-8") as file:
            json.dump(self.data, file, indent=2, ensure_ascii=False)

    def _read_data(self):
        with self.infrastructure_path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def test_reads_norm_baas_for_domain_id_zero(self):
        value = read_domain_property(
            self.infrastructure_path,
            0,
            "first_domain",
            "norm_BaaS",
        )

        self.assertEqual(value, "BootOTE [3.0 - 5.4]")

    def test_updates_only_the_selected_domain(self):
        update_domain_property(
            self.infrastructure_path,
            0,
            "first_domain",
            "norm_BaaS",
            "NovaOS [26.00 - 28.09]",
        )

        domains = self._read_data()[0]["domains"]
        self.assertEqual(domains[0]["norm_BaaS"], "NovaOS [26.00 - 28.09]")
        self.assertEqual(domains[1]["norm_BaaS"], "BootMGR [0.5 - 2.9]")

    def test_adds_norm_baas_when_the_property_is_missing(self):
        self.data[0]["domains"][0].pop("norm_BaaS")
        self._write_data()

        self.assertEqual(
            read_domain_property(
                self.infrastructure_path,
                0,
                "first_domain",
                "norm_BaaS",
            ),
            "",
        )
        update_domain_property(
            self.infrastructure_path,
            0,
            "first_domain",
            "norm_BaaS",
            "BootTEX [1.0 - 1.9]",
        )

        self.assertEqual(
            self._read_data()[0]["domains"][0]["norm_BaaS"],
            "BootTEX [1.0 - 1.9]",
        )

    def test_uses_domain_name_when_id_is_unavailable(self):
        value = read_domain_property(
            self.infrastructure_path,
            None,
            "second_domain",
            "norm_BaaS",
        )

        self.assertEqual(value, "BootMGR [0.5 - 2.9]")

    def test_rejects_a_missing_domain(self):
        with self.assertRaisesRegex(ValueError, "No se encontró el dominio"):
            read_domain_property(
                self.infrastructure_path,
                999,
                "unknown",
                "norm_BaaS",
            )

    def test_rejects_a_non_list_document_root(self):
        self.infrastructure_path.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "debe ser una lista"):
            read_domain_property(
                self.infrastructure_path,
                0,
                "first_domain",
                "norm_BaaS",
            )


if __name__ == "__main__":
    unittest.main()
