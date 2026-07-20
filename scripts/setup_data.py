#!/usr/bin/env python3
"""Importeer een TTL-bronbestand en genereer de archiefversie 0.1."""

import argparse
import shutil
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
DEFAULT_SRC = root / "data" / "versions" / "0.2" / "begrippenkader_corporatiesector.ttl"
DST_02 = DEFAULT_SRC


def main() -> None:
    """Kopieer bron-TTL naar versie 0.2 en leid versie 0.1 af via tekstvervanging.

    Leest optioneel een bronbestand (standaard het bestaande 0.2-bestand),
    zorgt dat de versiemappen bestaan, kopieert indien nodig naar 0.2, en
    schrijft een archiefversie 0.1 met aangepaste metadata en beschrijving.
    Maakt ook de outputmap ``public/build`` aan voor de JSON-build.
    """    parser = argparse.ArgumentParser(
        description="Importeer een TTL-bestand naar versie 0.2 en genereer archiefversie 0.1."
    )
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=DEFAULT_SRC,
        help="Pad naar bron-TTL (standaard: data/versions/0.2/begrippenkader_corporatiesector.ttl)",
    )
    args = parser.parse_args()
    src = args.source.resolve()

    if not src.is_file():
        sys.exit(f"Bronbestand niet gevonden: {src}")

    for version in ("0.2", "0.1"):
        (root / "data" / "versions" / version).mkdir(parents=True, exist_ok=True)

    if src != DST_02.resolve():
        shutil.copy(src, DST_02)

    content = DST_02.read_text(encoding="utf-8")
    content01 = (
        content.replace("basisversie 0.2", "basisversie 0.1")
        .replace('dct:modified "2026-07-07"', 'dct:modified "2026-06-01"')
        .replace('dct:created "2026-07-06"', 'dct:created "2026-06-01"')
        .replace(
            "Basisversie 0.2, concept ter review. Wijzigingen t.o.v. 0.1:",
            "Basisversie 0.1, archief. Voorloper van 0.2:",
        )
    )
    (root / "data" / "versions" / "0.1" / "begrippenkader_corporatiesector.ttl").write_text(
        content01, encoding="utf-8"
    )
    (root / "public" / "build").mkdir(parents=True, exist_ok=True)
    print("Setup complete")


if __name__ == "__main__":
    main()
