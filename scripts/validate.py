#!/usr/bin/env python3
"""Validate SKOS TTL vocabulary files before deployment."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, SKOS

ROOT = Path(__file__).resolve().parent.parent
VERSIONS_FILE = ROOT / "versions.json"

RELATION_PROPERTIES = (SKOS.broader, SKOS.narrower, SKOS.related)


def validate_version(version_id: str, ttl_path: Path) -> list[str]:
  """Valideer één SKOS-vocabulaireversie op structuur en consistentie.

  Controleert o.a. aanwezigheid van ConceptScheme, verplichte conceptvelden
  (prefLabel, definition, inScheme), geldige relaties en collectielidmaatschap.
  Waarschuwingen (bijv. asymmetrische topConcept-relaties) worden naar stdout
  geschreven; alleen harde fouten worden teruggegeven.

  Args:
    version_id: Versie-identificatie voor foutmeldingen (bijv. ``"0.2"``).
    ttl_path: Pad naar het Turtle-bestand van deze versie.

  Returns:
    Lijst met foutmeldingen; leeg als de versie geldig is.
  """
  errors: list[str] = []
  warnings: list[str] = []

  try:
    graph = Graph()
    graph.parse(data=ttl_path.read_text(encoding="utf-8"), format="turtle")
  except Exception as exc:
    return [f"[{version_id}] TTL parse-fout: {exc}"]

  schemes = list(graph.subjects(RDF.type, SKOS.ConceptScheme))
  if not schemes:
    errors.append(f"[{version_id}] Geen skos:ConceptScheme gevonden")

  concepts = {str(c) for c in graph.subjects(RDF.type, SKOS.Concept)}
  concept_schemes = set()
  for concept in graph.subjects(RDF.type, SKOS.Concept):
    uri = str(concept)
    pref_labels = [v for v in graph.objects(concept, SKOS.prefLabel) if isinstance(v, Literal)]
    if not pref_labels:
      errors.append(f"[{version_id}] Concept zonder skos:prefLabel: {uri}")

    definitions = [v for v in graph.objects(concept, SKOS.definition) if isinstance(v, Literal)]
    if not definitions:
      errors.append(f"[{version_id}] Concept zonder skos:definition: {uri}")

    in_schemes = list(graph.objects(concept, SKOS.inScheme))
    if not in_schemes:
      errors.append(f"[{version_id}] Concept zonder skos:inScheme: {uri}")
    else:
      concept_schemes.update(str(s) for s in in_schemes)

  for concept in concepts:
    for prop in RELATION_PROPERTIES:
      for target in graph.objects(URIRef(concept), prop):
        if str(target) not in concepts:
          errors.append(
            f"[{version_id}] Relatie {prop} verwijst naar onbekend concept: {concept} -> {target}"
          )

  for collection in graph.subjects(RDF.type, SKOS.Collection):
    coll_uri = str(collection)
    for member in graph.objects(collection, SKOS.member):
      if str(member) not in concepts:
        errors.append(
          f"[{version_id}] Collectielid verwijst naar onbekend concept: {coll_uri} -> {member}"
        )

  for scheme in schemes:
    scheme_uri = str(scheme)
    has_top = {str(c) for c in graph.objects(scheme, SKOS.hasTopConcept)}
    top_of = {c for c in concepts if any(
      str(s) == scheme_uri for s in graph.objects(URIRef(c), SKOS.topConceptOf)
    )}

    for uri in has_top - top_of:
      warnings.append(
        f"[{version_id}] hasTopConcept zonder topConceptOf: {uri} in scheme {scheme_uri}"
      )
    for uri in top_of - has_top:
      warnings.append(
        f"[{version_id}] topConceptOf zonder hasTopConcept: {uri} in scheme {scheme_uri}"
      )

  for collection in graph.subjects(RDF.type, SKOS.Collection):
    for member in graph.objects(collection, SKOS.member):
      member_schemes = {str(s) for s in graph.objects(URIRef(str(member)), SKOS.inScheme)}
      if concept_schemes and member_schemes and not member_schemes.intersection(
        {str(s) for s in schemes}
      ):
        warnings.append(
          f"[{version_id}] Collectielid niet in scheme: {member}"
        )

  broader_pairs: set[tuple[str, str]] = set()
  for concept in concepts:
    for broader in graph.objects(URIRef(concept), SKOS.broader):
      pair = (concept, str(broader))
      if pair in broader_pairs:
        warnings.append(f"[{version_id}] Dubbele broader-relatie: {concept} -> {broader}")
      broader_pairs.add(pair)
      if (str(broader), concept) in broader_pairs:
        warnings.append(
          f"[{version_id}] Mogelijke circulaire broader/narrower: {concept} <-> {broader}"
        )

  for warning in warnings:
    print(f"WAARSCHUWING: {warning}")

  return errors


def main() -> int:
  """Valideer alle versies uit ``versions.json``.

  Returns:
    Exitcode 0 bij succes, 1 bij ontbrekende bestanden of validatiefouten.
  """
  if not VERSIONS_FILE.exists():
    print(f"versions.json niet gevonden: {VERSIONS_FILE}", file=sys.stderr)
    return 1

  manifest = json.loads(VERSIONS_FILE.read_text(encoding="utf-8"))
  all_errors: list[str] = []

  for version in manifest["versions"]:
    version_id = version["id"]
    ttl_path = ROOT / version["file"]
    if not ttl_path.exists():
      all_errors.append(f"[{version_id}] TTL-bestand niet gevonden: {ttl_path}")
      continue
    print(f"Valideren versie {version_id}...")
    all_errors.extend(validate_version(version_id, ttl_path))

  if all_errors:
    print("\nValidatie mislukt:", file=sys.stderr)
    for error in all_errors:
      print(f"  FOUT: {error}", file=sys.stderr)
    return 1

  print("Validatie geslaagd.")
  return 0


if __name__ == "__main__":
  sys.exit(main())
