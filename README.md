# nse-llm-picker

An experiment: pick stocks for the next NSE/BSE trading session using
(1) their last year of price behaviour and (2) recent news read by a Hugging Face
LLM (Llama by default), **log the expectation before the session, then score it
against reality after the close.**

> Not investment advice. The point is to measure whether this method has any
> edge, honestly, with a log nobody can edit after the fact.

## How a pick is made

1. **Pattern score** (-1..+1) for each of ~50 stocks from 2 years of daily bars:
   20d/5d momentum, price vs 50/200-day averages, RSI extremes, volume
   confirmation, what the stock did in the same window last year, and its
   behaviour on that weekday. See `picker/features.py`.
2. **News score**: the 10 best by pattern score get their last-72h Google News
   headlines read by the LLM, which returns sentiment (-1..+1), catalyst type
   and a one-line summary. Falls back to a keyword lexicon if the model cannot
   load, and records which engine was used.
3. **Combined** = 0.6 x pattern + 0.4 x news. Rank 1 is **the pick**; ranks 2-5
   are **shadow picks**, tracked too so you get ~5x the samples.
4. **Expectation** written to SQLite: expected %, expected close, target, stop
   (both scaled by the stock's ATR%), and a P(up) prior. Weights and scalings
   are hypotheses in `picker/config.py`.

After the next close, `evaluate` records open/high/low/close, the gap vs
expectation (percentage points), direction hit, target/stop hit and alpha vs
Nifty 50. `report` builds `reports/tracker.xlsx` (Manual | Scorecard with live
formulas | Predictions).

## Run it

```bash
pip install -r requirements.txt
export HF_TOKEN=hf_...            # Llama is gated: accept the licence on its HF page first
python -m picker pick             # evening, after 15:45 IST
python -m picker evaluate         # evening of the NEXT session, after 15:45 IST
python -m picker report           # -> reports/tracker.xlsx
python -m picker export           # -> reports/latest.json (used by the Space)
python -m picker show             # scorecard in the terminal
```

Useful flags: `--no-llm` (keyword fallback), `--model Qwen/Qwen2.5-3B-Instruct`
(ungated alternative), `--exchange BSE`, `--only RELIANCE TCS INFY` (quick test).
On free Colab (T4) the 3B Llama runs fine; on CPU use
`PICKER_LLM=meta-llama/Llama-3.2-1B-Instruct`.

## Rules that keep the test honest

- `pick` refuses to run once the target session has opened.
- Re-running `pick` before the session replaces pending rows; evaluated rows are never touched.
- Holidays live in `data/holidays.csv` (24 Nov 2026 is a holiday). Update yearly.
- `data/universe.csv` is an editable approximation of the Nifty 50; symbols that
  fail to download are skipped.

## Reading the result

Wait for 30-60 sessions before trusting any hit rate. Compare the **pick** column
with **shadow** (is rank 1 really better?), the **P(up) prior** with the real
hit rate (calibration), and **alpha** with zero (beating Nifty, not just rising
with it). Returns are close-to-close from the reference close, so they include
the overnight gap; costs and slippage are not modelled.

## Tests

`python -m pytest` runs the full pick -> evaluate -> scorecard -> Excel loop on
synthetic data (no network, no model).

## Automation and the live page

- `nightly.yml` runs every weekday at 17:00 IST: evaluate yesterday's pick, pick for the
  next session, rebuild the Excel tracker, write `reports/latest.json`, commit.
- `space/` is a Gradio app for a Hugging Face Space. It reads `reports/latest.json`
  from this repo, so the Space never needs redeploying for new data.
- `deploy-space.yml` uploads `space/` to the Space whenever it changes.

Setup (one time):
1. Repo secret `HF_TOKEN`: a Hugging Face **read** token (for the gated Llama model).
2. Repo secret `HF_WRITE_TOKEN`: a **write** token, used only to deploy the Space.
3. Create the Space (Gradio SDK) named `Aman519/nse-llm-picker`, or set the repo
   variable `SPACE_ID` to your own. Set Space variable `DATA_URL` if your repo name differs.

The nightly job and Space deploy are untested until their first live run.
