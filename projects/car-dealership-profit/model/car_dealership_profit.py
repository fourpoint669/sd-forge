"""
Python model 'car_dealership_profit.py'
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
    "final_time": lambda: 180,
    "time_step": lambda: 0.0625,
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
    15 years: >= 3x the longest delay (replacement cycle, up to 60-72 months); decision horizon 60 months, valuation 120.
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
    At most 1/4 of the shortest time constant in the ranges (reconditioning time, 0.25 month); divides 60, 120 and 180.
    """
    return __data["time"].time_step()


#######################################################################
#                           MODEL VARIABLES                           #
#######################################################################


@component.add(
    name="Prospects",
    units="Household",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_prospects": 1},
    other_deps={
        "_integ_prospects": {
            "initial": {"initial_prospects": 1},
            "step": {
                "market_entries": 1,
                "marketing_starts": 1,
                "repeat_to_store": 1,
                "used_sales": 1,
                "new_sales": 1,
            },
        }
    },
)
def prospects():
    """
    Material. Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_prospects()


_integ_prospects = Integ(
    lambda: (market_entries() + marketing_starts() + repeat_to_store())
    - (new_sales() + used_sales()),
    lambda: initial_prospects(),
    "_integ_prospects",
)


@component.add(
    name="Owners",
    units="Household",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_owners": 1},
    other_deps={
        "_integ_owners": {
            "initial": {"initial_owners": 1},
            "step": {"retail_new_buys": 1, "used_sales": 1, "replacement": 1},
        }
    },
)
def owners():
    """
    Material (ownership period). Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_owners()


_integ_owners = Integ(
    lambda: (retail_new_buys() + used_sales()) - replacement(),
    lambda: initial_owners(),
    "_integ_owners",
)


@component.add(
    name="Lessees Early",
    units="Household",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_lessees_early": 1},
    other_deps={
        "_integ_lessees_early": {
            "initial": {"initial_lessees_per_stage": 1},
            "step": {"lease_starts": 1, "lease_advance_1": 1},
        }
    },
)
def lessees_early():
    """
    Material (lease stage 1). Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_lessees_early()


_integ_lessees_early = Integ(
    lambda: lease_starts() - lease_advance_1(),
    lambda: initial_lessees_per_stage(),
    "_integ_lessees_early",
)


@component.add(
    name="Lessees Mid",
    units="Household",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_lessees_mid": 1},
    other_deps={
        "_integ_lessees_mid": {
            "initial": {"initial_lessees_per_stage": 1},
            "step": {"lease_advance_1": 1, "lease_advance_2": 1},
        }
    },
)
def lessees_mid():
    """
    Material (lease stage 2). Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_lessees_mid()


_integ_lessees_mid = Integ(
    lambda: lease_advance_1() - lease_advance_2(),
    lambda: initial_lessees_per_stage(),
    "_integ_lessees_mid",
)


@component.add(
    name="Lessees Late",
    units="Household",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_lessees_late": 1},
    other_deps={
        "_integ_lessees_late": {
            "initial": {"initial_lessees_per_stage": 1},
            "step": {"lease_advance_2": 1, "lease_end": 1},
        }
    },
)
def lessees_late():
    """
    Material (lease stage 3). Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_lessees_late()


_integ_lessees_late = Integ(
    lambda: lease_advance_2() - lease_end(),
    lambda: initial_lessees_per_stage(),
    "_integ_lessees_late",
)


@component.add(
    name="Households Elsewhere",
    units="Household",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_households_elsewhere": 1},
    other_deps={"_integ_households_elsewhere": {"initial": {}, "step": {"leakage": 1}}},
)
def households_elsewhere():
    """
    Material sink (bought or leased at other stores). Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_households_elsewhere()


_integ_households_elsewhere = Integ(
    lambda: leakage(), lambda: 0, "_integ_households_elsewhere"
)


@component.add(
    name="Households Outside Market",
    units="Household",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_households_outside_market": 1},
    other_deps={
        "_integ_households_outside_market": {
            "initial": {
                "market_entry_rate": 1,
                "maximum_marketing_starts": 1,
                "simulation_horizon": 1,
            },
            "step": {"market_entries": 1, "marketing_starts": 1},
        }
    },
)
def households_outside_market():
    """
    Material source. Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_households_outside_market()


_integ_households_outside_market = Integ(
    lambda: -(market_entries() + marketing_starts()),
    lambda: (market_entry_rate() + maximum_marketing_starts()) * simulation_horizon(),
    "_integ_households_outside_market",
)


@component.add(
    name="New Inventory",
    units="Vehicle",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_new_inventory": 1},
    other_deps={
        "_integ_new_inventory": {
            "initial": {"initial_new_inventory": 1},
            "step": {
                "deliveries": 1,
                "vehicles_per_household_purchase": 1,
                "new_sales": 1,
            },
        }
    },
)
def new_inventory():
    """
    Material. Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_new_inventory()


_integ_new_inventory = Integ(
    lambda: deliveries() - new_sales() * vehicles_per_household_purchase(),
    lambda: initial_new_inventory(),
    "_integ_new_inventory",
)


@component.add(
    name="New Vehicles On Order",
    units="Vehicle",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_new_vehicles_on_order": 1},
    other_deps={
        "_integ_new_vehicles_on_order": {
            "initial": {"initial_new_vehicles_on_order": 1},
            "step": {"new_orders": 1, "deliveries": 1},
        }
    },
)
def new_vehicles_on_order():
    """
    Material (order lead time). Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_new_vehicles_on_order()


_integ_new_vehicles_on_order = Integ(
    lambda: new_orders() - deliveries(),
    lambda: initial_new_vehicles_on_order(),
    "_integ_new_vehicles_on_order",
)


@component.add(
    name="Used Frontline Inventory",
    units="Vehicle",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_used_frontline_inventory": 1},
    other_deps={
        "_integ_used_frontline_inventory": {
            "initial": {"initial_used_frontline_inventory": 1},
            "step": {
                "recon_done": 1,
                "used_sales": 1,
                "vehicles_per_household_purchase": 1,
                "wholesale_exits": 1,
            },
        }
    },
)
def used_frontline_inventory():
    """
    Material. Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_used_frontline_inventory()


_integ_used_frontline_inventory = Integ(
    lambda: recon_done()
    - (used_sales() * vehicles_per_household_purchase() + wholesale_exits()),
    lambda: initial_used_frontline_inventory(),
    "_integ_used_frontline_inventory",
)


@component.add(
    name="Reconditioning Pipeline",
    units="Vehicle",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_reconditioning_pipeline": 1},
    other_deps={
        "_integ_reconditioning_pipeline": {
            "initial": {"initial_reconditioning_pipeline": 1},
            "step": {"used_acquisitions": 1, "recon_done": 1},
        }
    },
)
def reconditioning_pipeline():
    """
    Material (reconditioning time). Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_reconditioning_pipeline()


_integ_reconditioning_pipeline = Integ(
    lambda: used_acquisitions() - recon_done(),
    lambda: initial_reconditioning_pipeline(),
    "_integ_reconditioning_pipeline",
)


@component.add(
    name="Manufacturer Supply Outside",
    units="Vehicle",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_manufacturer_supply_outside": 1},
    other_deps={
        "_integ_manufacturer_supply_outside": {
            "initial": {"manufacturer_allocation": 1, "simulation_horizon": 1},
            "step": {"new_orders": 1},
        }
    },
)
def manufacturer_supply_outside():
    """
    Material source (bounded by the allocation cap). Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_manufacturer_supply_outside()


