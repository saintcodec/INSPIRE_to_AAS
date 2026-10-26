# E04: First generator run, CadastralParcels + AdministrativeUnits → AAS v3.1

- **Date:** 2026-10-26
- **Question:** Can the INSPIRE model be turned automatically into valid AAS v3.1 Submodel Templates, and can a parcel AAS be created from them?
- **Status:** done. CP and AU work end-to-end.

## What was built

| Part | File | What it does |
|---|---|---|
| Reader | [src/inspire2aas/xmi_reader.py](../../src/inspire2aas/xmi_reader.py) | XMI → intermediate model (all reader rules from E01/E02) |
| Registry | [src/inspire2aas/registry.py](../../src/inspire2aas/registry.py) | codelists, feature concepts, schema prefixes |
| Mapper | [src/inspire2aas/mapper.py](../../src/inspire2aas/mapper.py) | model → Submodel Templates + ConceptDescriptions + loss ledger; rules in [docs/mapping_rules.md](../../docs/mapping_rules.md) |
| Build | [src/inspire2aas/build.py](../../src/inspire2aas/build.py) | command line; verification; JSON + AASX |
| Instance | [src/inspire2aas/instance.py](../../src/inspire2aas/instance.py) | template + values (JSON) → AAS of one object |
| Tests | [tests/](../../tests/) | 14 automatic tests (E01–E03 regression, templates, instances, wrong input) |

Environment: Python 3.14.5, the packages in [requirements.txt](../../requirements.txt).

## Results

| Check | Result |
|---|---|
| Templates generated | 7: CadastralParcel, CadastralZoning, BasicPropertyUnit, CadastralBoundary, AdministrativeUnit, AdministrativeBoundary, Condominium |
| ConceptDescriptions | 114 |
| **aas-core3.1 verification** (all AASd constraints) | **0 errors** |
| Is the checker itself working? | Yes. A deliberately broken submodel was rejected with AASd-022, AASd-109, the idShort pattern and the version pattern. |
| Independent re-read with BaSyx 2.2.0 | 122 identifiables read with `failsafe=False`, no error |
| CP template content vs INSPIRE | 13/13 CadastralParcel properties, with multiplicity and voidable as in ShapeChange's FC (automatic test) |
| Example parcel AAS (fictitious data) | 0 verification errors; AASX contains the shell, the submodel, 18 CDs and the GeoJSON file |
| Wrong input to the instance builder | all 6 test cases rejected with a clear message (missing mandatory field, nilReason on a non-voidable field, invalid nilReason, unknown field, unknown sub-field, value not in a closed codelist) |

### Loss ledger, CP + AU ([output/templates/cp_au/loss_ledger.csv](../../output/templates/cp_au/loss_ledger.csv))

| Kind | Count | Meaning |
|---|---|---|
| ocl-constraint-not-translated | 17 | OCL rules are not part of the templates |
| codelist-extensibility-conflict | 14 | UML vs Registry. The Registry is used (D1); e.g. LegalStatusValue: UML `any`, Registry `none` |
| geometry-as-geojson | 9 | GM_* → GeoJSON File; arcs and CRS are not checked |
| measure-unit-not-fixed | 4 | e.g. `areaValue` (Area) → xs:double, no unit |
| codelist-extensibility-missing-in-uml | 3 | taken from the Registry |
| multiplicity-approximated | 2 | AU `country` [1..2] and `nationalLevel` [1..6] → OneToMany |

## Findings

| # | Finding |
|---|---|
| B1 | AAS 3.1 idShort needs **at least 2 characters** (pattern `^[a-zA-Z][a-zA-Z0-9_-]*[a-zA-Z0-9_]+$`), and `version`/`revision` must be numeric. Both claims in first_reaserch.md (I-7, I-12) are confirmed by the checker. |
| B2 | aas-core3.1 1.0.0 did **not** report an idShort on a list item (AASd-120) in our negative test. The checker is not complete for that constraint, so our generator guarantees it itself. |
| B3 | BaSyx `AASXWriter.write_aas()` **drops ConceptDescriptions** that are referenced by ExternalReference (our semanticIds). Fixed by using `write_all_aas_objects()`. |
| B4 | BaSyx 2.2.0 and aas-core3.1 are both on metamodel **3.1**. The report's claim "BaSyx PyPI = 3.0.1" is outdated. |

## Reproduce

```
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
set PYTHONPATH=src
.venv\Scripts\python -m inspire2aas.build CadastralParcels AdministrativeUnits
.venv\Scripts\python -m inspire2aas.instance examples\parcel_example.json
.venv\Scripts\python -m pytest tests
```

## Open / next

1. Real parcel data: the input is currently a hand-written JSON file. Next would be reading real INSPIRE CP data (GML from a download service) or ALKIS.
2. Open the results in AASX Package Explorer (a visual check by the researcher).
3. Soil, ELU and LCV templates (association class, coverages, OM_Observation, open nomenclatures).
4. Green-space / parcel AAS composition: one AAS referencing several submodels (CP + AU + LU + LC + SO).
