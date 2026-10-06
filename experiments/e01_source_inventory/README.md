# E01: Source inventory of the INSPIRE UML model and mapping tables

- **Date:** 2026-10-06
- **Question:** What does the approved INSPIRE UML export actually contain, and can a converter rely on it? Which claims in [first_reaserch.md](../../first_reaserch.md) hold? Are the mapping tables usable?
- **Status:** done (first pass). Follow-ups are listed at the end.

## Inputs

Downloaded manually from INSPIRE-MIF/uml-models `approved/` into `data/raw/approved/` (git-ignored).

| File | Size | SHA-256 |
|---|---|---|
| `ea+xmi/EAXMI/INSPIRE_Consolidated_UML_Model_ANNEX I-II-III-Only_IR_2025.1.xml` | 42.1 MB | `ab29c368f69a0137cb1683b3ed7fea5d1c5ac618e0923252d50425a8dee13f98` |
| `ea+xmi/EAXMI/INSPIRE_Consolidated_UML_Model_ANNEX I-II-III-Only_IR_2025.1.EAP` | 53.0 MB | `17949f34e46727895c12bcfd2e3079fa680b2213b6fc355b5c776c353b58caeb` |
| `mapping/*.xls` | 40 workbooks | not hashed |

## Method

- [xmi_load.py](xmi_load.py): tolerant loader (see F1).
- [inventory.py](inventory.py): counts constructs per «applicationSchema» using EA's `xmi:Extension`. Writes [results/schemas.csv](results/schemas.csv) and [results/classes.csv](results/classes.csv).
- [compare_mapping.py](compare_mapping.py): for AU, CP, SO, LCV and ELU, flattens each concrete featureType/dataType from the XMI (own + inherited attributes + navigable roles) and compares name, multiplicity and voidable with the xls. Writes `results/mapping_vs_xmi_*.csv`.

Environment: Python 3.14.5, lxml 6.1.1, xlrd 2.0.2, pandas 3.0.5. No Java installed.

Reproduce: `cd experiments/e01_source_inventory; python inventory.py; python compare_mapping.py`

## Findings: XMI

| # | Finding | Evidence | Consequence |
|---|---|---|---|
| F1 | The file declares `encoding="windows-1252"` but contains byte `0x90`, which is undefined in cp1252. It is Shift-JIS residue (`設計中`) in a Note's `status`, line 167032. libxml2 aborts with a misleading "Growing input buffer" error, even with `huge_tree`. | 1 occurrence | Decode leniently (`errors="replace"`). It affects only Note metadata. |
| F2 | The format is **XMI 2.1 / UML 2.1**, EA exporter 6.5, one consolidated file. The report discussed XMI 1.x caveats, which don't apply. | file header | Parse directly with lxml. |
| F3 | **No standard UML stereotype applications.** Stereotypes and tagged values exist only in EA's proprietary `xmi:Extension` (`elements` 4218, `connectors` 4702). | top-level children | The parser is tied to the EA dialect. |
| F4 | When an element has several stereotypes, EA's `<stereotype>` element shows **only the first**. The full list is only in the `xrefs` string (`@STEREO;Name=…;`). Example: `beginLifespanVersion` is «voidable» + «lifeCycleInfo». | AU AdministrativeUnit | Parse `xrefs`, or voidability is lost. |
| F5 | Tag values carry an EA suffix `value#NOTES#<doc>`. | `extensibility` tags | Strip it. |
| F6 | Data quality: misspelled tag names (`extensiblity`, `extensibilty`, `inlinOrByReference`, `Obligation`), the stereotype spelled `code list` (with a space, 8×), and a «voidable» stereotype on a class (1×). | inventory output | Normalise names; log anomalies. |
| F7 | **91 «applicationSchema» packages**: 65 theme schemas + 10 Generic Conceptual Model schemas + 16 foundation schemas (GeoSciML, O&M, SWE, WaterML). | schemas.csv | Confirms the report's "~75" (65+10) for INSPIRE proper. Every schema has a version tag (AU 5.0, CP 4.0, SO 4.0.2, LCV 5.0, ELU 4.0). |
| F8 | Totals over the 91 schemas: 405 featureType, 178 dataType, 65 «type», 21 union, 3 enumeration, 358 codelist, 85 abstract, 6 association classes, 2778 attributes (including codelist values held as attributes), 705 voidable attributes, 158 voidable association ends, 259 constraints. | inventory output | This is the baseline for coverage metrics. |
| F9 | **107 of 358 codelists in the application schemas have no `extensibility` tag**, among them CP `CadastralZoningLevelValue` and AU `AdministrativeHierarchyLevel`. The rest: any 169, none 69, narrower 12, open 1. | inventory output | The codelist policy needs a default, or the Registry's extensibility register. |
| F10 | 115 `uml:Class` elements are not classes: 110 are EA *Boundary* and 5 are *Text* diagram elements (e.g. "Data Types - Soil coverages"). | EA `sType` | Filter on `sType == "Class"`. |
| F11 | Type references: many point to `EAJava_<Name>` / `EAnone_<Name>`, i.e. **by name**, not by ID. Over the whole model, 852 references resolve neither by ID nor by unique name (generics such as `Sequence_Number_`, missing ISO types such as `GM_Geometry` and `MD_Scope`). In the 5 test themes, **100% resolve** (156 by ID, 18 by unique name). The one exception is **Soil `ParticleSizeFractionType.fractionParticleSizeRange`, which has no type**. | type resolution | Resolve by ID, then fall back to name, and record failures in the loss ledger. |
| F12 | Codelist values are **mostly absent** from the UML. Example: all 17 Soil codelists have 0 values. AU and CP do list theirs (`1stOrder`…). | classes.csv | The Registry is required for values (as the report said). |

