# INSPIRE_to_AAS — reply to EcoTwin

From: INSPIRE_to_AAS · To: EcoTwin · Date: 2026-10-26
Reply to: "INSPIRE_to_AAS — requests from EcoTwin" (2026-10-26, tested against `1095ee8`)
Delivered in: commit `4e02c96`. Details in [experiments/e05_ecotwin_requests](../../experiments/e05_ecotwin_requests/README.md), rules in [docs/mapping_rules.md](../mapping_rules.md).

---

## 1. Summary

Thank you for the precise handover. We reproduced your run on `1095ee8` before changing anything, and all your observations held: 14 templates, 242 CDs, 4 AASc-3a-008 errors, silent loss of `OM_Observation` and of the association class, and INSPIRE URIs minted for national codes.

**All six requests are implemented.** The build of your themes now passes verification, and your test case (`L5106_>Q531`, `DENWAT011QW000Ed`) is part of our automatic tests.

| # | Request | Status | Acceptance |
|---|---|---|---|
| R1 | `OM_Observation` carries values | ✅ done | NFK 88.9 mm stored as an observation, 0 errors |
| R2 | association classes | ✅ done, generic | SoilBody → DerivedSoilProfile with range 100–100 %, 0 errors |
| R3 | no INSPIRE URIs for non-Registry codes | ✅ done | `4400` never gets an INSPIRE URI |
| R4 | 4 verification errors | ✅ fixed | build: 0 errors |
| R5 | identifier function, reference check | ✅ done | 0 dangling in the test pair; 1 reported when the target is missing |
| R6 | submodel-level API | ✅ done | returns the submodel + its CDs |

| Check | Result |
|---|---|
| `ecotwin_themes` build | 14 SMTs, **0 verification errors**, BaSyx re-read 277 identifiables |
| `cp_au` build (regression) | 7 SMTs, 0 errors |
| Tests | 26/26 passed (12 of them are acceptance tests for this handover) |

**Please read §3 (two corrections to the handover) and §4 (one breaking change) before you update.**

---

## 2. What is available now

### R1: observations

Every role typed `OM_Observation` becomes a list of observation collections:

```
soilProfileObservation              SubmodelElementList (ZeroToMany, voidable)
└── [item]                          SMC  semanticId = role CD, supplementalSemanticId = OM_Observation CD
    ├── observedProperty            Property xs:string → parameter code list (One)
    ├── result                      SMC, exactly one of: number (xs:double) | text (xs:string) | range (Range)
    ├── uom                         Property xs:string, UCUM recommended (ZeroToOne)
    ├── phenomenonTime              Property xs:dateTime (One)
    ├── resultTime                  Property xs:dateTime (One)
    ├── procedure                   ReferenceElement → INSPIRE Process (One)
    └── parameter                   SubmodelElementList of SMC {name, value, uom?} (ZeroToMany)
```

- **The parameter code list is not hard-coded.** It is read from the owning class's OCL (`observedProperty->oclIsKindOf(…)`). For Soil this gives all **four** lists, including `SoilSiteParameterNameValue`.
- **Omitted**, and recorded in the loss ledger as `observation-profile`:
  - featureOfInterest (by constraint, it is the object itself)
  - resultQuality, validTime, metadata, relatedObservation
- **Simplified:** TM_Object is reduced to a dateTime, and NamedValue.value is stored as text.

This is your suggested encoding, with two differences:
- `result` is a choice collection, so number, text and range keep their own types.
- The reference depth goes in `parameter`, not `processParameter` (see §3.1).

Input for your acceptance case:

```json
"soilProfileObservation": [
  {"observedProperty": "availableWaterCapacity",
   "result": {"number": 88.9}, "uom": "mm",
   "phenomenonTime": "1971-01-01T00:00:00Z", "resultTime": "1971-01-01T00:00:00Z",
   "procedure": {"uri": "<method document URI>"},
   "parameter": [{"name": "referenceDepth", "value": 9.6, "uom": "dm"}]},
  {"observedProperty": "potentialRootDepth", "result": {"number": 9.6}, "uom": "dm",
   "phenomenonTime": "1971-01-01T00:00:00Z", "resultTime": "1971-01-01T00:00:00Z",
   "procedure": {"uri": "<method document URI>"}}
]
```

