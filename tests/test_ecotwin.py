"""Acceptance tests for the EcoTwin requests R1-R6 (handover 2026-10-26).

The identifiers are those of EcoTwin's test case (ATKIS object DENWAT011QW000Ed, BK50 unit L5106_>Q531).
Namespaces, procedure URIs and national code URIs are test assumptions, as in the handover.
"""
import pytest

from inspire2aas import build, check_refs, config, ids
from inspire2aas.instance import InstanceError, Templates, build_submodel

BK50 = {"namespace": "https://registry.gdi-de.org/id/de.nw.gd.bk50", "localId": "L5106_>Q531"}
GEOM = {"type": "Polygon", "coordinates": [[[6.95, 50.94], [6.951, 50.94], [6.951, 50.941], [6.95, 50.94]]]}


@pytest.fixture(scope="module")
def T():
    assert build.main(["Existing Land Use", "Land Use Nomenclature", "LandCoverVector",
                       "LandCoverNomenclature", "Soil", "--name", "ecotwin_themes"]) == 0
    return Templates(config.OUTPUT_DIR / "templates/ecotwin_themes/ecotwin_themes_templates.json")


def obs(prop, result, uom=None, parameter=None):
    o = {"observedProperty": prop, "result": result, "phenomenonTime": "1971-01-01T00:00:00Z",
         "resultTime": "1971-01-01T00:00:00Z", "procedure": {"uri": "https://example.org/method/bk50"}}
    if uom:
        o["uom"] = uom
    if parameter:
        o["parameter"] = parameter
    return o


def soil_profile(observations):
    return {"inspireId": BK50, "localIdentifier": "L5106_>Q531",
            "otherSoilName": [{"soilName": ">Q", "isOriginalClassification": True}],
            "WRBSoilName": {"nilReason": "unpopulated"}, "beginLifespanVersion": {"nilReason": "unpopulated"},
            "validFrom": "1971-01-01T00:00:00Z", "isDescribedBy": {"nilReason": "unpopulated"},
            "soilProfileObservation": observations}


def item_by(sm, id_short):
    return next(e for e in sm["submodelElements"] if e["idShort"] == id_short)


# ---------------------------------------------------------------- R4
def test_r4_templates_verify(T):
    report = (config.OUTPUT_DIR / "templates/ecotwin_themes/report.md").read_text(encoding="utf-8")
    assert "PASSED (0 errors)" in report
    assert "definition-missing" in report


# ---------------------------------------------------------------- R1
def test_r1_soil_observation_values(T):
    r = build_submodel(T, "DerivedSoilProfile", soil_profile([
        obs("availableWaterCapacity", {"number": 88.9}, "mm",
            [{"name": "referenceDepth", "value": 9.6, "uom": "dm"}]),
        obs("potentialRootDepth", {"number": 9.6}, "dm"),
    ]))
    assert r.errors == []
    o = item_by(r.submodel, "soilProfileObservation")["value"][0]
    op = next(x for x in o["value"] if x["idShort"] == "observedProperty")
    assert op["valueId"]["keys"][0]["value"] == \
        "http://inspire.ec.europa.eu/codelist/SoilProfileParameterNameValue/availableWaterCapacity"
    result = next(x for x in o["value"] if x["idShort"] == "result")
    assert result["value"] == [dict(result["value"][0], value="88.9")]
    par = next(x for x in o["value"] if x["idShort"] == "parameter")["value"][0]["value"]
    assert {x["idShort"]: x["value"] for x in par} == {"name": "referenceDepth", "value": "9.6", "uom": "dm"}


def test_r1_result_exactly_one(T):
    with pytest.raises(InstanceError, match="exactly one"):
        build_submodel(T, "DerivedSoilProfile", soil_profile([obs("availableWaterCapacity", {"number": 1, "text": "x"})]))


def test_r1_range_result(T):
    r = build_submodel(T, "DerivedSoilProfile", soil_profile([obs("availableWaterCapacity", {"range": {"min": 80, "max": 95}}, "mm")]))
    assert r.errors == []


def test_r1_observation_on_all_soil_parameter_lists(T):
    for tmpl, prop, cl in [("DerivedSoilProfile", "soilProfileObservation", "SoilProfileParameterNameValue"),
                           ("SoilLayer", "profileElementObservation", "ProfileElementParameterNameValue"),
                           ("SoilDerivedObject", "soilDerivedObjectObservation", "SoilDerivedObjectParameterNameValue"),
                           ("SoilSite", "soilSiteObservation", "SoilSiteParameterNameValue")]:
        lst = next(e for e in T.template(tmpl)["submodelElements"] if e["idShort"] == prop)
        op = next(x for x in lst["value"][0]["value"] if x["idShort"] == "observedProperty")
        assert op["supplementalSemanticIds"][0]["keys"][0]["value"].endswith("/" + cl), tmpl


# ---------------------------------------------------------------- R3 (narrower lists, national codes)
def test_r3_narrower_national_value_with_parent(T):
    r = build_submodel(T, "DerivedSoilProfile", soil_profile([
        obs({"code": "fieldCapacity", "uri": "https://example.org/bk50/parameter/FK", "broader": "physicalParameter"},
            {"number": 120.3}, "mm")]))
    assert r.errors == []
    op = next(x for x in item_by(r.submodel, "soilProfileObservation")["value"][0]["value"] if x["idShort"] == "observedProperty")
    assert op["valueId"]["keys"][0]["value"] == "https://example.org/bk50/parameter/FK"
    assert op["qualifiers"][0]["type"] == "INSPIRE/broaderValue"
    assert op["qualifiers"][0]["value"].endswith("/SoilProfileParameterNameValue/physicalParameter")


