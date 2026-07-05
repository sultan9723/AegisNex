import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-0.5 text-[11px] font-medium tracking-wide transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary text-primary-foreground shadow-sm",
        secondary:
          "border-border bg-surface text-text-secondary",
        destructive:
          "border-transparent bg-danger text-white shadow-sm",
        outline:
          "border-border-strong text-text-primary",
        success:
          "border-transparent bg-success text-white shadow-sm",
        warning:
          "border-transparent bg-warning text-white shadow-sm",
        info:
          "border-transparent bg-info text-white shadow-sm",
        ghost:
          "border-transparent text-text-secondary",
        "success-subtle":
          "border-success-border bg-success-bg text-success-subtle",
        "warning-subtle":
          "border-warning-border bg-warning-bg text-warning-subtle",
        "danger-subtle":
          "border-danger-border bg-danger-bg text-danger-subtle",
        "info-subtle":
          "border-info-border bg-info-bg text-info-subtle",
      },
      size: {
        default: "h-6 px-2.5 text-[11px]",
        sm: "h-5 px-2 text-[10px]",
        lg: "h-7 px-3 text-xs",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {
  dot?: boolean
  pulse?: boolean
}

function Badge({ className, variant, size, dot, pulse, children, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant, size }), className)} {...props}>
      {dot && (
        <span className={cn(
          "size-1.5 rounded-full",
          pulse && "animate-ping-slow",
          (variant === "success" || variant === "success-subtle") && "bg-success",
          (variant === "warning" || variant === "warning-subtle") && "bg-warning",
          (variant === "destructive" || variant === "danger-subtle") && "bg-danger",
          (variant === "info" || variant === "info-subtle") && "bg-info",
          variant === "default" && "bg-primary-foreground",
          (!variant || variant === "secondary" || variant === "outline" || variant === "ghost") && "bg-text-secondary"
        )} />
      )}
      {children}
    </div>
  )
}

export { Badge, badgeVariants }
