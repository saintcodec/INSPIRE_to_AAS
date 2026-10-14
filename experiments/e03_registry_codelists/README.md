# E03: Codelists, UML model (XMI) vs INSPIRE Registry

- **Date:** 2026-10-14
- **Question:** Does the INSPIRE Registry fill the codelist gaps found in E01 (missing values, missing extensibility)? Do the UML and the Registry agree?
- **Status:** done (first pass).

## Inputs

Registry dump downloaded manually into `data/raw/INSPIRE Registry/` (git-ignored). It has 14 registers, each in 2 RDF variants: plain, and `-skos-ap-eu` (the EU Vocabularies profile with SKOS-XL labels; same content counts). This experiment uses the plain variant.

| File | SHA-256 | Registry version |
|---|---|---|
| `inspire-codelist.rdf` | `629d3a102953f03fed9cea43e0a9107248255e739ee84854f7bac3b54e85d7a2` | `20260826-0` (issued 2026-08-26) |
| `inspire-enumeration.rdf` | `392a265bbf4565eef82b9df2fcd7d72d6b2cc6d3b95805ee71e0811933448158` | `20260826-0` |
| `inspire-extensibility.rdf` | `de2b341c5b6c0e9d3618a79ae1d9c0215aa0f464e6ed7c1f0b0709f38423297c` | |

The UML (XMI) is the same file as in E01, dated 2025-01-31. **The Registry snapshot is about 19 months newer than the UML.**

## Method

[compare_registry.py](compare_registry.py) matches each of the **362** «codeList»/«enumeration» classes in the XMI application schemas to a Registry scheme, first by the UML `vocabulary` tag, then by name. It compares:
1. extensibility, after resolving the vocabulary difference (C1)
2. values held in the UML vs valid values in the Registry
3. for the 5 test themes: mapping-table (xls) labels vs Registry labels and codes

Results: [results/summary.txt](results/summary.txt), [results/codelists_xmi_vs_registry.csv](results/codelists_xmi_vs_registry.csv), [results/xls_labels_vs_registry.csv](results/xls_labels_vs_registry.csv), [results/registry_schemes_unused.csv](results/registry_schemes_unused.csv).

Reproduce: `cd experiments/e03_registry_codelists; python compare_registry.py`

## Findings

| # | Finding | Evidence | Consequence |
|---|---|---|---|
| C1 | **The same words mean different things.** In the UML tag, `any` means "may be extended by additional terms on any level". In the Registry, `any` is labelled "Empty code list" ("No values are specified … allowed values comprise any values defined by data providers"), and the UML's meaning is called `open` ("extended with additional values at any level"). | tag notes in the XMI; `inspire-extensibility.rdf` | A naive string comparison or mapping is **wrong**. The converter maps both sources to one common vocabulary: closed / narrower / extensible / empty(extensible). |
| C2 | Registry content: 349 schemes (332 codelists, 17 enumerations), 8,200 values. Value status: 8,080 valid, 24 invalid, 17 superseded, 9 retired. | summary | Only use `valid` values; keep the others for documentation. |
| C3 | **Matching:** 287 of 362 UML codelists have a Registry entry (74 via the vocabulary tag, 213 by name). Of the 75 without one, 64 are in the 16 foundation schemas (GeoSciML, EarthResourceML, WaterML…). The others: HumanHealth 5, Telecommunications 2, Base Types 2 (`ApplicationSchemaValue`, `ThemeValue`) 2, LandCoverNomenclature `CorineValue` 1. | codelists_xmi_vs_registry.csv | Foundation-schema codelists need other sources (e.g. CGI vocabularies), or are out of scope. |
| C4 | **Broken vocabulary links in the UML:** 119 `vocabulary` tags use `…/codeList/…` (capital L). URIs are case-sensitive, so these don't resolve to Registry schemes. 137 tags in total are not Registry scheme URIs; the rest are external vocabularies (EIONET, NERC, EEA CORINE). | vocabulary tag analysis | Match by name as a fallback, and log it. Don't trust the tag blindly. |
| C5 | **Extensibility, UML vs Registry:** 173 agree, **77 conflict**, 37 are missing in the UML (the Registry gives: none 33, open 2, any 2), 75 have no Registry entry. The conflicts (UML → Registry): extensible → closed 44×, closed → empty 17×, closed → open 5×, narrower → closed 5×, extensible → narrower 4×, narrower → open 1×, one with no Registry value. | summary | **A decision is needed** about which source is authoritative. Recommendation: the Registry (it is newer and is the legal reference for values), with the conflict recorded in the SMT. |
| C6 | **The Registry contradicts itself:** 37 schemes are marked `any` ("empty code list") but contain valid values, e.g. `MediaValue`, `ProcessTypeValue`, `VerticalReferenceValue`. | summary | Treat Registry `any` + values as "extensible, with suggested values". |
| C7 | **Values:** where the UML holds values (118 lists), 99 are identical to the Registry and 19 differ, e.g. Road `FormOfWayValue` (UML 15 / Registry 12), `RestrictionTypeValue` (7/10), `NaturalVegetationClassificationValue` (19/0). `CountryCode`: 29 values in the UML, 0 in the Registry codelist register. | value check | The Registry is the source for values. The UML values are only a cross-check. Country codes must come from elsewhere (EU Publications Office authority table). |
| C8 | 62 Registry schemes are not referenced by any UML codelist in the approved model, e.g. abstract codelists, draft/TG-only extensions and retired schemes. | registry_schemes_unused.csv | Not needed for the IR-only model. |

