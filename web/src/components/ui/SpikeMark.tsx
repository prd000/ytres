import { cn } from "@/lib/utils";

interface SpikeMarkProps {
  className?: string;
  size?: number;
}

export function SpikeMark({ className, size = 16 }: SpikeMarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
      className={cn("inline-block shrink-0", className)}
    >
      <path
        d="M8 0L8.8 6.4L14.93 3.07L11.6 9.2L18 8L11.6 6.8L14.93 12.93L8.8 9.6L8 16L7.2 9.6L1.07 12.93L4.4 6.8L-2 8L4.4 9.2L1.07 3.07L7.2 6.4L8 0Z"
        fill="currentColor"
      />
    </svg>
  );
}
