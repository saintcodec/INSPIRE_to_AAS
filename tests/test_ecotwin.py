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


# ---------------------------------------------------------------- R7 + defects of handover 2 (2026-10-27)
def soil_item(i, inline=True):
    return {"inspireId": {"namespace": "https://example.org/ecotwin/soilbody", "localId": f"DENWAT011rs0002A_soil{i}"},
            "geometry": GEOM, "soilBodyLabel": f"L5308_B33{i}", "beginLifespanVersion": {"nilReason": "unpopulated"},
            "isDescribedBy": [{"derivedSoilProfile": {"template": "DerivedSoilProfile", "inspireId": {
                "namespace": "https://registry.gdi-de.org/id/de.nw.gd.bk50", "localId": f"L5308_B33{i}"}},
                "derivedProfilePercentageRange": {"lowerValue": 100.0, "upperValue": 100.0, "uom": "%"}}]}


def lc_item(i, date="2023-07-09T00:00:00Z"):
    return {"inspireId": {"namespace": "https://example.org/ecotwin/landcover", "localId": f"DENWAT011rs0002A_lc{i}"},
            "geometry": GEOM, "beginLifespanVersion": {"nilReason": "unpopulated"},
            "landCoverObservation": [{"class": {"code": "LB_KrautigeVegetation_Gras",
                                                "uri": "https://example.org/ecotwin/lb-nrw-2023/lbklasse/LB_KrautigeVegetation_Gras"},
                                      "mosaic": {"nilReason": "unpopulated"}, "observationDate": date}],
            "dataset": {"uri": "https://example.org/ecotwin/source/lb-nrw/2023"}}


def collection(T, template, items, name):
    from inspire2aas.instance import build_feature_collection
    return build_feature_collection(T, template, items, f"https://example.org/ecotwin/sm/DENWAT011rs0002A/{name}",
                                    name, semantic_id=f"https://example.org/ecotwin/semantics/{name}", list_name=name)


def test_r7_soil_and_land_cover_collections(T):
    soil = collection(T, "SoilBody", [soil_item(i) for i in range(4)], "SoilBodies")
    lc = collection(T, "LandCoverUnit", [lc_item(i) for i in range(7)], "LandCoverUnits")
    assert soil.errors == [] and lc.errors == []
    for r, n, concept in [(soil, 4, "SoilBody"), (lc, 7, "LandCoverUnit")]:
        [lst] = r.submodel["submodelElements"]
        assert lst["semanticIdListElement"]["keys"][0]["value"] == f"http://inspire.ec.europa.eu/featureconcept/{concept}"
        assert len(lst["value"]) == n and all("idShort" not in it for it in lst["value"])
        assert all(it["semanticId"] == lst["semanticIdListElement"] for it in lst["value"])   # AASd-107
        assert len(r.files) == n and len(set(r.files)) == n                                   # one geometry each
    # references from items still resolve (R5)
    first = soil.submodel["submodelElements"][0]["value"][0]
    ref = next(x for x in first["value"] if x["idShort"] == "isDescribedBy")["value"][0]["value"][0]["value"]["keys"][0]["value"]
    assert ref == ids.submodel_id("so", "DerivedSoilProfile", "https://registry.gdi-de.org/id/de.nw.gd.bk50", "L5308_B330")


def test_r7_error_names_the_item(T):
    items = [soil_item(i) for i in range(4)]
    del items[3]["geometry"]                    # mandatory, not voidable
    with pytest.raises(InstanceError, match=r"SoilBodies\[3\]/geometry: mandatory element missing"):
        collection(T, "SoilBody", items, "SoilBodies")
    items = [soil_item(i) for i in range(4)]
    del items[2]["soilBodyLabel"]               # mandatory but voidable -> nilReason + warning naming the item
    r = collection(T, "SoilBody", items, "SoilBodies")
    assert r.errors == [] and any(w.startswith("SoilBodies[2]/soilBodyLabel") for w in r.warnings)
    items = [lc_item(0), lc_item(1)]
    items[1]["landCoverObservation"][0]["class"] = 7
    items[1]["inspireId"] = items[0]["inspireId"]
    with pytest.raises(InstanceError, match=r"LandCoverUnits\[1\]: inspireId is the same as LandCoverUnits\[0\]"):
        collection(T, "LandCoverUnit", items, "LandCoverUnits")