def test_r3_narrower_warnings_and_errors(T):
    r = build_submodel(T, "DerivedSoilProfile", soil_profile([obs("physicalParameter", {"number": 1})]))
    assert any("structuring value" in w for w in r.warnings)
    r = build_submodel(T, "DerivedSoilProfile", soil_profile([obs({"code": "FK"}, {"number": 1})]))
    assert any("should name its INSPIRE parent" in w for w in r.warnings)
    assert any("no URI" in w for w in r.warnings)
    with pytest.raises(InstanceError, match="broader 'nonsense'"):
        build_submodel(T, "DerivedSoilProfile", soil_profile([obs({"code": "FK", "broader": "nonsense"}, {"number": 1})]))


def elu(specific, ns=None):
    v = {"inspireId": {"namespace": "https://registry.gdi-de.org/id/de.nw.atkis-basis-dlm",
                       "localId": "DENWAT011QW000Ed", "versionId": "2026-08-21"},
         "geometry": GEOM, "hilucsLandUse": ["3_4_4_OpenAirRecreationalAreas"], "specificLandUse": [specific],
         "observationDate": "2026-08-21", "beginLifespanVersion": {"nilReason": "unpopulated"},
         "hilucsPresence": {"nilReason": "unpopulated"}, "specificPresence": {"nilReason": "unpopulated"},
         "dataset": {"uri": "https://example.org/ecotwin/dataset/atkis-basis-dlm-nw_2026-08-21"}}
    return v


def specific_value_id(r):
    item = item_by(r.submodel, "specificLandUse")["value"][0]
    return item.get("valueId", {}).get("keys", [{}])[0].get("value")


def test_r3_national_code_never_gets_inspire_uri(T):
    r = build_submodel(T, "ExistingLandUseObject", elu("4400"))
    assert r.errors == []
    assert specific_value_id(r) is None
    assert any("'4400'" in w and "no URI" in w for w in r.warnings)
    hil = item_by(r.submodel, "hilucsLandUse")["value"][0]
    assert hil["valueId"]["keys"][0]["value"] == "http://inspire.ec.europa.eu/codelist/HILUCSValue/3_4_4_OpenAirRecreationalAreas"


def test_r3_caller_uri_and_namespace_map(T):
    uri = "https://registry.gdi-de.org/codelist/de.adv-online.gid/AX_Funktion_SportFreizeitUndErholungsflaeche/4400"
    assert specific_value_id(build_submodel(T, "ExistingLandUseObject", elu({"code": "4400", "uri": uri}))) == uri
    r = build_submodel(T, "ExistingLandUseObject", elu("4400"),
                       codelist_namespaces={"LandUseClassificationValue": "https://example.org/atkis/"})
    assert specific_value_id(r) == "https://example.org/atkis/4400"
    with pytest.raises(InstanceError, match="INSPIRE URI would claim"):
        build_submodel(T, "ExistingLandUseObject", elu(
            {"code": "4400", "uri": "http://inspire.ec.europa.eu/codelist/LandUseClassificationValue/4400"}))


# ---------------------------------------------------------------- R2 + R5
def test_r2_r5_soil_body_with_share_and_resolved_reference(T):
    prof = build_submodel(T, "DerivedSoilProfile", soil_profile([]))
    body = build_submodel(T, "SoilBody", {
        "inspireId": {"namespace": "https://example.org/ecotwin/soilbody", "localId": "DENWAT011QW000Ed"},
        "geometry": GEOM, "soilBodyLabel": "L5106_>Q531 (100 %)", "beginLifespanVersion": {"nilReason": "unpopulated"},
        "isDescribedBy": [{"derivedSoilProfile": {"template": "DerivedSoilProfile", "inspireId": BK50},
                           "derivedProfilePercentageRange": {"lowerValue": 100.0, "upperValue": 100.0, "uom": "%"}}]})
    assert prof.errors == [] and body.errors == []
    item = item_by(body.submodel, "isDescribedBy")["value"][0]
    ref = next(x for x in item["value"] if x["idShort"] == "derivedSoilProfile")["value"]["keys"][0]["value"]
    assert ref == prof.submodel["id"] == ids.submodel_id("so", "DerivedSoilProfile", BK50["namespace"], BK50["localId"])
    assert "%3EQ531" in ref                                          # reversible encoding of '>'
    envs = {"profile": {"submodels": [prof.submodel]}, "body": {"submodels": [body.submodel]}}
    assert check_refs.dangling_references(envs) == []
    assert len(check_refs.dangling_references({"body": envs["body"]})) == 1


def test_r5_ids_are_unique_for_lt_gt():
    a = ids.object_key("x", "L1_>Q1")
    b = ids.object_key("x", "L1_<Q1")
    assert a != b


# ---------------------------------------------------------------- R6
def test_r6_submodel_api_returns_cds(T):
    r = build_submodel(T, "DerivedSoilProfile", soil_profile([obs("availableWaterCapacity", {"number": 88.9}, "mm")]))
    used = {c["id"] for c in r.concept_descriptions}
    assert r.submodel["semanticId"]["keys"][0]["value"] in used
    assert "http://inspire.ec.europa.eu/codelist/SoilProfileParameterNameValue" in used
    assert r.submodel["kind"] == "Instance"
