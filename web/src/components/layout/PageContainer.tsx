import { cn } from "@/lib/utils";
import { HTMLAttributes } from "react";

interface PageContainerProps extends HTMLAttributes<HTMLDivElement> {
  narrow?: boolean;
}

export function PageContainer({ narrow, className, children, ...props }: PageContainerProps) {
  return (
    <div
      className={cn(
        "mx-auto w-full px-4 sm:px-6 lg:px-8",
        narrow ? "max-w-3xl" : "max-w-content",
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}
