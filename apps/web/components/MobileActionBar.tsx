import type { ReactNode } from "react";

type MobileActionBarProps = {
  children?: ReactNode;
};

export function MobileActionBar({ children }: MobileActionBarProps) {
  return children ? <div>{children}</div> : null;
}
