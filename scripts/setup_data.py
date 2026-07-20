#!/usr/bin/env python3
"""Importeer een TTL-bronbestand en genereer een archiefversie indien nodig."""

import argparse
import re
import shutil
import sys
from datetime import date
from pathlib import Path

root = Path(__file__).resolve().parent.parent
DEFAULT_SRC = root / "data" / "versions" / "0.2" / "begrippenkader_corporatiesector.ttl"


def infer_version(path: Path) -> str | None:
    """Probeer een versie uit een pad of bestandsnaam af te leiden."""
    matches = re.findall(r"(\d+)\.(\d+)", str(path))
    if not matches:
        return None
    major, minor = matches[-1]
    return f"{major}.{minor}"


def parse_version(version: str) -> tuple[int, int] | None:
    """Parse een versie zoals 0.2 naar een tuple."""
    match = re.fullmatch(r"(\d+)\.(\d+)", version)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def extract_dct_dates(content: str) -> tuple[str, str]:
    """Haal dct:created en dct:modified uit de TTL-inhoud op, met fallback op de huidige datum."""
    created_match = re.search(r'dct:created\s+"([^"]+)"', content)
    modified_match = re.search(r'dct:modified\s+"([^"]+)"', content)

    created = created_match.group(1) if created_match else date.today().isoformat()
    modified = modified_match.group(1) if modified_match else date.today().isoformat()
    return created, modified


def build_archive_content(content: str, current_version: str, archive_version: str) -> str:
    """Maak een archiefversie met versie-gebonden tekstvervangingen."""
    created, modified = extract_dct_dates(content)

    archive_content = content.replace(f"basisversie {current_version}", f"basisversie {archive_version}")
    archive_content = archive_content.replace(
        f"Basisversie {current_version}, concept ter review. Wijzigingen t.o.v. {archive_version}:",
        f"Basisversie {archive_version}, archief. Voorloper van {current_version}:",
    )
    archive_content = re.sub(r'(dct:created\s+")([^"]+)(")', rf'\g<1>{created}\3', archive_content, count=1)
    archive_content = re.sub(r'(dct:modified\s+")([^"]+)(")', rf'\g<1>{modified}\3', archive_content, count=1)
    return archive_content


def main() -> None:
    """Kopieer bron-TTL naar de huidige versie en maak een archiefversie als er echt een nieuwe versie is.

    Het script leest optioneel een bronbestand, bepaalt de huidige versie, kopieert
    het naar de juiste versie-map en maakt alleen een archiefversie aan als er een
    nieuwe versie wordt geïntroduceerd.
    """
    parser = argparse.ArgumentParser(
        description="Importeer een TTL-bestand naar een versie-map en genereer een archiefversie indien nodig."
    )
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=DEFAULT_SRC,
        help="Pad naar bron-TTL (standaard: data/versions/0.2/begrippenkader_corporatiesector.ttl)",
    )
    parser.add_argument(
        "--current-version",
        default=None,
        help="Versie van het bronbestand, bijvoorbeeld 0.2 of 0.3.",
    )
    args = parser.parse_args()

    src = args.source.resolve()
    if not src.is_file():
        sys.exit(f"Bronbestand niet gevonden: {src}")

    current_version = args.current_version or infer_version(src) or "0.2"
    current_version_parsed = parse_version(current_version)
    if current_version_parsed is None:
        sys.exit(f"Ongeldige versie: {current_version}")

    current_dir = root / "data" / "versions" / current_version
    current_dir.mkdir(parents=True, exist_ok=True)

    current_file = current_dir / src.name
    shutil.copy(src, current_file)

    existing_versions = [
        version.name
        for version in (root / "data" / "versions").iterdir()
        if version.is_dir() and parse_version(version.name) is not None
    ]
    existing_versions = sorted(existing_versions, key=parse_version)

    archive_version = None
    if current_version not in existing_versions:
        previous_versions = [
            version for version in existing_versions
            if parse_version(version) is not None and parse_version(version) < current_version_parsed
        ]
        if previous_versions:
            archive_version = sorted(previous_versions, key=parse_version)[-1]

    if archive_version is not None:
        archive_dir = root / "data" / "versions" / archive_version
        archive_dir.mkdir(parents=True, exist_ok=True)
        content = current_file.read_text(encoding="utf-8")
        archive_content = build_archive_content(content, current_version, archive_version)
        (archive_dir / src.name).write_text(archive_content, encoding="utf-8")
        print(f"Archiefversie aangemaakt voor {archive_version} op basis van {current_version}")
    else:
        print(f"Geen nieuwe versie gedetecteerd; geen archiefversie aangemaakt voor {current_version}")

    (root / "public" / "build").mkdir(parents=True, exist_ok=True)
    print("Setup complete")


if __name__ == "__main__":
    main()
