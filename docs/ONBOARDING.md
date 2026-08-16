# Praman — Onboarding for the Next Engineer

**Goal:** Be productive by end of Day 1, without asking questions.

**Time:** ~4 hours (90 min reading, 90 min building)

---

## 30 Minutes: What This Is

Read `README.md` first. Then read these sections of `ARCHITECTURE.md`:
- Overview (the two-module diagram)
- Layered architecture (dependency rules)
- Module architecture (Module 1 + 2 concepts)

**After 30 min, you should be able to say:**
- What problem Praman solves
- Why logs are not evidence
- How Module 1 and Module 2 differ
- Why the layering matters

---

## 1 Hour: Run It

Clone the repo:

```bash
git clone https://github.com/YOUR_USERNAME/praman-evidence-engine.git
cd praman-evidence-engine
```

Set up the environment:

```bash
# Python 3.11+
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy .env.example to .env and fill it in
cp .env.example .env
# Edit .env: DATABASE_URL, OTEL_ENABLED, etc.
```

Start the backend locally:

```bash
uvicorn praman.main:app --reload
```

Visit: http://localhost:8000/health

You should see:
```json
{"status":"ok","version":"0.1.0"}
```

---

## 1 Hour: The Three Things Worth Understanding

**1. Why the ledger holds no personal data** — `praman/domain/canonical.py`

Read the module docstring and the `canonicalise()` function. It converts an event to deterministic JSON, but it never includes the data principal's name, email, or ID. Instead, it uses a hash of the principal ID. This resolves the DPDP §12 erasure paradox: the ledger can never be asked to erase because it never held identifying information.

**Action:** Find the line that hashes the principal ID. Write a one-sentence comment explaining why.

**2. Why tampering is detectable** — `praman/domain/merkle.py` and `tests/test_merkle.py`

Read the `compute_root()` function. It builds a tree where every leaf is an event's HMAC, and the root is the hash of all leaves. Change one event's HMAC by 1 bit, and the root changes completely.

Then read `test_tampering_changes_root()` in the test file. It proves the claim.

**Action:** Run the test locally:
```bash
pytest tests/test_merkle.py::test_tampering_changes_root -v
```

See it pass. This is the core property that makes the entire system work.

**3. Why the certificate matters** — `praman/adapters/certificate/reportlab_bsa63.py` and `docs/ARCHITECTURE.md` Module 1 event flow

A certificate is not just a PDF; it is a cryptographic claim that the system was operating properly on a specific date. Part A (description) says how the record was produced (hash value, algorithm). Part B (attestation) is signed by the customer's CTO, saying "yes, this system was operating properly."

Together, they satisfy BSA §63 requirements for admissibility.

**Action:** Generate a sample certificate:
```bash
python -c "from praman.adapters.certificate.reportlab_bsa63 import CertificateRenderer; cert = CertificateRenderer(); cert.render(root='abc123', algorithm='SHA-256', timestamp='2026-08-10T14:32:00Z')" > /tmp/cert.pdf
```

Open the PDF. Read Part A and Part B. Notice which parts are filled automatically (Part A) and which are templates (Part B).

---

## 30 Minutes: Make a Change

Add a new policy operator. Touch two files:

**1. `praman/adapters/policy/json_rules.py`**

Find the `evaluate()` function. It has a switch statement on `condition.operator`. Add a new case:

```python
case "greater_than_or_equal":
    return _operator_gte(condition.value, event_value)
```

Then define the function:

```python
def _operator_gte(threshold: float, actual: float) -> bool:
    """Greater than or equal comparison."""
    return actual >= threshold
```

**2. `tests/adapters/test_json_rules.py`**

Add a test:

```python
def test_greater_than_or_equal():
    """Policy allows action when value >= threshold."""
    policy = Policy(
        id="test_policy",
        rule={"operator": "greater_than_or_equal", "value": 100},
    )
    event = GovernedEvent(..., value=150)
    result = engine.evaluate(event, [policy])
    assert result.allowed is True
```

