"""
Network-wide OTIF is critically low: every region falls between 43.7% and 51.2%,
and every product category has a delay rate above 59%. The problem is not
isolated to one region or category, which points to a systemic cause.
Goal: identify the root cause.
"""

import pandas as pd

df = pd.read_csv("data/DataCoSupplyChainDataset.csv", encoding="latin-1")

mode_counts = df["Shipping Mode"].value_counts()
mode_share = df["Shipping Mode"].value_counts(normalize=True) * 100
mode_otif = df.groupby("Shipping Mode")["Late_delivery_risk"].apply(lambda x: (1 - x).mean() * 100)

print("Orders per shipping mode:")
print(mode_counts)
print("\nShare of orders per shipping mode (%):")
print(mode_share)
print("\nOTIF % by shipping mode:")
print(mode_otif)


sched_vs_real = df.groupby("Shipping Mode")[
    ["Days for shipment (scheduled)", "Days for shipping (real)"]
].mean()
sched_vs_real["gap (real - scheduled)"] = (
    sched_vs_real["Days for shipping (real)"] - sched_vs_real["Days for shipment (scheduled)"]
)

print("\nScheduled vs actual days by shipping mode:")
print(sched_vs_real.round(2))


promise_check = df.groupby("Shipping Mode")["Days for shipment (scheduled)"].nunique()
print("\nDistinct scheduled-day values per mode:")
print(promise_check)

distribution = pd.crosstab(df["Shipping Mode"], df["Days for shipping (real)"])
print("\nOrders by actual delivery days:")
print(distribution)


status_by_mode = pd.crosstab(df["Shipping Mode"], df["Delivery Status"])
print("\nDelivery Status by shipping mode:")
print(status_by_mode)


valid = df[df["Delivery Status"] != "Shipping canceled"]

true_otif = valid.groupby("Shipping Mode")["Late_delivery_risk"].apply(
    lambda x: (1 - x).mean() * 100
)
network_otif = (1 - valid["Late_delivery_risk"]).mean() * 100

print("\nOTIF % by shipping mode (canceled orders excluded):")
print(true_otif)
print("\nNetwork OTIF % (canceled orders excluded):", round(network_otif, 1))


"""
5 WHYS
Problem: 57% of delivered orders arrive late (network OTIF 42.7%, canceled
         orders excluded).

Why 1: Why are so many orders late?
       Premium tiers fail almost every time: First Class OTIF is 0% and
       Second Class is 20.2%. Standard Class is 60.2%.            [DATA-PROVEN]

Why 2: Why do the premium tiers fail?
       Their actual delivery time exceeds the promised time.
       First Class: promised 1 day, actual 2 days (all 27,814 orders).
       Second Class: promised 2 days, actual about 4 days.         [DATA-PROVEN]

Why 3: Why is the actual time longer than the promise?
       The promise is one fixed number per tier (1 distinct value per mode),
       and it doesn't match what the network delivers. Second Class performs
       like Standard Class (3.99 vs 4.00 days) but is promised in half the time.
                                                                    [DATA-PROVEN]

Why 4: Why is the promise fixed regardless of performance?
       Tier promises are most likely set as pricing/product commitments
       (what the customer pays for), not derived from measured fulfilment
       performance.                                                 [HYPOTHESIS]

Why 5: Why isn't the promise corrected when performance falls short?
       There is no feedback loop between delivery performance data and
       promise-setting, and no clear owner for reconciling the two.
                                                                    [HYPOTHESIS]

ROOT CAUSE: Delivery promises are set per shipping tier without a feedback
loop from actual delivery performance, so premium tiers promise speed the
network cannot deliver.

Note: Whys 1-3 are proven by the data. Whys 4-5 are reasoned hypotheses and
would need validation with the teams that set tier promises.
"""


valid = df[df["Delivery Status"] != "Shipping canceled"].copy()

target = 0.9
new_promise = valid.groupby("Shipping Mode")["Days for shipping (real)"].quantile(target)
print("\nProposed promise (days) at the 90th percentile:")
print(new_promise)

valid["new_promise"] = valid["Shipping Mode"].map(new_promise)
valid["on_time_new"] = valid["Days for shipping (real)"] <= valid["new_promise"]

print("\nWhat-if OTIF % by mode:")
print(valid.groupby("Shipping Mode")["on_time_new"].mean() * 100)
print("\nWhat-if network OTIF %:", round(valid["on_time_new"].mean() * 100, 1))


standard = valid[valid["Shipping Mode"] == "Standard Class"]["Days for shipping (real)"]

print("\nStandard Class trade-off (promise length vs OTIF):")
for target in [0.5, 0.7, 0.9]:
    promise = standard.quantile(target)
    otif = (standard <= promise).mean() * 100
    print(f"Target {int(target * 100)}%: promise {promise:.0f} days -> OTIF {otif:.1f}%")


"""
IMPROVE
Recommended action: re-baseline delivery promises per shipping tier using
actual delivery performance, instead of fixed tier-level promises.

- First Class: change the promise from 1 day to 2 days. Every order takes
  exactly 2 days, so OTIF moves from 0% to 100%.
- Second Class: the tier performs like Standard Class (about 4 days actual,
  spread over 2-6 days). A 5-day promise gives about 80% OTIF.
- Standard Class: change the promise from 4 days to 5 days. OTIF moves from
  60.2% to 79.8%.
- Same Day: change the promise from 0 days to 1 day (orders take 0 or 1 day).

Trade-off: this fixes the honesty of the promise, not the speed of delivery.
Customers are told a longer time, and Second Class shows no speed advantage
over Standard Class. The business should decide whether to reprice Second
Class, or investigate its fulfilment process to make it genuinely faster.

Owner (proposed): Planning / Ops Analytics lead, with Product for the
customer-facing promise.
Timeline (proposed): 2 weeks to approve new promises, then roll out per tier.
Longer term: investigate why First Class takes 2 days (hypotheses on the
fishbone: carrier lanes, no promise-feasibility check).
"""

"""
CONTROL
Primary KPI: OTIF per shipping tier, canceled orders excluded, tracked weekly.
Supporting KPI: gap between actual delivery days (90th percentile) and the
promised days, per tier. Track the cancellation rate separately (currently
about 4-5%), because it was hidden inside the old OTIF formula.

Thresholds (illustrative, to be agreed with the business):
- Green: OTIF at or above 85% for the tier
- Amber: 80-85%
- Red: below 80% for two consecutive weeks -> review that tier's promise
  and its fulfilment process

Review cycle: reset each tier's promise quarterly from the last 90 days of
actual delivery data, so promises follow performance and don't drift again.
Owner (proposed): Ops Analytics lead.
"""