A range result is `{"range": {"min": 80, "max": 95}}`. Giving two result forms at once is rejected.

### R2: association classes

A role whose association has an association class becomes a collection holding the reference plus the class's attributes, as you suggested. The rule is generic: the reader detects all 19 such roles in the model, not only the Soil one.

```json
"isDescribedBy": [
  {"derivedSoilProfile": {"template": "DerivedSoilProfile",
                          "inspireId": {"namespace": "https://registry.gdi-de.org/id/de.nw.gd.bk50", "localId": "L5106_>Q531"}},
   "derivedProfilePercentageRange": {"lowerValue": 100.0, "upperValue": 100.0, "uom": "%"}}
]
```

`derivedProfilePercentageRange` stays an SMC {lowerValue, upperValue, uom} rather than an AAS `Range`, because INSPIRE's RangeType carries its own `uom` and an AAS Range has no place for it.

### R3: national code values

Each template build now writes `<name>_codelists.json` next to the templates. It holds the valid Registry codes (URI, parent, has-narrower) of every list the templates use. The instance builder reads it automatically, so you do not need the Registry dump.

| Input | Result |
|---|---|
| a code that is in the Registry, e.g. `"3_4_4_OpenAirRecreationalAreas"` | valueId = Registry URI |
| `"4400"` (not in the Registry) | no valueId, plus a warning |
| `{"code": "4400", "uri": "https://registry.gdi-de.org/…/4400"}` | valueId = your URI |
| `codelistNamespaces: {"LandUseClassificationValue": "https://…/"}` (spec file or API argument) | valueId = namespace + code |
| a code that is not in the Registry, given with an `http://inspire.ec.europa.eu/…` URI | **rejected** |
| a code that is not in a closed list | **rejected** (unchanged) |

For **narrower** lists (all four Soil parameter lists), a provider value names its INSPIRE parent:

```json
{"observedProperty": {"code": "fieldCapacity", "uri": "https://…/bk50/parameter/FK", "broader": "physicalParameter"}}
```

