# Claim states

These are scoped classifications, not one linear ladder. A finite certificate,
a conjecture, and a restricted proof describe different claim types. Changing
the domain or quantifiers creates a new claim ID; it does not promote the old
claim by analogy. A claim may be demoted immediately, while every stronger
classification requires its stated gate.

| State | Meaning | Minimum promotion gate |
| --- | --- | --- |
| `observation` | Pattern, analogy, visualization, or question | Reproducible description with scope |
| `reproduced` | A prior finite result was independently rerun in the declared environment | Matching output plus pinned inputs and code |
| `certified_finite` | An exact claim over an explicitly finite domain | Deterministic exhaustive checker or complete certificate |
| `conjectured` | A precise statement offered for attack | Definitions, quantifiers, dependencies, and counterexample conditions |
| `proved_restricted` | A proof over a named strict subdomain or model | Complete auditable argument or kernel check; restriction prominent |
| `proof_candidate` | A claimed full argument for the exact official target | Every step supplied; all dependencies disclosed; no known gap or unresolved proof obligation |
| `externally_established` | A result accepted outside this project | Identified publication and competent independent acceptance evidence |

`proof_candidate` is the highest state this project may assign to its own full
argument. `externally_established` is evidence-bound and cannot be
self-awarded.

External status is tracked separately. Publication in a claimed qualifying
outlet, passage of two years, and evidence of general acceptance are recorded
as separate conditions. Only CMI can determine eligibility, open detailed
consideration, and award a prize. Suggested status names are
`none`, `eligibility_conditions_claimed`, `eligible_for_CMI_consideration`,
`CMI_detailed_review`, and `CMI_prize_awarded`.

No internal score, seal, benchmark, vote among related agents, or passage of
time automatically establishes any external condition or advances CMI state.

## Scoring

A run scores when it leaves a reusable, checkable object:

- a smallest counterexample;
- an exact finite certificate;
- a restricted theorem with its restriction in the title;
- a dependency or quantifier audit;
- a falsified route with the failure condition preserved;
- an incomplete argument whose unresolved obligations are explicit, without
  calling it a proof candidate.

The score is informational. It is not probability that a Millennium problem
has been solved.
