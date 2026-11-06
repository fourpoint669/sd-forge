"""
Python model 'saas_churn_vs_winrate.py'
Translated using PySD
"""

from pathlib import Path
import numpy as np

from pysd.py_backend.functions import if_then_else
from pysd.py_backend.statefuls import Integ
from pysd import Component

__pysd_version__ = "3.14.3"

__data = {"scope": None, "time": lambda: 0}

_root = Path(__file__).parent


component = Component()

#######################################################################
#                          CONTROL VARIABLES                          #
#######################################################################

_control_vars = {
    "initial_time": lambda: 0,
    "final_time": lambda: 120,
    "time_step": lambda: 0.25,
    "saveper": lambda: 1,
}


def _init_outer_references(data):
    for key in data:
        __data[key] = data[key]


@component.add(name="Time")
def time():
    """
    Current time of the model.
    """
    return __data["time"]()


@component.add(
    name="FINAL TIME", units="Month", comp_type="Constant", comp_subtype="Normal"
)
def final_time():
    """
    Ten years: >= 3x the longest delay (36-month cool-off); decision horizon 60 months.
    """
    return __data["time"].final_time()


@component.add(
    name="INITIAL TIME", units="Month", comp_type="Constant", comp_subtype="Normal"
)
def initial_time():
    return __data["time"].initial_time()


