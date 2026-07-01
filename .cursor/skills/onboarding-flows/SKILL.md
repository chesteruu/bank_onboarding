---
name: onboarding-flows
description: >-
  Create or modify onboarding shell flows, component sub-flows, forms, and
  decision rules for the bank_onboarding repo. Use when adding a country,
  market, shell step, component YAML, integration step, or changing flow order.
---

# Onboarding flows — agent rulebook

You are editing an **event-driven**, **two-level YAML** onboarding system. Follow these rules exactly. When unsure, read `docs/FLOWS_GUIDE.md` and `docs/ARCHITECTURE.md`.

## Architecture constraints (never break)

1. **Shell vs component separation**
   - Shell (`flows/{cc}_{type}.yaml`): step order, titles, `form_schema`, `orchestrator`, `component_flow`, `on_complete`.
   - Component (`flows/components/...`): `internal_steps`, `integrations`, `optional`.
   - **Never** put `integrations` on shell steps.

2. **Coordinator owns shell pointer**
   - Only `FlowCoordinatorHandler` updates `onboarding_applications.current_step_key`.
   - Do not advance steps in services, routes, or custom orchestrator Python.

3. **Use YamlComponentOrchestrator**
   - Do not create new orchestrator Python classes unless YAML cannot express the behaviour.
   - New orchestrator **ids** must be registered in `src/onboarding/flow/orchestrators/registry.py` `register_defaults()`.

4. **Event-driven path is default**
   - `Settings.event_driven_enabled = True`. Do not reintroduce synchronous integration calls in routes.

5. **Integration keys are closed set**
   - Only use keys from `INTEGRATION_MAP` in `src/onboarding/integrations/gateway.py`.
   - New keys require gateway + mock client + map entry.

6. **Do not edit**
   - Plan files in `.cursor/plans/`
   - Unrelated refactors, formatting sweeps, or legacy `OnboardingService` unless explicitly requested

## Before you change anything

1. Identify **scope**: new country | new shell step | component-only change | new integration key | form change.
2. Find the **closest existing market** and copy its pattern.
3. List files you will touch (checklist at end).

## Shell YAML template

```yaml
flow_id: {cc}_{type}          # must match filename without .yaml
country: {CC}                 # Country enum value
account_type: private|business
steps:
  - key: {step_key}
    title: "Human title"
    orchestrator: {registry_id}
    component_flow: components/{orchestrator}/{variant}.yaml
    form_schema: {PydanticClassName}   # omit if no form (e.g. credit_decision)
    on_complete: {next_step_key}
  - key: review
    orchestrator: review
    component_flow: components/review/default.yaml
    form_schema: ReviewStep
    is_review: true
    on_complete: decision
  - key: decision
    orchestrator: decision
    component_flow: components/decision/default.yaml
    triggers_decision: true
```

Private markets typically: `identity → contact → consent → financial → credit_decision → review → decision`.

## Component YAML template

```yaml
component_id: {unique_id}
orchestrator: {same_as_shell_orchestrator}
internal_steps:
  - key: {internal_key}
    title: "Optional title for segment UI"
    integrations: [{valid_integration_key}]   # optional
    optional: false                             # true to allow skip
  - key: complete                             # terminal step — always last
```

Rules:

- Last internal step should be `complete` (or orchestrator treats end of list as complete).
- `orchestrator` field must match shell step's `orchestrator`.
- `component_id` should be unique and descriptive.

## Registered orchestrator ids

```
identity, contact, compliance, affordability_input, credit, kyb, review, decision,
financial, company, signatory, representative, board, ubo, bank
```

## Valid integration keys

```
bankid_identity, dni_nie_check, pesel_eid_check, address_lookup,
bolagsverket_registry, registro_mercantil, ceidg_krs_registry,
signatory_check, ubo_kyc, sanctions_screen, credit_bureau, bik_credit,
affordability, kyb_check, iban_verify, bank_verify
```

## Adding a form step

1. Pydantic model in `src/onboarding/web/forms.py`
2. Register in `FORM_SCHEMAS` dict
3. Template partial in `templates/partials/forms/`
4. Branch in `templates/step.html` on `step.form_schema`
5. Reference `form_schema` on shell step (not component, unless component adds `form_schema` on internal step — rare)