The parent is stored as the ValueQualifier `INSPIRE/broaderValue` (valueId = the parent's Registry URI).

| Narrower-list situation | Result |
|---|---|
| no `broader` given | warning |
| an unknown `broader` | error |
| a structuring value such as `physicalParameter` used directly | warning |

### R4: definitions

A missing English definition falls back to the name and is logged as `definition-missing`. This covers the four Land Use Nomenclature CDs.

### R5: identifiers and references

```python
from inspire2aas import ids
ids.submodel_id("so", "DerivedSoilProfile", namespace, local_id)   # also aas_id, asset_id, object_key
ids.template_prefix(template_id)                                     # '…/smt/so/4.0.2/SoilBody' -> 'so'
```

References in instance input can take three forms:
- `{"template": "…", "inspireId": {"namespace": …, "localId": …}}`: resolved with `ids.submodel_id`. **We recommend this form.**
- `{"uri": "…"}`: an ExternalReference, e.g. for the ELU `dataset` or for `procedure`.
- a plain submodel id: kept for compatibility.

To check a set of instance files for dangling references:

```
python -m inspire2aas.check_refs "<folder>/*.json"
```

It reports ModelReferences to Submodels that no file contains. In Python, use `check_refs.dangling_references({name: env, …})`.

### R6: submodel-level API

```python
from inspire2aas.instance import build_submodel
r = build_submodel("output/templates/ecotwin_themes/ecotwin_themes_templates.json",
                   "SoilBody", values, base_dir=".", codelist_namespaces={...})
r.submodel              # dict (AAS JSON), kind = Instance, administration.templateId set
r.concept_descriptions  # only the CDs this submodel uses
r.files                 # {"/aasx/files/<name>": bytes}, e.g. geometry
r.warnings              # list of str (national codes without URI, missing parents, …)
r.errors                # aas-core3.1 verification of submodel + CDs ([] = valid)
```

No shell is created, so you compose your own. `instance.write_aasx(env, files, path)` packages an environment, including the supplementary files. The command line is unchanged.

---

## 3. Corrections to the handover

### 3.1 The reference depth cannot be a process parameter

In the INSPIRE UML (schema *Processes*), the class is called `Process` (the TG name is `INSPIRE_OM_Process`). Its `ProcessParameter` is `{name: ProcessParameterNameValue, description: CharacterString}`. **It has no value attribute.** A processParameter can declare *that* a method uses a reference depth, but it cannot carry 9.6 dm.

In ISO 19156, the place for per-observation settings is `OM_Observation.parameter` (NamedValue), and that is what we implemented. Please store TIEFE (and LF_TIEFE for LK) as `parameter`, as in the example in §2.

### 3.2 Four parameter lists, not three

`SoilSite.soilSiteObservation` uses its own `SoilSiteParameterNameValue` (136 values, narrower). It is covered automatically.

### 3.3 Note on the official model

The Soil OCL constraints refer to `self.soilProfileParameter.observedProperty` and the corresponding names for the other three classes. Those properties do not exist; the actual names are `…Observation`. This is a defect in the INSPIRE model, not in your report. We read the code list name from these constraints and ignore the wrong property name.

---

## 4. Breaking change: instance identifiers

The object key in instance ids is now **percent-encoded** instead of having characters replaced by `_`:

| | id of DerivedSoilProfile `L5106_>Q531` |
|---|---|
| before (`1095ee8`) | `…/sm/so/DerivedSoilProfile/registry.gdi-de.org_id_de.nw.gd.bk50_L5106__Q531` |
| now (`4e02c96`) | `…/sm/so/DerivedSoilProfile/registry.gdi-de.org/id/de.nw.gd.bk50/L5106_%3EQ531` |

**Reason.** The old form was not collision-free in general: `>` and `<` both became `_`, and `/` and `_` were merged. It also could not be reversed. Your measurement that BK50's 8,327 keys stay unique holds for BK50, but the converter has to be safe for any dataset.

**What to do:** regenerate existing instances, and give references as `{"template", "inspireId"}` so that you never need the formula. Ids still use the placeholder base `https://example.org/inspire-aas/`.

---

## 5. Points for your side

1. **`resultTime` is mandatory and not voidable** in ISO 19156, and your example spec did not include it. For BK50, the survey year (`KJAHR`) is a candidate for both phenomenonTime and resultTime. Whether that is acceptable for resultTime is your decision.
2. **Units are not converted or checked.** The Registry defines `potentialRootDepth` "in cm", while TIEFE is in dm. Convert the value, or record dm with the `uom` field and accept the deviation. The converter stores what you give it.
3. **Absent values:** as you wrote, the importer should map empty strings, `0`-as-absent and the sentinel `99` to "not given" or `{"nilReason": …}` before calling the converter. The converter cannot tell a real `99` from the sentinel.
4. **`specificLandUse` 4400:** if a URI exists for the ATKIS code (e.g. in the GDI-DE registry), pass it via `uri` or `codelistNamespaces`; otherwise you get a warning per value.
5. **Land cover:** the LandCoverUnit template is unchanged. We'll be glad to receive a test case once your LB NRW copy is repaired.

---

## 6. How to update

```
git pull                                   # 4e02c96 or later
.venv\Scripts\pip install -r requirements.txt
set PYTHONPATH=src
.venv\Scripts\python -m inspire2aas.build "Existing Land Use" "Land Use Nomenclature" LandCoverVector LandCoverNomenclature Soil --name ecotwin_themes
.venv\Scripts\python -m pytest tests       # 26 passed expected
```

The build writes `ecotwin_themes_templates.json`, `.aasx`, `ecotwin_themes_codelists.json` (new, needed by the instance builder), `loss_ledger.csv` and `report.md`.

Your test instances have been removed from the INSPIRE_to_AAS working copy; they were never committed. Please keep test data on the EcoTwin side.

Questions or further requests: as before, by handover file, preferably with a reproducible spec.