@component.add(
    name="SAVEPER",
    units="Month",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def saveper():
    return __data["time"].saveper()


@component.add(
    name="TIME STEP",
    units="Month",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def time_step():
    """
    At most 1/8 of the shortest time constant in the ranges (CS ramp-up 2 months); divides 24, 60 and 120.
    """
    return __data["time"].time_step()


#######################################################################
#                           MODEL VARIABLES                           #
#######################################################################


@component.add(
    name="Potential Customers",
    units="Firm",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_potential_customers": 1},
    other_deps={
        "_integ_potential_customers": {
            "initial": {"initial_total_market": 1, "initial_customers": 1},
            "step": {"re_entry": 1, "market_entries": 1, "evaluation_starts": 1},
        }
    },
)
def potential_customers():
    """
    Target firms that are neither customers, in an evaluation, nor cooling off. Original model for sd-forge; customer engine as in projects/bass-b2b-adoption.
    """
    return _integ_potential_customers()


_integ_potential_customers = Integ(
    lambda: re_entry() + market_entries() - evaluation_starts(),
    lambda: initial_total_market() - initial_customers(),
    "_integ_potential_customers",
)


@component.add(
    name="Firms in Evaluation",
    units="Firm",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_firms_in_evaluation": 1},
    other_deps={
        "_integ_firms_in_evaluation": {
            "initial": {"initial_firms_in_evaluation": 1},
            "step": {"evaluation_starts": 1, "deals_won": 1, "deals_lost": 1},
        }
    },
)
def firms_in_evaluation():
    """
    Open sales opportunities; first-order sales-cycle delay.
    """
    return _integ_firms_in_evaluation()


_integ_firms_in_evaluation = Integ(
    lambda: evaluation_starts() - deals_won() - deals_lost(),
    lambda: initial_firms_in_evaluation(),
    "_integ_firms_in_evaluation",
)


@component.add(
    name="Customers",
    units="Firm",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_customers": 1},
    other_deps={
        "_integ_customers": {
            "initial": {"initial_customers": 1},
            "step": {"deals_won": 1, "churn": 1},
        }
    },
)
def customers():
    """
    Paying customer firms (logos).
    """
    return _integ_customers()


_integ_customers = Integ(
    lambda: deals_won() - churn(), lambda: initial_customers(), "_integ_customers"
)


@component.add(
    name="Cooling Off Firms",
    units="Firm",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_cooling_off_firms": 1},
    other_deps={
        "_integ_cooling_off_firms": {
            "initial": {"initial_cooling_off_firms": 1},
            "step": {"deals_lost": 1, "churn": 1, "re_entry": 1},
        }
    },
)
def cooling_off_firms():
    """
    Firms that lost a deal or churned; return to the pool after the cool-off time.
    """
    return _integ_cooling_off_firms()


_integ_cooling_off_firms = Integ(
    lambda: deals_lost() + churn() - re_entry(),
    lambda: initial_cooling_off_firms(),
    "_integ_cooling_off_firms",
)


@component.add(
    name="Firms Yet To Enter",
    units="Firm",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_firms_yet_to_enter": 1},
    other_deps={
        "_integ_firms_yet_to_enter": {
            "initial": {"initial_firms_yet_to_enter": 1},
            "step": {"market_entries": 1},
        }
    },
)
def firms_yet_to_enter():
    """
    Source stock for linear market growth; empties exactly at the market growth horizon (keeps the firm total conserved).
    """
    return _integ_firms_yet_to_enter()


_integ_firms_yet_to_enter = Integ(
    lambda: -market_entries(),
    lambda: initial_firms_yet_to_enter(),
    "_integ_firms_yet_to_enter",
)


@component.add(
    name="Recently Churned Firms",
    units="Firm",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_recently_churned_firms": 1},
    other_deps={
        "_integ_recently_churned_firms": {
            "initial": {},
            "step": {"churn": 1, "detractor_fade": 1},
        }
    },
)
def recently_churned_firms():
    """
    Information co-flow: count of recent churners (detractors). Not part of the firm conservation group.
    """
    return _integ_recently_churned_firms()


_integ_recently_churned_firms = Integ(
    lambda: churn() - detractor_fade(), lambda: 0, "_integ_recently_churned_firms"
)


@component.add(
    name="CS Capacity",
    units="Firm",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_cs_capacity": 1},
    other_deps={
        "_integ_cs_capacity": {"initial": {}, "step": {"cs_capacity_change": 1}}
    },
)
def cs_capacity():
    """
    Customers the churn programme can cover, additional to today's CS; goal-seeks to funded capacity with a ramp-up delay.
    """
    return _integ_cs_capacity()


_integ_cs_capacity = Integ(
    lambda: cs_capacity_change(), lambda: 0, "_integ_cs_capacity"
)


@component.add(
    name="Win Rate Capability",
    units="Dmnl",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_win_rate_capability": 1},
    other_deps={
        "_integ_win_rate_capability": {"initial": {}, "step": {"capability_change": 1}}
    },
)
def win_rate_capability():
    """
    Enablement level 0-1, additional to today's; goal-seeks to the target funded by spend with a ramp-up delay.
    """
    return _integ_win_rate_capability()


_integ_win_rate_capability = Integ(
    lambda: capability_change(), lambda: 0, "_integ_win_rate_capability"
)


@component.add(
    name="ARR",
    units="USD/Year",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_arr": 1},
    other_deps={
        "_integ_arr": {
            "initial": {"initial_customers": 1, "new_customer_acv": 1},
            "step": {"new_arr": 1, "expansion_arr": 1, "churned_arr": 1},
        }
    },
)
def arr():
    """
    Annual recurring revenue (objective at month 60).
    """
    return _integ_arr()


_integ_arr = Integ(
    lambda: new_arr() + expansion_arr() - churned_arr(),
    lambda: initial_customers() * new_customer_acv(),
    "_integ_arr",
)


@component.add(
    name="Cumulative Revenue",
    units="USD",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_cumulative_revenue": 1},
    other_deps={
        "_integ_cumulative_revenue": {"initial": {}, "step": {"revenue_recognition": 1}}
    },
)
def cumulative_revenue():
    """
    Revenue recognised since month 0.
    """
    return _integ_cumulative_revenue()


_integ_cumulative_revenue = Integ(
    lambda: revenue_recognition(), lambda: 0, "_integ_cumulative_revenue"
)


@component.add(
    name="Cumulative Programme Spend",
    units="USD",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_cumulative_programme_spend": 1},
    other_deps={
        "_integ_cumulative_programme_spend": {
            "initial": {},
            "step": {"total_programme_spend": 1},
        }
    },
)
def cumulative_programme_spend():
    """
    Programme dollars spent since month 0.
    """
    return _integ_cumulative_programme_spend()


_integ_cumulative_programme_spend = Integ(
    lambda: total_programme_spend(), lambda: 0, "_integ_cumulative_programme_spend"
)


@component.add(
    name="evaluation starts",
    units="Firm/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"marketing_driven_starts": 1, "word_of_mouth_starts": 1},
)
def evaluation_starts():
    """
    Bass adoption flow into evaluation.
    """
    return marketing_driven_starts() + word_of_mouth_starts()


@component.add(
    name="marketing driven starts",
    units="Firm/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"marketing_reach_rate_monthly": 1, "potential_customers": 1},
)
def marketing_driven_starts():
    """
    Bass innovation term.
    """
    return marketing_reach_rate_monthly() * potential_customers()


@component.add(
    name="word of mouth starts",
    units="Firm/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "word_of_mouth_rate_monthly": 1,
        "potential_customers": 1,
        "detractor_share": 1,
        "customer_share": 1,
        "negative_word_of_mouth_multiplier": 1,
    },
)
def word_of_mouth_starts():
    """
    Bass imitation term, reduced by recent churners when the multiplier (parameter C) > 0; never negative.
    """
    return (
        word_of_mouth_rate_monthly()
        * potential_customers()
        * float(
            np.maximum(
                0,
                customer_share()
                - negative_word_of_mouth_multiplier() * detractor_share(),
            )
        )
    )


@component.add(
    name="customer share",
    units="Dmnl",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"customers": 1, "total_market": 1},
)
def customer_share():
    """
    Share of the target market that are customers.
    """
    return customers() / total_market()


