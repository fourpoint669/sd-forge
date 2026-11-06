"""Gate 4 structure spec: stocks, auxiliaries/flows, parameters. Checks dependencies against the CLD."""
import re, networkx as nx

# name, unit, initial, inflows, outflows, kind
STOCKS = [
 ("Prospects", "Household", "initial prospects", "market entries + marketing starts + repeat to store", "new sales + used sales", "material"),
 ("Owners", "Household", "initial owners", "retail new buys + used sales", "replacement", "material (ownership period)"),
 ("Lessees Early", "Household", "initial lessees per stage", "lease starts", "lease advance 1", "material (lease stage 1)"),
 ("Lessees Mid", "Household", "initial lessees per stage", "lease advance 1", "lease advance 2", "material (lease stage 2)"),
 ("Lessees Late", "Household", "initial lessees per stage", "lease advance 2", "lease end", "material (lease stage 3)"),
 ("Households Elsewhere", "Household", "0", "leakage", "", "material sink (bought or leased at other stores)"),
 ("Households Outside Market", "Household", "(market entry rate + maximum marketing starts) * simulation horizon", "", "market entries + marketing starts", "material source"),
 ("New Inventory", "Vehicle", "initial new inventory", "deliveries", "new sales * vehicles per household purchase", "material"),
 ("New Vehicles On Order", "Vehicle", "initial new vehicles on order", "new orders", "deliveries", "material (order lead time)"),
 ("Used Frontline Inventory", "Vehicle", "initial used frontline inventory", "recon done", "used sales * vehicles per household purchase + wholesale exits", "material"),
 ("Reconditioning Pipeline", "Vehicle", "initial reconditioning pipeline", "used acquisitions", "recon done", "material (reconditioning time)"),
 ("Manufacturer Supply Outside", "Vehicle", "manufacturer allocation * simulation horizon", "", "new orders", "material source (bounded by the allocation cap)"),
 ("New Vehicles Sold", "Vehicle", "0", "new sales * vehicles per household purchase", "", "material sink"),
 ("Used Vehicle Supply Outside", "Vehicle", "initial used supply outside", "", "used acquisitions", "material source"),
 ("Used Vehicles Sold On", "Vehicle", "0", "used sales * vehicles per household purchase + wholesale exits", "", "material sink"),
 ("Trailing New Sales", "Household/Month", "reference new sales", "trailing change", "", "information (allocation memory)"),
 ("Trailing Used Sales", "Household/Month", "reference used sales", "trailing used change", "", "information (used sales memory)"),
 ("Service Customers", "Household", "initial service customers", "service capture", "defection", "material subset of the customer base"),
 ("Technicians", "Technician", "initial technicians", "hiring", "attrition", "resource (hiring delay)"),
 ("Inventory at Cost", "USD", "initial inventory at cost", "deliveries * new vehicle unit cost + used acquisitions * used vehicle unit cost", "inventory cost released", "money (valued at unit cost)"),
 ("Floorplan Debt", "USD", "initial floorplan debt", "advance rate * (deliveries * new vehicle unit cost + used acquisitions * used vehicle unit cost)", "floorplan payoff", "money"),
 ("Cash Received", "USD", "0", "MAX(0, net cash flow)", "", "accumulator (non-negative part of cash flow)"),
 ("Cash Paid Out", "USD", "0", "MAX(0, 0 - net cash flow)", "", "accumulator (non-negative part of cash flow)"),
 ("Cumulative Profit Earned", "USD", "0", "MAX(0, net profit)", "", "accumulator (non-negative part of net profit)"),
 ("Cumulative Loss Incurred", "USD", "0", "MAX(0, 0 - net profit)", "", "accumulator (non-negative part of net profit)"),
 ("Cumulative Discounted Cash Received", "USD", "0", "MAX(0, discounted net cash flow)", "", "accumulator (non-negative part)"),
 ("Cumulative Discounted Cash Paid", "USD", "0", "MAX(0, 0 - discounted net cash flow)", "", "accumulator (non-negative part)"),
]

