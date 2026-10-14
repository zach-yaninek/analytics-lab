# Follow-up summary (db_followup.py)

Database `ipa_transaction_events_202508_202608.db`; elapsed 175.5 s; checks {'PASS': 4}.

| part | status | seconds | note |
|---|---|---:|---|
| setup | done | 2.7 | 7183 devices, 7471 tickets, 6113 device-matched |
| F4 | done | 8.3 | 7183 devices; 847 locations |
| F3 | done | 26.5 | 30 pilot tickets |
| F5 | done | 29.2 | 1,500,000 sampled rows |
| F1 | done | 108.7 | 6113 tickets on 3041 machines; 16,861,716 events read |

## Key facts

### setup
- **transaction_events_columns**: ["external_device_id", "event_time_utc", "transaction_time_utc", "transaction_time_local", "transaction_date_local", "event_time_offset", "transaction_code"]
- **devices_columns**: ["device_uuid", "external_device_id", "device_status", "location_name", "city", "state", "country", "ip_address", "subnet_mask", "cpu_firmware", "machine_type", "clearview_url"]

### F4
- **devices with a location_name**: 6732
- **distinct locations (normalised)**: 847
- **ticketed devices: location_name vs ticket account**: {"exact": 2972, "normalised": 38, "different": 15, "missing": 15, "contained": 1}
- **ticketed devices: device state vs ticket state**: {"same": 3011, "missing": 25, "different": 5}
- **fleet share by location class (%)**: {"Multi-account": 0.92, "No location": 6.28, "No tickets": 6.89, "Single-account": 85.91}
- **devices attributable to one account via location (incl. unticketed)**: 6171
- **accounts with a location-based fleet**: 666

### F3
- **tickets with non-success codes (equal clock / corrected)**: [26, 26]
- **tickets with non-success codes in the 4-5 h Zac missed**: 11
- **rank-1 code unchanged**: "20/26"
- **last-3 events unchanged**: "18/26"
- **last-10 distinct list unchanged**: "19/26"
- **median Jaccard of last-10 distinct sets**: 1.0

### F5
- **sample rows**: 1500000
- **sample rows by device-state zone**: {"Eastern": 1029208, "Central": 236290, "Pacific": 171451, "Mountain": 23650, "Arizona (no DST)": 19577, "Hawaii (no DST)": 18576, "Newfoundland": 682, "Unknown": 566}
- **clock hypotheses consistent with device-state zones**: ["utc"]
- **event_time_offset values (top 15)**: {"0.0": 1499999, "-4.0": 1}
- **share of rows where event_time_offset == UTC offset of device zone**: 0.0
- **share of rows where event_time_offset == minus UTC offset of device zone**: 0.0
- **share of rows where event_time_offset == 0**: 1.0
- **event_time_utc - transaction_time_utc (hours) quantiles**: {"0.01": 0.001, "0.05": 0.002, "0.25": 0.006, "0.5": 0.01, "0.75": 0.014, "0.95": 0.018, "0.99": 0.026}
- **share of rows with event_time_utc == transaction_time_utc**: 0.0

### F1
- **tickets**: 6113
- **machines**: 3041
- **events_read**: 16861716
- **utc_offset_added_hours**: {"4.0": 4151, "5.0": 1962}
- **tickets_with_full_30d_lookback**: 5477
- **all: tickets with any transaction in 30 d**: 4977
- **all: tickets with >=1 non-success code in 30 d**: 4912
- **all: tickets with >=10 distinct non-success codes in 30 d**: 478
- **all: median distinct non-success codes in 30 d**: 5.0
- **all: median hours from rank-1 code to anchor**: 2.4135
- **unplanned: tickets with any transaction in 30 d**: 4832
- **unplanned: tickets with >=1 non-success code in 30 d**: 4768
- **unplanned: tickets with >=10 distinct non-success codes in 30 d**: 463
- **unplanned: median distinct non-success codes in 30 d**: 5.0
- **unplanned: median hours from rank-1 code to anchor**: 2.44
- **last-10 distinct list unchanged with a 30-min guard band (usable tickets with codes)**: "4443/4912"
- **last-10 distinct list unchanged with a 60-min guard band (usable tickets with codes)**: "4197/4912"

### F2
- **clean, complete control windows (paired with usable tickets)**: 3366
- **control window: >=1 non-success code**: 2994
- **control window: median distinct non-success codes**: 4.0
- **same tickets, corrected window: >=1 non-success code**: 3036
- **same tickets, corrected window: median distinct non-success codes**: 5.0

## Checks

| part | check | expected | actual | status |
|---|---|---|---|---|
| setup | device-matched tickets (Zac: 6,113) | 6113 | 6113 | PASS |
| F3 | pilot ids present in this workbook | 30 | 30 | PASS |
| F3 | Zac's equal-clock counts reproduced (30-day window, offset 0) | 30 | 30 | PASS |
| F5 | whole-fleet clock verdict (device-state zones) | ["utc"] | ["utc"] | PASS |
