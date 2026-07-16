import { DemoSessionLauncher } from "@/components/demo/DemoSessionLauncher";
import { MansionDemo } from "@/components/demo/MansionDemo";

export default function DemoPage() {
  return <MansionDemo overlay={<DemoSessionLauncher />} />;
}