# name, unit, equation
AUX = [
 ("shock active", "Dmnl", "IF THEN ELSE(Time >= shock start month, IF THEN ELSE(Time < shock start month + shock duration, 1, 0), 0)"),
 ("shoppers", "Household/Month", "Prospects * shopping rate monthly * (1 - demand shock size * shock active)"),
 ("new demand", "Household/Month", "shoppers * new share of shoppers"),
 ("used demand", "Household/Month", "shoppers * (1 - new share of shoppers) * (1 + discount demand sensitivity * used price discount)"),
 ("new sales", "Household/Month", "MIN(new demand * New Inventory / (New Inventory + availability constant new), New Inventory / (minimum sellout time * vehicles per household purchase))"),
 ("used sales", "Household/Month", "MIN(used demand * Used Frontline Inventory / (Used Frontline Inventory + availability constant used), Used Frontline Inventory / (minimum sellout time * vehicles per household purchase))"),
 ("lease starts", "Household/Month", "new sales * lease share"),
 ("retail new buys", "Household/Month", "new sales * (1 - lease share)"),
 ("lease stage time", "Month", "lease term / number of lease stages"),
 ("lease advance 1", "Household/Month", "Lessees Early / lease stage time"),
 ("lease advance 2", "Household/Month", "Lessees Mid / lease stage time"),
 ("lease end", "Household/Month", "Lessees Late / lease stage time"),
 ("replacement", "Household/Month", "Owners / ownership period"),
 ("service ratio", "Dmnl", "Service Customers / MAX(Owners, minimum owner base)"),
 ("store loyalty", "Dmnl", "loyalty floor + (loyalty ceiling - loyalty floor) * service ratio / (service ratio + loyalty half saturation)"),
 ("repeat to store", "Household/Month", "(replacement + lease end) * store loyalty"),
 ("leakage", "Household/Month", "replacement + lease end - repeat to store"),
 ("marketing starts", "Household/Month", "maximum marketing starts * (1 - EXP(-marketing spend / marketing spend scale))"),
 ("market entries", "Household/Month", "market entry rate"),
 ("trade ins", "Vehicle/Month", "replacement * trade in share * vehicles per household purchase"),
 ("off lease returns", "Vehicle/Month", "lease end * off lease return share * vehicles per household purchase"),
 ("target used inventory", "Vehicle", "used sales * vehicles per household purchase * (target used days supply / days per month + reconditioning time)"),
 ("auction buys", "Vehicle/Month", "MAX(0, used sales * vehicles per household purchase + (target used inventory - Used Frontline Inventory - Reconditioning Pipeline) / used inventory adjustment time - trade ins - off lease returns)"),
 ("used acquisitions", "Vehicle/Month", "trade ins + off lease returns + auction buys"),
 ("recon done", "Vehicle/Month", "Reconditioning Pipeline / reconditioning time"),
 ("trailing used change", "Household/Month/Month", "(used sales - Trailing Used Sales) / used sales memory"),
 ("used days supply", "Day", "Used Frontline Inventory / MAX(Trailing Used Sales * vehicles per household purchase, minimum used sales rate) * days per month"),
 ("used price discount", "Dmnl", "MIN(maximum price discount, discount sensitivity * (used days supply - target used days supply) / target used days supply)"),
 ("wholesale exits", "Vehicle/Month", "Used Frontline Inventory * wholesale exit rate monthly * used days supply / target used days supply"),
 ("target new inventory", "Vehicle", "new sales * vehicles per household purchase * (target new days supply / days per month + order lead time)"),
 ("allocation response", "Dmnl", "allocation response strength * (Trailing New Sales / reference new sales - 1)"),
 ("new orders", "Vehicle/Month", "MIN(manufacturer allocation, MAX(0, (new sales * vehicles per household purchase + (target new inventory - New Inventory - New Vehicles On Order) / new inventory adjustment time) * (1 + allocation response)))"),
 ("deliveries", "Vehicle/Month", "New Vehicles On Order / order lead time"),
 ("trailing change", "Household/Month/Month", "(new sales - Trailing New Sales) / allocation memory"),
 ("service capture", "Household/Month", "(new sales + used sales) * service capture share"),
 ("capacity", "RO/Month", "Technicians * repairs per technician"),
 ("ro demand", "RO/Month", "Service Customers * visits per customer monthly"),
 ("utilisation", "Dmnl", "ro demand / capacity"),
 ("defection", "Household/Month", "Service Customers * base defection rate monthly * (1 + retention loss when overloaded * (utilisation - 1))"),
 ("ro done", "RO/Month", "MIN(ro demand, capacity)"),
 ("hiring", "Technician/Month", "(technician target - Technicians) / hire time"),
 ("attrition", "Technician/Month", "Technicians * attrition rate monthly"),
 ("inventory cost released", "USD/Month", "new sales * vehicles per household purchase * new vehicle unit cost + (used sales * vehicles per household purchase + wholesale exits) * used vehicle unit cost"),
 ("floorplan payoff", "USD/Month", "advance rate * inventory cost released"),
 # profit chain (outside every loop)
 ("margin shock factor", "Dmnl", "1 - margin shock size * shock active"),
 ("new gross", "USD/Month", "new sales * vehicles per household purchase * new gross per vehicle * margin shock factor"),
 ("used gross", "USD/Month", "used sales * vehicles per household purchase * (used gross per vehicle - used price discount * used retail price)"),
 ("lease remarketing gain", "USD/Month", "0 - off lease returns * lease remarketing loss per vehicle"),
 ("F and I penetration", "Dmnl", "F and I base penetration + F and I maximum penetration uplift * (1 - EXP(-F and I programme spend / F and I spend scale))"),
 ("F and I income", "USD/Month", "(new sales + used sales) * F and I penetration * F and I gross per contract * (1 - chargeback rate)"),
 ("service gross", "USD/Month", "ro done * gross per repair order"),
 ("parts gross", "USD/Month", "ro done * parts gross per repair order"),
 ("total gross", "USD/Month", "new gross + used gross + lease remarketing gain + F and I income + service gross + parts gross"),
 ("commissions", "USD/Month", "commission rate * (new gross + used gross + F and I income)"),
 ("technician payroll", "USD/Month", "Technicians * technician cost monthly"),
 ("wholesale loss", "USD/Month", "wholesale exits * wholesale loss per vehicle"),
 ("floorplan rate effective", "1/Month", "floorplan rate monthly + rate shock size / months per year * shock active"),
 ("floorplan interest", "USD/Month", "Floorplan Debt * floorplan rate effective"),
 ("net profit", "USD/Month", "total gross - commissions - marketing spend - F and I programme spend - technician payroll - wholesale loss - fixed overhead - floorplan interest"),
 ("net cash flow", "USD/Month", "net profit - (1 - advance rate) * (deliveries * new vehicle unit cost + used acquisitions * used vehicle unit cost - inventory cost released)"),
 ("Cash", "USD", "initial cash + Cash Received - Cash Paid Out"),
 ("Cumulative Net Profit", "USD", "Cumulative Profit Earned - Cumulative Loss Incurred"),
 ("Cumulative Discounted Cash Flow", "USD", "Cumulative Discounted Cash Received - Cumulative Discounted Cash Paid"),
 ("discount factor", "Dmnl", "EXP(-discount rate monthly * Time)"),
 ("discounted net cash flow", "USD/Month", "net cash flow * discount factor"),
 ("absorption rate", "Dmnl", "(service gross + parts gross - technician payroll) / fixed overhead"),
 ("floorplan rate monthly", "1/Month", "floorplan rate / months per year"),
 ("discount rate monthly", "1/Month", "discount rate / months per year"),
 ("shopping rate monthly", "1/Month", "shopping rate / months per year"),
 ("base defection rate monthly", "1/Month", "base defection rate / months per year"),
 ("attrition rate monthly", "1/Month", "attrition rate / months per year"),
 ("wholesale exit rate monthly", "1/Month", "wholesale exit rate / months per year"),
 ("visits per customer monthly", "RO/(Household*Month)", "visits per customer / months per year"),
 ("technician cost monthly", "USD/(Technician*Month)", "technician cost / months per year"),
 ("minimum used sales rate", "Vehicle/Month", "minimum used sales rate"),  # placeholder, replaced below
]
AUX = [a for a in AUX if a[0] != "minimum used sales rate"]  # it is a constant, not an auxiliary


