# Customer segmentation with Orchestra

This project uses a generated `customer_transactions.csv` sample to build
customer-level RFM segments in BigQuery. The sample includes synthetic
customer/contact fields. The segmentation query uses `customer_id`,
transaction date, product category, amount, channel, and region; name, email,
phone, and date of birth are not copied to the output table, but remain in the
source CSV in GCS and are exposed by the external table.

This is an RFM-based segmentation prototype, not a trained predictive model.
Time since last transaction is also used as an explainable inactivity-risk
indicator with editable 30/60/90-day thresholds.

> This direct-load setup is for the generated synthetic sample. Do not use it
> with real customer data: the source CSV is stored in GCS, even though the
> BigQuery output omits contact fields. For real data, use an approved privacy
> process and adapt the source schema/ingestion accordingly.

## Input sample

The generated CSV should be named `customer_transactions.csv`, have a header
row, and use the following columns in this order:

```text
transaction_id, customer_id, customer_name, email, phone, date_of_birth,
transaction_date, product_category, amount_gbp, channel, region, last_updated
```

Dates must be parseable as BigQuery `DATE` values (`YYYY-MM-DD`) and transaction
amounts should be numeric. The pipeline ignores rows with blank customer IDs,
unparseable dates, or transaction dates after the chosen `as_of_date`.

## Project files

| File | Purpose |
| --- | --- |
| `customer-segmentation.yaml` | Orchestra pipeline definition for the 12-column generated CSV |
| `prepare_transactions.py` | Optional privacy-reduction utility for other exports; not used by the direct synthetic-sample flow |
| `test_prepare_transactions.py` | Standard-library tests for that optional utility |

The optional preparation utility writes a different, six-column CSV with an
HMAC customer key. The pipeline is configured for the 12-column generated
sample; do not substitute the utility's output without changing the
external-table schema in the YAML.

## Pipeline flow

```text
Generate synthetic customer_transactions.csv locally
  -> upload CSV to GCS
  -> Orchestra checks the object exists
  -> BigQuery creates an external table over the CSV
  -> BigQuery computes customer RFM features and inactivity-risk bands
  -> BigQuery checks the segmentation output
```

RFM means recency (days since last purchase), frequency (transaction count),
and monetary value (sum of valid `amount_gbp`). The output also includes
category count, missing-amount transaction count, channel/region summaries,
quartile scores, an RFM segment, and an inactivity band:

- `recently_active`: 0–29 days since last transaction
- `cooling_30_59d`: 30–59 days
- `high_risk_60_89d`: 60–89 days
- `inactive_90d_plus`: 90 or more days

These segments and inactivity bands are heuristics, not statistically trained
or validated predictions. Tune thresholds with business owners and historical
outcomes before using them for customer treatment or financial decisions.

## First-time setup and run

Run the commands below from this project directory:

```sh
cd /path/to/orchestra_customer_segmentation
```

### 1. Generate the sample CSV

Run your sample-data generator and save its output here as
`customer_transactions.csv`. Do not commit the generated CSV; this project
ignores both generated input and preparation output files.

Confirm the file has the header and column order documented above before
uploading it. This synthetic-sample path needs no HMAC key or anonymization
step.

### 2. Upload the CSV to GCS

Create or select a bucket for the demo and upload the generated sample:

```sh
gcloud storage cp \
  ./customer_transactions.csv \
  gs://YOUR_BUCKET/customer_transactions.csv
```

Keep the bucket private and grant access only to the required identities.

### 3. Configure BigQuery and Orchestra

1. Create a BigQuery dataset named `customer_segmentation_poc` in the GCP project
   associated with your BigQuery connection. Ensure its location is compatible
   with the GCS bucket.
2. Ensure the BigQuery identity can read the object and create/query tables in
   that dataset.
3. Create or select GCP Cloud Storage and GCP BigQuery connections in
   Orchestra.
4. The YAML currently refers to the existing GCS connection
   `orchestra_gcp_59732` and BigQuery connection `orchestra_gcp_52611`.
   Confirm both connections exist in this Orchestra workspace and have valid
   credentials/permissions.
5. Confirm the GCS check and external-table URI both point to
   `gs://orchestra-gcp-poc/customer_transactions.csv`. If you use a different
   bucket, update the bucket name in both places in the YAML.
6. Validate the pipeline:

```sh
orchestra login
orchestra pipeline validate ./customer-segmentation.yaml
```

### 4. Rename the GitHub repository and push

Rename the existing GitHub repository to `orchestra-customer-segmentation` in
**Settings → General → Repository name**. Set its visibility to **Private**
before pushing project updates; the current GitHub repository is public. Then
update this local checkout's remote URL:

```sh
git remote set-url origin \
  https://github.com/sudiptamondalqs/orchestra-customer-segmentation.git
git remote -v
```

Review the staged files to ensure the generated CSV is not included:

```sh
git status --short
git add .gitignore README.md customer-segmentation.yaml \
  prepare_transactions.py test_prepare_transactions.py
git diff --cached
git commit -m "Add customer segmentation pipeline"
git push -u origin main
```

Connect the renamed private repository and `main` branch to Orchestra. If
`main` is protected, push a feature branch and merge it through a pull request
instead.

### 5. Register the pipeline once

After the configured YAML is pushed to the connected GitHub branch, import it
once from this project directory:

```sh
orchestra pipeline import \
  --alias customer_segmentation \
  --path ./customer-segmentation.yaml
```

Save the returned pipeline ID. Import registers the Git-backed pipeline; it
does not run it. Do not import again for YAML updates—push changes to the
connected branch instead.

### 6. Run and review

In Orchestra, open `customer_segmentation`, start a run, and set `as_of_date`.
The sample used for this prototype has a maximum transaction date of
`2027-05-18`; use that date to include all sample transactions, or choose a
business snapshot date (transactions after it are excluded).

Review the run's source check, BigQuery task results, and quality check. The
output table is `customer_segmentation_poc.customer_segments`. It stores one
row per customer ID per snapshot date; rerunning the same date refreshes that
date's rows while retaining other snapshots.

This prototype is for exploration. Validate the data, RFM logic, and risk
thresholds against known historical customer outcomes before production use.