@component.add(
    name="detractor share",
    units="Dmnl",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"recently_churned_firms": 1, "total_market": 1},
)
def detractor_share():
    """
    Share of the market that churned recently.
    """
    return recently_churned_firms() / total_market()


@component.add(
    name="marketing reach rate monthly",
    units="1/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"marketing_reach_rate": 1, "months_per_year": 1},
)
def marketing_reach_rate_monthly():
    return marketing_reach_rate() / months_per_year()


@component.add(
    name="word of mouth rate monthly",
    units="1/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"word_of_mouth_rate": 1, "months_per_year": 1},
)
def word_of_mouth_rate_monthly():
    return word_of_mouth_rate() / months_per_year()


@component.add(
    name="re entry",
    units="Firm/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"cooling_off_firms": 1, "cool_off_time": 1},
)
def re_entry():
    """
    First-order return to the potential pool.
    """
    return cooling_off_firms() / cool_off_time()


@component.add(
    name="market entries",
    units="Firm/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "market_growth_rate_monthly": 1,
        "initial_total_market": 1,
        "market_growth_active": 1,
    },
)
def market_entries():
    """
    Linear market growth; stops at the market growth horizon.
    """
    return (
        market_growth_rate_monthly() * initial_total_market() * market_growth_active()
    )


@component.add(
    name="market growth active",
    units="Dmnl",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"time": 1, "market_growth_horizon": 1},
)
def market_growth_active():
    return if_then_else(time() < market_growth_horizon(), lambda: 1, lambda: 0)


@component.add(
    name="market growth rate monthly",
    units="1/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"market_growth_rate": 1, "months_per_year": 1},
)
def market_growth_rate_monthly():
    return market_growth_rate() / months_per_year()


@component.add(
    name="initial firms yet to enter",
    units="Firm",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "market_growth_rate": 1,
        "initial_total_market": 1,
        "market_growth_horizon": 1,
        "months_per_year": 1,
    },
)
def initial_firms_yet_to_enter():
    """
    All firms that enter within the horizon.
    """
    return (
        market_growth_rate()
        * initial_total_market()
        * market_growth_horizon()
        / months_per_year()
    )


@component.add(
    name="total market",
    units="Firm",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "initial_total_market": 1,
        "initial_firms_yet_to_enter": 1,
        "firms_yet_to_enter": 1,
    },
)
def total_market():
    """
    Current market size.
    """
    return initial_total_market() + initial_firms_yet_to_enter() - firms_yet_to_enter()