# ---------------------------------------------------------------------------------------------------------------
# Constants that are definitions, not uncertain parameters (not sampled, not in [parameters]).
CONSTANTS = {
    "months per year": (12, "Month/Year"), "days per month": (30.4, "Day/Month"),
    "vehicles per household purchase": (1, "Vehicle/Household"), "number of lease stages": (3, "Dmnl"),
    "simulation horizon": (180, "Month"), "minimum owner base": (1, "Household"),
    "minimum used sales rate": (1, "Vehicle/Month"), "minimum sellout time": (0.25, "Month"),
}
# Parameters: name -> (unit, base, low, high, distribution, domain, role, confidence, source)
# role "time_constant" = low end in the fastest corner (T4); "rate" = high end. fixed = a store policy or a scenario
# lever: it changes only through [[policies]].
T, F = "triangular", "fixed"
P_ = {}
def p(name, unit, base, low, high, dist, domain, role, conf, src):
    P_[name] = dict(unit=unit, base=base, low=low, high=high, dist=dist, domain=domain, role=role, conf=conf, src=src)

NCM = "Presidio-NCM data via Digital Dealer (secondary; the primary NADA/NCM report was not opened)"
# demand and prospects
p("shopping rate", "1/Year", 6.0, 3.0, 10.0, T, [0, 24], "rate", "estimated", "Share of the prospect pool actively shopping per year; 6/yr = a prospect shops about every 2 months. No source; scales with the pool size, which settles to match sales.")
p("new share of shoppers", "Dmnl", 0.55, 0.35, 0.75, F, [0.05, 0.95], None, "estimated", "Store mix, a lens C lever. About 55% new by units is the order of the NADA 2024 sales-dollar split (new 54.7%, used 32.0%, service and parts 13.2%; sales dollars, not units). Fixed; changes only through policies.")
p("market entry rate", "Household/Month", 70.0, 45.0, 95.0, T, [0, 1000], "rate", "estimated", "New households entering the store's addressable market per month. Set (by running settle.py) so the settled base sales are about 83 new and 65 used units a month, a store of about 1,000 new and 780 used units a year. Replace with your own market data.")
p("maximum marketing starts", "Household/Month", 30.0, 15.0, 50.0, T, [0, 500], "rate", "estimated", "Ceiling on prospects a month that paid marketing can add. No source.")
p("marketing spend scale", "USD/Month", 20000, 10000, 50000, T, [100, 1e7], None, "estimated", "Spend at which 63% of the marketing ceiling is reached (diminishing returns). No source.")
p("marketing spend", "USD/Month", 25000, 0.0, 60000.0, F, [0, 1e7], None, "estimated", "Store's current monthly advertising and lead cost. A lens A lever; changes only through policies.")
# new vehicles
p("availability constant new", "Vehicle", 8.0, 4.0, 16.0, T, [0.5, 200], None, "estimated", "Stock at which half of new demand can be served from the lot (sales = demand x stock/(stock + constant)). No source.")
p("target new days supply", "Day", 60.0, 60.0, 60.0, F, [5, 200], None, "estimated", "Store's stocking policy. Dealer new-car days supply in recent years has been roughly 50-80 days (industry commentary, not checked). Fixed.")
p("new inventory adjustment time", "Month", 1.5, 1.0, 3.0, T, [0.1, 24], "time_constant", "estimated", "How fast ordering closes the gap to target. No source.")
p("order lead time", "Month", 1.0, 0.5, 2.0, T, [0.1, 12], "time_constant", "estimated", "Factory order to delivery. No source.")
p("manufacturer allocation", "Vehicle/Month", 160.0, 120.0, 220.0, T, [0, 2000], None, "estimated", "Hard cap on monthly orders; set above the store's need so it does not bind in the base run. Not a forecast of allocation.")
p("allocation response strength", "Dmnl", 0.0, 0.0, 0.8, T, [0, 1], None, "estimated", "Optional parameter C (gate 2): extra orders per unit of trailing sales above its reference. 0 = off. Upper end gives +80% orders when trailing sales double.")
p("allocation memory", "Month", 6.0, 3.0, 12.0, T, [0.5, 36], "time_constant", "estimated", "Averaging time of trailing new sales. Inactive while C = 0. No source.")
# used vehicles
p("availability constant used", "Vehicle", 8.0, 4.0, 16.0, T, [0.5, 200], None, "estimated", "As for new. No source.")
p("discount demand sensitivity", "Dmnl", 1.5, 0.5, 3.0, T, [0, 3], None, "estimated", "Used demand rises by this multiple of the price discount fraction (1.5 means a 10% discount lifts demand 15%). Domain upper bound 3 with discount sensitivity <= 0.3 keeps demand positive.")
p("discount sensitivity", "Dmnl", 0.15, 0.05, 0.30, T, [0, 0.3], None, "estimated", "Price discount fraction per unit of relative excess days supply (0.15: days supply at twice target = 15% discount).")
p("maximum price discount", "Dmnl", 0.25, 0.15, 0.35, T, [0.05, 0.5], None, "estimated", "Ceiling on the used price discount (aged units are wholesaled rather than discounted further). With discount demand sensitivity <= 3 it keeps used demand within 1.75x. No source.")
p("target used days supply", "Day", 45.0, 30.0, 80.0, F, [5, 150], None, "estimated", "Store's used stocking policy; 45 days is a common dealer target (industry commentary, not checked). A lens A and C lever; fixed.")
p("used sales memory", "Month", 2.0, 1.0, 4.0, T, [0.5, 24], "time_constant", "estimated", "Averaging time of the used-sales rate that days supply is measured against; breaks what would otherwise be an algebraic loop (days supply -> discount -> demand -> sales -> days supply). No source.")
p("used inventory adjustment time", "Month", 1.5, 1.0, 3.0, T, [0.1, 24], "time_constant", "estimated", "How fast purchasing closes the gap to target. No source.")
p("reconditioning time", "Month", 0.5, 0.25, 1.0, T, [0.1, 6], "time_constant", "estimated", "Acquisition to frontline-ready: about 8-30 days. No source; shortest time constant, sets dt.")
p("wholesale exit rate", "1/Year", 0.5, 0.25, 1.0, T, [0, 5], "rate", "estimated", "Share of frontline stock wholesaled per year at target days supply (aged units). No source.")
p("trade in share", "Dmnl", 0.25, 0.15, 0.40, T, [0, 1], None, "estimated", "Share of replacing owners whose vehicle the store acquires (trade-in or buy-center); implies trade-ins are about half of used sourcing, a commonly quoted order of magnitude (not checked).")
p("off lease return share", "Dmnl", 0.8, 0.6, 0.95, T, [0, 1], None, "estimated", "Share of lease ends where the car comes back to the store (rest are buyouts). No source.")
p("lease remarketing loss per vehicle", "USD/Vehicle", 200.0, -1000.0, 1500.0, T, [-5000, 5000], None, "estimated", "Shortfall of resale value against the lease residual per off-lease vehicle (positive = loss, negative = gain); sign depends on the used-price cycle. Written as a loss so the base is a positive literal (the explorer converter needs that). No source.")
p("used retail price", "USD/Vehicle", 28000.0, 24000.0, 32000.0, T, [5000, 100000], None, "estimated", "Average used retail price; order of magnitude only.")
p("used vehicle unit cost", "USD/Vehicle", 26500.0, 22000.0, 30000.0, T, [5000, 100000], None, "estimated", "Used price less gross per unit and recon; order of magnitude only.")
# customer base and leases
p("lease share", "Dmnl", 0.25, 0.1, 0.5, F, [0, 0.9], None, "estimated", "Share of new sales that are leases; a lens C lever; fixed. US new-vehicle lease share has run roughly 20-25% in recent years (industry commentary, not checked).")
p("lease term", "Month", 36.0, 24.0, 48.0, T, [12, 60], "time_constant", "estimated", "Typical 36-month lease; sets the longest delay in the lease echo.")
p("ownership period", "Month", 66.0, 48.0, 96.0, T, [12, 240], "time_constant", "estimated", "Mean time before an owner replaces. Average ownership of a new vehicle has been quoted at about 6-8 years (not checked).")
p("loyalty floor", "Dmnl", 0.10, 0.05, 0.20, T, [0, 0.3], None, "estimated", "Share of replacing owners who return when they have no service relationship. No source.")
p("loyalty ceiling", "Dmnl", 0.60, 0.40, 0.75, T, [0.3, 1], None, "estimated", "Share returning with a full service relationship. No source.")
p("loyalty half saturation", "Dmnl", 1.5, 0.5, 3.0, T, [0.1, 10], None, "estimated", "Service customers per owner at which loyalty is halfway from floor to ceiling. No source.")
# service and parts
p("service capture share", "Dmnl", 2.2, 1.6, 3.2, F, [0, 6], None, "estimated", "Service customers gained per vehicle sold (buyers plus conquest and outreach); sets service base about 13,000 households and about 1,700 repair orders a month, the order of an average franchised store implied by NADA 2024 service and parts sales of over $156 billion (derived, not checked). Lens C lever; fixed.")
p("base defection rate", "1/Year", 0.25, 0.15, 0.40, T, [0, 2], "rate", "estimated", "Annual share of service customers lost (tenure about 4 years). No source.")
p("visits per customer", "RO/(Household*Year)", 1.5, 1.0, 2.2, T, [0.1, 6], None, "estimated", "Repair orders per service customer per year. No source.")
p("repairs per technician", "RO/(Technician*Month)", 80.0, 60.0, 100.0, T, [10, 300], None, "estimated", "Repair orders a technician completes a month (about 160 flag hours / 2 hours per RO). Productivity benchmarks were not found.")
p("retention loss when overloaded", "Dmnl", 0.0, 0.0, 0.6, T, [0, 1], None, "estimated", "Optional parameter A (gate 2): extra defection per unit of utilisation above 1. 0 = off.")
p("technician target", "Technician", 28.0, 20.0, 34.0, F, [0, 200], None, "estimated", "Store's hiring target; settled headcount is about 26 after attrition, giving base utilisation near 0.9. A lens A and C lever; fixed.")
p("hire time", "Month", 3.0, 1.5, 6.0, T, [0.5, 24], "time_constant", "estimated", "Recruit and train a technician. No source.")
p("attrition rate", "1/Year", 0.25, 0.15, 0.40, T, [0, 2], "rate", "estimated", "Technician turnover; the shortage is widely reported but no figure was found.")
p("gross per repair order", "USD/RO", 165.0, 120.0, 220.0, T, [0, 2000], None, "estimated", "Labor gross before technician pay. Calibrated with parts gross and technician cost so fixed-ops gross after pay covers about 70-90% of overhead (NCM H1 2024 average 69.3%, secondary).")
p("parts gross per repair order", "USD/RO", 103.0, 70.0, 140.0, T, [0, 2000], None, "estimated", "Parts gross per RO; same calibration note.")
p("technician cost", "USD/(Technician*Year)", 70000.0, 55000.0, 90000.0, T, [10000, 300000], "rate", "estimated", "Loaded annual cost per technician. No source.")
# F and I
p("F and I base penetration", "Dmnl", 0.85, 0.70, 0.92, T, [0, 0.92], None, "estimated", "Share of retail sales with a finance or insurance product. Upper bound 0.92 so penetration plus uplift cannot exceed 1.")
p("F and I maximum penetration uplift", "Dmnl", 0.05, 0.0, 0.08, T, [0, 0.08], None, "estimated", "Extra penetration a funded F and I programme can add. No source.")
p("F and I spend scale", "USD/Month", 10000, 5000, 30000, T, [100, 1e7], None, "estimated", "Spend at which 63% of the uplift is reached. No source.")
p("F and I programme spend", "USD/Month", 0.0, 0.0, 20000.0, F, [0, 1e7], None, "estimated", "Funded F and I programme on top of base staff cost; 0 in the base store. A lens A lever; fixed.")
p("F and I gross per contract", "USD/Household", 2050.0, 1500.0, 2600.0, T, [0, 20000], None, "reported", "Chosen so that penetration x gross x (1 - chargebacks) = about $1,570 per retail unit, matching F and I income per retail unit of $1,574 in H1 2024 (" + NCM + ").")
p("chargeback rate", "Dmnl", 0.10, 0.05, 0.20, T, [0, 1], None, "estimated", "Share of F and I income reversed by early cancellations. No source.")
# profit and cost
p("new gross per vehicle", "USD/Vehicle", 2250.0, 1200.0, 3200.0, T, [-5000, 20000], None, "reported", "Average gross profit per new vehicle, full-year 2024 $2,247 (" + NCM + "). Down 33% on 2023: the base is a squeezed year; range is wide on purpose.")
p("used gross per vehicle", "USD/Vehicle", 1400.0, 900.0, 1900.0, T, [-5000, 20000], None, "reported", "Average gross profit per used vehicle, full-year 2024 $1,399 (" + NCM + ").")
p("fixed overhead", "USD/Month", 530000.0, 400000.0, 650000.0, T, [1000, 1e8], None, "estimated", "Fixed expenses excluding technician pay and floorplan interest (rent, salaried staff, owner pay, utilities, insurance). Calibrated at gate 5 (one free parameter, set once) so the settled base earns a pre-tax margin of roughly 2% of sales and an absorption rate near the NCM H1 2024 average of 69.3% (secondary). Both are consistency checks, not data from one store.")
p("commission rate", "Dmnl", 0.25, 0.15, 0.30, T, [0, 1], None, "estimated", "Variable selling pay as a share of front-end gross. No source.")
p("wholesale loss per vehicle", "USD/Vehicle", 1200.0, 600.0, 2000.0, T, [0, 20000], None, "estimated", "Loss on an aged unit wholesaled. No source.")
p("new vehicle unit cost", "USD/Vehicle", 45000.0, 40000.0, 50000.0, T, [5000, 150000], None, "estimated", "Invoice cost per new vehicle; order of magnitude.")
p("advance rate", "Dmnl", 0.90, 0.80, 1.0, T, [0, 1], None, "estimated", "Share of inventory cost floorplan finances. No source.")
p("floorplan rate", "1/Year", 0.07, 0.05, 0.10, T, [0, 0.5], "rate", "estimated", "Floorplan interest rate; order of magnitude, not checked.")
p("discount rate", "1/Year", 0.10, 0.07, 0.15, T, [0, 1], None, "estimated", "Lens D discount rate. A stated parameter, not a finding.")
# shocks (lens B); sizes fixed at 0 in the base store and set through policies
p("margin shock size", "Dmnl", 0.0, 0.0, 0.5, F, [0, 1], None, "verified", "Lens B scenario input; 0 in the base. Definition.")
p("rate shock size", "1/Year", 0.0, 0.0, 0.08, F, [0, 0.2], None, "verified", "Lens B scenario input; 0 in the base. Definition.")
p("demand shock size", "Dmnl", 0.0, 0.0, 0.4, F, [0, 1], None, "verified", "Lens B scenario input; 0 in the base. Definition.")
p("shock start month", "Month", 24.0, 0.0, 60.0, F, [0, 180], None, "verified", "Shock window start; definition.")
p("shock duration", "Month", 12.0, 0.0, 36.0, F, [0, 180], None, "verified", "Shock window length; policies set 24 for the long squeeze. Definition.")
PARAMS_META = P_
# Initial stocks: fixed, set by settle.py from a long run at the base parameters (numbers produced by running code).
INITIAL_NAMES = {
    "Prospects": "initial prospects", "Trailing Used Sales": "reference used sales", "Owners": "initial owners", "Lessees Early": "initial lessees per stage",
    "Lessees Mid": "initial lessees per stage", "Lessees Late": "initial lessees per stage",
    "New Inventory": "initial new inventory", "New Vehicles On Order": "initial new vehicles on order",
    "Used Frontline Inventory": "initial used frontline inventory", "Reconditioning Pipeline": "initial reconditioning pipeline",
    "Service Customers": "initial service customers", "Technicians": "initial technicians",
    "Inventory at Cost": "initial inventory at cost", "Floorplan Debt": "initial floorplan debt",
}
