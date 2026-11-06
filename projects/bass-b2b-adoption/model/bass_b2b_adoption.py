"""
Python model 'bass_b2b_adoption.py'
Translated using PySD
"""

from pathlib import Path
import numpy as np

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
    "final_time": lambda: 180,
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
    Fifteen-year horizon: long enough to see the saturation limit (decision horizon is 5 years).
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
    At most 1/12 of the shortest time constant in the parameter ranges (sales cycle 3 months).
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
            "initial": {"total_market": 1, "initial_customers": 1},
            "step": {"re_entry": 1, "evaluation_starts": 1},
        }
    },
)
def potential_customers():
    """
    Firms in the target market that are neither customers, in an evaluation, nor cooling off. Original model for sd-forge (structure from library/archetypes.md section 4 plus a sales pipeline and churn).
    """
    return _integ_potential_customers()


_integ_potential_customers = Integ(
    lambda: re_entry() - evaluation_starts(),
    lambda: total_market() - initial_customers(),
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
    Open sales opportunities (trial, proof of concept, procurement).
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
    Firms that lost a deal or churned and will not re-evaluate until the cool-off time has passed.
    """
    return _integ_cooling_off_firms()


_integ_cooling_off_firms = Integ(
    lambda: deals_lost() + churn() - re_entry(),
    lambda: initial_cooling_off_firms(),
    "_integ_cooling_off_firms",
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
    Bass adoption flow, here entry into a sales evaluation.
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
    Bass innovation term p*P.
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
        "customer_share": 1,
    },
)
def word_of_mouth_starts():
    """
    Bass imitation term q*P*C/N.
    """
    return word_of_mouth_rate_monthly() * potential_customers() * customer_share()


@component.add(
    name="customer share",
    units="Dmnl",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"customers": 1, "total_market": 1},
)
def customer_share():
    """
    Fraction of the target market that are customers.
    """
    return customers() / total_market()


@component.add(
    name="deal closings",
    units="Firm/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"firms_in_evaluation": 1, "sales_cycle_time": 1},
)
def deal_closings():
    """
    First-order exit from the pipeline (average time in evaluation = sales cycle time).
    """
    return firms_in_evaluation() / sales_cycle_time()


@component.add(
    name="deals won",
    units="Firm/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"deal_closings": 1, "win_rate": 1},
)
def deals_won():
    return deal_closings() * win_rate()


@component.add(
    name="deals lost",
    units="Firm/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"deal_closings": 1, "win_rate": 1},
)
def deals_lost():
    return deal_closings() * (1 - win_rate())


@component.add(
    name="churn",
    units="Firm/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"customers": 1, "churn_rate_monthly": 1},
)
def churn():
    """
    Logo churn.
    """
    return customers() * churn_rate_monthly()


@component.add(
    name="re entry",
    units="Firm/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"cooling_off_firms": 1, "cool_off_time": 1},
)
def re_entry():
    """
    Firms return to the potential pool after the cool-off time.
    """
    return cooling_off_firms() / cool_off_time()


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
    name="churn rate monthly",
    units="1/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"annual_logo_churn_rate": 1, "months_per_year": 1},
)
def churn_rate_monthly():
    return annual_logo_churn_rate() / months_per_year()


@component.add(
    name="marketing reach rate",
    units="1/Year",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def marketing_reach_rate():
    """
    p for entry into evaluation. Bass innovation coefficient p
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
    q for entry into evaluation. Bass imitation coefficient q
    """
    return 1.8


@component.add(
    name="sales cycle time",
    units="Month",
    limits=(0.5, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def sales_cycle_time():
    """
    Mid-market B2B SaaS, 3-9 months. Confidence: reported (secondary benchmarks).
    """
    return 6


@component.add(
    name="win rate",
    units="Dmnl",
    limits=(0.0, 1.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def win_rate():
    """
    Share of evaluations that close won, 0.15-0.30. Confidence: reported (secondary benchmarks).
    """
    return 0.21


@component.add(
    name="annual logo churn rate",
    units="1/Year",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def annual_logo_churn_rate():
    """
    Mid-market logo churn, 0.05-0.20 per year. Confidence: reported (secondary benchmarks, wide disagreement).
    """
    return 0.08


@component.add(
    name="cool off time",
    units="Month",
    limits=(0.5, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def cool_off_time():
    """
    Time before a lost or churned firm re-evaluates, 12-36 months. Confidence: estimated.
    """
    return 18


@component.add(
    name="total market",
    units="Firm",
    limits=(1.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def total_market():
    """
    Illustrative count of target firms (replace with your own market sizing), 3000-8000. Confidence: estimated.
    """
    return 5000


@component.add(
    name="initial customers",
    units="Firm",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def initial_customers():
    """
    Design partners at launch, 5-25. Confidence: estimated.
    """
    return 10


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
