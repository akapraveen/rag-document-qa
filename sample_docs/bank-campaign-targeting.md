# Campaign targeting: a call list that survives a rate shock

Ranks bank customers by likelihood to open a term deposit, evaluated the way it would actually be
used: trained on past calls, scored on future ones.

**Data:** [Bank Marketing](https://archive.ics.uci.edu/dataset/222/bank+marketing) (UCI, Portuguese
bank, May 2008 to Nov 2010), `bank-additional-full.csv`, 41,188 calls.

## Why the evaluation setup matters

| Setup | AUC |
|---|---|
| Random split, with call duration | 0.955 |
| Random split, no duration | 0.815 |
| Chronological split, trained once on the first 80% | 0.670 |
| **Walk-forward: retrained before each of 5 test blocks** | **0.757** |

![Evaluation setups](figures/evaluation.png)

`duration` is only known after the call ends, so it can't be used to decide whom to call. The last 20%
of calls converted at 30.8% against 6.4% before, while the 3-month Euribor fell from 4.3% to 1.0%.
A model trained once never saw that regime; monthly retraining recovers most of the lost accuracy.

## Model comparison (same test rows)

| Model | AUC trained once | AUC walk-forward | PR-AUC walk-forward |
|---|---|---|---|
| Logistic regression | 0.748 | 0.745 | 0.532 |
| **Gradient boosting** | 0.670 | **0.757** | **0.585** |
| Gradient boosting, client features only | 0.689 | 0.726 | 0.561 |

## What the list buys

| Call the top | Share of subscribers reached | Conversion | Calls per sale |
|---|---|---|---|
| 10% | 24.0% | 74.0% | 1.35 |
| 20% | 40.5% | 62.4% | 1.60 |
| 30% | 53.5% | 55.0% | 1.82 |
| Everyone | 100% | 30.8% | 3.24 |

<p><img src="figures/deciles.png" width="49%"> <img src="figures/importance.png" width="49%"></p>

Probabilities are still too low in the test period (mean prediction 21.5% vs 30.8% actual), so a
production version would recalibrate each month on the latest outcomes before using scores as rates.

## Run
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./download_data.sh
python train.py      # writes results.json
python figures.py    # writes figures/*.png
```
