"""Verbatim copies from verification/common.py. Do not edit by hand: regenerate with
trends/tests/sync_definitions.py --write (MIT side) and check with trends/tests/test_parity.py.
"""
import pandas as pd


EQUIP_KEEP = {'Serial Number': 'serial', 'Account Name': 'account', 'Model': 'model', 'Product Family': 'family',
              'Service Status': 'service_status', 'Service Plan': 'service_plan',
              'Equipment Ownership': 'ownership', 'Shipping Country': 'country'}

EQUIP_DATES = {'install_date': 'Install Date', 'go_live_date': 'Go Live Date'}

EQUIP_PRIVATE_COLUMNS = ['Serial Number', 'Account Name', 'Hospital Address', 'Hospital City', 'Hospital Zip Code',
                         'Phone', 'Location', 'Poll Position', 'Vendor Credentialing Notes']

def clean(x):
    """Zac's identifier cleaner: strip whitespace, blank -> None (NaN-safe under pandas 3)."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    return None if str(x).strip() == '' else str(x).strip()

def _timestamp(value):
    """Element-wise equivalent of cell 4's pd.to_datetime(...).dt.strftime for mixed cells."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str):
        value = pd.to_datetime(value)
    return pd.Timestamp(value).strftime('%Y-%m-%d %H:%M:%S')

CASE_VIEWS = """
DROP VIEW IF EXISTS case_base;
CREATE VIEW case_base AS
SELECT c.*, substr(opened_at,1,7) month,
 COALESCE(trouble_code,'[Missing]') || ' / ' || COALESCE(category,'[Missing]') || ' / ' || COALESCE(subcategory,'[Missing]') AS issue_path,
 CASE WHEN trouble_code IN ('Preventative Maintenance','Installation') OR record_type='Install Case' THEN 'Planned work'
      WHEN category='Cancelled Request' THEN 'Cancelled request'
      WHEN category='Duplicate Case' THEN 'Duplicate case'
      WHEN category='No Trouble Found' THEN 'No Trouble Found'
      WHEN trouble_code IS NULL THEN 'Missing trouble code'
      ELSE 'Other recorded issue' END service_group
FROM cases c;
DROP VIEW IF EXISTS service_cases;
CREATE VIEW service_cases AS SELECT * FROM case_base
WHERE service_group NOT IN ('Planned work','Cancelled request','Duplicate case');
"""
