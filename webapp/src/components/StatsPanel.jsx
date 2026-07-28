import { useState } from "react";
import { X } from "lucide-react";
import ModelPicker from "./ModelPicker.jsx";

// Grafana dashboard UIDs/slugs confirmed live against the running cluster
// (kube-prometheus-stack's bundled dashboard UIDs aren't stable across chart
// versions, so these were looked up via /api/grafana/api/search, not guessed).
const DASHBOARDS = [
  { key: "lifeos", label: "LifeOS Overview", uid: "lifeos-overview", slug: "lifeos-overview" },
  {
    key: "cluster",
    label: "Kubernetes / Cluster",
    uid: "efa86fd1d0c121a26444b636a3f509a8",
    slug: "kubernetes-compute-resources-cluster",
  },
  {
    key: "nodes",
    label: "Node Exporter / Nodes",
    uid: "7d57716318ee0dddbac5a7f451fb7753",
    slug: "node-exporter-nodes",
  },
];

export default function StatsPanel({ onClose }) {
  const [selected, setSelected] = useState(DASHBOARDS[0].key);
  const dashboard = DASHBOARDS.find((d) => d.key === selected) ?? DASHBOARDS[0];

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-surface">
      <div
        className="flex items-center gap-3 border-b border-border p-4"
        style={{ paddingTop: "max(1rem, env(safe-area-inset-top))" }}
      >
        <h2 className="text-sm font-semibold text-ink">Stats</h2>
        <ModelPicker
          value={selected}
          options={DASHBOARDS.map((d) => ({ key: d.key, label: d.label }))}
          onChange={setSelected}
        />
        <button
          onClick={onClose}
          className="ml-auto text-faint hover:text-ink"
          aria-label="Close"
        >
          <X size={18} />
        </button>
      </div>
      <iframe
        key={dashboard.key}
        src={`/api/grafana/d/${dashboard.uid}/${dashboard.slug}?orgId=1&kiosk`}
        className="w-full flex-1 border-0"
        title="Grafana dashboard"
      />
    </div>
  );
}
