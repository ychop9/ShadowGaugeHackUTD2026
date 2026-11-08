// ONLY used when you open the page with ?sample=1 (to test the UI without the backend).
// This is a REAL response from GET /api/v1/datasets/snapshot_2026-10-08T1200/dashboard,
// trimmed to the facilities with open issues plus one healthy one. Regenerate it from the API
// if the backend's response shape changes.
export default {
 "dataset": "snapshot_2026-10-08T1200",
 "now_ts": "2026-10-08T12:00:00Z",
 "now_unix": 1791460800,
 "time_range": {
  "start_unix": 1791158400,
  "end_unix": 1791460800
 },
 "units": {
  "volume": "bbl",
  "rate": "bpd",
  "gas_rate": "mcfd",
  "pressure": "psi"
 },
 "prices": {
  "oil_per_bbl": 60,
  "gas_per_mcf": 3.0
 },
 "emergency_trucking": {
  "truck_capacity_bbl": 150,
  "cost_per_trip": 905
 },
 "expected_repair_hours": {
  "pump_failure": 6
 },
 "systems": [
  {
   "id": "S1",
   "center": [
    31.85,
    -102.3
   ],
   "truck_yard": [
    31.65,
    -102.6
   ],
   "disposal_site": {
    "id": "S1_DISPOSAL",
    "lat": 31.87,
    "lon": -102.295,
    "pressure_psi": 1050
   },
   "emergency_fleet_size": 2,
   "trucks_assigned": [],
   "trucks_free": 2
  },
  {
   "id": "S2",
   "center": [
    32.25,
    -101.85
   ],
   "truck_yard": [
    32.05,
    -101.5
   ],
   "disposal_site": {
    "id": "S2_DISPOSAL",
    "lat": 32.24,
    "lon": -101.84,
    "pressure_psi": 1000
   },
   "emergency_fleet_size": 2,
   "trucks_assigned": [
    {
     "facility_id": "S2_FACILITY_A",
     "trucks": 1,
     "trips_per_truck": 1
    },
    {
     "facility_id": "S2_FACILITY_B",
     "trucks": 1,
     "trips_per_truck": 1
    }
   ],
   "trucks_free": 0
  },
  {
   "id": "S3",
   "center": [
    31.4,
    -102.8
   ],
   "truck_yard": [
    31.2,
    -102.4
   ],
   "disposal_site": {
    "id": "S3_DISPOSAL",
    "lat": 31.41,
    "lon": -102.8,
    "pressure_psi": 950
   },
   "emergency_fleet_size": 3,
   "trucks_assigned": [],
   "trucks_free": 3
  },
  {
   "id": "S4",
   "center": [
    31.45,
    -101.75
   ],
   "truck_yard": [
    31.7,
    -101.4
   ],
   "disposal_site": {
    "id": "S4_DISPOSAL",
    "lat": 31.47,
    "lon": -101.74,
    "pressure_psi": 1100
   },
   "emergency_fleet_size": 2,
   "trucks_assigned": [],
   "trucks_free": 2
  },
  {
   "id": "S5",
   "center": [
    32.2,
    -102.85
   ],
   "truck_yard": [
    32.5,
    -102.45
   ],
   "disposal_site": {
    "id": "S5_DISPOSAL",
    "lat": 32.2,
    "lon": -102.85,
    "pressure_psi": 1020
   },
   "emergency_fleet_size": 2,
   "trucks_assigned": [],
   "trucks_free": 2
  }
 ],
 "facilities": [
  {
   "id": "S1_FACILITY_A",
   "system_id": "S1",
   "lat": 31.912,
   "lon": -102.34,
   "wells": [
    {
     "id": "S1_WELL_A1",
     "status": 1,
     "water_bpd": 1001.0,
     "baseline_water_bpd": 1000,
     "oil_bpd": 280,
     "gas_mcfd": 1000
    },
    {
     "id": "S1_WELL_A2",
     "status": 1,
     "water_bpd": 798.6,
     "baseline_water_bpd": 800,
     "oil_bpd": 490,
     "gas_mcfd": 1750
    },
    {
     "id": "S1_WELL_A3",
     "status": 1,
     "water_bpd": 600.5,
     "baseline_water_bpd": 600,
     "oil_bpd": 630,
     "gas_mcfd": 2250
    }
   ],
   "inflow_bpd": 2400.1,
   "tank": {
    "id": "S1_TANK_A",
    "capacity_bbl": 1200,
    "level_pct": 68.21,
    "warning_pct": 85,
    "shutdown_pct": 92
   },
   "pump": {
    "id": "S1_PUMP_A",
    "status": 1,
    "state": "running",
    "flow_bpd": 3593.4,
    "max_flow_bpd": 3600,
    "discharge_psi": 1195.5,
    "start_level_pct": 70,
    "stop_level_pct": 30,
    "health": "ok"
   },
   "pipeline": {
    "id": "S1_PIPELINE_A",
    "receive_flow_bpd": 3625.5,
    "pressure_psi": 1106.0,
    "max_bpd": 4000,
    "max_pressure_psi": 1700,
    "normal_running_pressure_psi": 1099.8,
    "health": "ok"
   },
   "issues": []
  },
  {
   "id": "S2_FACILITY_A",
   "system_id": "S2",
   "lat": 32.29,
   "lon": -101.9,
   "wells": [
    {
     "id": "S2_WELL_A1",
     "status": 1,
     "water_bpd": 1091.5,
     "baseline_water_bpd": 1100,
     "oil_bpd": 400,
     "gas_mcfd": 1500
    },
    {
     "id": "S2_WELL_A2",
     "status": 1,
     "water_bpd": 643.3,
     "baseline_water_bpd": 650,
     "oil_bpd": 400,
     "gas_mcfd": 1500
    },
    {
     "id": "S2_WELL_A3",
     "status": 1,
     "water_bpd": 452.5,
     "baseline_water_bpd": 450,
     "oil_bpd": 520,
     "gas_mcfd": 2050
    }
   ],
   "inflow_bpd": 2187.3,
   "tank": {
    "id": "S2_TANK_A",
    "capacity_bbl": 1000,
    "level_pct": 68.18,
    "warning_pct": 85,
    "shutdown_pct": 92
   },
   "pump": {
    "id": "S2_PUMP_A",
    "status": 2,
    "state": "fault",
    "flow_bpd": 0.0,
    "max_flow_bpd": 3300,
    "discharge_psi": 998.1,
    "start_level_pct": 70,
    "stop_level_pct": 30,
    "health": "failed"
   },
   "pipeline": {
    "id": "S2_PIPELINE_A",
    "receive_flow_bpd": 0.0,
    "pressure_psi": 1000.8,
    "max_bpd": 3700,
    "max_pressure_psi": 1650,
    "normal_running_pressure_psi": 1049.8,
    "health": "ok"
   },
   "issues": [
    {
     "event_id": "EV-0013",
     "system_id": "S2",
     "facility_id": "S2_FACILITY_A",
     "asset_id": "S2_PUMP_A",
     "category": "pump_failure",
     "status": "ongoing",
     "onset_ts": "2026-10-08T10:00:00Z",
     "onset_unix": 1791453600,
     "end_ts": null,
     "end_unix": null,
     "confidence": 1.0,
     "evidence": [
      "Pump reports fault status since Thu 10:00 UTC",
      "Tank at 68.2%, reaches shutdown (92%) in 2.6 h if nothing is done"
     ],
     "level_pct": 68.2,
     "hours_to_limit": {
      "p50": 2.6
     },
     "recommended_actions": [
      {
       "type": "dispatch_truck",
       "facility_id": "S2_FACILITY_A",
       "trucks": 1,
       "trips_per_truck": 1
      }
     ],
     "plan_summary": "1 truck, 1 trip (~$905)",
     "est_cost": 905.0,
     "cost_breakdown": {
      "trucks": 905,
      "planned_shut_in": 0.0,
      "automatic_shut_in": 0.0
     },
     "truck_arrivals_min": [
      85
     ],
     "repair_remaining_h": 4.0,
     "lost_revenue_per_hour": 3931.25,
     "do_nothing": {
      "cost": 5502.34,
      "shutdown_after_min": 156
     },
     "savings": 4597.34
    }
   ]
  },
  {
   "id": "S2_FACILITY_B",
   "system_id": "S2",
   "lat": 32.215,
   "lon": -101.8,
   "wells": [
    {
     "id": "S2_WELL_B1",
     "status": 1,
     "water_bpd": 402.9,
     "baseline_water_bpd": 400,
     "oil_bpd": 420,
     "gas_mcfd": 1500
    },
    {
     "id": "S2_WELL_B2",
     "status": 1,
     "water_bpd": 644.9,
     "baseline_water_bpd": 650,
     "oil_bpd": 120,
     "gas_mcfd": 450
    },
    {
     "id": "S2_WELL_B3",
     "status": 1,
     "water_bpd": 544.9,
     "baseline_water_bpd": 550,
     "oil_bpd": 290,
     "gas_mcfd": 1050
    }
   ],
   "inflow_bpd": 1592.8,
   "tank": {
    "id": "S2_TANK_B",
    "capacity_bbl": 700,
    "level_pct": 78.49,
    "warning_pct": 85,
    "shutdown_pct": 92
   },
   "pump": {
    "id": "S2_PUMP_B",
    "status": 2,
    "state": "fault",
    "flow_bpd": 0.0,
    "max_flow_bpd": 2400,
    "discharge_psi": 1000.6,
    "start_level_pct": 70,
    "stop_level_pct": 30,
    "health": "failed"
   },
   "pipeline": {
    "id": "S2_PIPELINE_B",
    "receive_flow_bpd": 0.0,
    "pressure_psi": 1000.2,
    "max_bpd": 2700,
    "max_pressure_psi": 1650,
    "normal_running_pressure_psi": 1049.8,
    "health": "ok"
   },
   "issues": [
    {
     "event_id": "EV-0011",
     "system_id": "S2",
     "facility_id": "S2_FACILITY_B",
     "asset_id": "S2_PUMP_B",
     "category": "pump_failure",
     "status": "ongoing",
     "onset_ts": "2026-10-08T09:00:00Z",
     "onset_unix": 1791450000,
     "end_ts": null,
     "end_unix": null,
     "confidence": 1.0,
     "evidence": [
      "Pump reports fault status since Thu 09:00 UTC",
      "Tank at 78.5%, reaches shutdown (92%) in 1.4 h if nothing is done"
     ],
     "level_pct": 78.5,
     "hours_to_limit": {
      "p50": 1.42
     },
     "recommended_actions": [
      {
       "type": "dispatch_truck",
       "facility_id": "S2_FACILITY_B",
       "trucks": 1,
       "trips_per_truck": 1
      }
     ],
     "plan_summary": "1 truck, 1 trip (~$905)",
     "est_cost": 905.0,
     "cost_breakdown": {
      "trucks": 905,
      "planned_shut_in": 0.0,
      "automatic_shut_in": 0.0
     },
     "truck_arrivals_min": [
      70
     ],
     "repair_remaining_h": 3.0,
     "lost_revenue_per_hour": 2450.0,
     "do_nothing": {
      "cost": 3862.78,
      "shutdown_after_min": 85
     },
     "savings": 2957.78
    }
   ]
  },
  {
   "id": "S2_FACILITY_C",
   "system_id": "S2",
   "lat": 32.18,
   "lon": -101.9,
   "wells": [
    {
     "id": "S2_WELL_C1",
     "status": 1,
     "water_bpd": 600.2,
     "baseline_water_bpd": 600,
     "oil_bpd": 160,
     "gas_mcfd": 600
    },
    {
     "id": "S2_WELL_C2",
     "status": 1,
     "water_bpd": 446.2,
     "baseline_water_bpd": 450,
     "oil_bpd": 280,
     "gas_mcfd": 1000
    },
    {
     "id": "S2_WELL_C3",
     "status": 1,
     "water_bpd": 348.6,
     "baseline_water_bpd": 350,
     "oil_bpd": 370,
     "gas_mcfd": 1350
    }
   ],
   "inflow_bpd": 1395.0,
   "tank": {
    "id": "S2_TANK_C",
    "capacity_bbl": 600,
    "level_pct": 69.47,
    "warning_pct": 85,
    "shutdown_pct": 92
   },
   "pump": {
    "id": "S2_PUMP_C",
    "status": 2,
    "state": "fault",
    "flow_bpd": 0.0,
    "max_flow_bpd": 2100,
    "discharge_psi": 1004.1,
    "start_level_pct": 70,
    "stop_level_pct": 30,
    "health": "failed"
   },
   "pipeline": {
    "id": "S2_PIPELINE_C",
    "receive_flow_bpd": 0.0,
    "pressure_psi": 1001.7,
    "max_bpd": 2400,
    "max_pressure_psi": 1650,
    "normal_running_pressure_psi": 1049.8,
    "health": "ok"
   },
   "issues": [
    {
     "event_id": "EV-0012",
     "system_id": "S2",
     "facility_id": "S2_FACILITY_C",
     "asset_id": "S2_PUMP_C",
     "category": "pump_failure",
     "status": "ongoing",
     "onset_ts": "2026-10-08T09:30:00Z",
     "onset_unix": 1791451800,
     "end_ts": null,
     "end_unix": null,
     "confidence": 1.0,
     "evidence": [
      "Pump reports fault status since Thu 09:30 UTC",
      "Tank at 69.5%, reaches shutdown (92%) in 2.3 h if nothing is done"
     ],
     "level_pct": 69.5,
     "hours_to_limit": {
      "p50": 2.32
     },
     "recommended_actions": [
      {
       "type": "shut_in_wells",
       "wells": [
        "S2_WELL_C1"
       ],
       "start_after_min": 45
      }
     ],
     "plan_summary": "shut in S2_WELL_C1 at +45 min (~$1,306)",
     "est_cost": 1306.25,
     "cost_breakdown": {
      "trucks": 0,
      "planned_shut_in": 1306.25,
      "automatic_shut_in": 0.0
     },
     "truck_arrivals_min": [],
     "repair_remaining_h": 3.5,
     "lost_revenue_per_hour": 2393.75,
     "do_nothing": {
      "cost": 2827.35,
      "shutdown_after_min": 139
     },
     "savings": 1521.1
    }
   ]
  },
  {
   "id": "S3_FACILITY_A",
   "system_id": "S3",
   "lat": 31.44,
   "lon": -102.85,
   "wells": [
    {
     "id": "S3_WELL_A1",
     "status": 1,
     "water_bpd": 845.7,
     "baseline_water_bpd": 850,
     "oil_bpd": 240,
     "gas_mcfd": 900
    },
    {
     "id": "S3_WELL_A2",
     "status": 1,
     "water_bpd": 647.7,
     "baseline_water_bpd": 650,
     "oil_bpd": 420,
     "gas_mcfd": 1550
    },
    {
     "id": "S3_WELL_A3",
     "status": 1,
     "water_bpd": 502.8,
     "baseline_water_bpd": 500,
     "oil_bpd": 540,
     "gas_mcfd": 1950
    }
   ],
   "inflow_bpd": 1996.2,
   "tank": {
    "id": "S3_TANK_A",
    "capacity_bbl": 900,
    "level_pct": 68.21,
    "warning_pct": 85,
    "shutdown_pct": 92
   },
   "pump": {
    "id": "S3_PUMP_A",
    "status": 1,
    "state": "running",
    "flow_bpd": 2675.6,
    "max_flow_bpd": 3000,
    "discharge_psi": 1055.0,
    "start_level_pct": 70,
    "stop_level_pct": 30,
    "health": "degraded"
   },
   "pipeline": {
    "id": "S3_PIPELINE_A",
    "receive_flow_bpd": 2656.6,
    "pressure_psi": 1000.5,
    "max_bpd": 3400,
    "max_pressure_psi": 1600,
    "normal_running_pressure_psi": 999.8,
    "health": "ok"
   },
   "issues": [
    {
     "event_id": "EV-0007",
     "system_id": "S3",
     "facility_id": "S3_FACILITY_A",
     "asset_id": "S3_PUMP_A",
     "category": "pump_degradation",
     "status": "ongoing",
     "onset_ts": "2026-10-07T08:35:00Z",
     "onset_unix": 1791362100,
     "end_ts": null,
     "end_unix": null,
     "confidence": 1.0,
     "evidence": [
      "Pump moving 10.5% less than its rated 3,000 bpd while running",
      "Pipeline flow matches pump flow, so the water is not leaking"
     ],
     "level_pct": null,
     "hours_to_limit": null,
     "recommended_actions": [
      {
       "type": "field_inspection",
       "asset_id": "S3_PUMP_A"
      }
     ]
    }
   ]
  },
  {
   "id": "S4_FACILITY_C",
   "system_id": "S4",
   "lat": 31.39,
   "lon": -101.8,
   "wells": [
    {
     "id": "S4_WELL_C1",
     "status": 1,
     "water_bpd": 1053.4,
     "baseline_water_bpd": 1050,
     "oil_bpd": 350,
     "gas_mcfd": 1250
    },
    {
     "id": "S4_WELL_C2",
     "status": 1,
     "water_bpd": 635.2,
     "baseline_water_bpd": 630,
     "oil_bpd": 350,
     "gas_mcfd": 1250
    },
    {
     "id": "S4_WELL_C3",
     "status": 1,
     "water_bpd": 419.3,
     "baseline_water_bpd": 420,
     "oil_bpd": 470,
     "gas_mcfd": 1700
    }
   ],
   "inflow_bpd": 2107.9,
   "tank": {
    "id": "S4_TANK_C",
    "capacity_bbl": 900,
    "level_pct": 46.15,
    "warning_pct": 85,
    "shutdown_pct": 92
   },
   "pump": {
    "id": "S4_PUMP_C",
    "status": 1,
    "state": "running",
    "flow_bpd": 2874.2,
    "max_flow_bpd": 3150,
    "discharge_psi": 1211.9,
    "start_level_pct": 70,
    "stop_level_pct": 30,
    "health": "degraded"
   },
   "pipeline": {
    "id": "S4_PIPELINE_C",
    "receive_flow_bpd": 2866.5,
    "pressure_psi": 1152.6,
    "max_bpd": 3500,
    "max_pressure_psi": 1630,
    "normal_running_pressure_psi": 1149.8,
    "health": "ok"
   },
   "issues": [
    {
     "event_id": "EV-0008",
     "system_id": "S4",
     "facility_id": "S4_FACILITY_C",
     "asset_id": "S4_PUMP_C",
     "category": "pump_degradation",
     "status": "ongoing",
     "onset_ts": "2026-10-07T16:25:00Z",
     "onset_unix": 1791390300,
     "end_ts": null,
     "end_unix": null,
     "confidence": 1.0,
     "evidence": [
      "Pump moving 8.5% less than its rated 3,150 bpd while running",
      "Pipeline flow matches pump flow, so the water is not leaking"
     ],
     "level_pct": null,
     "hours_to_limit": null,
     "recommended_actions": [
      {
       "type": "field_inspection",
       "asset_id": "S4_PUMP_C"
      }
     ]
    }
   ]
  },
  {
   "id": "S5_FACILITY_B",
   "system_id": "S5",
   "lat": 32.17,
   "lon": -102.8,
   "wells": [
    {
     "id": "S5_WELL_B1",
     "status": 1,
     "water_bpd": 853.9,
     "baseline_water_bpd": 850,
     "oil_bpd": 280,
     "gas_mcfd": 1000
    },
    {
     "id": "S5_WELL_B2",
     "status": 1,
     "water_bpd": 505.3,
     "baseline_water_bpd": 510,
     "oil_bpd": 280,
     "gas_mcfd": 1000
    },
    {
     "id": "S5_WELL_B3",
     "status": 1,
     "water_bpd": 346.6,
     "baseline_water_bpd": 340,
     "oil_bpd": 370,
     "gas_mcfd": 1400
    }
   ],
   "inflow_bpd": 1705.7,
   "tank": {
    "id": "S5_TANK_B",
    "capacity_bbl": 750,
    "level_pct": 42.98,
    "warning_pct": 85,
    "shutdown_pct": 92
   },
   "pump": {
    "id": "S5_PUMP_B",
    "status": 1,
    "state": "running",
    "flow_bpd": 2548.7,
    "max_flow_bpd": 2550,
    "discharge_psi": 1173.6,
    "start_level_pct": 70,
    "stop_level_pct": 30,
    "health": "ok"
   },
   "pipeline": {
    "id": "S5_PIPELINE_B",
    "receive_flow_bpd": 2446.6,
    "pressure_psi": 1038.7,
    "max_bpd": 2900,
    "max_pressure_psi": 1670,
    "normal_running_pressure_psi": 1069.8,
    "health": "leak"
   },
   "issues": [
    {
     "event_id": "EV-0010",
     "system_id": "S5",
     "facility_id": "S5_FACILITY_B",
     "asset_id": "S5_PIPELINE_B",
     "category": "pipeline_leak",
     "status": "ongoing",
     "onset_ts": "2026-10-08T06:10:00Z",
     "onset_unix": 1791439800,
     "end_ts": null,
     "end_unix": null,
     "confidence": 1.0,
     "evidence": [
      "3.4% of pumped water is not arriving at disposal",
      "Pipeline pressure 32 psi below normal"
     ],
     "level_pct": null,
     "hours_to_limit": null,
     "recommended_actions": [
      {
       "type": "field_inspection",
       "asset_id": "S5_PIPELINE_B"
      }
     ]
    }
   ]
  }
 ],
 "alerts": [
  {
   "event_id": "EV-0011",
   "system_id": "S2",
   "facility_id": "S2_FACILITY_B",
   "asset_id": "S2_PUMP_B",
   "category": "pump_failure",
   "status": "ongoing",
   "onset_ts": "2026-10-08T09:00:00Z",
   "onset_unix": 1791450000,
   "end_ts": null,
   "end_unix": null,
   "confidence": 1.0,
   "evidence": [
    "Pump reports fault status since Thu 09:00 UTC",
    "Tank at 78.5%, reaches shutdown (92%) in 1.4 h if nothing is done"
   ],
   "level_pct": 78.5,
   "hours_to_limit": {
    "p50": 1.42
   },
   "recommended_actions": [
    {
     "type": "dispatch_truck",
     "facility_id": "S2_FACILITY_B",
     "trucks": 1,
     "trips_per_truck": 1
    }
   ],
   "plan_summary": "1 truck, 1 trip (~$905)",
   "est_cost": 905.0,
   "cost_breakdown": {
    "trucks": 905,
    "planned_shut_in": 0.0,
    "automatic_shut_in": 0.0
   },
   "truck_arrivals_min": [
    70
   ],
   "repair_remaining_h": 3.0,
   "lost_revenue_per_hour": 2450.0,
   "do_nothing": {
    "cost": 3862.78,
    "shutdown_after_min": 85
   },
   "savings": 2957.78
  },
  {
   "event_id": "EV-0012",
   "system_id": "S2",
   "facility_id": "S2_FACILITY_C",
   "asset_id": "S2_PUMP_C",
   "category": "pump_failure",
   "status": "ongoing",
   "onset_ts": "2026-10-08T09:30:00Z",
   "onset_unix": 1791451800,
   "end_ts": null,
   "end_unix": null,
   "confidence": 1.0,
   "evidence": [
    "Pump reports fault status since Thu 09:30 UTC",
    "Tank at 69.5%, reaches shutdown (92%) in 2.3 h if nothing is done"
   ],
   "level_pct": 69.5,
   "hours_to_limit": {
    "p50": 2.32
   },
   "recommended_actions": [
    {
     "type": "shut_in_wells",
     "wells": [
      "S2_WELL_C1"
     ],
     "start_after_min": 45
    }
   ],
   "plan_summary": "shut in S2_WELL_C1 at +45 min (~$1,306)",
   "est_cost": 1306.25,
   "cost_breakdown": {
    "trucks": 0,
    "planned_shut_in": 1306.25,
    "automatic_shut_in": 0.0
   },
   "truck_arrivals_min": [],
   "repair_remaining_h": 3.5,
   "lost_revenue_per_hour": 2393.75,
   "do_nothing": {
    "cost": 2827.35,
    "shutdown_after_min": 139
   },
   "savings": 1521.1
  },
  {
   "event_id": "EV-0013",
   "system_id": "S2",
   "facility_id": "S2_FACILITY_A",
   "asset_id": "S2_PUMP_A",
   "category": "pump_failure",
   "status": "ongoing",
   "onset_ts": "2026-10-08T10:00:00Z",
   "onset_unix": 1791453600,
   "end_ts": null,
   "end_unix": null,
   "confidence": 1.0,
   "evidence": [
    "Pump reports fault status since Thu 10:00 UTC",
    "Tank at 68.2%, reaches shutdown (92%) in 2.6 h if nothing is done"
   ],
   "level_pct": 68.2,
   "hours_to_limit": {
    "p50": 2.6
   },
   "recommended_actions": [
    {
     "type": "dispatch_truck",
     "facility_id": "S2_FACILITY_A",
     "trucks": 1,
     "trips_per_truck": 1
    }
   ],
   "plan_summary": "1 truck, 1 trip (~$905)",
   "est_cost": 905.0,
   "cost_breakdown": {
    "trucks": 905,
    "planned_shut_in": 0.0,
    "automatic_shut_in": 0.0
   },
   "truck_arrivals_min": [
    85
   ],
   "repair_remaining_h": 4.0,
   "lost_revenue_per_hour": 3931.25,
   "do_nothing": {
    "cost": 5502.34,
    "shutdown_after_min": 156
   },
   "savings": 4597.34
  },
  {
   "event_id": "EV-0007",
   "system_id": "S3",
   "facility_id": "S3_FACILITY_A",
   "asset_id": "S3_PUMP_A",
   "category": "pump_degradation",
   "status": "ongoing",
   "onset_ts": "2026-10-07T08:35:00Z",
   "onset_unix": 1791362100,
   "end_ts": null,
   "end_unix": null,
   "confidence": 1.0,
   "evidence": [
    "Pump moving 10.5% less than its rated 3,000 bpd while running",
    "Pipeline flow matches pump flow, so the water is not leaking"
   ],
   "level_pct": null,
   "hours_to_limit": null,
   "recommended_actions": [
    {
     "type": "field_inspection",
     "asset_id": "S3_PUMP_A"
    }
   ]
  },
  {
   "event_id": "EV-0008",
   "system_id": "S4",
   "facility_id": "S4_FACILITY_C",
   "asset_id": "S4_PUMP_C",
   "category": "pump_degradation",
   "status": "ongoing",
   "onset_ts": "2026-10-07T16:25:00Z",
   "onset_unix": 1791390300,
   "end_ts": null,
   "end_unix": null,
   "confidence": 1.0,
   "evidence": [
    "Pump moving 8.5% less than its rated 3,150 bpd while running",
    "Pipeline flow matches pump flow, so the water is not leaking"
   ],
   "level_pct": null,
   "hours_to_limit": null,
   "recommended_actions": [
    {
     "type": "field_inspection",
     "asset_id": "S4_PUMP_C"
    }
   ]
  },
  {
   "event_id": "EV-0010",
   "system_id": "S5",
   "facility_id": "S5_FACILITY_B",
   "asset_id": "S5_PIPELINE_B",
   "category": "pipeline_leak",
   "status": "ongoing",
   "onset_ts": "2026-10-08T06:10:00Z",
   "onset_unix": 1791439800,
   "end_ts": null,
   "end_unix": null,
   "confidence": 1.0,
   "evidence": [
    "3.4% of pumped water is not arriving at disposal",
    "Pipeline pressure 32 psi below normal"
   ],
   "level_pct": null,
   "hours_to_limit": null,
   "recommended_actions": [
    {
     "type": "field_inspection",
     "asset_id": "S5_PIPELINE_B"
    }
   ]
  }
 ]
};