_integ_manufacturer_supply_outside = Integ(
    lambda: -new_orders(),
    lambda: manufacturer_allocation() * simulation_horizon(),
    "_integ_manufacturer_supply_outside",
)


@component.add(
    name="New Vehicles Sold",
    units="Vehicle",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_new_vehicles_sold": 1},
    other_deps={
        "_integ_new_vehicles_sold": {
            "initial": {},
            "step": {"new_sales": 1, "vehicles_per_household_purchase": 1},
        }
    },
)
def new_vehicles_sold():
    """
    Material sink. Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_new_vehicles_sold()


_integ_new_vehicles_sold = Integ(
    lambda: new_sales() * vehicles_per_household_purchase(),
    lambda: 0,
    "_integ_new_vehicles_sold",
)


@component.add(
    name="Used Vehicle Supply Outside",
    units="Vehicle",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_used_vehicle_supply_outside": 1},
    other_deps={
        "_integ_used_vehicle_supply_outside": {
            "initial": {"initial_used_supply_outside": 1},
            "step": {"used_acquisitions": 1},
        }
    },
)
def used_vehicle_supply_outside():
    """
    Material source. Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_used_vehicle_supply_outside()


_integ_used_vehicle_supply_outside = Integ(
    lambda: -used_acquisitions(),
    lambda: initial_used_supply_outside(),
    "_integ_used_vehicle_supply_outside",
)


@component.add(
    name="Used Vehicles Sold On",
    units="Vehicle",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_used_vehicles_sold_on": 1},
    other_deps={
        "_integ_used_vehicles_sold_on": {
            "initial": {},
            "step": {
                "used_sales": 1,
                "vehicles_per_household_purchase": 1,
                "wholesale_exits": 1,
            },
        }
    },
)
def used_vehicles_sold_on():
    """
    Material sink. Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_used_vehicles_sold_on()


_integ_used_vehicles_sold_on = Integ(
    lambda: used_sales() * vehicles_per_household_purchase() + wholesale_exits(),
    lambda: 0,
    "_integ_used_vehicles_sold_on",
)


@component.add(
    name="Trailing New Sales",
    units="Household/Month",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_trailing_new_sales": 1},
    other_deps={
        "_integ_trailing_new_sales": {
            "initial": {"reference_new_sales": 1},
            "step": {"trailing_change": 1},
        }
    },
)
def trailing_new_sales():
    """
    Information (allocation memory). Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_trailing_new_sales()


_integ_trailing_new_sales = Integ(
    lambda: trailing_change(),
    lambda: reference_new_sales(),
    "_integ_trailing_new_sales",
)


@component.add(
    name="Trailing Used Sales",
    units="Household/Month",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_trailing_used_sales": 1},
    other_deps={
        "_integ_trailing_used_sales": {
            "initial": {"reference_used_sales": 1},
            "step": {"trailing_used_change": 1},
        }
    },
)
def trailing_used_sales():
    """
    Information (used sales memory). Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_trailing_used_sales()


_integ_trailing_used_sales = Integ(
    lambda: trailing_used_change(),
    lambda: reference_used_sales(),
    "_integ_trailing_used_sales",
)


@component.add(
    name="Service Customers",
    units="Household",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_service_customers": 1},
    other_deps={
        "_integ_service_customers": {
            "initial": {"initial_service_customers": 1},
            "step": {"service_capture": 1, "defection": 1},
        }
    },
)
def service_customers():
    """
    Material subset of the customer base. Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_service_customers()


_integ_service_customers = Integ(
    lambda: service_capture() - defection(),
    lambda: initial_service_customers(),
    "_integ_service_customers",
)


@component.add(
    name="Technicians",
    units="Technician",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_technicians": 1},
    other_deps={
        "_integ_technicians": {
            "initial": {"initial_technicians": 1},
            "step": {"hiring": 1, "attrition": 1},
        }
    },
)
def technicians():
    """
    Resource (hiring delay). Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_technicians()


_integ_technicians = Integ(
    lambda: hiring() - attrition(), lambda: initial_technicians(), "_integ_technicians"
)


@component.add(
    name="Inventory at Cost",
    units="USD",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_inventory_at_cost": 1},
    other_deps={
        "_integ_inventory_at_cost": {
            "initial": {"initial_inventory_at_cost": 1},
            "step": {
                "deliveries": 1,
                "new_vehicle_unit_cost": 1,
                "used_acquisitions": 1,
                "used_vehicle_unit_cost": 1,
                "inventory_cost_released": 1,
            },
        }
    },
)
def inventory_at_cost():
    """
    Money (valued at unit cost). Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_inventory_at_cost()


_integ_inventory_at_cost = Integ(
    lambda: (
        deliveries() * new_vehicle_unit_cost()
        + used_acquisitions() * used_vehicle_unit_cost()
    )
    - inventory_cost_released(),
    lambda: initial_inventory_at_cost(),
    "_integ_inventory_at_cost",
)


@component.add(
    name="Floorplan Debt",
    units="USD",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_floorplan_debt": 1},
    other_deps={
        "_integ_floorplan_debt": {
            "initial": {"initial_floorplan_debt": 1},
            "step": {
                "advance_rate": 1,
                "used_acquisitions": 1,
                "new_vehicle_unit_cost": 1,
                "used_vehicle_unit_cost": 1,
                "deliveries": 1,
                "floorplan_payoff": 1,
            },
        }
    },
)
def floorplan_debt():
    """
    Money. Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_floorplan_debt()


_integ_floorplan_debt = Integ(
    lambda: advance_rate()
    * (
        deliveries() * new_vehicle_unit_cost()
        + used_acquisitions() * used_vehicle_unit_cost()
    )
    - floorplan_payoff(),
    lambda: initial_floorplan_debt(),
    "_integ_floorplan_debt",
)


@component.add(
    name="Cash Received",
    units="USD",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_cash_received": 1},
    other_deps={"_integ_cash_received": {"initial": {}, "step": {"net_cash_flow": 1}}},
)
def cash_received():
    """
    Accumulator (non-negative part of cash flow). Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_cash_received()


_integ_cash_received = Integ(
    lambda: float(np.maximum(0, net_cash_flow())), lambda: 0, "_integ_cash_received"
)


@component.add(
    name="Cash Paid Out",
    units="USD",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_cash_paid_out": 1},
    other_deps={"_integ_cash_paid_out": {"initial": {}, "step": {"net_cash_flow": 1}}},
)
def cash_paid_out():
    """
    Accumulator (non-negative part of cash flow). Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_cash_paid_out()


_integ_cash_paid_out = Integ(
    lambda: float(np.maximum(0, 0 - net_cash_flow())), lambda: 0, "_integ_cash_paid_out"
)


@component.add(
    name="Cumulative Profit Earned",
    units="USD",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_cumulative_profit_earned": 1},
    other_deps={
        "_integ_cumulative_profit_earned": {"initial": {}, "step": {"net_profit": 1}}
    },
)
def cumulative_profit_earned():
    """
    Accumulator (non-negative part of net profit). Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_cumulative_profit_earned()


