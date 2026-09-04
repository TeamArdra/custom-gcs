import { useEffect, useState } from "react";
import { getHealth } from "../api";

// Shows the literal configured rosbridge target so a developer can judge
// sim vs. real hardware for themselves -- the architecture deliberately
// keeps sim and real indistinguishable to backend logic (see
// custom-gcs/docs/DECISIONS.md D-0's hardware-isolation seam note), so
// this must not guess or label it "MOCK"/"REAL".
export default function Footer() {
  const [target, setTarget] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    getHealth()
      .then((h) => {
        if (mounted) setTarget(`${h.rosbridge_host}:${h.rosbridge_port}`);
      })
      .catch(() => {
        if (mounted) setTarget(null);
      });
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <footer className="mt-4 text-dim text-[11px]">
      rosbridge target: {target ?? "unknown"}
    </footer>
  );
}