@component.add(
    name="deal closings",
    units="Firm/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"firms_in_evaluation": 1, "sales_cycle_time": 1, "sales_capacity": 1},
)
def deal_closings():
    """
    Opportunities closed (won or lost); limited by sales capacity, excess stays in the pipeline.
    """
    return float(
        np.minimum(firms_in_evaluation() / sales_cycle_time(), sales_capacity())
    )


@component.add(
    name="sales capacity",
    units="Firm/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "initial_sales_capacity": 1,
        "sales_capacity_growth_rate": 1,
        "time": 1,
        "months_per_year": 1,
    },
)
def sales_capacity():
    """
    Closings the sales team can handle; grows linearly with time when parameter B > 0 (not driven by revenue).
    """
    return initial_sales_capacity() * (
        1 + sales_capacity_growth_rate() * time() / months_per_year()
    )


@component.add(
    name="deals won",
    units="Firm/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"deal_closings": 1, "effective_win_rate": 1},
)
def deals_won():
    return deal_closings() * effective_win_rate()


@component.add(
    name="deals lost",
    units="Firm/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"deal_closings": 1, "effective_win_rate": 1},
)
def deals_lost():
    return deal_closings() * (1 - effective_win_rate())


@component.add(
    name="effective win rate",
    units="Dmnl",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "base_win_rate": 1,
        "maximum_win_rate_uplift": 1,
        "win_rate_capability": 1,
    },
)
def effective_win_rate():
    """
    At most 1: base win rate domain <= 0.9, uplift domain <= 0.1.
    """
    return base_win_rate() + maximum_win_rate_uplift() * win_rate_capability()


@component.add(
    name="churn",
    units="Firm/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"customers": 1, "effective_churn_fraction": 1},
)
def churn():
    """
    Logo churn.
    """
    return customers() * effective_churn_fraction()


@component.add(
    name="effective churn fraction",
    units="1/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"base_churn_rate_monthly": 1, "churn_reduction": 1},
)
def effective_churn_fraction():
    return base_churn_rate_monthly() * (1 - churn_reduction())


@component.add(
    name="base churn rate monthly",
    units="1/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"base_annual_churn_rate": 1, "months_per_year": 1},
)
def base_churn_rate_monthly():
    return base_annual_churn_rate() / months_per_year()


@component.add(
    name="detractor fade",
    units="Firm/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"recently_churned_firms": 1, "detractor_memory_time": 1},
)
def detractor_fade():
    return recently_churned_firms() / detractor_memory_time()


@component.add(
    name="churn programme spend",
    units="USD/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "monthly_programme_budget": 1,
        "programme_active": 1,
        "churn_share_now": 1,
    },
)
def churn_programme_spend():
    return monthly_programme_budget() * programme_active() * churn_share_now()


@component.add(
    name="funded CS capacity",
    units="Firm",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"churn_programme_spend": 1, "cs_cost_per_covered_firm": 1},
)
def funded_cs_capacity():
    """
    Customers the current spend pays to cover.
    """
    return churn_programme_spend() / cs_cost_per_covered_firm()


@component.add(
    name="CS capacity change",
    units="Firm/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"funded_cs_capacity": 1, "cs_capacity": 1, "cs_ramp_up_time": 1},
)
def cs_capacity_change():
    """
    Goal seeking (loop B7).
    """
    return (funded_cs_capacity() - cs_capacity()) / cs_ramp_up_time()


@component.add(
    name="CS coverage",
    units="Dmnl",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"cs_capacity": 1, "minimum_customer_base": 1, "customers": 1},
)
def cs_coverage():
    """
    Diluted as Customers grow (loop B11).
    """
    return cs_capacity() / float(np.maximum(customers(), minimum_customer_base()))


@component.add(
    name="CS effect",
    units="Dmnl",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"cs_coverage": 1, "coverage_scale": 1},
)
def cs_effect():
    """
    Diminishing returns in coverage.
    """
    return 1 - float(np.exp(-cs_coverage() / coverage_scale()))


@component.add(
    name="churn reduction",
    units="Dmnl",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"maximum_churn_reduction": 1, "cs_effect": 1},
)
def churn_reduction():
    return maximum_churn_reduction() * cs_effect()


