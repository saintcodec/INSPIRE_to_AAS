"""Read the INSPIRE Registry RDF dump (EU Vocabularies) - codelists, feature concepts, application schemas.

Implements E03: the Registry is authoritative for codelist values and extensibility
(decision 2026-10-26); UML/Registry disagreements are reported by the mapper.
"""
from dataclasses import dataclass, field

from lxml import etree

from . import config

RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
SKOS = "{http://www.w3.org/2004/02/skos/core#}"
REGM = "{http://inspire.ec.europa.eu/registry/model/ontology#}"
OWL = "{http://www.w3.org/2002/07/owl#}"
LANG = "{http://www.w3.org/XML/1998/namespace}lang"


@dataclass
class Concept:
    uri: str
    labels: dict = field(default_factory=dict)       # lang -> text
    definitions: dict = field(default_factory=dict)  # lang -> text
    status: str = ""
    broader: str = ""                                # URI of the parent value (hierarchical lists)


@dataclass
class CodeList(Concept):
    extensibility: str = ""                          # Registry vocabulary: none|narrower|open|any
    values: dict = field(default_factory=dict)       # code -> Concept


@dataclass
class Registry:
    version: str
    codelists: dict        # scheme URI -> CodeList
    featureconcepts: dict  # name -> Concept
    schema_prefix: dict    # UML application schema name -> prefix ("CadastralParcels" -> "cp")

    def codelist(self, name, vocabulary_tag=""):
        """Find a scheme by the UML vocabulary tag, else by name (E03 C4: tags can be broken)."""
        for uri in (vocabulary_tag, f"{config.INSPIRE}codelist/{name}", f"{config.INSPIRE}enumeration/{name}"):
            if uri and uri in self.codelists:
                return self.codelists[uri]
        return None


def _lang(d, tag):
    return {p.get(LANG): (p.text or "").strip() for p in d.findall(tag) if p.get(LANG)}


def _res(d, tag):
    x = d.find(tag)
    return x.get(RDF + "resource") if x is not None else None


def _parse(name):
    return etree.parse(str(config.REGISTRY_DIR / f"inspire-{name}.rdf"), etree.XMLParser(huge_tree=True)).getroot()


def read() -> Registry:
    codelists, values, version = {}, [], ""
    for reg in ("codelist", "enumeration"):
        for d in _parse(reg):
            uri = d.get(RDF + "about")
            types = {t.get(RDF + "resource").rsplit("#", 1)[-1] for t in d.findall(RDF + "type")}
            status = (_res(d, REGM + "status") or "").rsplit("/", 1)[-1]
            if types & {"CodeListConceptScheme", "EnumerationConceptScheme", "AbstractCodelist"}:
                ext = _res(d, REGM + "extensibility")
                codelists[uri] = CodeList(uri=uri, labels=_lang(d, SKOS + "prefLabel"),
                                          definitions=_lang(d, SKOS + "definition"), status=status,
                                          extensibility=ext.rsplit("/", 1)[-1] if ext else "")
                version = version or (d.findtext(OWL + "versionInfo") or "")
            elif types & {"CodeListValue", "EnumerationValue"}:
                values.append((d, uri, status))
    for d, uri, status in values:
        for s in d.findall(SKOS + "inScheme"):
            cl = codelists.get(s.get(RDF + "resource"))
            if cl is not None:
                cl.values[uri.rsplit("/", 1)[-1]] = Concept(uri=uri, labels=_lang(d, SKOS + "prefLabel"),
                                                            definitions=_lang(d, SKOS + "definition"),
                                                            status=status, broader=_res(d, SKOS + "broader") or "")
    fcs = {}
    for d in _parse("featureconcept"):
        uri = d.get(RDF + "about") or ""
        if uri.startswith(f"{config.INSPIRE}featureconcept/"):
            fcs[uri.rsplit("/", 1)[-1]] = Concept(uri=uri, labels=_lang(d, SKOS + "prefLabel"),
                                                  definitions=_lang(d, SKOS + "definition"))
    prefix = {}
    for d in _parse("applicationschema"):
        uml = d.findtext(REGM + "umlName")
        uri = d.get(RDF + "about") or ""
        if uml and uri.startswith(f"{config.INSPIRE}applicationschema/"):
            prefix[uml.strip()] = uri.rsplit("/", 1)[-1]
    return Registry(version=version, codelists=codelists, featureconcepts=fcs, schema_prefix=prefix)
