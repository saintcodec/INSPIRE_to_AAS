# Build report: cp_au

- date: 2026-11-14
- schemas: CadastralParcels 4.0, AdministrativeUnits 5.0
- INSPIRE UML: INSPIRE_Consolidated_UML_Model_ANNEX I-II-III-Only_IR_2025.1.xml
- INSPIRE Registry version: 20260826-0
- Submodel Templates: 7 (AdministrativeBoundary, AdministrativeUnit, Condominium, BasicPropertyUnit, CadastralBoundary, CadastralParcel, CadastralZoning)
- ConceptDescriptions: 114
- aas-core3.1 verification: **PASSED (0 errors)**
- AASX written; BaSyx re-read 122 identifiables without error.

## Loss ledger (not translated 1:1)

| kind | count |
|---|---|
| ocl-constraint-not-translated | 17 |
| codelist-extensibility-conflict | 14 |
| geometry-as-geojson | 9 |
| measure-unit-not-fixed | 4 |
| codelist-extensibility-missing-in-uml | 3 |
| multiplicity-approximated | 2 |
