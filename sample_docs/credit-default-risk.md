# Credit default risk: who should collections call first?

Predicts next-month default for 30,000 credit-card accounts and ranks them for an early-collections
team that can contact 20% of the book each month.

**Data:** [Default of Credit Card Clients](https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients)
(UCI, Taiwan 2005). 22.1% default rate.

## Results (30% stratified hold-out, 9,000 accounts)

| Model | CV AUC | Test AUC | Gini | KS | Brier |
|---|---|---|---|---|---|
| Logistic regression (scorecard baseline) | 0.761 | 0.754 | 0.508 | 0.399 | 0.142 |
| Gradient boosting | 0.786 | **0.780** | 0.560 | 0.420 | 0.135 |

At 20% contact capacity:

| Ranking | Defaulted balance captured | Defaulters captured | Hit rate |
|---|---|---|---|
| **Model: expected loss (PD × balance)** | **77.4%** | 34.6% | 38.2% |
| Model: PD only | 51.1% | 50.8% | 56.2% |
| Rule: paid late last month | 54.0% | 47.3% | 52.3% |

![Capture curve](figures/capture_curve.png)

Ranking by expected loss rather than probability alone is the main decision: it trades some hit rate
for far more money at risk reached per call.

<p><img src="figures/risk_grades.png" width="49%"> <img src="figures/importance.png" width="49%"></p>

## Method
- Features: repayment status history, balances, payments, plus engineered utilisation, payment ratio,
  months late, max delay and balance trend.
- `SEX` and `MARRIAGE` are excluded from the model. `SEX` is used only for a post-hoc audit: flag rates
  20.6% (male) vs 19.6% (female) against actual default rates of 23.9% vs 21.0%; recall 0.33 vs 0.36.
- 5-fold stratified CV on the training set; permutation importance on the hold-out.

## Run
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./download_data.sh
python train.py      # writes results.json
python figures.py    # writes figures/*.png
```

## Limits
Exposure is the latest statement balance, a proxy for exposure at default. Data is from 2005 Taiwan,
so the fitted model is a method demonstration, not a deployable scorecard.