@component.add(
    name="win rate programme spend",
    units="USD/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "monthly_programme_budget": 1,
        "programme_active": 1,
        "churn_share_now": 1,
    },
)
def win_rate_programme_spend():
    return monthly_programme_budget() * programme_active() * (1 - churn_share_now())


@component.add(
    name="target capability",
    units="Dmnl",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"win_rate_programme_spend": 1, "win_spend_scale": 1},
)
def target_capability():
    """
    Diminishing returns in spend.
    """
    return 1 - float(np.exp(-win_rate_programme_spend() / win_spend_scale()))


@component.add(
    name="capability change",
    units="1/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "target_capability": 1,
        "win_rate_capability": 1,
        "enablement_ramp_up_time": 1,
    },
)
def capability_change():
    """
    Goal seeking (loop B8).
    """
    return (target_capability() - win_rate_capability()) / enablement_ramp_up_time()


@component.add(
    name="new ARR",
    units="USD/(Year*Month)",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"deals_won": 1, "new_customer_acv": 1},
)
def new_arr():
    return deals_won() * new_customer_acv()


@component.add(
    name="expansion ARR",
    units="USD/(Year*Month)",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "arr": 1,
        "effective_expansion_rate_monthly": 1,
        "expansion_headroom": 1,
    },
)
def expansion_arr():
    """
    Net expansion, slowing as average ARR per customer nears the ceiling (loop B14).
    """
    return arr() * effective_expansion_rate_monthly() * expansion_headroom()


@component.add(
    name="churned ARR",
    units="USD/(Year*Month)",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"arr": 1, "effective_churn_fraction": 1},
)
def churned_arr():
    """
    Churners carry average ARR (assumption S9).
    """
    return arr() * effective_churn_fraction()


@component.add(
    name="ARR per customer",
    units="USD/(Firm*Year)",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"arr": 1, "minimum_customer_base": 1, "customers": 1},
)
def arr_per_customer():
    return arr() / float(np.maximum(customers(), minimum_customer_base()))


@component.add(
    name="expansion headroom",
    units="Dmnl",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "arr_per_customer": 1,
        "expansion_ceiling_multiple": 1,
        "new_customer_acv": 1,
    },
)
def expansion_headroom():
    return 1 - arr_per_customer() / (new_customer_acv() * expansion_ceiling_multiple())


@component.add(
    name="expansion lift",
    units="1/Year",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"expansion_lift_at_full_cs_effect": 1, "cs_effect": 1},
)
def expansion_lift():
    """
    Parameter A; 0 at base.
    """
    return expansion_lift_at_full_cs_effect() * cs_effect()


@component.add(
    name="effective expansion rate",
    units="1/Year",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"base_net_expansion_rate": 1, "expansion_lift": 1},
)
def effective_expansion_rate():
    return base_net_expansion_rate() + expansion_lift()


@component.add(
    name="effective expansion rate monthly",
    units="1/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"effective_expansion_rate": 1, "months_per_year": 1},
)
def effective_expansion_rate_monthly():
    return effective_expansion_rate() / months_per_year()


@component.add(
    name="revenue recognition",
    units="USD/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"arr": 1, "months_per_year": 1},
)
def revenue_recognition():
    """
    ARR (USD/Year) per Month: the /12 conversion (gate 1).
    """
    return arr() / months_per_year()


@component.add(
    name="cumulative revenue net of programme spend",
    units="USD",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"cumulative_revenue": 1, "cumulative_programme_spend": 1},
)
def cumulative_revenue_net_of_programme_spend():
    return cumulative_revenue() - cumulative_programme_spend()


@component.add(
    name="monthly programme budget",
    units="USD/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"total_programme_budget": 1, "programme_months": 1},
)
def monthly_programme_budget():
    return total_programme_budget() / programme_months()


@component.add(
    name="programme active",
    units="Dmnl",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"time": 1, "programme_months": 1},
)
def programme_active():
    return if_then_else(time() < programme_months(), lambda: 1, lambda: 0)


