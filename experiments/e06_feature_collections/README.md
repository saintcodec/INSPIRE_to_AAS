# E06: EcoTwin request R7 (feature collections) and two packaging defects

- **Date:** 2026-10-27
- **Input:** EcoTwin handover 2 "request R7" (2026-10-27, tested against `034158e`)
- **Question:** Can many features of one type be items of one submodel, with every rule of the single-feature builder applied? Are the two reported packaging defects real?
- **Status:** done. Tests: 31/31 (5 new).

## 1. Verification of the handover

| Claim | Our check | Result |
|---|---|---|
| Inline geometry always becomes `/aasx/files/geometry.geojson` | `instance.py` (E05) | ✅ confirmed. The name was built from the element path only. |
| A file given by path uses only its base name | same | ✅ confirmed. `a/parcel.geojson` and `b/parcel.geojson` collide. |
| `write_aasx` writes XML into a part called `data.json` | opened the zip of all three committed packages | ✅ confirmed, and **also in the template build** (`build.py`) since E04. Cause: BaSyx `write_all_aas_objects(…, write_json=False)` defaults to XML; we chose the part name. The content type `application/xml` was correct. |
| R7 is generic, not EcoTwin-specific | – | agreed. The item content is unchanged INSPIRE; only the container is new. |

Further findings from the acceptance data:
- EcoTwin's appendix gives `observationDate: "2023-07-09"`. INSPIRE types it as DateTime → `xs:dateTime`, which the AAS verifier rejects (verified). Before E06, the error came only from verification, with a verifier path (`.submodels[0]…value[2]`) instead of the item.
- `SoilBody.inspireId` is **optional** in INSPIRE ([0..1]). The builder requires it, because ids and file folders are derived from it.
- The SoilBody template's geometry is GM_MultiSurface, while EcoTwin sends Polygons. Geometry types are not checked (known gap, logged as `geometry-as-geojson`).

## 2. Changes

| Item | Change |
|---|---|
| R7 | `build_feature_collection(...)` → `SubmodelResult`. Structure exactly as requested (see [docs/mapping_rules.md](../../docs/mapping_rules.md)). Single features and collection items share one function, `fill_feature`, so the rules cannot drift apart. Items additionally carry `supplementalSemanticId` = their Submodel Template id. |
| R7 item errors | Paths start with `<list_name>[i]/`. A duplicate inspireId is checked **before** filling (otherwise a file-name clash was reported first). |
| value types | Property and Range values are checked with `aas_core3_1.verification.value_consistent_with_xsd_type` while filling → `LandCoverUnits[0]/landCoverObservation[0]/observationDate: '2023-07-09' is not a valid xs:dateTime (…)`. |
| defect 1 | files go to `/aasx/files/<localId>_<sha1(object key)[:8]>/<element path><suffix>`; a reused name in one package is an error |
| defect 2 | part name `/aasx/data.xml` in `instance.write_aasx` and in `build.py`; content types of supplementary files are taken from the extension (was always `application/geo+json`) |

## 3. Acceptance (EcoTwin §3)

| Check | Result |
|---|---|
| Soil collection: 1 submodel, 4 SoilBody items, each with a geometry file and one `isDescribedBy` at 100 % | ✅ |
| Land-cover collection: 1 submodel, 7 LandCoverUnit items with geometry and class | ✅ |
| aas-core3.1 verification | ✅ 0 errors |
| A missing mandatory element is rejected, and the message names the item | ✅ `SoilBodies[3]/geometry: mandatory element missing`. A mandatory **voidable** element (e.g. soilBodyLabel) gives nilReason "unpopulated" plus a warning naming the item. |
| Two items with geometry → two different file paths | ✅ 11 distinct files for 4+7 items; also distinct across separate `build_submodel` calls (inline and by path) |
| BaSyx: publishes and reads back | ✅ AASX with both submodels written, read back with BaSyx `AASXReader`: 4 and 7 items, 11 files. A BaSyx *server* (publish) was not tested. |
| References from items resolve (R5) | ✅ `isDescribedBy` → `ids.submodel_id("so", "DerivedSoilProfile", …)` |

Test data: synthetic items following EcoTwin's appendix (identifiers as given; geometries are a small test polygon). EcoTwin's real files were not used and are not stored in this repository.

## 4. Regression

- cp_au and ecotwin_themes builds: 0 errors; packages now contain `aasx/data.xml`.
- Example parcel: the geometry moved from `/aasx/files/parcel_example.geojson` to `/aasx/files/EX-0001_16871640/geometry.geojson` (test updated).
