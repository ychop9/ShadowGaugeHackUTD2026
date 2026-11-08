ShadowGauge
Gauge the Risk. Beat the Clock.


ShadowGauge is a produced-water monitoring and response-planning engine built for the EOG Resources challenge at HackUTD 2026. It turns raw SCADA telemetry into early problem detection and a cost-ranked action plan that protects upstream oil production, prevents tank shutdowns, and keeps response costs as low as possible.


Executive Overview & Problem Statement


In produced water gathering networks, a failed pump or a leaking line triggers a cascading operational disaster:


Flow Stagnation: Water stops moving from the facility tank to the disposal site (SWD).


Capacity Exhaustion: The tank fills toward its shutdown level as the wells keep producing.


Forced Well Shut-ins: When the tank hits shutdown, the wells feeding it shut in automatically and oil and gas revenue stops.


ShadowGauge closes the gap left by traditional SCADA alarms by shifting from reactive alerts to predictive, cost-based planning. It detects pump failures, leaks and worn pumps from the telemetry, forecasts the time until each tank reaches shutdown, and recommends the cheapest mix of vacuum trucks and well shut-ins before the tank trips.


Key Features


Real-Time Interactive SVG Facility Canvas: Live tank level, pump rotation that follows real flow, and color-coded pipes (blue = flowing, gray = no flow, orange = leak).


Statistical Problem Detection: Pump failure from the fault code; leak only when missing water and a pipeline pressure drop agree; worn pump when flow while running stays below rated by more than meter noise. Thresholds are learned from each dataset.


Shutdown Countdown: Time until the tank reaches its shutdown level, shown only when that happens before the pump repair is expected to finish. Repair time is estimated from past repairs in the data.


Cost-Optimal Response Planner: Minute-by-minute tank simulation over every combination of trucks, trips, wells to shut in, and shut-in timing. Trucks are shared across a system, so concurrent failures are planned together.


Operator Console: Ranked alerts (CRITICAL / URGENT / WATCH), a step-by-step action checklist, a "Why this plan" cost comparison, a plain-language facility summary, a zoomable network map, and an Operator guide.


Secure Access: Operator login powered by JWT authentication.


Business Logic & Math Engine


Time to Shutdown (failed pump)
T_shutdown = (Level_shutdown - Level_current) x Tank_capacity / Q_in
Countdown shown only if T_shutdown < T_repair_remaining


Response Optimization Objective
For each system with failed pumps, choose trucks k, trips m, shut-in well set S and shut-in time t:
min  k x m x Cost_trip  +  SUM_{w in S} Revenue_w x Hours_shut_in(w)  +  Revenue_lost_if_tank_trips
Subject to: k <= system truck fleet (shared across the system's facilities); each arrival removes k x Truck_capacity.


Tech Stack


Frontend: Next.js, React, Tailwind CSS, Dynamic SVG Canvas


Backend API: FastAPI (Python), Uvicorn, REST Services, CORS Middleware, JWT Auth


Detection & Planning Engine: Python, NumPy (statistical detection, tank simulation, exhaustive plan search)


Data Processing Pipeline: Pandas, PyArrow (Parquet telemetry cache)


Quickstart & Local Setup


Clone & Repository Setup
git clone https://github.com/ychop9/ShadowGaugeHackUTD2026.git
cd ShadowGaugeHackUTD2026
git checkout alt-backend


Backend Setup (FastAPI)
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
API Docs available at: http://localhost:8000/docs
Datasets are read from data/history/*; a test/ folder is picked up automatically.


Frontend Setup (Next.js)
cd frontend
npm install
npm run dev
Console UI available at: http://localhost:3000 


Team
HackUTD 2026 — EOG Resources Track


Yagnika Choppadandi

Sreeja Amaresam

Siri Kishore Dola

Vaishali Subash
