import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0 select-none",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-md shadow-primary/20 hover:bg-primary-hover hover:shadow-lg hover:shadow-primary/25 hover:scale-[1.02] active:scale-[0.98]",
        destructive:
          "bg-danger text-white shadow-md shadow-danger/20 hover:bg-danger/90 hover:shadow-lg hover:shadow-danger/25 hover:scale-[1.02] active:scale-[0.98]",
        outline:
          "border border-border-strong bg-transparent hover:bg-surface-elevated hover:border-primary/40 hover:text-primary",
        secondary:
          "bg-surface-elevated border border-border text-text-primary shadow-sm hover:bg-surface-elevated/80 hover:border-border-strong hover:shadow-md",
        ghost:
          "hover:bg-surface-elevated hover:text-text-primary",
        link:
          "text-primary underline-offset-4 hover:underline hover:text-primary-hover h-auto p-0",
        success:
          "bg-success text-white shadow-md shadow-success/20 hover:bg-success/90 hover:shadow-lg hover:shadow-success/25 hover:scale-[1.02] active:scale-[0.98]",
        warning:
          "bg-warning text-white shadow-md shadow-warning/20 hover:bg-warning/90 hover:shadow-lg hover:shadow-warning/25 hover:scale-[1.02] active:scale-[0.98]",
        glass:
          "glass-card text-text-primary shadow-lg hover:shadow-xl hover:scale-[1.02] active:scale-[0.98]",
        gradient:
          "bg-gradient-to-r from-[#00E5FF] to-[#8B5CF6] text-white shadow-lg shadow-[#00E5FF]/20 hover:shadow-xl hover:shadow-[#00E5FF]/30 hover:scale-[1.02] active:scale-[0.98]",
      },
      size: {
        default: "h-9 px-4 py-2 text-sm",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-11 rounded-lg px-6 text-base",
        xl: "h-13 rounded-xl px-8 text-lg",
        icon: "h-9 w-9",
        "icon-sm": "h-8 w-8",
        "icon-lg": "h-11 w-11",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
