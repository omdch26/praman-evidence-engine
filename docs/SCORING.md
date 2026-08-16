# Praman — Drift Scoring: Why It Is Stubbed

**TL;DR:** Drift detection requires operational data. The stub is deterministic (reproducible demo). Production requires real algorithms (PSI, semantic entropy). See `LIMITATIONS.md` for details.

---

## Why Drift Detection Matters

Module 2 (AI Risk) halts an agent when it detects drift — a statistically significant change in the distribution. Three types:

1. **Data drift:** Input distribution has changed (e.g., seasonal payment patterns)
2. **Semantic drift:** Output semantics have shifted (e.g., model started recommending different products)
3. **Behavioural drift:** Decision distribution has changed (e.g., model approval rate jumped from 20% to 80%)

Each failure mode is independent. A model might be safe on data drift but unsafe on semantic drift. Having three detectors means a reviewer can see *which* failed.

---

## Why It Is Stubbed in v0.1.0

Production drift detection requires:

1. **Reference distribution:** A baseline of "normal" behaviour to compare against
2. **Labelled data:** Examples of what normal/anomalous states look like
3. **Time series:** Multiple observations to establish a distribution
4. **Recomputation:** Running inference over historical data to score drift
5. **Thresholds:** Calibrated to the specific model and use case (not one-size-fits-all)

None of these exist before the first customer runs production workloads. Building a drift detector on synthetic data is a waste — it will not capture real failure modes.

---

## The Demonstrator Approach

The stub:
- Takes event data and returns a fixed, reproducible score (deterministic based on input hash)
- Never changes the score if the input does not change
- Allows the demo to run through the full flow: evaluate policy → detect drift → trigger breaker → log decision
- Proves the circuit-breaker mechanism works (the interesting engineering challenge)
- Does not pretend to measure real drift

---

## Production Approaches (Not Yet Implemented)

### Option 1: Population Stability Index (PSI)

Measures how much the observed distribution has diverged from the reference.

**Formula:** PSI = Σ (observed% - reference%) × ln(observed% / reference%)

**Requires:**
- Binning strategy for continuous variables
- Reference distribution from a clean training period
- Threshold calibration (typical: PSI > 0.25 triggers alert)

**Pros:**
- Well-understood in the industry (banks use it for model monitoring)
- Works with any data type (numerical, categorical)
- Interpretable (single number)

**Cons:**
- Requires labelled, historical data
- Binning strategy is arbitrary (too few bins = insensitivity; too many = noise)

**See:** `adapters/drift/psi.py` (documented, not implemented)

### Option 2: Semantic Entropy

Measures how much the semantic meaning of outputs has changed.

**Approach:**
- Embed the model's outputs using a reference semantic model (e.g., sentence-BERT)
- Compute the entropy of the embedding distribution
- Compare to reference entropy
- Large divergence = semantic drift

**Requires:**
- Reference semantic embeddings from a clean period
- Multiple sampled generations per event (high cost)
- Threshold calibration

**Pros:**
- Catches semantic shifts that PSI would miss (e.g., same loan products recommended, but to different profiles)
- Works for free-text outputs

**Cons:**
- Expensive (requires LLM resampling)
- Requires a reference semantic embedding model (another dependency)
- Less interpretable

**See:** `adapters/drift/semantic_entropy.py` (documented, not implemented)

### Option 3: Behavioural Distribution Shift

Measures how the decision distribution has changed over time.

**Approach:**
- Track approval rate, rejection rate, etc. as a distribution
- Compare to a rolling baseline (e.g., last 30 days)
- Significant change = behavioural drift

**Requires:**
- Sufficient decision volume to establish a baseline
- Threshold calibration (typical: 5–10% shift)

**Pros:**
- Simplest to implement
- Works with any discrete decision set
- High signal-to-noise ratio (changes in approval rate are observable)

**Cons:**
- Only works for discrete outcomes (does not detect continuous shift)
- Requires steady-state decisions to establish baseline
- Lag time before drift is detected (need 100+ decisions to see a trend)

---

## Implementation Timeline

**Month 1 (Shipped):** Deterministic stub (allow demo to run)

**Month 2:** Implement PSI with configurable binning  
- Customer provides reference period
- PSI is computed on a schedule (e.g., hourly)
- Threshold is configurable per model

**Month 3:** Add semantic entropy (for free-text models)  
- Requires LLM integration
- Threshold calibration is harder (no industry standard yet)

**Month 4:** Add behavioural shift detector  
- Works with any discrete decision

---

## How to Swap It

When you have real data:

1. Implement your chosen detector in `adapters/drift/your_detector.py`
2. Inherit from `DriftScorer` protocol
3. In `factories.py`, change:
   ```python
   case "deterministic_stub":
       return DeterministicStubDriftScorer()
   case "psi":
       return PopulationStabilityIndexDriftScorer(reference_period=config.reference_period)
   ```
4. Set `DRIFT_DETECTOR=psi` in `.env`
5. Restart the app

The entire system runs your new detector. No refactoring required.

---

## Validation & Testing

Once you have a real detector:

```python
def test_psi_detects_distribution_shift():
    """PSI > threshold triggers when distribution drifts."""
    reference_dist = [0.1, 0.2, 0.3, 0.4]  # baseline
    observed_dist = [0.3, 0.3, 0.2, 0.2]   # shifted
    
    scorer = PopulationStabilityIndexDriftScorer(reference=reference_dist)
    score = scorer.score(observed_dist)
    
    assert score > 0.25  # PSI threshold
    assert score < 1.0   # Not extreme
```

Then run it against your customer's data (with permission) to calibrate thresholds.

---

## Related

- `LIMITATIONS.md` — Full disclosure of what is stubbed
- `ARCHITECTURE.md` — Event flow (where drift detection plugs in)
- `docs/ADR/0012-module-two-build-gate.md` — Why Module 2 has a commercial gate (no real detector yet)
