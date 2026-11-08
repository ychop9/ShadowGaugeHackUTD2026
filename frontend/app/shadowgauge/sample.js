// ONLY used when you open the page with ?sample=1 (for testing the UI without the backend).
// This shows the JSON shape the page expects from GET /api/snapshot?dataset=<name>.
// None of these numbers are used in normal mode: every number comes from your backend.
export default {
  asOf: "2026-10-10T10:00:00",
  facilities: [
    {
      id: "C07", name: "Cedar 07", wells: 6, tankCapacityBbl: 1000, x: 22, y: 30,
      tank: { id: "TK-07", levelPct: 72, shutdownPct: 92, inflowBpd: 2880 },
      pump: { id: "P-07", status: "failed", flowBpd: 0, normalFlowBpd: 2880, dischargePsi: 4, since: "2026-10-10T09:42:00" },
      pipeline: { id: "PL-12", status: "ok", pressurePsi: 4, normalPressurePsi: 52, receiveFlowBpd: 0, expectedReceiveBpd: 2880 },
      issue: { type: "pump_failure", startedAt: "2026-10-10T09:42:00", shutdownAt: "2026-10-10T11:30:00", repairEta: "2026-10-10T15:42:00", doNothingCost: 5016 },
      plan: { steps: ["Send 1 truck. It arrives at 10:57 and removes 150 bbl.", "The tank stays under the limit until the repair."], cost: 905, doNothingCost: 5016 },
    },
    {
      id: "M03", name: "Mesa 03", wells: 4, tankCapacityBbl: 800, x: 78, y: 28,
      tank: { id: "TK-03", levelPct: 41, shutdownPct: 92, inflowBpd: 2100 },
      pump: { id: "P-03", status: "worn", flowBpd: 1932, normalFlowBpd: 2100, dischargePsi: 47, since: "2026-10-10T03:10:00" },
      pipeline: { id: "PL-03", status: "ok", pressurePsi: 50, normalPressurePsi: 52, receiveFlowBpd: 1932, expectedReceiveBpd: 1932 },
    },
    {
      id: "J02", name: "Juniper 02", wells: 5, tankCapacityBbl: 900, x: 34, y: 78,
      tank: { id: "TK-02", levelPct: 35, shutdownPct: 92, inflowBpd: 2400 },
      pump: { id: "P-02", status: "ok", flowBpd: 2400, normalFlowBpd: 2400, dischargePsi: 52 },
      pipeline: { id: "PL-08", status: "leak", pressurePsi: 21, normalPressurePsi: 52, receiveFlowBpd: 2305, expectedReceiveBpd: 2400, since: "2026-10-10T09:06:00" },
    },
  ],
  trucks: { total: 2, slots: 6, assignments: [{ facilityId: "C07", slots: 1 }] },
};