def test_r7_handover_date_value_is_not_a_datetime(T):
    """EcoTwin's appendix gives observationDate '2023-07-09'; the template (INSPIRE DateTime) needs xs:dateTime."""
    with pytest.raises(InstanceError, match=r"LandCoverUnits\[0\]/landCoverObservation\[0\]/observationDate: "
                                            r"'2023-07-09' is not a valid xs:dateTime"):
        collection(T, "LandCoverUnit", [lc_item(0, date="2023-07-09")], "LandCoverUnits")


def test_defect1_unique_file_names_across_objects_and_items(T, tmp_path):
    from inspire2aas.instance import build_submodel as bs
    for d in ("a", "b"):    # same base name in two folders
        (tmp_path / d).mkdir()
        (tmp_path / d / "parcel.geojson").write_text('{"type": "Point", "coordinates": [7, 51]}')
    v1, v2 = soil_item(0), soil_item(1)
    v1["geometry"], v2["geometry"] = {"file": "a/parcel.geojson"}, {"file": "b/parcel.geojson"}
    r1, r2 = bs(T, "SoilBody", v1, base_dir=tmp_path), bs(T, "SoilBody", v2, base_dir=tmp_path)
    assert set(r1.files).isdisjoint(r2.files)
    r3, r4 = bs(T, "SoilBody", soil_item(2)), bs(T, "SoilBody", soil_item(3))     # inline geometries
    assert set(r3.files).isdisjoint(r4.files)


def test_defect2_aasx_part_name_matches_content_and_basyx_round_trip(T, tmp_path):
    import zipfile
    from basyx.aas import model
    from basyx.aas.adapter import aasx
    from inspire2aas.instance import write_aasx
    soil = collection(T, "SoilBody", [soil_item(i) for i in range(4)], "SoilBodies")
    lc = collection(T, "LandCoverUnit", [lc_item(i) for i in range(7)], "LandCoverUnits")
    env = {"submodels": [soil.submodel, lc.submodel],
           "conceptDescriptions": list({c["id"]: c for c in soil.concept_descriptions + lc.concept_descriptions}.values())}
    path = tmp_path / "parcel.aasx"
    write_aasx(env, {**soil.files, **lc.files}, path)
    z = zipfile.ZipFile(path)
    data = [n for n in z.namelist() if n.startswith("aasx/data")]
    assert data == ["aasx/data.xml"] and z.read("aasx/data.xml").startswith(b"<?xml")
    assert len([n for n in z.namelist() if n.startswith("aasx/files/")]) == 11
    store, files = model.DictIdentifiableStore(), aasx.DictSupplementaryFileContainer()
    with aasx.AASXReader(str(path)) as r:
        r.read_into(store, files)
    assert {o.id_short for o in store if isinstance(o, model.Submodel)} == {"SoilBodies", "LandCoverUnits"}
    back = {o.id_short: o for o in store if isinstance(o, model.Submodel)}
    assert len(back["SoilBodies"].get_referable("SoilBodies").value) == 4
    assert len(back["LandCoverUnits"].get_referable("LandCoverUnits").value) == 7


# ---------------------------------------------------------------- R6
def test_r6_submodel_api_returns_cds(T):
    r = build_submodel(T, "DerivedSoilProfile", soil_profile([obs("availableWaterCapacity", {"number": 88.9}, "mm")]))
    used = {c["id"] for c in r.concept_descriptions}
    assert r.submodel["semanticId"]["keys"][0]["value"] in used
    assert "http://inspire.ec.europa.eu/codelist/SoilProfileParameterNameValue" in used
    assert r.submodel["kind"] == "Instance"
