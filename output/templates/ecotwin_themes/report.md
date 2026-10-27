# Build report: ecotwin_themes

- date: 2026-10-27
- schemas: Existing Land Use 4.0, Land Use Nomenclature 4.0, LandCoverVector 5.0, LandCoverNomenclature 4.0, Soil 4.0.2
- INSPIRE UML: INSPIRE_Consolidated_UML_Model_ANNEX I-II-III-Only_IR_2025.1.xml
- INSPIRE Registry version: 20260826-0
- Submodel Templates: 14 (ExistingLandUseDataSet, ExistingLandUseObject, LandCoverDataset, LandCoverUnit, DerivedSoilProfile, ObservedSoilProfile, SoilBody, SoilDerivedObject, SoilHorizon, SoilLayer, SoilPlot, SoilSite, SoilThemeCoverage, SoilThemeDescriptiveCoverage)
- ConceptDescriptions: 262
- aas-core3.1 verification: **PASSED (0 errors)**
- AASX written; BaSyx re-read 277 identifiables without error.

## Loss ledger (not translated 1:1)

| kind | count |
|---|---|
| type-placeholder | 23 |
| ocl-constraint-not-translated | 10 |
| schema-version-patch-dropped | 10 |
| datatype-recursion-cut | 7 |
| codelist-extensibility-conflict | 7 |
| geometry-as-geojson | 6 |
| observation-profile | 6 |
| definition-missing | 4 |
| union-xor-not-enforced | 4 |
| multiplicity-approximated | 2 |
| association-class-as-collection | 1 |
