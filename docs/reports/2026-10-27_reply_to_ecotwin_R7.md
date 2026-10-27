# INSPIRE_to_AAS — reply to EcoTwin on R7

From: INSPIRE_to_AAS · To: EcoTwin · Date: 2026-10-27
Reply to: "INSPIRE_to_AAS — request R7 from EcoTwin" (2026-10-27, tested against `034158e`)
Details: [experiments/e06_feature_collections](../../experiments/e06_feature_collections/README.md) · rules: [docs/mapping_rules.md](../mapping_rules.md)

---

## 1. Summary

R7 is implemented as you specified, and both defects you found are confirmed and fixed. The second defect also affected our template packages, not only `write_aasx`.

| # | Item | Status |
|---|---|---|
| R7 | several features of one type as items of one submodel | ✅ `build_feature_collection` |
| D1 | geometry files share a name | ✅ fixed, one folder per object |
| D2 | XML in a part called `data.json` | ✅ fixed, `/aasx/data.xml`, in both the instance builder and the template build |

| Your acceptance check | Result |
|---|---|
| Soil: 1 submodel, 4 SoilBody items, geometry + `isDescribedBy` 100 % each | ✅ |
| Land cover: 1 submodel, 7 LandCoverUnit items, geometry + class each | ✅ |
| aas-core3.1 verification | ✅ 0 errors |
| Missing mandatory element → rejected, the message names the item | ✅ `SoilBodies[3]/geometry: mandatory element missing` |
| Two items with geometry → two different file paths | ✅ 11 distinct files for 4 + 7 items |
| BaSyx | ✅ AASX read back with BaSyx `AASXReader`, unchanged item counts and files. **Not tested:** publishing to a BaSyx server. Please confirm this on your side. |

We ran the acceptance with synthetic items shaped like your Appendix A (your identifiers, a small test polygon), not with your geometry files. Tests: 31/31.

---

## 2. Using R7

```python
from inspire2aas.instance import Templates, build_feature_collection, write_aasx

T = Templates("output/templates/ecotwin_themes/ecotwin_themes_templates.json")   # load once, reuse
r = build_feature_collection(
    T, "SoilBody", soil_items,                       # list of value dicts, same format as build_submodel
    submodel_id="https://example.org/ecotwin/sm/DENWAT011rs0002A/soil",
    id_short="SoilBodies",
    semantic_id="https://example.org/ecotwin/semantics/SoilBodies",   # optional, your concept
    list_name="SoilBodies",
    base_dir="<folder of the geometry files>",
    codelist_namespaces={...})                       # optional, as in R3
r.submodel, r.concept_descriptions, r.files, r.warnings, r.errors   # same SubmodelResult as R6
```

The resulting structure is exactly your §2:
- `SubmodelElementList` with `typeValueListElement = SubmodelElementCollection`, `semanticIdListElement` = the feature concept.
- Each item is an SMC with no idShort, and `semanticId` = the feature concept.
- **Addition:** each item has `supplementalSemanticId` = the id of the Submodel Template it follows, so a reader knows which template was used.

Your seven points:

1. **Same rules per item:** single features and items go through one shared function (`fill_feature`), so the rules cannot drift apart.
2. **Errors name the item:** errors and warnings start with `<list_name>[i]/…`.
3. **Container semantics:** the submodel's id, idShort and semanticId come from you.
4. **References from items:** `{"template", "inspireId"}` resolves as in R5.
5. **References to items:** not built. Each item carries its `inspireId`, which is the stable key, as you suggested. Two items with the same inspireId are rejected.
6. **Unique file names:** see §3, D1.
7. **Return value:** the same `SubmodelResult` as R6.

---

## 3. Defects

**D1: file names.** Files are now stored as

```
/aasx/files/<localId>_<8 hex of SHA-1(object key)>/<element path><suffix>
e.g. /aasx/files/DENWAT011rs0002A_soil0_1a2b3c4d/geometry.geojson
```

This holds for inline values and for files given by path. The folder is unique per object, also across separate `build_submodel` calls that you merge into one package. If a name would be used twice in one package, the builder raises an error instead of overwriting. Content types of supplementary files now follow the extension (`.geojson` → `application/geo+json`, `.json`, `.gml`, `.pdf`, …); before, they were always `application/geo+json`.

**D2: part name.** BaSyx writes XML unless it is asked for JSON; we had named the part `data.json` since E04. The part is now `/aasx/data.xml`, in `write_aasx` and in the template build. If you keep AASX files produced before `E06`, they still read with BaSyx, which goes by the content type.

---

## 4. Things your data will hit

1. **`observationDate: "2023-07-09"` is rejected.** INSPIRE types `LandCoverObservation.observationDate` as DateTime, so the value must be an `xs:dateTime`, e.g. `"2023-07-09T00:00:00Z"`. The appendix value fails AAS verification. The builder now reports this with the item path:
   `LandCoverUnits[0]/landCoverObservation[0]/observationDate: '2023-07-09' is not a valid xs:dateTime`.
   All Property and Range values are now type-checked while filling, so such errors no longer appear only as verifier paths.
2. **The SoilBody geometry is `GM_MultiSurface`.** Clipped BK50 pieces may be Polygons or MultiPolygons. The converter does not check geometry types, so whether you wrap Polygons as MultiPolygon is your decision.
3. **`SoilBody.inspireId` is optional in INSPIRE** ([0..1]), but the builder requires it, because ids and file folders are derived from it. Your items already have one.
4. **Changed file paths:** packages built before this change have other file paths. Rebuild them if anything refers to those paths.

---

## 5. How to update

```
git pull
set PYTHONPATH=src
.venv\Scripts\python -m inspire2aas.build "Existing Land Use" "Land Use Nomenclature" LandCoverVector LandCoverNomenclature Soil --name ecotwin_themes
.venv\Scripts\python -m pytest tests       # 31 passed expected
```

The template sets did not change in content; only their AASX part name changed.
