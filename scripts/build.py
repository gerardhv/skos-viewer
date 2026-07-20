#!/usr/bin/env python3
"""Build JSON indexes from SKOS TTL vocabulary files."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS, SKOS, DCTERMS

ROOT = Path(__file__).resolve().parent.parent
VERSIONS_FILE = ROOT / "versions.json"
OUTPUT_DIR = ROOT / "public" / "build"

SOURCE_CATEGORIES = {
    "overgenomen": re.compile(r"^overgenomen\s+uit", re.IGNORECASE),
    "afgeleid": re.compile(r"^afgeleid\s+van", re.IGNORECASE),
    "eigen": re.compile(r"^eigen\s+definitie\s+van\s+het\s+begrippenkader", re.IGNORECASE),
}


def normalize_ttl_content(content: str) -> str:
  """Normaliseer regeleinden naar Unix-stijl (``\\n``)."""
  return content.replace("\r\n", "\n").replace("\r", "\n")


def extract_header_comment(content: str) -> str:
  """Haal het blok commentaarregels bovenaan een TTL-bestand op.

  Stopt bij de eerste lege regel na commentaar, of bij ``@prefix``/``@base``.
  """
  lines: list[str] = []
  for line in normalize_ttl_content(content).splitlines():
    stripped = line.strip()
    if not stripped:
      if lines:
        break
      continue
    if stripped.startswith("@prefix") or stripped.startswith("@base"):
      break
    if stripped.startswith("#"):
      lines.append(stripped[1:].lstrip())
    elif lines:
      break
  return "\n".join(lines)


def literal_nl(graph: Graph, subject: URIRef, predicate) -> tuple[str, str]:
  """Geef de eerste Nederlandse literal voor *predicate*, of anders de eerste beschikbare.

  Returns:
    Tuple van (tekst, taalcode).
  """
  literals = [v for v in graph.objects(subject, predicate) if isinstance(v, Literal)]
  nl_literals = [v for v in literals if v.language == "nl"]
  if nl_literals:
    return str(nl_literals[0]), "nl"
  if literals:
    first = literals[0]
    return str(first), first.language or "nl"
  return "", "nl"


def literals_nl(graph: Graph, subject: URIRef, predicate) -> list[str]:
  """Geef alle Nederlandse literals voor *predicate*, of anders alle beschikbare."""
  values = [v for v in graph.objects(subject, predicate) if isinstance(v, Literal)]
  nl_values = [str(v) for v in values if v.language == "nl"]
  if nl_values:
    return nl_values
  return [str(v) for v in values]


def date_literal(graph: Graph, subject: URIRef, predicate) -> str:
  """Lees een datumliteral (xsd:date) als ISO-datumstring zonder type-suffix."""
  for value in graph.objects(subject, predicate):
    if isinstance(value, Literal):
      return str(value).split("^^", 1)[0].strip('"')
  return ""


def get_dct_predicate(graph: Graph, subject: URIRef, local_name: str):
  """Bepaal het juiste dct-predicaat (volledige URI of rdflib DCTERMS-namespace)."""
  dct = URIRef(f"http://purl.org/dc/terms/{local_name}")
  if list(graph.objects(subject, dct)):
    return dct
  return DCTERMS[local_name]


def scheme_uri_for_graph(graph: Graph) -> str:
  """Bepaal de primaire ConceptScheme-URI (meest gebruikt via skos:inScheme)."""
  schemes = list(graph.subjects(RDF.type, SKOS.ConceptScheme))
  if not schemes:
    return ""
  if len(schemes) == 1:
    return str(schemes[0])

  counts: dict[str, int] = {}
  for concept in graph.subjects(RDF.type, SKOS.Concept):
    for scheme in graph.objects(concept, SKOS.inScheme):
      counts[str(scheme)] = counts.get(str(scheme), 0) + 1
  if counts:
    return max(counts, key=counts.get)
  return str(schemes[0])


def uri_to_slug(uri: str) -> str | None:
  """Leid een URL-slug af uit een begrip- of collectie-URI."""
  parsed = urlparse(uri)
  path = unquote(parsed.path).rstrip("/")
  for segment in ("/begrip/", "/collectie/"):
    if segment in path:
      return path.split(segment, 1)[1].split("/")[0]
  if path:
    return path.rsplit("/", 1)[-1]
  fragment = parsed.fragment
  return fragment if fragment else None


def classify_source_text(text: str) -> str | None:
  """Classificeer brontekst als ``overgenomen``, ``afgeleid`` of ``eigen``."""
  for category, pattern in SOURCE_CATEGORIES.items():
    if pattern.search(text.strip()):
      return category
  return None


def parse_sources(graph: Graph, subject: URIRef) -> list[dict[str, Any]]:
  """Parse dct:source-waarden naar gestructureerde bronobjecten met categorie."""
  sources: list[dict[str, Any]] = []
  source_pred = get_dct_predicate(graph, subject, "source")
  for value in graph.objects(subject, source_pred):
    if isinstance(value, Literal):
      text = str(value)
      sources.append({
        "text": text,
        "category": classify_source_text(text),
        "url": None,
      })
    elif isinstance(value, URIRef):
      sources.append({
        "text": None,
        "category": None,
        "url": str(value),
      })
  return sources


def resolve_relation(graph: Graph, uri: str, concept_by_uri: dict[str, dict]) -> dict[str, Any]:
  """Los een relatie-URI op naar slug, prefLabel en of het een intern concept is."""
  concept = concept_by_uri.get(uri)
  if concept:
    return {
      "uri": uri,
      "slug": concept["slug"],
      "prefLabel": concept["prefLabel"],
      "internal": True,
    }
  label, _ = literal_nl(graph, URIRef(uri), SKOS.prefLabel)
  slug = uri_to_slug(uri)
  return {
    "uri": uri,
    "slug": slug,
    "prefLabel": label or slug or uri,
    "internal": False,
  }


def first_letter_nl(label: str) -> str:
  """Geef de eerste letter van *label* voor alfabet-index (``#`` als fallback)."""
  if not label:
    return "#"
  first = label[0].upper()
  if first.isalpha():
    return first
  return "#"


def build_version(version_id: str, ttl_path: Path) -> None:
  """Parse één TTL-versie en schrijf alle JSON-indexen naar ``public/build/{version_id}/``.

  Genereert o.a. concepts, collections, search-index, alphabet-index en
  graph-edges. Gooit ``ValueError`` bij dubbele slugs of ontbrekende slugs.

  Args:
    version_id: Versie-identificatie (mapnaam in de output).
    ttl_path: Pad naar het Turtle-bronbestand.
  """
  raw_content = ttl_path.read_text(encoding="utf-8")
  graph = Graph()
  graph.parse(data=raw_content, format="turtle")

  scheme_uri = scheme_uri_for_graph(graph)
  scheme_ref = URIRef(scheme_uri) if scheme_uri else None

  concepts: list[dict[str, Any]] = []
  concept_by_uri: dict[str, dict] = {}
  slug_counts: dict[str, list[str]] = {}

  for concept in graph.subjects(RDF.type, SKOS.Concept):
    uri = str(concept)
    slug = uri_to_slug(uri)
    if not slug:
      raise ValueError(f"Kan geen slug afleiden voor concept-URI: {uri}")
    slug_counts.setdefault(slug, []).append(uri)

    pref_label, _ = literal_nl(graph, concept, SKOS.prefLabel)
    definition, _ = literal_nl(graph, concept, SKOS.definition)
    comment, _ = literal_nl(graph, concept, RDFS.comment)
    scope_note, _ = literal_nl(graph, concept, SKOS.scopeNote)
    change_note, _ = literal_nl(graph, concept, SKOS.changeNote)
    history_note, _ = literal_nl(graph, concept, SKOS.historyNote)
    example, _ = literal_nl(graph, concept, SKOS.example)

    in_scheme = next((str(s) for s in graph.objects(concept, SKOS.inScheme)), "")
    is_top = any(graph.objects(concept, SKOS.topConceptOf))

    concept_data = {
      "uri": uri,
      "slug": slug,
      "prefLabel": pref_label,
      "altLabels": literals_nl(graph, concept, SKOS.altLabel),
      "hiddenLabels": literals_nl(graph, concept, SKOS.hiddenLabel),
      "definition": definition,
      "comment": comment,
      "scopeNote": scope_note,
      "changeNote": change_note,
      "historyNote": history_note,
      "example": example,
      "sources": parse_sources(graph, concept),
      "inScheme": in_scheme,
      "isTopConcept": is_top,
      "broader": [str(u) for u in graph.objects(concept, SKOS.broader)],
      "narrower": [str(u) for u in graph.objects(concept, SKOS.narrower)],
      "related": [str(u) for u in graph.objects(concept, SKOS.related)],
      "exactMatch": [str(u) for u in graph.objects(concept, SKOS.exactMatch)],
      "closeMatch": [str(u) for u in graph.objects(concept, SKOS.closeMatch)],
    }
    concepts.append(concept_data)
    concept_by_uri[uri] = concept_data

  duplicates = {slug: uris for slug, uris in slug_counts.items() if len(uris) > 1}
  if duplicates:
    raise ValueError(f"Dubbele slugs gevonden: {duplicates}")

  for concept in concepts:
    concept["broaderResolved"] = [resolve_relation(graph, u, concept_by_uri) for u in concept["broader"]]
    concept["narrowerResolved"] = [resolve_relation(graph, u, concept_by_uri) for u in concept["narrower"]]
    concept["relatedResolved"] = [resolve_relation(graph, u, concept_by_uri) for u in concept["related"]]
    concept["exactMatchResolved"] = [resolve_relation(graph, u, concept_by_uri) for u in concept["exactMatch"]]
    concept["closeMatchResolved"] = [resolve_relation(graph, u, concept_by_uri) for u in concept["closeMatch"]]

  concepts.sort(key=lambda c: c["prefLabel"].lower())

  collections: list[dict[str, Any]] = []
  for collection in graph.subjects(RDF.type, SKOS.Collection):
    uri = str(collection)
    slug = uri_to_slug(uri)
    if not slug:
      raise ValueError(f"Kan geen slug afleiden voor collectie-URI: {uri}")
    pref_label, _ = literal_nl(graph, collection, SKOS.prefLabel)
    members = []
    for member_uri in graph.objects(collection, SKOS.member):
      member = concept_by_uri.get(str(member_uri))
      if member:
        members.append({
          "uri": member["uri"],
          "slug": member["slug"],
          "prefLabel": member["prefLabel"],
        })
    collections.append({
      "uri": uri,
      "slug": slug,
      "prefLabel": pref_label,
      "memberCount": len(members),
      "members": sorted(members, key=lambda m: m["prefLabel"].lower()),
    })
  collections.sort(key=lambda c: c["prefLabel"].lower())

  scheme_data: dict[str, Any] = {}
  if scheme_ref:
    title_pred = get_dct_predicate(graph, scheme_ref, "title")
    desc_pred = get_dct_predicate(graph, scheme_ref, "description")
    created_pred = get_dct_predicate(graph, scheme_ref, "created")
    modified_pred = get_dct_predicate(graph, scheme_ref, "modified")
    lang_pred = get_dct_predicate(graph, scheme_ref, "language")

    title, title_lang = literal_nl(graph, scheme_ref, title_pred)
    description, description_lang = literal_nl(graph, scheme_ref, desc_pred)
    note, note_lang = literal_nl(graph, scheme_ref, SKOS.note)

    scheme_data = {
      "uri": scheme_uri,
      "title": title,
      "titleLang": title_lang,
      "description": description,
      "descriptionLang": description_lang,
      "created": date_literal(graph, scheme_ref, created_pred),
      "modified": date_literal(graph, scheme_ref, modified_pred),
      "language": next((str(v) for v in graph.objects(scheme_ref, lang_pred)), "nl"),
      "note": note,
      "noteLang": note_lang,
      "hasTopConcept": [str(u) for u in graph.objects(scheme_ref, SKOS.hasTopConcept)],
    }

  top_from_scheme = set(scheme_data.get("hasTopConcept", []))
  top_from_concepts = {c["uri"] for c in concepts if c["isTopConcept"]}
  top_concepts = sorted(top_from_scheme | top_from_concepts)

  top_concepts_data = []
  for uri in top_concepts:
    concept = concept_by_uri.get(uri)
    if concept:
      top_concepts_data.append({
        "uri": uri,
        "slug": concept["slug"],
        "prefLabel": concept["prefLabel"],
      })
  top_concepts_data.sort(key=lambda c: c["prefLabel"].lower())

  search_index = [
    {
      "id": c["slug"],
      "prefLabel": c["prefLabel"],
      "altLabels": c["altLabels"],
      "hiddenLabels": c["hiddenLabels"],
      "definition": c["definition"],
      "comment": c["comment"],
    }
    for c in concepts
  ]

  alphabet_index: dict[str, list[dict[str, str]]] = {}
  for concept in concepts:
    letter = first_letter_nl(concept["prefLabel"])
    alphabet_index.setdefault(letter, []).append({
      "slug": concept["slug"],
      "prefLabel": concept["prefLabel"],
    })
  for letter in alphabet_index:
    alphabet_index[letter].sort(key=lambda c: c["prefLabel"].casefold())

  graph_edges: list[dict[str, str]] = []
  for concept in concepts:
    for rel_type, key in (("broader", "broader"), ("narrower", "narrower"), ("related", "related")):
      for target_uri in concept[key]:
        graph_edges.append({
          "source": concept["slug"],
          "target": concept_by_uri.get(target_uri, {}).get("slug", uri_to_slug(target_uri) or target_uri),
          "type": rel_type,
        })

  header = {
    "comment": extract_header_comment(raw_content),
    "note": scheme_data.get("note", ""),
  }

  out = OUTPUT_DIR / version_id
  out.mkdir(parents=True, exist_ok=True)

  write_json(out / "scheme.json", scheme_data)
  write_json(out / "concepts.json", concepts)
  write_json(out / "collections.json", collections)
  write_json(out / "top-concepts.json", top_concepts_data)
  write_json(out / "search-index.json", search_index)
  write_json(out / "alphabet-index.json", alphabet_index)
  write_json(out / "graph-edges.json", graph_edges)
  write_json(out / "header.json", header)

  print(f"  {version_id}: {len(concepts)} begrippen, {len(collections)} collecties")


def write_json(path: Path, data: Any) -> None:
  """Schrijf *data* als UTF-8 JSON met inspringing naar *path*."""
  path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
  """Bouw JSON-indexen voor alle versies uit ``versions.json``.

  Returns:
    Exitcode 0 bij succes, 1 bij ontbrekende bestanden of buildfouten.
  """
  if not VERSIONS_FILE.exists():
    print(f"versions.json niet gevonden: {VERSIONS_FILE}", file=sys.stderr)
    return 1

  manifest = json.loads(VERSIONS_FILE.read_text(encoding="utf-8"))
  OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

  for version in manifest["versions"]:
    version_id = version["id"]
    ttl_path = ROOT / version["file"]
    if not ttl_path.exists():
      print(f"TTL-bestand niet gevonden voor {version_id}: {ttl_path}", file=sys.stderr)
      return 1
    print(f"Bouwen versie {version_id}...")
    build_version(version_id, ttl_path)

  write_json(OUTPUT_DIR / "versions.json", manifest)
  print("Build voltooid.")
  return 0


if __name__ == "__main__":
  sys.exit(main())