## Test themes

| Theme | Codelist | UML ext. | Registry ext. | UML values | Registry values |
|---|---|---|---|---|---|
| AU | AdministrativeHierarchyLevel | — (missing) | none | 6 | 6 ✅ |
| AU | LegalStatusValue | any (= extensible) | **none** ⚠️ | 2 | 2 ✅ |
| AU | TechnicalStatusValue | any (= extensible) | **none** ⚠️ | 2 | 2 ✅ |
| CP | CadastralZoningLevelValue | — (missing) | none | 3 | 3 ✅ |
| SO | 11 closed lists (FAO*, WRB*, LayerType, SoilPlotType…) | none | none ✅ | **0** | 2–179 |
| SO | 4 `*ParameterNameValue` lists | any (= extensible) | **narrower** ⚠️ | 0 | 7–136 |
| SO | OtherSoilNameTypeValue, OtherHorizonNotationTypeValue | any | any (empty) ✅ | 0 | 0 |
| ELU | HILUCSValue (Land Use Nomenclature) | none | none ✅ | 0 | 98 |
| ELU | LandUseClassificationValue | any | any (empty) ✅ | 0 | 0 |
| LCV | LandCoverClassValue (LandCoverNomenclature) | any | any (empty) ✅ | 0 | 0 |

- **Every mapping-table label (41/41)** in the test themes matches a Registry value, by label or code. This confirms E01 M5: the xls holds labels, and the codes come from the Registry.
- ELU and LCV define no codelists themselves. They use the Nomenclature schemas.
- `LandCoverClassValue` and `LandUseClassificationValue` are deliberately empty: the data provider defines the classes. This is where national classifications (ATKIS, LB-NRW, …) come in.

## Report claims checked

| Claim in first_reaserch.md | Result |
|---|---|
| Codelist values must come from the Registry and are not in the UML | ✅ e.g. Soil: 0 values in the UML, 2–179 per list in the Registry |
| Registry URIs `http://inspire.ec.europa.eu/codelist/<List>/<value>` usable as valueIds | ✅ the URI pattern is confirmed in the dump |
| Registry migrated to EU Vocabularies | ✅ the dump has the EU Vocabularies profile (`-skos-ap-eu`), version 2026-08-26 |
| Embed valueList only for `extensibility=none`; never for open/any | ⚠️ the right idea, but **"open/any" means different things in the UML and the Registry** (C1), and the two sources disagree for 77 lists (C5). |

## Open / next

1. **Decision (researcher):** which source wins on extensibility conflicts, the Registry or the UML? (C5)
2. Multilingual labels: the Registry has up to 24 languages per value. Do we put them into AAS MultiLanguageProperty / ConceptDescription definitions?
3. Hierarchical codelists (`broader`, e.g. HILUCS levels; `narrower` extensibility) need a representation in AAS.