_integ_cumulative_profit_earned = Integ(
    lambda: float(np.maximum(0, net_profit())),
    lambda: 0,
    "_integ_cumulative_profit_earned",
)


@component.add(
    name="Cumulative Loss Incurred",
    units="USD",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_cumulative_loss_incurred": 1},
    other_deps={
        "_integ_cumulative_loss_incurred": {"initial": {}, "step": {"net_profit": 1}}
    },
)
def cumulative_loss_incurred():
    """
    Accumulator (non-negative part of net profit). Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_cumulative_loss_incurred()


_integ_cumulative_loss_incurred = Integ(
    lambda: float(np.maximum(0, 0 - net_profit())),
    lambda: 0,
    "_integ_cumulative_loss_incurred",
)


@component.add(
    name="Cumulative Discounted Cash Received",
    units="USD",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_cumulative_discounted_cash_received": 1},
    other_deps={
        "_integ_cumulative_discounted_cash_received": {
            "initial": {},
            "step": {"discounted_net_cash_flow": 1},
        }
    },
)
def cumulative_discounted_cash_received():
    """
    Accumulator (non-negative part). Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_cumulative_discounted_cash_received()


_integ_cumulative_discounted_cash_received = Integ(
    lambda: float(np.maximum(0, discounted_net_cash_flow())),
    lambda: 0,
    "_integ_cumulative_discounted_cash_received",
)


@component.add(
    name="Cumulative Discounted Cash Paid",
    units="USD",
    comp_type="Stateful",
    comp_subtype="Integ",
    depends_on={"_integ_cumulative_discounted_cash_paid": 1},
    other_deps={
        "_integ_cumulative_discounted_cash_paid": {
            "initial": {},
            "step": {"discounted_net_cash_flow": 1},
        }
    },
)
def cumulative_discounted_cash_paid():
    """
    Accumulator (non-negative part). Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.
    """
    return _integ_cumulative_discounted_cash_paid()


_integ_cumulative_discounted_cash_paid = Integ(
    lambda: float(np.maximum(0, 0 - discounted_net_cash_flow())),
    lambda: 0,
    "_integ_cumulative_discounted_cash_paid",
)


@component.add(
    name="shock active",
    units="Dmnl",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"time": 2, "shock_start_month": 2, "shock_duration": 1},
)
def shock_active():
    return if_then_else(
        time() >= shock_start_month(),
        lambda: if_then_else(
            time() < shock_start_month() + shock_duration(), lambda: 1, lambda: 0
        ),
        lambda: 0,
    )


@component.add(
    name="shoppers",
    units="Household/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "prospects": 1,
        "shopping_rate_monthly": 1,
        "demand_shock_size": 1,
        "shock_active": 1,
    },
)
def shoppers():
    return (
        prospects()
        * shopping_rate_monthly()
        * (1 - demand_shock_size() * shock_active())
    )


@component.add(
    name="new demand",
    units="Household/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"shoppers": 1, "new_share_of_shoppers": 1},
)
def new_demand():
    return shoppers() * new_share_of_shoppers()


@component.add(
    name="used demand",
    units="Household/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "shoppers": 1,
        "new_share_of_shoppers": 1,
        "used_price_discount": 1,
        "discount_demand_sensitivity": 1,
    },
)
def used_demand():
    return (
        shoppers()
        * (1 - new_share_of_shoppers())
        * (1 + discount_demand_sensitivity() * used_price_discount())
    )


@component.add(
    name="new sales",
    units="Household/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "new_demand": 1,
        "new_inventory": 3,
        "availability_constant_new": 1,
        "minimum_sellout_time": 1,
        "vehicles_per_household_purchase": 1,
    },
)
def new_sales():
    return float(
        np.minimum(
            new_demand()
            * new_inventory()
            / (new_inventory() + availability_constant_new()),
            new_inventory()
            / (minimum_sellout_time() * vehicles_per_household_purchase()),
        )
    )


@component.add(
    name="used sales",
    units="Household/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "used_demand": 1,
        "used_frontline_inventory": 3,
        "availability_constant_used": 1,
        "minimum_sellout_time": 1,
        "vehicles_per_household_purchase": 1,
    },
)
def used_sales():
    return float(
        np.minimum(
            used_demand()
            * used_frontline_inventory()
            / (used_frontline_inventory() + availability_constant_used()),
            used_frontline_inventory()
            / (minimum_sellout_time() * vehicles_per_household_purchase()),
        )
    )


@component.add(
    name="lease starts",
    units="Household/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"new_sales": 1, "lease_share": 1},
)
def lease_starts():
    return new_sales() * lease_share()


@component.add(
    name="retail new buys",
    units="Household/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"new_sales": 1, "lease_share": 1},
)
def retail_new_buys():
    return new_sales() * (1 - lease_share())


@component.add(
    name="lease stage time",
    units="Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"lease_term": 1, "number_of_lease_stages": 1},
)
def lease_stage_time():
    return lease_term() / number_of_lease_stages()


@component.add(
    name="lease advance 1",
    units="Household/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"lessees_early": 1, "lease_stage_time": 1},
)
def lease_advance_1():
    return lessees_early() / lease_stage_time()


@component.add(
    name="lease advance 2",
    units="Household/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"lessees_mid": 1, "lease_stage_time": 1},
)
def lease_advance_2():
    return lessees_mid() / lease_stage_time()


@component.add(
    name="lease end",
    units="Household/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"lessees_late": 1, "lease_stage_time": 1},
)
def lease_end():
    return lessees_late() / lease_stage_time()


@component.add(
    name="replacement",
    units="Household/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"owners": 1, "ownership_period": 1},
)
def replacement():
    return owners() / ownership_period()


@component.add(
    name="service ratio",
    units="Dmnl",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"service_customers": 1, "minimum_owner_base": 1, "owners": 1},
)
def service_ratio():
    return service_customers() / float(np.maximum(owners(), minimum_owner_base()))


@component.add(
    name="store loyalty",
    units="Dmnl",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "loyalty_floor": 2,
        "loyalty_ceiling": 1,
        "service_ratio": 2,
        "loyalty_half_saturation": 1,
    },
)
def store_loyalty():
    return loyalty_floor() + (loyalty_ceiling() - loyalty_floor()) * service_ratio() / (
        service_ratio() + loyalty_half_saturation()
    )


@component.add(
    name="repeat to store",
    units="Household/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"replacement": 1, "lease_end": 1, "store_loyalty": 1},
)
def repeat_to_store():
    return (replacement() + lease_end()) * store_loyalty()


@component.add(
    name="leakage",
    units="Household/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"replacement": 1, "lease_end": 1, "repeat_to_store": 1},
)
def leakage():
    return replacement() + lease_end() - repeat_to_store()


@component.add(
    name="marketing starts",
    units="Household/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "maximum_marketing_starts": 1,
        "marketing_spend": 1,
        "marketing_spend_scale": 1,
    },
)
def marketing_starts():
    return maximum_marketing_starts() * (
        1 - float(np.exp(-marketing_spend() / marketing_spend_scale()))
    )


