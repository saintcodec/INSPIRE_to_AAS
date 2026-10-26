# E05: EcoTwin requests R1–R6: verify, implement, accept

- **Date:** 2026-10-26
- **Input:** EcoTwin handover "INSPIRE_to_AAS — requests from EcoTwin" (2026-10-26, tested against commit `1095ee8`)
- **Question:** Are EcoTwin's observations correct? Can the converter store soil observations, association classes and national codes correctly?
- **Status:** done. All 6 requests are implemented and covered by acceptance tests ([tests/test_ecotwin.py](../../tests/test_ecotwin.py)).

## 1. Verification of the handover (before changing anything)

| Claim in the handover | Our check | Result |
|---|---|---|
| Build of ELU+LUN+LCV+LCN+SO gives 14 SMTs, 242 CDs, **4 verification errors** (AASc-3a-008) | re-ran the same command on `1095ee8` | ✅ reproduced exactly |
| R1: `OM_Observation` roles become ReferenceElements to a submodel that doesn't exist; not in the ledger | inspected the template + ledger | ✅ confirmed. A **silent loss**, which breaks our own principle. |
| R2: the association class `DerivedProfilePresenceInSoilBody` is dropped silently | same | ✅ confirmed, also silent |
| R3: an open-list code builds `<INSPIRE scheme>/<code>` | `instance.py` line 139 (E04) | ✅ confirmed |
| Soil OCL: observedProperty from the parameter lists; result Number/CharacterString/RangeType; featureOfInterest = self | read the OCL in the XMI | ✅ confirmed. **Correction:** there are **4** lists, not 3 (`SoilSite` → `SoilSiteParameterNameValue`). |
| `availableWaterCapacity` "based on the potential root depth"; `potentialRootDepth` "in cm" | Registry 20260826-0 | ✅ confirmed; both are under `physicalParameter` |
| "`procedure` is an `INSPIRE_OM_Process`; its `processParameter` carries settings such as the reference depth" | XMI, schema "Processes" | ⚠️ **Partly wrong.** The UML class is called `Process`, and `ProcessParameter` = {name: ProcessParameterNameValue, description} has **no value**. A reference depth of 9.6 dm can't be stored there. The ISO 19156 place for it is `OM_Observation.parameter` (NamedValue), and that is what we implement. |
| `RangeType {lowerValue, upperValue, uom}` | XMI, Soil | ✅ (SpeciesDistribution has a different RangeType {lowerBound, upperBound}) |

Additional finding: the Soil OCL itself refers to `self.soilProfileParameter.observedProperty` (also `profileElementParameter`, `soilDerivedObjectParameter`, `soilSiteParameter`). Those properties don't exist; the real names are `…Observation`. This is a further OCL error in the official model (cf. E02 G8).

## 2. Changes

| Request | Change | Where |
|---|---|---|
| R1 | `OM_Observation` → observation collection {observedProperty, result (number\|text\|range, exactly one), uom, phenomenonTime, resultTime, procedure, parameter[]}. The parameter codelist is **read from the owning class's OCL**, so it is not hard-coded for Soil. | `mapper.observation`, `mapper.observed_property_codelist` |
| R2 | Generic association-class rule: SMC {reference + class attributes}. The reader links roles to their association class (19 roles in the whole model). | `xmi_reader` (`assoc_class_id`), `mapper.association_item` |
| R3 | `<name>_codelists.json` next to every template build. Registry codes → Registry URI; other codes → caller URI / namespace map / no valueId plus a warning; an INSPIRE URI for an unknown code is **rejected**; `broader` for narrower lists → qualifier `INSPIRE/broaderValue`. | `mapper.codelist_sidecar`, `instance.Filler.codelist_value` |
| R4 | Missing definition → the name, logged `definition-missing` | `mapper.cd` |
| R5 | New module `ids` (`submodel_id`, `aas_id`, `asset_id`, `object_key`); references as `{template, inspireId}` or `{uri}`; `python -m inspire2aas.check_refs` | `ids.py`, `check_refs.py` |
| R6 | `build_submodel(templates, template, values, …)` → submodel + CDs + files + warnings + verification errors; no shell | `instance.py` |

**Breaking change:** instance ids now use percent-encoding instead of replacing characters with `_`. For example `…/sm/so/DerivedSoilProfile/registry.gdi-de.org/id/de.nw.gd.bk50/L5106_%3EQ531`, previously `…registry.gdi-de.org_id_de.nw.gd.bk50_L5106__Q531`. Reason: the old form is not collision-free (`>` and `<` both became `_`), and it could not be reversed. EcoTwin's measurement (no collision in BK50) holds for that dataset only.

Bugs found on the way:
- an empty list produced an AAS list with 0 items, which AAS forbids → now it is left out (or an error if OneToMany)
- a data-type recursion cut also logged a wrong "external type" reason (E04)

## 3. Results

| Check | Result |
|---|---|
| ecotwin_themes build | 14 SMTs, **0 verification errors**, BaSyx re-read 277 identifiables |
| cp_au build (regression) | 7 SMTs, 0 errors |
| Tests | **26/26 passed** (14 earlier + 12 new acceptance tests) |
| R1 acceptance: L5106_>Q531 with NFK 88.9 mm (`availableWaterCapacity`, uom mm, procedure URI, parameter referenceDepth 9.6 dm) + potentialRootDepth 9.6 dm | 0 errors; observedProperty valueId = Registry URI |
| R2 acceptance: SoilBody → DerivedSoilProfile with range 100–100 % | 0 errors; the reference resolves to the profile's submodel id; `check_refs` finds 0 dangling, and 1 when the profile is missing |
| R3 acceptance: `specificLandUse` 4400 | no INSPIRE URI: without a URI → no valueId plus a warning; with a caller URI → that URI; with an INSPIRE URI → rejected |

New ledger counts (ecotwin_themes): `observation-profile` 6, `association-class-as-collection` 1, `definition-missing` 4. `codelist-extensibility-conflict` rose from 1 to 7 because the four Soil parameter lists are now used (UML `any` vs Registry `narrower`, known from E03).

## 4. Points for EcoTwin

1. **Reference depth:** use the observation's `parameter` (`{"name": "referenceDepth", "value": 9.6, "uom": "dm"}`), not processParameter (see §1).
2. **`resultTime` is mandatory** in ISO 19156 (and not voidable). The handover's example did not give it. For BK50, the survey year (`KJAHR`) is a candidate for both phenomenonTime and resultTime.
3. **Units:** `potentialRootDepth` is defined "in cm" in the Registry. TIEFE is in dm. The converter does not check units; converting or using a narrower value is EcoTwin's decision.
4. Instance ids have changed (breaking change above). References should be given as `{"template", "inspireId"}` so they never need the formula.
5. Our example parcel (E04) has a dangling reference to a fictitious AdministrativeUnit. `check_refs` reports it, as intended.

## Reproduce

```
set PYTHONPATH=src
.venv\Scripts\python -m inspire2aas.build "Existing Land Use" "Land Use Nomenclature" LandCoverVector LandCoverNomenclature Soil --name ecotwin_themes
.venv\Scripts\python -m pytest tests
```