Run the test:
```bash
pytest tests/adapters/test_json_rules.py::test_greater_than_or_equal -v
```

**Action taken:** You added a new capability by changing two files, both small. No refactoring. No dependency updates. This is the shape of most changes in this codebase.

---

## 30 Minutes: Understand the Rules

Read `CLAUDE.md`. It is the engineering contract. Every line you write must follow it:

- [ ] Module docstring (purpose, responsibility, what it must not do)
- [ ] Function docstring (why it exists, args, returns, raises)
- [ ] Comments explain why, not what
- [ ] Functions ≤40 lines, files ≤400 lines, nesting ≤3 levels
- [ ] Full type hints
- [ ] Descriptive names (banned: `data`, `result`, `tmp`, `helper`, `utils.py`)
- [ ] Swappable concerns behind Strategy interfaces
- [ ] Dependency direction strictly inward

**Action:** Pick a file you just read. Check it against these rules. If it violates any, that is a bug — report it.

---

## What Is Deliberately Unfinished

Read `docs/LIMITATIONS.md`. Every stub is listed:
- Drift detection is deterministic (does not measure real drift)
- Timestamping is local-only (no independent time proof yet)
- Certificate Part B is a template (customer must legally review and sign)
- No audit logging (who accessed what, when)

**Action:** Do not ship any of these to production without reading the "Production approach" section and implementing the full version.

---

## Who To Ask

If the repo does not answer your question, that is a bug in the docs. File it.

- Architectural questions? Read `docs/ARCHITECTURE.md` and the relevant ADR (`docs/ADR/0001-*`)
- API questions? Check `api/` routers and their docstrings
- Cryptographic questions? Read `domain/` and the test that proves it
- Regulatory questions? Check `docs/commercial/` and the relevant Act/Section

---

## The First Pull Request

Your first PR should:

1. **Pick a small change.** Not a refactor. Not a new module.
2. **Follow CLAUDE.md exactly.** Every point.
3. **Update docs in the same commit.** If you change logic, update a docstring or an ADR.
4. **Include a test proving your claim.** If your change is to the policy engine, include a test showing it works.
5. **Check the architecture.** Run `pytest tests/test_architecture.py -v` and make sure it passes.

Example:
- Add a new policy operator (like you just did above)
- Add a test for it
- Update `docs/ARCHITECTURE.md` if the new operator changes the policy evaluation flow
- Commit: `feat(policy): add greater_than_or_equal operator with test`

---

## Debugging

**Backend won't start?**
```bash
python -m praman.main
```

Check the error. Likely causes:
- `.env` is missing or DATABASE_URL is wrong
- A dependency is not installed (`pip list | grep fastapi`)
- A Python version is too old (need 3.11+)

**Test fails?**
```bash
pytest tests/ -v --tb=short
```

Read the traceback. Look at the test name — it tells you what was being tested.

**Import error?**
```bash
python -c "from praman.domain import canonical; print(canonical.__doc__)"
```

Check the module docstring. If it imports something it should not, `test_architecture.py` will catch it.

---

## Daily Standup

When you deploy, update `HANDOFF.md`:

```markdown
## Project State Checkpoint (updated [DATE])

**Completed today:**
- [x] Added operator X to policy engine
- [x] Tests passing; architecture clean

**Next session starts with:**
- Implement [feature Y]
- Check [blocking issue Z]

**Blockers:** None
```

Keep the file under 15KB. Prune completed bullets as they age.

---

## The Handover Test

Every day, ask yourself:

1. Could a staff engineer who has never met me clone this and be productive tomorrow, using only the repo?
2. Does every file say what it is for and what it must not do?
3. Can they find why any non-obvious decision was made, without asking?
4. Is every stub disclosed in `docs/LIMITATIONS.md`?
5. Can they add a new policy engine by touching two files?
6. Does the architecture diagram match the actual folder tree?
7. Can they deploy from `docs/DEPLOYMENT.md` alone, with no tribal knowledge?

**Any "no" is the next task.**

---

**Ready to build?** You are. Clone, read, run, and make a change. The repo will answer your questions.
