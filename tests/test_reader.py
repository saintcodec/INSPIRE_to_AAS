"""Regression tests for the reader: the results of experiments E01-E03 must keep holding."""
from lxml import etree

from inspire2aas import config
from inspire2aas.xmi_reader import flatten

FC = config.ROOT / "data/raw/approved/fc/FC_INSPIRE_v2025.1.tmp.xml"


def fc_props(schema, type_name):
    """Own properties of a type in ShapeChange's Feature Catalogue: name -> (cardinality, voidable)."""
    root = etree.parse(str(FC)).getroot()
    byid = {e.get("id"): e for e in root if e.get("id")}
    schema_id = next(e.get("id") for e in root if e.tag == "ApplicationSchema" and e.findtext("name") == schema)
    ft = next(e for e in root if e.tag == "FeatureType" and e.findtext("name") == type_name
              and e.find("package").get("idref") == schema_id)
    out = {}
    for cb in ft.findall("characterizedBy"):
        p = byid[cb.get("idref")]
        card = p.findtext("cardinality")
        out[p.findtext("name")] = (card, p.findtext("voidable") == "true")
    return out


def card(p):
    return p.lower if p.lower == p.upper else f"{p.lower}..{p.upper}"


def test_schema_count_and_versions(model):
    assert len(model.schemas) == 91                       # E01 F7
    assert model.schemas["CadastralParcels"].version == "4.0"
    assert model.schemas["AdministrativeUnits"].version == "5.0"
    assert model.schemas["Soil"].version == "4.0.2"


def test_cp_au_properties_equal_shapechange(model):     # E02: identical to ShapeChange's FC
    for schema, types in {"CadastralParcels": ["CadastralParcel", "CadastralZoning", "BasicPropertyUnit", "CadastralBoundary"],
                          "AdministrativeUnits": ["AdministrativeUnit", "AdministrativeBoundary", "Condominium"]}.items():
        for t in types:
            mine = {p.name: (card(p), p.voidable) for p in model.by_name(schema, t).props}
            assert mine == fc_props(schema, t), t


def test_voidable_from_second_stereotype(model):       # E01 F4
    au = model.by_name("AdministrativeUnits", "AdministrativeUnit")
    p = next(p for p in au.props if p.name == "beginLifespanVersion")
    assert p.voidable and p.lifecycle


def test_flatten_soil_profile(model):                 # inherited properties appear in the subtype
    names = {p.name for p in flatten(model, model.by_name("Soil", "ObservedSoilProfile"))}
    assert {"inspireId", "WRBSoilName", "beginLifespanVersion", "isDescribedBy"} <= names


def test_registry_extensibility_vocabulary(reg):       # E03 C1/C5
    assert reg.codelist("LegalStatusValue").extensibility == "none"
    assert set(reg.codelist("LegalStatusValue").values) == {"agreed", "notAgreed"}
    assert len(reg.codelist("WRBQualifierValue").values) >= 179
    assert reg.schema_prefix["CadastralParcels"] == "cp"
