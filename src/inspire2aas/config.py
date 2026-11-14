"""Paths, namespaces and fixed mapping tables. Everything a researcher may want to change lives here."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
XMI_PATH = ROOT / "data/raw/approved/ea+xmi/EAXMI/INSPIRE_Consolidated_UML_Model_ANNEX I-II-III-Only_IR_2025.1.xml"
REGISTRY_DIR = ROOT / "data/raw/INSPIRE Registry"
OUTPUT_DIR = ROOT / "output"

# Namespace of the identifiers this converter mints itself: Submodel Templates and
# ConceptDescriptions. A persistent identifier (w3id.org), so it stays when the project moves.
BASE_URI = "https://w3id.org/inspire-aas/"
# Namespace of the instances built with the templates (shells, submodels, assets). They belong to
# the project that builds them, which sets its own namespace here; the default is the converter's.
INSTANCE_BASE_URI = BASE_URI

INSPIRE = "http://inspire.ec.europa.eu/"

# Stereotype -> category (E02 R3: take the first *known* class stereotype)
CLASS_STEREOTYPES = {
    "featuretype": "featureType",
    "datatype": "dataType",
    "union": "union",
    "codelist": "codeList",
    "code list": "codeList",   # E02 G4: misspelled in the model
    "enumeration": "enumeration",
    "type": "type",
}

# ISO 19103 / basic types -> AAS element kind + xsd value type.
# kind: "property" | "mlp" (MultiLanguageProperty)
PRIMITIVES = {
    "CharacterString": ("property", "xs:string"),
    "Character_String": ("property", "xs:string"),
    "Boolean": ("property", "xs:boolean"),
    "Integer": ("property", "xs:integer"),
    "Real": ("property", "xs:double"),
    "Decimal": ("property", "xs:decimal"),
    "Number": ("property", "xs:decimal"),
    "Date": ("property", "xs:date"),
    "DateTime": ("property", "xs:dateTime"),
    "Time": ("property", "xs:time"),
    "URI": ("property", "xs:anyURI"),
    "URL": ("property", "xs:anyURI"),
    "GenericName": ("property", "xs:string"),
    "LocalName": ("property", "xs:string"),
    "ScopedName": ("property", "xs:string"),
    # measures: value only, unit of measure is left to the instance (see ledger)
    "Measure": ("property", "xs:double"),
    "Length": ("property", "xs:double"),
    "Distance": ("property", "xs:double"),
    "Area": ("property", "xs:double"),
    "Volume": ("property", "xs:double"),
    "Angle": ("property", "xs:double"),
    "Velocity": ("property", "xs:double"),
    "Weight": ("property", "xs:double"),
    "Scale": ("property", "xs:double"),
    # multilingual text
    "LocalisedCharacterString": ("mlp", None),
    "PT_FreeText": ("mlp", None),
}
MEASURES = {"Measure", "Length", "Distance", "Area", "Volume", "Angle", "Velocity", "Weight", "Scale"}

# xsd value type -> IEC 61360 data type for ConceptDescriptions (measures: none, avoids AASc-3a-009)
XSD_TO_IEC = {
    "xs:string": "STRING", "xs:boolean": "BOOLEAN", "xs:integer": "INTEGER_COUNT",
    "xs:date": "DATE", "xs:dateTime": "TIMESTAMP", "xs:time": "TIME", "xs:anyURI": "IRI",
}

GEOMETRY_CONTENT_TYPE = "application/geo+json"
DATATYPE_MAX_DEPTH = 4   # unroll nested data types up to this depth

# Qualifier types we introduce (documented in the README)
Q_CARDINALITY = "SMT/Cardinality"
Q_VOIDABLE = "INSPIRE/voidable"
Q_UNION = "INSPIRE/union"
Q_TARGET = "INSPIRE/referenceTarget"
Q_GEOMETRY = "INSPIRE/geometryType"
Q_LIFECYCLE = "INSPIRE/lifeCycleInfo"
