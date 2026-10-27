"""Templates and instances: AAS-valid, and the content we expect."""
import json

import pytest

from inspire2aas import config, instance


def env(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_templates(cp_au_templates):
    e = env(cp_au_templates)
    names = {s["idShort"] for s in e["submodels"]}
    assert names == {"CadastralParcel", "CadastralZoning", "BasicPropertyUnit", "CadastralBoundary",
                     "AdministrativeUnit", "AdministrativeBoundary", "Condominium"}
    cp = next(s for s in e["submodels"] if s["idShort"] == "CadastralParcel")
    assert cp["kind"] == "Template"
    assert cp["semanticId"]["keys"][0]["value"] == "http://inspire.ec.europa.eu/featureconcept/CadastralParcel"
    assert len(cp["submodelElements"]) == 13
    geom = next(x for x in cp["submodelElements"] if x["idShort"] == "geometry")
    assert geom["modelType"] == "File" and geom["contentType"] == "application/geo+json"
    report = (cp_au_templates.parent / "report.md").read_text(encoding="utf-8")
    assert "PASSED (0 errors)" in report
    assert "BaSyx re-read" in report


def test_closed_codelist_has_registry_values(cp_au_templates):
    cds = {c["id"]: c for c in env(cp_au_templates)["conceptDescriptions"]}
    cd = cds["http://inspire.ec.europa.eu/codelist/LegalStatusValue"]
    vl = cd["embeddedDataSpecifications"][0]["dataSpecificationContent"]["valueList"]["valueReferencePairs"]
    assert {v["value"] for v in vl} == {"agreed", "notAgreed"}
    assert vl[0]["valueId"]["keys"][0]["value"].startswith("http://inspire.ec.europa.eu/codelist/LegalStatusValue/")


def spec(tmp_path, values):
    base = json.loads((config.ROOT / "examples/parcel_example.json").read_text(encoding="utf-8"))
    base["values"].update(values)
    for k in [k for k, v in values.items() if v is None]:
        del base["values"][k]
    (tmp_path / "parcel_example.geojson").write_bytes((config.ROOT / "examples/parcel_example.geojson").read_bytes())
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(base), encoding="utf-8")
    return p


def test_example_parcel_instance(cp_au_templates, tmp_path):
    e, f, errors, _ = instance.build_instance(spec(tmp_path, {}))
    assert errors == []
    sm = e["submodels"][0]
    assert sm["kind"] == "Instance"
    assert sm["administration"]["templateId"].endswith("/smt/cp/4.0/CadastralParcel")
    vf = next(x for x in sm["submodelElements"] if x["idShort"] == "validFrom")
    assert vf["qualifiers"][0] == {"type": "INSPIRE/nilReason", "valueType": "xs:string",
                                   "kind": "ValueQualifier", "value": "unknown"}
    [path] = list(f.files)    # one folder per object, file named after the element (E06)
    assert path.startswith("/aasx/files/EX-0001_") and path.endswith("/geometry.geojson")


@pytest.mark.parametrize("values, message", [
    ({"label": None}, "mandatory element missing"),
    ({"label": {"nilReason": "unknown"}}, "not voidable"),
    ({"validFrom": {"nilReason": "because"}}, "nilReason must be one of"),
    ({"colour": "red"}, "unknown fields"),
    ({"inspireId": {"namespace": "x", "localId": "y", "extra": 1}}, "unknown fields"),
])
def test_instance_input_errors(cp_au_templates, tmp_path, values, message):
    with pytest.raises(instance.InstanceError, match=message):
        instance.build_instance(spec(tmp_path, values))


def test_closed_codelist_value_checked(cp_au_templates, tmp_path):
    s = json.loads(spec(tmp_path, {}).read_text())
    s["template"] = "AdministrativeBoundary"
    s["values"] = {"inspireId": {"namespace": "x", "localId": "b1"}, "country": "DE",
                   "geometry": {"type": "LineString", "coordinates": [[7, 51], [7.1, 51]]},
                   "nationalLevel": ["1stOrder"], "legalStatus": "maybe", "technicalStatus": "edgeMatched"}
    p = tmp_path / "b.json"
    p.write_text(json.dumps(s))
    with pytest.raises(instance.InstanceError, match="not in the closed codelist"):
        instance.build_instance(p)
    s["values"]["legalStatus"] = "agreed"
    p.write_text(json.dumps(s))
    e, _, errors, _ = instance.build_instance(p)
    assert errors == []
    ls = next(x for x in e["submodels"][0]["submodelElements"] if x["idShort"] == "legalStatus")
    assert ls["valueId"]["keys"][0]["value"] == "http://inspire.ec.europa.eu/codelist/LegalStatusValue/agreed"
