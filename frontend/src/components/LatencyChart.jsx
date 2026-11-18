import { Tooltip, ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid } from "recharts";

function fmtTime(t) {
  return new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function LatencyChart({ data, degradedThresholdMs = 1000 }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={data} margin={{ top: 10, right: 12, bottom: 0, left: -14 }}>
        <defs>
          <linearGradient id="latencyFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#6366f1" stopOpacity={0.25} />
            <stop offset="100%" stopColor="#6366f1" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#eceef4" vertical={false} />
        <XAxis
          dataKey="t"
          tickFormatter={fmtTime}
          tick={{ fontSize: 11, fill: "#8b90a0" }}
          axisLine={false}
          tickLine={false}
          minTickGap={60}
        />
        <YAxis tick={{ fontSize: 11, fill: "#8b90a0" }} axisLine={false} tickLine={false} unit="ms" width={64} />
        <Tooltip
          contentStyle={{ borderRadius: 8, border: "1px solid #e6e8ef", fontSize: 12 }}
          formatter={(v) => [`${v} ms`, "Response time"]}
          labelFormatter={fmtTime}
        />
        {degradedThresholdMs > 0 && (
          <Area
            type="monotone"
            dataKey={() => degradedThresholdMs}
            stroke="#d97706"
            strokeDasharray="5 4"
            fill="none"
            dot={false}
            isAnimationActive={false}
            name="Degradation threshold"
          />
        )}
        <Area type="monotone" dataKey="ms" stroke="#6366f1" strokeWidth={2} fill="url(#latencyFill)" dot={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
