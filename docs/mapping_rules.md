# Mapping rules INSPIRE UML → AAS v3.1 (version v0, 2026-10-26)

Implemented in [src/inspire2aas/mapper.py](../src/inspire2aas/mapper.py) (templates) and [src/inspire2aas/instance.py](../src/inspire2aas/instance.py) (instances). Each rule is either taken from an experiment (E01–E03) or is a decision; where it is a decision, that is said. Everything that is not a 1:1 translation is written to `loss_ledger.csv` in each build.

## Decisions (researcher, 2026-10-26)

| # | Decision |
|---|---|
| D1 | Codelists: when the UML and the Registry disagree, the **INSPIRE Registry is authoritative**, and every disagreement is recorded in the loss ledger. |
| D2 | Identifiers we mint ourselves use the placeholder `https://example.org/inspire-aas/` (one setting: `config.BASE_URI`). |
| D3 | Target: **AAS v3.1** (aas-core3.1 1.0.0; no Python library for v3.2 exists). idShorts are kept valid for v3.0 too (no hyphens). |
| D4 | The geometry CRS policy is deferred. Geometry is stored as a GeoJSON file as given; the CRS is not checked. |

## Structure

| INSPIRE / UML | AAS | Notes |
|---|---|---|
| Application schema (e.g. CadastralParcels 4.0) | part of the ids: `…/smt/cp/4.0/…`; `administration.version=4`, `revision=0` | AAS 3.1 allows numeric versions only. A patch level (4.0.**2**) is dropped and logged. |
| concrete «featureType» | **Submodel**, `kind=Template`, idShort = class name | `semanticId` = the Registry feature concept, e.g. `http://inspire.ec.europa.eu/featureconcept/CadastralParcel`. Display names come from the Registry (en, de). |
| abstract «featureType» | no template of its own | Its properties are **flattened** into each concrete subtype. |
| inheritance | flattened: root-first, a subclass redefinition wins | Lineage is kept implicitly through the property ConceptDescription ids (they name the *defining* class). |
| «dataType», «type» (INSPIRE) | **SubmodelElementCollection** with the flattened properties | Unrolled up to depth 4; cycles are cut to an `xs:string` placeholder (logged). `supplementalSemanticId` = the data type's CD. |
| «union» | SubmodelElementCollection; all children `ZeroToOne`; qualifier `INSPIRE/union` | The "exactly one" rule can't be expressed in AAS: it is enforced by the instance builder and logged. |
| «featureType» as property type / association role | **ReferenceElement**; qualifier `INSPIRE/referenceTarget` = target feature concept | In instances: a ModelReference to the target's Submodel. |
| «codeList» / «enumeration» | Property `xs:string` + `supplementalSemanticId` = Registry scheme URI | See Codelists. |
| ISO types outside the INSPIRE schemas (EX_Extent, CI_Citation, …) | Property `xs:string` placeholder | Logged as `type-placeholder`. Not needed for CP/AU. |

## Simple types

| UML type | AAS |
|---|---|
| CharacterString, GenericName, … | Property `xs:string` |
| Boolean / Integer / Real / Decimal, Number | `xs:boolean` / `xs:integer` / `xs:double` / `xs:decimal` |
| Date / DateTime / URI | `xs:date` / `xs:dateTime` / `xs:anyURI` |
| Measure, Length, Area, … | Property `xs:double`. **The unit is not fixed** (left to the instance; logged). The CD has no IEC dataType, so AASc-3a-009 is not violated. |
| LocalisedCharacterString, PT_FreeText | MultiLanguageProperty |
| GM_*, TP_* (geometry) | **File** `contentType=application/geo+json`; qualifier `INSPIRE/geometryType` = the UML type (e.g. GM_MultiSurface) |

## Multiplicity, voidable, life-cycle

| UML | AAS template | AAS instance |
|---|---|---|
| [1] / [0..1] / [0..*] / [1..*] | qualifier `SMT/Cardinality` = One / ZeroToOne / ZeroToMany / OneToMany (TemplateQualifier) | removed |
| upper bound > 1 | **SubmodelElementList** containing one template item (no idShort, AASd-120) | one item per value |
| other bounds, e.g. [1..6], [1..2] | approximated (OneToMany) and logged | not checked |
| «voidable» | qualifier `INSPIRE/voidable=true` | value `{"nilReason": "unknown\|unpopulated\|withheld"}` → element without a value plus ValueQualifier `INSPIRE/nilReason` |
| «lifeCycleInfo» | qualifier `INSPIRE/lifeCycleInfo=true` | removed |
| OCL constraints | **not translated**, logged (`ocl-constraint-not-translated`) | not checked |

**To verify:** the qualifier name `SMT/Cardinality` and its values follow common IDTA practice (IDTA-01004 Submodel Template specification). That document isn't in `data/aas/`.

## Codelists (E03)

- The Registry (version `20260826-0`) supplies values, labels (en, de) and extensibility.
- The UML's `any` = the Registry's `open` (E03 C1).
- ConceptDescription id = the Registry scheme URI. The CD description states the extensibility and the number of valid values.
- **Closed lists** (Registry `none`): an IEC 61360 `valueList` with code + valueId (the Registry value URI), both in the codelist CD and in the property CD. The instance builder rejects codes that are not in the list.
- **Open/narrower/any lists:** no valueList. The instance builder sets valueId = `<scheme URI>/<code>`.

## Identifiers

| Thing | id |
|---|---|
| Submodel Template | `{BASE}smt/{prefix}/{schemaVersion}/{Class}` |
| ConceptDescription, feature type | Registry feature concept URI |
| ConceptDescription, property | `{BASE}cd/{prefix}/{schemaVersion}/{DefiningClass}/{property}` |
| ConceptDescription, codelist | Registry scheme URI |
| Submodel instance | `{BASE}sm/{prefix}/{Class}/{namespace}_{localId}` |
| AAS (instance) | `{BASE}aas/{prefix}/{namespace}_{localId}`; asset `{BASE}asset/…`; `specificAssetIds`: inspireId, nationalCadastralReference |