## Findings: Mapping tables (xls)

These are data-provider "matching tables". The left half is INSPIRE, already **flattened** (inherited properties are suffixed `- <SuperType>`). The right half is an empty template for the provider's own model.

| # | Finding | Evidence |
|---|---|---|
| M1 | Flattened attributes agree with the XMI on name and multiplicity for **all** compared attributes (AU 25, CP 38, SO 98, LCV 18, ELU 18). | mapping_vs_xmi_*.csv |
| M2 | The voidable column holds **one** value. Lifespan attributes («voidable»+«lifeCycleInfo») are written as `voidable` in AU but `lifeCycleInfo` in CP, SO and ELU, so the tables are internally inconsistent. All 26 "VOID_DIFF" are this case. | same |
| M3 | **18 association roles are missing** from the xls, e.g. AU `lowerLevelUnit`, `administeredBy`, `condominium`, `coAdminister`; SO `isDescribedBy`, `soilSiteObservation`; ELU `dataset`. | same |
| M4 | Names are de-camelCased ("W R B Qualifier Group"), and multiplicities are mangled by Excel (`1.0`, `0...1`). | raw sheets |
| M5 | Codelist sheets give **labels, not codes** ("trial pit", "not Agreed"). They cover only part of the lists: SO 5 of 17 have values, and WRB/FAO lists are empty or absent. | codelist comparison |
| M6 | Workbooks include objects from other schemas, e.g. AU contains MaritimeUnits and Hydro types (Shoreline, Sea Area), plus generic lists (CountryCode, CharacterSetCode). | sheet contents |

**Verdict:** the xls is not usable as a primary source because it is lossy and incomplete for associations. It is useful as (a) an independent **oracle for the flattening rule** for attributes (M1), and (b) a **layout template** for the later national mapping (ATKIS/ALKIS → INSPIRE → AAS).

## Report claims checked

| Claim in first_reaserch.md | Result |
|---|---|
| ~75 application schemas | ✅ 65 themes + 10 GCM = 75. The file has 91 including foundation schemas. |
| Release v2025.1 is the latest | ⚠️ The file is v2025.1. Whether a newer release exists has **not been checked**. |
| The XMI keeps stereotypes, voidable, association classes and constraints | ✅ but only in the EA extension (F3–F5) |
| XMI 1.x caveats (default 0..* multiplicities) | ❌ not applicable, the file is XMI 2.1 (F2) |
| AU: 3 feature types; 3 OCL constraints incl. the `AdmininstrativeUnitHighestLevel` typo | ✅ |
| AU: no unions or enumerations; codelists LegalStatus/TechnicalStatus/AdministrativeHierarchyLevel | ✅ (CountryCode is defined elsewhere) |
| CP: 4 feature types | ✅ |
| SO: 12 feature types, association class DerivedProfilePresenceInSoilBody, `isDescribedBy` voidable 1..* | ✅ |
| LCV 2 / ELU 2 feature types | ✅ |
| LandCoverObservation data type "not verified in FC" | ✅ exists in LCV (dataType, 3 attributes) |
| Few enumerations remain after v2024.1 | ✅ 3 in the application schemas |
| ShapeChange → SCXML as ingest | ⏳ untested; needs Java. Direct XMI parsing works for the test themes. |

## Open / next

1. Decide on the ingest path: direct XMI parsing (working now, EA-dialect-specific) vs ShapeChange (needs Java; can it read this XMI 2.1 or only the EAP?).
2. Get codelist values and extensibility from the INSPIRE Registry (EU Vocabularies), and check whether `.json`/`.rdf` still resolve.
3. Check for a UML release newer than 2025.1.
4. Bring association-class and union handling into the comparison (not covered by E01).