@component.add(
    name="market entries",
    units="Household/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"market_entry_rate": 1},
)
def market_entries():
    return market_entry_rate()


@component.add(
    name="trade ins",
    units="Vehicle/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "replacement": 1,
        "trade_in_share": 1,
        "vehicles_per_household_purchase": 1,
    },
)
def trade_ins():
    return replacement() * trade_in_share() * vehicles_per_household_purchase()


@component.add(
    name="off lease returns",
    units="Vehicle/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "lease_end": 1,
        "off_lease_return_share": 1,
        "vehicles_per_household_purchase": 1,
    },
)
def off_lease_returns():
    return lease_end() * off_lease_return_share() * vehicles_per_household_purchase()


@component.add(
    name="target used inventory",
    units="Vehicle",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "used_sales": 1,
        "vehicles_per_household_purchase": 1,
        "days_per_month": 1,
        "target_used_days_supply": 1,
        "reconditioning_time": 1,
    },
)
def target_used_inventory():
    return (
        used_sales()
        * vehicles_per_household_purchase()
        * (target_used_days_supply() / days_per_month() + reconditioning_time())
    )


@component.add(
    name="auction buys",
    units="Vehicle/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "used_sales": 1,
        "vehicles_per_household_purchase": 1,
        "used_inventory_adjustment_time": 1,
        "used_frontline_inventory": 1,
        "reconditioning_pipeline": 1,
        "target_used_inventory": 1,
        "trade_ins": 1,
        "off_lease_returns": 1,
    },
)
def auction_buys():
    return float(
        np.maximum(
            0,
            used_sales() * vehicles_per_household_purchase()
            + (
                target_used_inventory()
                - used_frontline_inventory()
                - reconditioning_pipeline()
            )
            / used_inventory_adjustment_time()
            - trade_ins()
            - off_lease_returns(),
        )
    )


@component.add(
    name="used acquisitions",
    units="Vehicle/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"trade_ins": 1, "off_lease_returns": 1, "auction_buys": 1},
)
def used_acquisitions():
    return trade_ins() + off_lease_returns() + auction_buys()


@component.add(
    name="recon done",
    units="Vehicle/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"reconditioning_pipeline": 1, "reconditioning_time": 1},
)
def recon_done():
    return reconditioning_pipeline() / reconditioning_time()


@component.add(
    name="trailing used change",
    units="Household/Month/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"used_sales": 1, "trailing_used_sales": 1, "used_sales_memory": 1},
)
def trailing_used_change():
    return (used_sales() - trailing_used_sales()) / used_sales_memory()


@component.add(
    name="used days supply",
    units="Day",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "used_frontline_inventory": 1,
        "minimum_used_sales_rate": 1,
        "vehicles_per_household_purchase": 1,
        "trailing_used_sales": 1,
        "days_per_month": 1,
    },
)
def used_days_supply():
    return (
        used_frontline_inventory()
        / float(
            np.maximum(
                trailing_used_sales() * vehicles_per_household_purchase(),
                minimum_used_sales_rate(),
            )
        )
        * days_per_month()
    )


@component.add(
    name="used price discount",
    units="Dmnl",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "maximum_price_discount": 1,
        "discount_sensitivity": 1,
        "target_used_days_supply": 2,
        "used_days_supply": 1,
    },
)
def used_price_discount():
    return float(
        np.minimum(
            maximum_price_discount(),
            discount_sensitivity()
            * (used_days_supply() - target_used_days_supply())
            / target_used_days_supply(),
        )
    )


@component.add(
    name="wholesale exits",
    units="Vehicle/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "used_frontline_inventory": 1,
        "wholesale_exit_rate_monthly": 1,
        "used_days_supply": 1,
        "target_used_days_supply": 1,
    },
)
def wholesale_exits():
    return (
        used_frontline_inventory()
        * wholesale_exit_rate_monthly()
        * used_days_supply()
        / target_used_days_supply()
    )


@component.add(
    name="target new inventory",
    units="Vehicle",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "new_sales": 1,
        "vehicles_per_household_purchase": 1,
        "days_per_month": 1,
        "order_lead_time": 1,
        "target_new_days_supply": 1,
    },
)
def target_new_inventory():
    return (
        new_sales()
        * vehicles_per_household_purchase()
        * (target_new_days_supply() / days_per_month() + order_lead_time())
    )


@component.add(
    name="allocation response",
    units="Dmnl",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "allocation_response_strength": 1,
        "trailing_new_sales": 1,
        "reference_new_sales": 1,
    },
)
def allocation_response():
    return allocation_response_strength() * (
        trailing_new_sales() / reference_new_sales() - 1
    )


@component.add(
    name="new orders",
    units="Vehicle/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "manufacturer_allocation": 1,
        "target_new_inventory": 1,
        "new_inventory_adjustment_time": 1,
        "new_vehicles_on_order": 1,
        "vehicles_per_household_purchase": 1,
        "allocation_response": 1,
        "new_inventory": 1,
        "new_sales": 1,
    },
)
def new_orders():
    return float(
        np.minimum(
            manufacturer_allocation(),
            float(
                np.maximum(
                    0,
                    (
                        new_sales() * vehicles_per_household_purchase()
                        + (
                            target_new_inventory()
                            - new_inventory()
                            - new_vehicles_on_order()
                        )
                        / new_inventory_adjustment_time()
                    )
                    * (1 + allocation_response()),
                )
            ),
        )
    )


@component.add(
    name="deliveries",
    units="Vehicle/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"new_vehicles_on_order": 1, "order_lead_time": 1},
)
def deliveries():
    return new_vehicles_on_order() / order_lead_time()


@component.add(
    name="trailing change",
    units="Household/Month/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"new_sales": 1, "trailing_new_sales": 1, "allocation_memory": 1},
)
def trailing_change():
    return (new_sales() - trailing_new_sales()) / allocation_memory()


@component.add(
    name="service capture",
    units="Household/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"new_sales": 1, "used_sales": 1, "service_capture_share": 1},
)
def service_capture():
    return (new_sales() + used_sales()) * service_capture_share()


@component.add(
    name="capacity",
    units="RO/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"technicians": 1, "repairs_per_technician": 1},
)
def capacity():
    return technicians() * repairs_per_technician()


@component.add(
    name="ro demand",
    units="RO/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"service_customers": 1, "visits_per_customer_monthly": 1},
)
def ro_demand():
    return service_customers() * visits_per_customer_monthly()


@component.add(
    name="utilisation",
    units="Dmnl",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"ro_demand": 1, "capacity": 1},
)
def utilisation():
    return ro_demand() / capacity()


@component.add(
    name="defection",
    units="Household/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "service_customers": 1,
        "base_defection_rate_monthly": 1,
        "retention_loss_when_overloaded": 1,
        "utilisation": 1,
    },
)
def defection():
    return (
        service_customers()
        * base_defection_rate_monthly()
        * (1 + retention_loss_when_overloaded() * (utilisation() - 1))
    )


@component.add(
    name="ro done",
    units="RO/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"ro_demand": 1, "capacity": 1},
)
def ro_done():
    return float(np.minimum(ro_demand(), capacity()))


