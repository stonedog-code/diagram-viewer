# diagram-viewer

FastAPI serving the Mermaid diagrams in `diagrams/` — an index plus a page per
`.mer` file, rendered client-side. Run it with `bash run.sh` (:8000); the gate
is `bash run.sh test`. Details in `README.md`.

## ⚠️ WHILE THE `nehsa-net` ACCOUNT IS BILLING-LOCKED (since 2026-08-20)

**This section is carried by every `nehsa-net` repo and must be deleted from all
of them the day the lock is lifted.** It is not specific to this repo; it is
specific to the outage.

**Every workflow run in this org currently fails without starting.** The account
is locked for billing, so GitHub refuses to allocate a runner — on public repos
as well as private ones, because being unmetered buys nothing when the account
cannot start jobs at all.

### 1. Prove it is the lock before you believe any red check

Two calls. Do not skip them and do not assume — a genuinely broken branch looks
identical in the PR list:

```bash
gh api repos/nehsa-net/diagram-viewer/actions/runs/<run-id>/jobs \
  -q '.jobs[] | "\(.name): conclusion=\(.conclusion) runner=\"\(.runner_name)\" steps=\(.steps|length)"'

JOB=$(gh api repos/nehsa-net/diagram-viewer/actions/runs/<run-id>/jobs -q '.jobs[0].id')
gh api repos/nehsa-net/diagram-viewer/check-runs/$JOB/annotations -q '.[].message'
```

`runner=""` with `steps=0` means nothing executed and the red says nothing about
your branch. The annotation, when present, says so in words: *"The job was not
started because your account is locked due to a billing issue."*

**A runner id plus executed steps means the failure is real — fix your branch.**
So does `startup_failure`: that is the workflow file being invalid or its
triggers not matching, which is your problem and not the account's.

### 2. Do not "fix" CI

Disabling the workflow, deleting it, removing a required context from branch
protection, or re-running the job all leave the repo worse off and none of them
start a runner. The gate is correct; it is the account that is blocked. Branch
protection stays exactly as it is.

### 3. Gate locally, with the same command CI would run

```bash
bash run.sh test        # 29 tests — unit + integration
```

That is what `.github/workflows/ci.yml` runs, verbatim. It needs `uv`, which
fetches its own Python from `.python-version`.

It must find every tool it needs. A missing interpreter is a **failure**, not a
skip — otherwise the run quietly halves its coverage and still prints OK. No
toolchain on the box? Then you have not gated it, and you say that instead.

### 4. Say it in the PR (or the commit), with counts and with what you did NOT run

Post the job-query output, the local counts, and the tools' versions. Name what
the local run does not cover. *"I gated locally"* with no numbers is not
evidence; a reader cannot tell it from *"it looked fine"*.

### 5. Then merge, and label what you bypassed

```bash
gh pr merge <n> --squash --delete-branch --admin --repo nehsa-net/diagram-viewer
```

`--admin` is for a required check that could not run; it exists for exactly this
situation. Every admin-merge gets a sentence saying it was one, what passed
locally, and that the required check never ran. An unexplained bypass is
indistinguishable from carelessness.

### 6. Re-check the lock each session — one call

The workaround expires the moment billing is fixed, and nobody will announce it.
If a run allocates a runner, **stop using this section and delete it from every
repo that carries it.** A team taught to discount red checks, who then get
working CI without being told, is worse off than one that never had a
workaround.

### 7. What this cannot catch, and what to do the day it lifts

A local gate proves the code works on **this** machine with **these** tools. It
does not prove the workflow file is valid, that CI's runner image has what the
job assumes, or that a step nobody has run since the outage still works. So when
runners return: push to `main`, watch the first real run, and treat anything
merged during the outage as unverified until it is green.

**The billing fix itself is not code work and no agent should attempt it** — it
is a vendor console and a payment method. Report the lock, work under this
section, and leave the fix to the owner.