Identity steps must expose `national_id`, `pesel`, or `dni` for duplicate detection (or extend `command_service._extract_identifier_hash`).

## Adding a new country

1. `Country` enum in `src/onboarding/domain/enums.py`
2. Shell YAML `flows/{cc}_{type}.yaml`
3. Component YAMLs for market-specific steps
4. Form schemas + templates for local identity/company fields
5. Decision rules `src/onboarding/decision/rules/{flow_id}.yaml`
6. `Settings.available_flows` in `config.py`
7. Tests in `tests/unit/test_flow_engine.py` (step list)

## Adding a shell step only

1. Create component YAML if new capability
2. Insert shell step with `on_complete` rewired on previous step
3. Add form wiring if applicant input required
4. Do **not** modify other markets' shell files unless requested

## Changing integrations only

Edit **only** the component YAML under `flows/components/{orchestrator}/`. Do not touch shell YAML.

## Decision rules

File: `src/onboarding/decision/rules/{flow_id}.yaml`

```yaml
flow_id: {flow_id}
critical_checks: [identity, address, sanctions, credit, affordability]
min_credit_score: 550
```

`flow_id` must match shell. `critical_checks` use `IntegrationCheckType` values.

## Tests to run

```bash
pytest tests/unit/test_flow_engine.py -q
pytest -m "not postgres" -q
# If Docker available:
pytest -m postgres -q
```

Add parametrize case when shell step list changes.

## Output format for the user

When completing a flow change, report:

1. **Scope** — what was added/changed
2. **Files touched** — bullet list
3. **Shell step order** — for affected flow
4. **Reuse** — which components were shared vs new
5. **Manual test** — country, account type, happy-path identifiers
6. **Test commands** — what you ran and results

## Validation checklist (agent must verify)

- [ ] Shell file at `flows/*.yaml` top level (not nested)
- [ ] `flow_id` matches filename
- [ ] Every shell step has `orchestrator`, `component_flow`, `on_complete` (except terminal)
- [ ] Component paths exist
- [ ] `orchestrator` matches between shell and component
- [ ] No shell-level `integrations`
- [ ] Integration keys valid
- [ ] Form schema registered + template wired (if form step)
- [ ] Decision rules exist for flow
- [ ] Country in enum + `i18n/markets.yaml` entry (if new country)
- [ ] Translation bundle for new market (if new country)
- [ ] Tests updated/passing

## Internationalization

| File | Purpose |
|------|---------|
| `i18n/markets.yaml` | Per-country locale, bundle, enabled account types |
| `i18n/bundles/en.yaml` | Default strings (pre-country pages) |
| `i18n/bundles/{CC}.yaml` | Country-specific UI copy |

Templates use `{{ t('key.path') }}`. Do not hardcode applicant-facing strings in HTML.

## Common mistakes to reject

| Mistake | Fix |
|---------|-----|
| Monolithic flow with integrations on shell | Move integrations to component YAML |
| `component_flow: identity/se_private.yaml` | Path must be `components/identity/se_private.yaml` |
| Missing `on_complete` | Chain steps explicitly |
| New orchestrator id not in registry | Add to `register_defaults()` |
| Editing all 6 shells to add one country's feature | Scope to target market only |
| Custom step advancement in routes | Use existing submit → event → coordinator path |

## Reference files

| Purpose | Path |
|---------|------|
| Example private shell | `flows/se_private.yaml` |
| Example business shell | `flows/es_business.yaml` |
| Example component | `flows/components/credit/se_private.yaml` |
| Coordinator | `src/onboarding/events/handlers/coordinator.py` |
| Registry | `src/onboarding/flow/orchestrators/registry.py` |
| Integration map | `src/onboarding/integrations/gateway.py` |
| Forms | `src/onboarding/web/forms.py` |
| Market i18n | `i18n/markets.yaml`, `i18n/bundles/` |
| Full human guide | `docs/FLOWS_GUIDE.md` |
| Architecture + swimlanes | `docs/ARCHITECTURE.md` |
| AWS migration | `docs/AWS_MIGRATION.md` |