@component.add(
    name="hiring",
    units="Technician/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"technician_target": 1, "technicians": 1, "hire_time": 1},
)
def hiring():
    return (technician_target() - technicians()) / hire_time()


@component.add(
    name="attrition",
    units="Technician/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"technicians": 1, "attrition_rate_monthly": 1},
)
def attrition():
    return technicians() * attrition_rate_monthly()


@component.add(
    name="inventory cost released",
    units="USD/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "new_sales": 1,
        "vehicles_per_household_purchase": 2,
        "new_vehicle_unit_cost": 1,
        "used_sales": 1,
        "used_vehicle_unit_cost": 1,
        "wholesale_exits": 1,
    },
)
def inventory_cost_released():
    return (
        new_sales() * vehicles_per_household_purchase() * new_vehicle_unit_cost()
        + (used_sales() * vehicles_per_household_purchase() + wholesale_exits())
        * used_vehicle_unit_cost()
    )


@component.add(
    name="floorplan payoff",
    units="USD/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"advance_rate": 1, "inventory_cost_released": 1},
)
def floorplan_payoff():
    return advance_rate() * inventory_cost_released()


@component.add(
    name="margin shock factor",
    units="Dmnl",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"margin_shock_size": 1, "shock_active": 1},
)
def margin_shock_factor():
    return 1 - margin_shock_size() * shock_active()


@component.add(
    name="new gross",
    units="USD/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "new_sales": 1,
        "vehicles_per_household_purchase": 1,
        "new_gross_per_vehicle": 1,
        "margin_shock_factor": 1,
    },
)
def new_gross():
    return (
        new_sales()
        * vehicles_per_household_purchase()
        * new_gross_per_vehicle()
        * margin_shock_factor()
    )


@component.add(
    name="used gross",
    units="USD/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "used_sales": 1,
        "vehicles_per_household_purchase": 1,
        "used_gross_per_vehicle": 1,
        "used_price_discount": 1,
        "used_retail_price": 1,
    },
)
def used_gross():
    return (
        used_sales()
        * vehicles_per_household_purchase()
        * (used_gross_per_vehicle() - used_price_discount() * used_retail_price())
    )


@component.add(
    name="lease remarketing gain",
    units="USD/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"off_lease_returns": 1, "lease_remarketing_loss_per_vehicle": 1},
)
def lease_remarketing_gain():
    return 0 - off_lease_returns() * lease_remarketing_loss_per_vehicle()


@component.add(
    name="F and I penetration",
    units="Dmnl",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "f_and_i_base_penetration": 1,
        "f_and_i_programme_spend": 1,
        "f_and_i_spend_scale": 1,
        "f_and_i_maximum_penetration_uplift": 1,
    },
)
def f_and_i_penetration():
    return f_and_i_base_penetration() + f_and_i_maximum_penetration_uplift() * (
        1 - float(np.exp(-f_and_i_programme_spend() / f_and_i_spend_scale()))
    )


@component.add(
    name="F and I income",
    units="USD/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "new_sales": 1,
        "used_sales": 1,
        "f_and_i_penetration": 1,
        "f_and_i_gross_per_contract": 1,
        "chargeback_rate": 1,
    },
)
def f_and_i_income():
    return (
        (new_sales() + used_sales())
        * f_and_i_penetration()
        * f_and_i_gross_per_contract()
        * (1 - chargeback_rate())
    )


@component.add(
    name="service gross",
    units="USD/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"ro_done": 1, "gross_per_repair_order": 1},
)
def service_gross():
    return ro_done() * gross_per_repair_order()


@component.add(
    name="parts gross",
    units="USD/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"ro_done": 1, "parts_gross_per_repair_order": 1},
)
def parts_gross():
    return ro_done() * parts_gross_per_repair_order()


@component.add(
    name="total gross",
    units="USD/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "new_gross": 1,
        "used_gross": 1,
        "lease_remarketing_gain": 1,
        "f_and_i_income": 1,
        "service_gross": 1,
        "parts_gross": 1,
    },
)
def total_gross():
    return (
        new_gross()
        + used_gross()
        + lease_remarketing_gain()
        + f_and_i_income()
        + service_gross()
        + parts_gross()
    )


@component.add(
    name="commissions",
    units="USD/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "commission_rate": 1,
        "new_gross": 1,
        "f_and_i_income": 1,
        "used_gross": 1,
    },
)
def commissions():
    return commission_rate() * (new_gross() + used_gross() + f_and_i_income())


@component.add(
    name="technician payroll",
    units="USD/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"technicians": 1, "technician_cost_monthly": 1},
)
def technician_payroll():
    return technicians() * technician_cost_monthly()


@component.add(
    name="wholesale loss",
    units="USD/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"wholesale_exits": 1, "wholesale_loss_per_vehicle": 1},
)
def wholesale_loss():
    return wholesale_exits() * wholesale_loss_per_vehicle()


@component.add(
    name="floorplan rate effective",
    units="1/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "floorplan_rate_monthly": 1,
        "rate_shock_size": 1,
        "months_per_year": 1,
        "shock_active": 1,
    },
)
def floorplan_rate_effective():
    return (
        floorplan_rate_monthly()
        + rate_shock_size() / months_per_year() * shock_active()
    )


@component.add(
    name="floorplan interest",
    units="USD/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"floorplan_debt": 1, "floorplan_rate_effective": 1},
)
def floorplan_interest():
    return floorplan_debt() * floorplan_rate_effective()


@component.add(
    name="net profit",
    units="USD/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "total_gross": 1,
        "commissions": 1,
        "marketing_spend": 1,
        "f_and_i_programme_spend": 1,
        "technician_payroll": 1,
        "wholesale_loss": 1,
        "fixed_overhead": 1,
        "floorplan_interest": 1,
    },
)
def net_profit():
    return (
        total_gross()
        - commissions()
        - marketing_spend()
        - f_and_i_programme_spend()
        - technician_payroll()
        - wholesale_loss()
        - fixed_overhead()
        - floorplan_interest()
    )


@component.add(
    name="net cash flow",
    units="USD/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "net_profit": 1,
        "used_acquisitions": 1,
        "used_vehicle_unit_cost": 1,
        "deliveries": 1,
        "inventory_cost_released": 1,
        "new_vehicle_unit_cost": 1,
        "advance_rate": 1,
    },
)
def net_cash_flow():
    return net_profit() - (1 - advance_rate()) * (
        deliveries() * new_vehicle_unit_cost()
        + used_acquisitions() * used_vehicle_unit_cost()
        - inventory_cost_released()
    )


@component.add(
    name="Cash",
    units="USD",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"initial_cash": 1, "cash_received": 1, "cash_paid_out": 1},
)
def cash():
    return initial_cash() + cash_received() - cash_paid_out()


@component.add(
    name="Cumulative Net Profit",
    units="USD",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"cumulative_profit_earned": 1, "cumulative_loss_incurred": 1},
)
def cumulative_net_profit():
    return cumulative_profit_earned() - cumulative_loss_incurred()


@component.add(
    name="Cumulative Discounted Cash Flow",
    units="USD",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "cumulative_discounted_cash_received": 1,
        "cumulative_discounted_cash_paid": 1,
    },
)
def cumulative_discounted_cash_flow():
    return cumulative_discounted_cash_received() - cumulative_discounted_cash_paid()


