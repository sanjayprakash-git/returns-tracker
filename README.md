# Returns Tracker

A comeback and returns tracker for a phone repair & accessories shop. Technicians and sales staff log anything that comes back in about 30 seconds: a repair comeback, a new or reconditioned phone, or an accessory. The manager gets a dashboard showing which parts, grades and suppliers fail, what returns cost, and how much can be claimed back from suppliers.

**Live demo:** _link coming after deployment_ · **Requirements:** [docs/requirements.md](docs/requirements.md)

![Manager dashboard](screenshots/dashboard-top.png)

---

## The problem

In a repair shop, most of what comes back is repair comebacks: a replacement screen with ghost touch or lines, a battery that drains fast, a sensor flex that stops Face ID or the fingerprint reader working. These usually get re-done at the counter with nothing recorded, so the shop can't answer:

- Are cheaper aftermarket screens a false economy?
- Which supplier's parts are failing, and is it a bad batch?
- How much credit are we losing by binning faulty parts instead of claiming them?
- Is it the part, or the fitting?

## How I approached it

1. **Requirements first.** I wrote the [requirements document](docs/requirements.md): problem statement, stakeholders, 12 user stories with acceptance criteria, business rules (warranty and returns policy), the data model, and current vs future process diagrams.
2. **Data model.** One `items` table covers repair jobs (device, part, grade, supplier), phones and accessories, so comeback and return rates use one formula: returns ÷ jobs or units sold.
3. **Build.** A Streamlit app on SQLite with three pages: log a return, a filterable returns log, and a manager dashboard.
4. **Rules built into the form.** Reasons and outcomes adapt to what's coming back. The form calculates days since repair or purchase, warns about out-of-policy decisions (such as a free re-repair after the 90-day warranty), and suggests a supplier claim when a part is faulty.

## What it does

| Page | For | Features |
|---|---|---|
| **Log a return** | Technicians & sales staff | Type → brand or accessory group → exact item (e.g. *iPhone 13 · Screen · Standard aftermarket*); reason and outcome lists that fit the type; automatic days and responsibility; policy warnings; supplier claim suggestion |
| **Returns log** | Manager | Filter by date, type, brand, reason and outcome; show only out-of-policy cases or supplier claims; running cost; CSV export |
| **Manager dashboard** | Manager | Comeback rate by part × grade, return rate by type, worst repairs, reasons by responsibility (part fault, workmanship, customer damage, sale-related), monthly trend, accessory returns by group, outcomes, cost of returns, claimable value, and automatically written insights |

| Log a return: warranty warning and supplier claim | Returns log |
|---|---|
| ![Log a return](screenshots/log-return.png) | ![Returns log](screenshots/returns-log.png) |

<details>
<summary>Full dashboard</summary>

![Full dashboard](screenshots/dashboard.png)

</details>

## What the demo data shows

The demo uses generated data: 6 months, about 7,100 repair jobs and sales, and about 280 returns (70% repair comebacks), with patterns for the dashboard to find:

- **Standard aftermarket screens come back 12.8% of the time**, vs 4.9% for premium and 2.7% for genuine. Fitting premium instead would have avoided about 40 comebacks.
- **A bad battery batch from one supplier** shows up as 15 comebacks in June against a typical 5 a month. The dashboard flags it automatically.
- **About €8,800 of faulty parts and products can be claimed back** from suppliers once they're recorded instead of binned.
- **14% of repair comebacks are fitting issues**, which points to technician training rather than parts.

No real customer, supplier or shop data is used.

## Run it locally

```bash
git clone https://github.com/sanjayprakash-git/returns-tracker.git
cd returns-tracker
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The database is created and filled with demo data on first start. To regenerate it, delete `data/returns.db`. Run the tests with `python -m unittest`.

## Project structure

```
app.py                 Entry point and page navigation
pages/                 Log a return, returns log, manager dashboard
tracker/db.py          SQLite schema, queries and cost-of-return rules
tracker/policy.py      Reference values, warranty/returns policy, responsibility
tracker/analytics.py   Comeback rates, spike detection and generated insights
tracker/seed.py        Demo data generator
tests/                 Tests for policy rules and dashboard maths
docs/requirements.md   Requirements, user stories, data model, process diagrams
```

**Stack:** Python · Streamlit · SQLite · pandas · Altair

## What I'd do next

- Connect to the repair-ticket and POS system so jobs and sales don't need entering twice
- Track supplier claims through to credit received
- Record the technician on each job to compare comeback rates fairly
- Add logins and move to a hosted database so data persists and several branches can share it

---

Built by [Sanjay Prakash Ravi](https://sanjayprakash.vercel.app/) · [LinkedIn](https://linkedin.com/in/sanjay-prakash-a92291186)
