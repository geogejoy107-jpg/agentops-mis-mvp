import { redirect } from "next/navigation";

export default function LegacyRunLedgerRedirect() {
  redirect("/workspace/runs");
}