@component.add(
    name="discount factor",
    units="Dmnl",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"discount_rate_monthly": 1, "time": 1},
)
def discount_factor():
    return float(np.exp(-discount_rate_monthly() * time()))


@component.add(
    name="discounted net cash flow",
    units="USD/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"net_cash_flow": 1, "discount_factor": 1},
)
def discounted_net_cash_flow():
    return net_cash_flow() * discount_factor()


@component.add(
    name="absorption rate",
    units="Dmnl",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={
        "service_gross": 1,
        "parts_gross": 1,
        "technician_payroll": 1,
        "fixed_overhead": 1,
    },
)
def absorption_rate():
    return (service_gross() + parts_gross() - technician_payroll()) / fixed_overhead()


@component.add(
    name="floorplan rate monthly",
    units="1/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"floorplan_rate": 1, "months_per_year": 1},
)
def floorplan_rate_monthly():
    return floorplan_rate() / months_per_year()


@component.add(
    name="discount rate monthly",
    units="1/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"discount_rate": 1, "months_per_year": 1},
)
def discount_rate_monthly():
    return discount_rate() / months_per_year()


@component.add(
    name="shopping rate monthly",
    units="1/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"shopping_rate": 1, "months_per_year": 1},
)
def shopping_rate_monthly():
    return shopping_rate() / months_per_year()


@component.add(
    name="base defection rate monthly",
    units="1/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"base_defection_rate": 1, "months_per_year": 1},
)
def base_defection_rate_monthly():
    return base_defection_rate() / months_per_year()


@component.add(
    name="attrition rate monthly",
    units="1/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"attrition_rate": 1, "months_per_year": 1},
)
def attrition_rate_monthly():
    return attrition_rate() / months_per_year()


@component.add(
    name="wholesale exit rate monthly",
    units="1/Month",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"wholesale_exit_rate": 1, "months_per_year": 1},
)
def wholesale_exit_rate_monthly():
    return wholesale_exit_rate() / months_per_year()


@component.add(
    name="visits per customer monthly",
    units="RO/(Household*Month)",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"visits_per_customer": 1, "months_per_year": 1},
)
def visits_per_customer_monthly():
    return visits_per_customer() / months_per_year()


@component.add(
    name="technician cost monthly",
    units="USD/(Technician*Month)",
    comp_type="Auxiliary",
    comp_subtype="Normal",
    depends_on={"technician_cost": 1, "months_per_year": 1},
)
def technician_cost_monthly():
    return technician_cost() / months_per_year()


