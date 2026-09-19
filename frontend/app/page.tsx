import { redirect } from "next/navigation";
import { workspacePaths } from "@/lib/workspace-routes";

export default function Home() {
  redirect(workspacePaths.work);
}
