# Orchestra customer segmentation and churn-risk prototype

This is a separate Orchestra example using
`customer_transactions.csv` to create customer-level RFM segments and a
rule-based inactivity-risk indicator in BigQuery.

This is **not a trained churn-prediction model**. The CSV has transaction
history but no confirmed churn label. The pipeline uses time since last
transaction as an explainable churn-risk proxy, with editable 30/60/90-day
thresholds.

## Data and privacy

The supplied CSV contains direct identifiers (name, email, phone, date of
birth) as well as transaction IDs. Do not upload that raw file to GCS or
BigQuery for this demo. The local preparation script:

- drops names, emails, phone numbers, dates of birth, transaction IDs, and
  `last_updated`;
- drops transactions with no customer ID (92 in the inspected sample);
- normalizes transaction dates in `YYYY-MM-DD`, `DD/MM/YYYY`, or the observed
  `YYYY-DD-MM` form; omits missing-date sentinels and invalid calendar dates,
  reporting their counts;
- replaces `customer_id` with an HMAC-SHA256 customer key;
- retains only transaction date, product category, amount, channel, and region;
- retains blank amounts as blank so they can be counted in data-quality
  metrics.

HMAC keys are secrets, and hashed customer keys remain linkable pseudonymous
data. Keep both the key and prepared CSV private. Use only in an approved
environment with appropriate access controls and retention.

## What the supplied sample indicates

Only aggregate facts were inspected; no customer records were copied into
this project. The source contained 695 rows, 200 distinct non-empty customer IDs,
92 rows with missing customer IDs, and valid transaction dates from
2025-03-01 through 2027-05-18. It also contains 13 `not recorded` dates,
11 `00/00/0000` date sentinels, and 14 impossible `31/02/2026` dates. These
24 missing/sentinel dates and 14 invalid dates are omitted and reported by the
preparation script. There are 27 blank amounts in the source; blank amounts on
retained transactions are kept and counted rather than treated as zero spend.

The demo `as_of_date` defaults to the sample's maximum transaction date
(`2027-05-18`) so the sample's future-dated transactions are not all
misclassified against today's date. For a real operational snapshot, choose
the correct business date when running the pipeline.

## Folder contents

| File | Purpose |
| --- | --- |
| `prepare_transactions.py` | Local PII-minimizing and HMAC pseudonymization step |
| `test_prepare_transactions.py` | Standard-library tests for the preparation step |
| `churn-prediction.yaml` | Orchestra pipeline definition |

The pipeline flow is:

```text
Raw local CSV
  -> local preparation (drop direct identifiers, HMAC customer ID)
  -> sanitized transaction CSV
  -> upload sanitized file to GCS
  -> Orchestra checks GCS object
  -> BigQuery creates an external table
  -> BigQuery computes customer RFM features and inactivity-risk segment
  -> BigQuery data-quality check
```

RFM means recency (days since last purchase), frequency (transaction count),
and monetary value (sum of valid `amount_gbp`). The output also includes
category count, missing-amount transaction count, channel/region summaries,
quartile scores, an RFM segment, and an inactivity band:

- `recently_active`: 0–29 days since last transaction
- `cooling`: 30–59 days
- `high_risk_60_89d`: 60–89 days
- `inactive_90d_plus`: 90 or more days

These are heuristic segments, not a statistically trained or validated
prediction. Tune thresholds with business owners and historical outcomes
before using them for customer treatment or financial decisions.

## Configure and run

### 1. Prepare a privacy-reduced CSV locally

Use a fresh, private HMAC key. Keep the same key for later snapshots of the
same customers so their pseudonymous keys remain stable. Store the key in a
password manager or approved secret store:

```sh
openssl rand -hex 32
```

Do not commit the key. Set it in your terminal, then prepare the CSV (quote
paths that contain spaces):

```sh
export CUSTOMER_ID_HMAC_KEY='paste-your-private-key-here'
python3 prepare_transactions.py \
  '/path/to/customer_transactions.csv' \
  './customer_transactions_sanitized.csv'
```

The sanitized CSV is still pseudonymous customer data. Do not commit it.

### 2. Upload only the sanitized CSV

Create an access-controlled bucket/object for the demo, then upload the
prepared file:

```sh
gcloud storage cp \
  ./customer_transactions_sanitized.csv \
  gs://YOUR_BUCKET/customer_transactions_sanitized.csv
```

### 3. Configure Orchestra and BigQuery

1. Create a BigQuery dataset named `customer_churn_poc` in the GCP project
   associated with your BigQuery connection.
2. Ensure the BigQuery identity can read the sanitized GCS object and create
   and query tables in that dataset.
3. Configure a GCP Cloud Storage connection and a GCP BigQuery connection in
   Orchestra.
4. In `churn-prediction.yaml`, replace:
   - `replace_with_gcs_00000`
   - `replace_with_bigquery_00000`
   - `YOUR_BUCKET` in both the file-check and external-table URI
5. Validate the YAML with the Orchestra CLI:

```sh
orchestra login
orchestra pipeline validate ./churn-prediction.yaml
```

### 4. Register once and run

Push the configured YAML to a GitHub repository connected to Orchestra, then
import it once:

```sh
orchestra pipeline import \
  --alias customer_churn_demo \
  --path ./churn-prediction.yaml
```

Save the returned pipeline ID. Do not import again to update the pipeline.
Run it in Orchestra with `as_of_date = 2027-05-18` for the supplied sample,
or set a suitable business snapshot date for another dataset. Review the
BigQuery output `customer_churn_poc.customer_segments` and the quality-check
task result.

## Output table

`customer_churn_poc.customer_segments` stores one row per pseudonymous
customer per snapshot date. Rerunning for the same `as_of_date` refreshes
that date's customer rows while retaining other snapshot dates.

This prototype is for exploration. Validate data quality, the RFM logic, and
the risk thresholds against known historical churn outcomes before production
use.