@component.add(
    name="churn share now",
    units="Dmnl",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "time": 1,
        "phase_switch_month": 1,
        "churn_share_phase_1": 1,
        "churn_share_phase_2": 1,
    },
)
def churn_share_now():
    return if_then_else(
        time() < phase_switch_month(),
        lambda: churn_share_phase_1(),
        lambda: churn_share_phase_2(),
    )


@component.add(
    name="total programme spend",
    units="USD/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"churn_programme_spend": 1, "win_rate_programme_spend": 1},
)
def total_programme_spend():
    return churn_programme_spend() + win_rate_programme_spend()


@component.add(
    name="marketing reach rate",
    units="1/Year",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def marketing_reach_rate():
    """
    Bass p for entry into evaluation. Range 0.05-0.25, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0.14


@component.add(
    name="word of mouth rate",
    units="1/Year",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def word_of_mouth_rate():
    """
    Bass q for entry into evaluation. Range 1-2.9, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 1.8


@component.add(
    name="negative word of mouth multiplier",
    units="Dmnl",
    limits=(0.0, 10.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def negative_word_of_mouth_multiplier():
    """
    Parameter C (optional, default 0). Range 0-2, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0


@component.add(
    name="cool off time",
    units="Month",
    limits=(0.5, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def cool_off_time():
    """
    Time before a lost or churned firm re-evaluates. Range 12-36, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 18


@component.add(
    name="market growth rate",
    units="1/Year",
    limits=(0.0, 1.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def market_growth_rate():
    """
    Linear market growth (optional, default 0). Range 0-0.1, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0


@component.add(
    name="initial total market",
    units="Firm",
    limits=(100.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def initial_total_market():
    """
    Illustrative; replace with your own market sizing. Range 3000-8000, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 5000


@component.add(
    name="sales cycle time",
    units="Month",
    limits=(0.5, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def sales_cycle_time():
    """
    Average time in evaluation. Range 3-9, triangular. Confidence: reported. Source: assumptions_register.md.
    """
    return 6


@component.add(
    name="initial sales capacity",
    units="Firm/Month",
    limits=(1.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def initial_sales_capacity():
    """
    Closings per month (won + lost). Range 20-120, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 45


@component.add(
    name="sales capacity growth rate",
    units="1/Year",
    limits=(0.0, 2.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def sales_capacity_growth_rate():
    """
    Parameter B (optional, default 0). Range 0-0.5, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0


@component.add(
    name="base win rate",
    units="Dmnl",
    limits=(0.0, 0.9),
    comp_type="Constant",
    comp_subtype="Normal",
)
def base_win_rate():
    """
    Win rate without the programme. Range 0.15-0.3, triangular. Confidence: reported. Source: assumptions_register.md.
    """
    return 0.21


@component.add(
    name="base annual churn rate",
    units="1/Year",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def base_annual_churn_rate():
    """
    Logo churn without the programme. Range 0.05-0.2, triangular. Confidence: reported. Source: assumptions_register.md.
    """
    return 0.08


@component.add(
    name="detractor memory time",
    units="Month",
    limits=(0.5, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def detractor_memory_time():
    """
    How long a churner affects referrals. Range 6-24, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 12


@component.add(
    name="initial customers",
    units="Firm",
    limits=(0.0, 100.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def initial_customers():
    """
    Design partners at launch. Range 5-25, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 10


@component.add(
    name="CS cost per covered firm",
    units="USD/(Firm*Month)",
    limits=(1.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def cs_cost_per_covered_firm():
    """
    Fully loaded CSM cost per account per month. Range 100-380, triangular. Confidence: reported. Source: assumptions_register.md.
    """
    return 185


@component.add(
    name="CS ramp up time",
    units="Month",
    limits=(0.5, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def cs_ramp_up_time():
    """
    Hiring and onboarding delay. Range 2-9, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 4


@component.add(
    name="coverage scale",
    units="Dmnl",
    limits=(0.01, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def coverage_scale():
    """
    Coverage giving 63% of the maximum churn effect. Range 0.25-1, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0.5


@component.add(
    name="maximum churn reduction",
    units="Dmnl",
    limits=(0.0, 1.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def maximum_churn_reduction():
    """
    Churn cut at full CS effect. Range 0.05-0.45, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0.25


@component.add(
    name="win spend scale",
    units="USD/Month",
    limits=(100.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def win_spend_scale():
    """
    Spend giving 63% of full enablement capability. Range 10000-60000, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 25000


@component.add(
    name="enablement ramp up time",
    units="Month",
    limits=(0.5, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def enablement_ramp_up_time():
    """
    Adoption delay of enablement. Range 3-12, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 6


@component.add(
    name="maximum win rate uplift",
    units="Dmnl",
    limits=(0.0, 0.1),
    comp_type="Constant",
    comp_subtype="Normal",
)
def maximum_win_rate_uplift():
    """
    Win-rate points at full capability. Range 0.02-0.1, triangular. Confidence: reported. Source: assumptions_register.md.
    """
    return 0.06


@component.add(
    name="new customer ACV",
    units="USD/(Firm*Year)",
    limits=(1.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def new_customer_acv():
    """
    Annual contract value of a new customer. Range 15000-60000, triangular. Confidence: reported. Source: assumptions_register.md.
    """
    return 30000


@component.add(
    name="base net expansion rate",
    units="1/Year",
    limits=(-0.5, 1.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def base_net_expansion_rate():
    """
    Expansion net of contraction on retained ARR. Range 0.02-0.2, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0.09


@component.add(
    name="expansion lift at full CS effect",
    units="1/Year",
    limits=(0.0, 1.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def expansion_lift_at_full_cs_effect():
    """
    Parameter A (optional, default 0). Range 0-0.1, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0


@component.add(
    name="expansion ceiling multiple",
    units="Dmnl",
    limits=(1.0, 20.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def expansion_ceiling_multiple():
    """
    Ceiling on average ARR per customer as a multiple of ACV. Range 1.3-4, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 2


@component.add(
    name="total programme budget",
    units="USD",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def total_programme_budget():
    """
    Same total in every scenario; illustrative. Range 1.5e+06-6e+06, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 3000000.0


@component.add(
    name="phase switch month",
    units="Month",
    limits=(0.0, 60.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def phase_switch_month():
    """
    End of phase 1 (scenario lever, fixed). Range 24-24, fixed. Confidence: verified. Source: assumptions_register.md.
    """
    return 24


@component.add(
    name="churn share phase 1",
    units="Dmnl",
    limits=(0.0, 1.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def churn_share_phase_1():
    """
    Share of spend on churn before the switch (scenario lever). Range 0.5-0.5, fixed. Confidence: verified. Source: assumptions_register.md.
    """
    return 0.5


@component.add(
    name="churn share phase 2",
    units="Dmnl",
    limits=(0.0, 1.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def churn_share_phase_2():
    """
    Share of spend on churn after the switch (scenario lever). Range 0.5-0.5, fixed. Confidence: verified. Source: assumptions_register.md.
    """
    return 0.5


@component.add(
    name="market growth horizon",
    units="Month",
    comp_type="Constant",
    comp_subtype="Normal",
)
def market_growth_horizon():
    """
    Market entries stop here (end of the 120-month run).
    """
    return 120


@component.add(
    name="programme months", units="Month", comp_type="Constant", comp_subtype="Normal"
)
def programme_months():
    """
    Budget is spent evenly over the 5-year decision horizon.
    """
    return 60


@component.add(
    name="minimum customer base",
    units="Firm",
    comp_type="Constant",
    comp_subtype="Normal",
)
def minimum_customer_base():
    """
    Keeps ratios per customer finite when Customers = 0.
    """
    return 1


@component.add(
    name="initial firms in evaluation",
    units="Firm",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def initial_firms_in_evaluation():
    """
    Launch starts with an empty pipeline.
    """
    return 0


@component.add(
    name="initial cooling off firms",
    units="Firm",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def initial_cooling_off_firms():
    return 0


@component.add(
    name="months per year",
    units="Month/Year",
    comp_type="Constant",
    comp_subtype="Normal",
)
def months_per_year():
    """
    Unit conversion.
    """
    return 12
