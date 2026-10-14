"""Core logic of the PFD process-record and investment-estimate app, in Python (PRD 전환 계획 1단계).

Same inputs, same results as apps/pfd-flow-viewer/app.html: PDF reading (pdf.js text items), sheet links,
Equipment List, equipment-cost matching, construction quantities and the investment estimate, and the app's
Excel downloads. Data shapes are the app's record shapes (data-schema.md), so records move between the two.
"""
from .cost import compute_costs, eq_key, expand_tags, load_cost_list, norm_tag, parse_cost_workbook
from .equipment import build_equipment, extract_equipment, link_equipment_to_flow
from .layout import is_layout_sheet, layout_index, split_sheets
from .estimate import default_rates, est_compute, learn_from, load_rates, new_est, read_qty, read_rates
from .pdf import read_pdf
from .sheets import build_links
from .xlsx import read_workbook

__version__ = "0.1.0"
APP_VERSIONS = {"pdf.js": "3.11.174", "SheetJS": "0.18.5"}   # the libraries whose results pfdcore reproduces

__all__ = ["read_pdf", "build_links", "build_equipment", "extract_equipment", "link_equipment_to_flow", "read_workbook",
           "parse_cost_workbook", "load_cost_list", "compute_costs", "eq_key", "norm_tag", "expand_tags",
           "split_sheets", "is_layout_sheet", "layout_index", "read_qty", "read_rates", "default_rates", "load_rates", "learn_from", "new_est", "est_compute"]