@component.add(
    name="shopping rate",
    units="1/Year",
    limits=(0.0, 24.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def shopping_rate():
    """
    Range 3 to 10, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 6


@component.add(
    name="new share of shoppers",
    units="Dmnl",
    limits=(0.05, 0.95),
    comp_type="Constant",
    comp_subtype="Normal",
)
def new_share_of_shoppers():
    """
    fixed in the Monte Carlo (a store policy or scenario input); lever range 0.35 to 0.75 for exploration. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0.55


@component.add(
    name="market entry rate",
    units="Household/Month",
    limits=(0.0, 1000.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def market_entry_rate():
    """
    Range 45 to 95, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 70


@component.add(
    name="maximum marketing starts",
    units="Household/Month",
    limits=(0.0, 500.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def maximum_marketing_starts():
    """
    Range 15 to 50, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 30


@component.add(
    name="marketing spend scale",
    units="USD/Month",
    limits=(100.0, 10000000.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def marketing_spend_scale():
    """
    Range 10000 to 50000, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 20000


@component.add(
    name="marketing spend",
    units="USD/Month",
    limits=(0.0, 10000000.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def marketing_spend():
    """
    fixed in the Monte Carlo (a store policy or scenario input); lever range 0 to 60000 for exploration. Confidence: estimated. Source: assumptions_register.md.
    """
    return 25000


@component.add(
    name="availability constant new",
    units="Vehicle",
    limits=(0.5, 200.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def availability_constant_new():
    """
    Range 4 to 16, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 8


@component.add(
    name="target new days supply",
    units="Day",
    limits=(5.0, 200.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def target_new_days_supply():
    """
    fixed in the Monte Carlo (a store policy or scenario input); lever range 60 to 60 for exploration. Confidence: estimated. Source: assumptions_register.md.
    """
    return 60


@component.add(
    name="new inventory adjustment time",
    units="Month",
    limits=(0.1, 24.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def new_inventory_adjustment_time():
    """
    Range 1 to 3, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 1.5


@component.add(
    name="order lead time",
    units="Month",
    limits=(0.1, 12.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def order_lead_time():
    """
    Range 0.5 to 2, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 1


@component.add(
    name="manufacturer allocation",
    units="Vehicle/Month",
    limits=(0.0, 2000.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def manufacturer_allocation():
    """
    Range 120 to 220, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 160


@component.add(
    name="allocation response strength",
    units="Dmnl",
    limits=(0.0, 1.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def allocation_response_strength():
    """
    Range 0 to 0.8, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0


@component.add(
    name="allocation memory",
    units="Month",
    limits=(0.5, 36.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def allocation_memory():
    """
    Range 3 to 12, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 6


@component.add(
    name="availability constant used",
    units="Vehicle",
    limits=(0.5, 200.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def availability_constant_used():
    """
    Range 4 to 16, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 8


@component.add(
    name="discount demand sensitivity",
    units="Dmnl",
    limits=(0.0, 3.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def discount_demand_sensitivity():
    """
    Range 0.5 to 3, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 1.5


@component.add(
    name="discount sensitivity",
    units="Dmnl",
    limits=(0.0, 0.3),
    comp_type="Constant",
    comp_subtype="Normal",
)
def discount_sensitivity():
    """
    Range 0.05 to 0.3, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0.15


@component.add(
    name="maximum price discount",
    units="Dmnl",
    limits=(0.05, 0.5),
    comp_type="Constant",
    comp_subtype="Normal",
)
def maximum_price_discount():
    """
    Range 0.15 to 0.35, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0.25


@component.add(
    name="target used days supply",
    units="Day",
    limits=(5.0, 150.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def target_used_days_supply():
    """
    fixed in the Monte Carlo (a store policy or scenario input); lever range 30 to 80 for exploration. Confidence: estimated. Source: assumptions_register.md.
    """
    return 45


@component.add(
    name="used sales memory",
    units="Month",
    limits=(0.5, 24.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def used_sales_memory():
    """
    Range 1 to 4, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 2


@component.add(
    name="used inventory adjustment time",
    units="Month",
    limits=(0.1, 24.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def used_inventory_adjustment_time():
    """
    Range 1 to 3, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 1.5


@component.add(
    name="reconditioning time",
    units="Month",
    limits=(0.1, 6.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def reconditioning_time():
    """
    Range 0.25 to 1, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0.5


@component.add(
    name="wholesale exit rate",
    units="1/Year",
    limits=(0.0, 5.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def wholesale_exit_rate():
    """
    Range 0.25 to 1, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0.5


@component.add(
    name="trade in share",
    units="Dmnl",
    limits=(0.0, 1.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def trade_in_share():
    """
    Range 0.15 to 0.4, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0.25


@component.add(
    name="off lease return share",
    units="Dmnl",
    limits=(0.0, 1.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def off_lease_return_share():
    """
    Range 0.6 to 0.95, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0.8


@component.add(
    name="lease remarketing loss per vehicle",
    units="USD/Vehicle",
    limits=(-5000.0, 5000.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def lease_remarketing_loss_per_vehicle():
    """
    Range -1000 to 1500, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 200


@component.add(
    name="used retail price",
    units="USD/Vehicle",
    limits=(5000.0, 100000.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def used_retail_price():
    """
    Range 24000 to 32000, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 28000


@component.add(
    name="used vehicle unit cost",
    units="USD/Vehicle",
    limits=(5000.0, 100000.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def used_vehicle_unit_cost():
    """
    Range 22000 to 30000, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 26500


@component.add(
    name="lease share",
    units="Dmnl",
    limits=(0.0, 0.9),
    comp_type="Constant",
    comp_subtype="Normal",
)
def lease_share():
    """
    fixed in the Monte Carlo (a store policy or scenario input); lever range 0.1 to 0.5 for exploration. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0.25


@component.add(
    name="lease term",
    units="Month",
    limits=(12.0, 60.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def lease_term():
    """
    Range 24 to 48, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 36


@component.add(
    name="ownership period",
    units="Month",
    limits=(12.0, 240.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def ownership_period():
    """
    Range 48 to 96, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 66


@component.add(
    name="loyalty floor",
    units="Dmnl",
    limits=(0.0, 0.3),
    comp_type="Constant",
    comp_subtype="Normal",
)
def loyalty_floor():
    """
    Range 0.05 to 0.2, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0.1


@component.add(
    name="loyalty ceiling",
    units="Dmnl",
    limits=(0.3, 1.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def loyalty_ceiling():
    """
    Range 0.4 to 0.75, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0.6


@component.add(
    name="loyalty half saturation",
    units="Dmnl",
    limits=(0.1, 10.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def loyalty_half_saturation():
    """
    Range 0.5 to 3, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 1.5


@component.add(
    name="service capture share",
    units="Dmnl",
    limits=(0.0, 6.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def service_capture_share():
    """
    fixed in the Monte Carlo (a store policy or scenario input); lever range 1.6 to 3.2 for exploration. Confidence: estimated. Source: assumptions_register.md.
    """
    return 2.2


@component.add(
    name="base defection rate",
    units="1/Year",
    limits=(0.0, 2.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def base_defection_rate():
    """
    Range 0.15 to 0.4, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0.25


@component.add(
    name="visits per customer",
    units="RO/(Household*Year)",
    limits=(0.1, 6.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def visits_per_customer():
    """
    Range 1 to 2.2, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 1.5


@component.add(
    name="repairs per technician",
    units="RO/(Technician*Month)",
    limits=(10.0, 300.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def repairs_per_technician():
    """
    Range 60 to 100, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 80


@component.add(
    name="retention loss when overloaded",
    units="Dmnl",
    limits=(0.0, 1.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def retention_loss_when_overloaded():
    """
    Range 0 to 0.6, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0


@component.add(
    name="technician target",
    units="Technician",
    limits=(0.0, 200.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def technician_target():
    """
    fixed in the Monte Carlo (a store policy or scenario input); lever range 20 to 34 for exploration. Confidence: estimated. Source: assumptions_register.md.
    """
    return 28


@component.add(
    name="hire time",
    units="Month",
    limits=(0.5, 24.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def hire_time():
    """
    Range 1.5 to 6, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 3


@component.add(
    name="attrition rate",
    units="1/Year",
    limits=(0.0, 2.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def attrition_rate():
    """
    Range 0.15 to 0.4, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0.25


@component.add(
    name="gross per repair order",
    units="USD/RO",
    limits=(0.0, 2000.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def gross_per_repair_order():
    """
    Range 120 to 220, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 165


@component.add(
    name="parts gross per repair order",
    units="USD/RO",
    limits=(0.0, 2000.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def parts_gross_per_repair_order():
    """
    Range 70 to 140, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 103


@component.add(
    name="technician cost",
    units="USD/(Technician*Year)",
    limits=(10000.0, 300000.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def technician_cost():
    """
    Range 55000 to 90000, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 70000


@component.add(
    name="F and I base penetration",
    units="Dmnl",
    limits=(0.0, 0.92),
    comp_type="Constant",
    comp_subtype="Normal",
)
def f_and_i_base_penetration():
    """
    Range 0.7 to 0.92, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0.85


@component.add(
    name="F and I maximum penetration uplift",
    units="Dmnl",
    limits=(0.0, 0.08),
    comp_type="Constant",
    comp_subtype="Normal",
)
def f_and_i_maximum_penetration_uplift():
    """
    Range 0 to 0.08, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0.05


@component.add(
    name="F and I spend scale",
    units="USD/Month",
    limits=(100.0, 10000000.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def f_and_i_spend_scale():
    """
    Range 5000 to 30000, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 10000


@component.add(
    name="F and I programme spend",
    units="USD/Month",
    limits=(0.0, 10000000.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def f_and_i_programme_spend():
    """
    fixed in the Monte Carlo (a store policy or scenario input); lever range 0 to 20000 for exploration. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0


@component.add(
    name="F and I gross per contract",
    units="USD/Household",
    limits=(0.0, 20000.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def f_and_i_gross_per_contract():
    """
    Range 1500 to 2600, triangular. Confidence: reported. Source: assumptions_register.md.
    """
    return 2050


@component.add(
    name="chargeback rate",
    units="Dmnl",
    limits=(0.0, 1.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def chargeback_rate():
    """
    Range 0.05 to 0.2, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0.1


@component.add(
    name="new gross per vehicle",
    units="USD/Vehicle",
    limits=(-5000.0, 20000.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def new_gross_per_vehicle():
    """
    Range 1200 to 3200, triangular. Confidence: reported. Source: assumptions_register.md.
    """
    return 2250


@component.add(
    name="used gross per vehicle",
    units="USD/Vehicle",
    limits=(-5000.0, 20000.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def used_gross_per_vehicle():
    """
    Range 900 to 1900, triangular. Confidence: reported. Source: assumptions_register.md.
    """
    return 1400


@component.add(
    name="fixed overhead",
    units="USD/Month",
    limits=(1000.0, 100000000.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def fixed_overhead():
    """
    Range 400000 to 650000, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 530000


@component.add(
    name="commission rate",
    units="Dmnl",
    limits=(0.0, 1.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def commission_rate():
    """
    Range 0.15 to 0.3, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0.25


@component.add(
    name="wholesale loss per vehicle",
    units="USD/Vehicle",
    limits=(0.0, 20000.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def wholesale_loss_per_vehicle():
    """
    Range 600 to 2000, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 1200


@component.add(
    name="new vehicle unit cost",
    units="USD/Vehicle",
    limits=(5000.0, 150000.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def new_vehicle_unit_cost():
    """
    Range 40000 to 50000, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 45000


@component.add(
    name="advance rate",
    units="Dmnl",
    limits=(0.0, 1.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def advance_rate():
    """
    Range 0.8 to 1, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0.9


@component.add(
    name="floorplan rate",
    units="1/Year",
    limits=(0.0, 0.5),
    comp_type="Constant",
    comp_subtype="Normal",
)
def floorplan_rate():
    """
    Range 0.05 to 0.1, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0.07


@component.add(
    name="discount rate",
    units="1/Year",
    limits=(0.0, 1.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def discount_rate():
    """
    Range 0.07 to 0.15, triangular. Confidence: estimated. Source: assumptions_register.md.
    """
    return 0.1


@component.add(
    name="margin shock size",
    units="Dmnl",
    limits=(0.0, 1.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def margin_shock_size():
    """
    fixed in the Monte Carlo (a store policy or scenario input); lever range 0 to 0.5 for exploration. Confidence: verified. Source: assumptions_register.md.
    """
    return 0


@component.add(
    name="rate shock size",
    units="1/Year",
    limits=(0.0, 0.2),
    comp_type="Constant",
    comp_subtype="Normal",
)
def rate_shock_size():
    """
    fixed in the Monte Carlo (a store policy or scenario input); lever range 0 to 0.08 for exploration. Confidence: verified. Source: assumptions_register.md.
    """
    return 0


@component.add(
    name="demand shock size",
    units="Dmnl",
    limits=(0.0, 1.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def demand_shock_size():
    """
    fixed in the Monte Carlo (a store policy or scenario input); lever range 0 to 0.4 for exploration. Confidence: verified. Source: assumptions_register.md.
    """
    return 0


@component.add(
    name="shock start month",
    units="Month",
    limits=(0.0, 180.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def shock_start_month():
    """
    fixed in the Monte Carlo (a store policy or scenario input); lever range 0 to 60 for exploration. Confidence: verified. Source: assumptions_register.md.
    """
    return 24


@component.add(
    name="shock duration",
    units="Month",
    limits=(0.0, 180.0),
    comp_type="Constant",
    comp_subtype="Normal",
)
def shock_duration():
    """
    fixed in the Monte Carlo (a store policy or scenario input); lever range 0 to 36 for exploration. Confidence: verified. Source: assumptions_register.md.
    """
    return 12


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


@component.add(
    name="days per month",
    units="Day/Month",
    comp_type="Constant",
    comp_subtype="Normal",
)
def days_per_month():
    """
    Unit conversion (365/12 rounded).
    """
    return 30.4


@component.add(
    name="vehicles per household purchase",
    units="Vehicle/Household",
    comp_type="Constant",
    comp_subtype="Normal",
)
def vehicles_per_household_purchase():
    """
    One vehicle per household purchase; unit conversion.
    """
    return 1


@component.add(
    name="number of lease stages",
    units="Dmnl",
    comp_type="Constant",
    comp_subtype="Normal",
)
def number_of_lease_stages():
    """
    Three-stage chain gives the lease term a spread of lease lengths.
    """
    return 3


@component.add(
    name="simulation horizon",
    units="Month",
    comp_type="Constant",
    comp_subtype="Normal",
)
def simulation_horizon():
    """
    Gate 1: 180 months; sizes the source stocks so they never go negative.
    """
    return 180


@component.add(
    name="minimum owner base",
    units="Household",
    comp_type="Constant",
    comp_subtype="Normal",
)
def minimum_owner_base():
    """
    Guard against dividing by zero; inactive at base.
    """
    return 1


@component.add(
    name="minimum used sales rate",
    units="Vehicle/Month",
    comp_type="Constant",
    comp_subtype="Normal",
)
def minimum_used_sales_rate():
    """
    Guard against dividing by zero; inactive at base.
    """
    return 1


@component.add(
    name="minimum sellout time",
    units="Month",
    comp_type="Constant",
    comp_subtype="Normal",
)
def minimum_sellout_time():
    """
    Physical limit: sales cannot empty the lot faster than this (about a week); inactive at base.
    """
    return 0.25


@component.add(
    name="initial prospects",
    units="Household",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def initial_prospects():
    """
    Fixed. Base-parameter steady state from settle.py (assumptions_register.md); not sampled.
    """
    return 315.4554853


@component.add(
    name="initial owners",
    units="Household",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def initial_owners():
    """
    Fixed. Base-parameter steady state from settle.py (assumptions_register.md); not sampled.
    """
    return 8318.053174


@component.add(
    name="initial lessees per stage",
    units="Household",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def initial_lessees_per_stage():
    """
    Fixed. Base-parameter steady state from settle.py (assumptions_register.md); not sampled.
    """
    return 248.0907754


@component.add(
    name="initial new inventory",
    units="Vehicle",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def initial_new_inventory():
    """
    Fixed. Base-parameter steady state from settle.py (assumptions_register.md); not sampled.
    """
    return 163.2176154


@component.add(
    name="initial new vehicles on order",
    units="Vehicle",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def initial_new_vehicles_on_order():
    """
    Fixed. Base-parameter steady state from settle.py (assumptions_register.md); not sampled.
    """
    return 82.69692513


@component.add(
    name="initial used frontline inventory",
    units="Vehicle",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def initial_used_frontline_inventory():
    """
    Fixed. Base-parameter steady state from settle.py (assumptions_register.md); not sampled.
    """
    return 87.94660474


@component.add(
    name="initial reconditioning pipeline",
    units="Vehicle",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def initial_reconditioning_pipeline():
    """
    Fixed. Base-parameter steady state from settle.py (assumptions_register.md); not sampled.
    """
    return 33.70488081


@component.add(
    name="initial service customers",
    units="Household",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def initial_service_customers():
    """
    Fixed. Base-parameter steady state from settle.py (assumptions_register.md); not sampled.
    """
    return 15492.0839


@component.add(
    name="initial technicians",
    units="Technician",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def initial_technicians():
    """
    Fixed. Base-parameter steady state from settle.py (assumptions_register.md); not sampled.
    """
    return 26.35294118


@component.add(
    name="initial inventory at cost",
    units="USD",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def initial_inventory_at_cost():
    """
    Fixed. Base-parameter steady state from settle.py (assumptions_register.md); not sampled.
    """
    return 10568557.06


@component.add(
    name="initial floorplan debt",
    units="USD",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def initial_floorplan_debt():
    """
    Fixed. Base-parameter steady state from settle.py (assumptions_register.md); not sampled.
    """
    return 9511701.353


@component.add(
    name="initial cash",
    units="USD",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def initial_cash():
    """
    Fixed. Base-parameter steady state from settle.py (assumptions_register.md); not sampled.
    """
    return 1500000


@component.add(
    name="reference new sales",
    units="Household/Month",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def reference_new_sales():
    """
    Fixed. Base-parameter steady state from settle.py (assumptions_register.md); not sampled.
    """
    return 82.69692513


@component.add(
    name="reference used sales",
    units="Household/Month",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def reference_used_sales():
    """
    Fixed. Base-parameter steady state from settle.py (assumptions_register.md); not sampled.
    """
    return 64.00841485


@component.add(
    name="initial used supply outside",
    units="Vehicle",
    limits=(0.0, np.nan),
    comp_type="Constant",
    comp_subtype="Normal",
)
def initial_used_supply_outside():
    """
    Fixed. Base-parameter steady state from settle.py (assumptions_register.md); not sampled.
    """
    return 1000000
