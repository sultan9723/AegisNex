/** @type {import('tailwindcss').Config} */
const config = {
  darkMode: "class",
  content: [
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "hsl(var(--background))",
        surface: "hsl(var(--surface))",
        "surface-elevated": "hsl(var(--surface-elevated))",
        "surface-glass": "hsl(var(--surface-glass))",

        "text-primary": "hsl(var(--text-primary))",
        "text-secondary": "hsl(var(--text-secondary))",
        "text-tertiary": "hsl(var(--text-tertiary))",
        "text-disabled": "hsl(var(--text-disabled))",

        foreground: "hsl(var(--foreground))",
        card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },
        popover: { DEFAULT: "hsl(var(--popover))", foreground: "hsl(var(--popover-foreground))" },

        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
          hover: "hsl(var(--primary-hover))",
          subtle: "hsl(var(--primary-subtle))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },

        success: {
          DEFAULT: "hsl(var(--success))",
          subtle: "hsl(var(--success-subtle))",
          bg: "hsl(var(--success-bg) / 0.08)",
          border: "hsl(var(--success-border) / 0.2)",
        },
        warning: {
          DEFAULT: "hsl(var(--warning))",
          subtle: "hsl(var(--warning-subtle))",
          bg: "hsl(var(--warning-bg) / 0.08)",
          border: "hsl(var(--warning-border) / 0.2)",
        },
        danger: {
          DEFAULT: "hsl(var(--danger))",
          subtle: "hsl(var(--danger-subtle))",
          bg: "hsl(var(--danger-bg) / 0.08)",
          border: "hsl(var(--danger-border) / 0.2)",
        },
        info: {
          DEFAULT: "hsl(var(--info))",
          subtle: "hsl(var(--info-subtle))",
          bg: "hsl(var(--info-bg) / 0.08)",
          border: "hsl(var(--info-border) / 0.2)",
        },

        chart: {
          1: "hsl(var(--chart-1))",
          2: "hsl(var(--chart-2))",
          3: "hsl(var(--chart-3))",
          4: "hsl(var(--chart-4))",
          5: "hsl(var(--chart-5))",
          6: "hsl(var(--chart-6))",
        },

        border: "hsl(var(--border))",
        "border-strong": "hsl(var(--border-strong))",
        divider: "hsl(var(--divider))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",

        cyan: {
          50: "#ecfeff",
          100: "#cffafe",
          200: "#a5f3fc",
          300: "#67e8f9",
          400: "#22d3ee",
          500: "#06b6d4",
          600: "#0891b2",
          700: "#0e7490",
          800: "#155e75",
          900: "#164e63",
        },
        violet: {
          50: "#f5f3ff",
          100: "#ede9fe",
          200: "#ddd6fe",
          300: "#c4b5fd",
          400: "#a78bfa",
          500: "#8b5cf6",
          600: "#7c3aed",
          700: "#6d28d9",
          800: "#5b21b6",
          900: "#4c1d95",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        xl: "calc(var(--radius) + 2px)",
        "2xl": "calc(var(--radius) + 6px)",
        "3xl": "calc(var(--radius) + 10px)",
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "Consolas", "monospace"],
        display: ["Inter", "-apple-system", "sans-serif"],
      },
      fontSize: {
        "2xs": ["0.625rem", { lineHeight: "0.875rem", letterSpacing: "0.02em" }],
        xs: ["0.75rem", { lineHeight: "1rem", letterSpacing: "0.01em" }],
        sm: ["0.8125rem", { lineHeight: "1.25rem", letterSpacing: "0.005em" }],
        base: ["0.9375rem", { lineHeight: "1.5rem", letterSpacing: "-0.006em" }],
        lg: ["1.0625rem", { lineHeight: "1.625rem", letterSpacing: "-0.01em" }],
        xl: ["1.1875rem", { lineHeight: "1.75rem", letterSpacing: "-0.015em" }],
        "2xl": ["1.375rem", { lineHeight: "1.875rem", letterSpacing: "-0.02em" }],
        "3xl": ["1.625rem", { lineHeight: "2rem", letterSpacing: "-0.025em" }],
        "4xl": ["2.25rem", { lineHeight: "2.5rem", letterSpacing: "-0.03em" }],
        "5xl": ["3rem", { lineHeight: "3.25rem", letterSpacing: "-0.035em" }],
        "6xl": ["3.75rem", { lineHeight: "4rem", letterSpacing: "-0.04em" }],
        "7xl": ["4.5rem", { lineHeight: "4.75rem", letterSpacing: "-0.045em" }],
      },
      letterSpacing: {
        tighter: "-0.05em",
        tight: "-0.025em",
        normal: "0",
        wide: "0.025em",
        wider: "0.05em",
        widest: "0.1em",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        DEFAULT: "var(--shadow-md)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        xl: "var(--shadow-xl)",
        "2xl": "var(--shadow-2xl)",
        glow: "var(--shadow-glow)",
        "glow-sm": "0 0 12px hsl(var(--primary) / 0.06), 0 0 24px hsl(var(--primary) / 0.03)",
        "glow-primary": "0 0 24px hsl(var(--primary) / 0.12), 0 0 48px hsl(var(--primary) / 0.05)",
        "glow-success": "0 0 24px hsl(var(--success) / 0.12), 0 0 48px hsl(var(--success) / 0.05)",
        "glow-warning": "0 0 24px hsl(var(--warning) / 0.12), 0 0 48px hsl(var(--warning) / 0.05)",
        "glow-danger": "0 0 24px hsl(var(--danger) / 0.12), 0 0 48px hsl(var(--danger) / 0.05)",
        "glow-cyan": "0 0 16px hsl(197 100% 50% / 0.1), 0 0 32px hsl(197 100% 50% / 0.05)",
        "glow-violet": "0 0 16px hsl(262 83% 58% / 0.1), 0 0 32px hsl(262 83% 58% / 0.05)",
        inner: "inset 0 1px 0 0 hsl(var(--border-strong) / 0.2)",
        "inner-glow": "inset 0 1px 0 0 rgba(255,255,255,0.5)",
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "gradient-conic": "conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))",
        "gradient-panel": "linear-gradient(135deg, hsl(var(--surface-elevated)), hsl(var(--surface)))",
        "gradient-glow": "radial-gradient(ellipse at 50% 0%, hsl(var(--primary) / 0.04), transparent 70%)",
        "gradient-hero": "radial-gradient(ellipse 80% 60% at 50% -20%, hsl(var(--primary) / 0.04), transparent)",
        "gradient-hero-violet": "radial-gradient(ellipse 60% 50% at 80% 20%, hsl(262 83% 58% / 0.03), transparent)",
        "gradient-mesh": "radial-gradient(at 40% 20%, hsl(var(--primary) / 0.03) 0px, transparent 50%), radial-gradient(at 80% 0%, hsl(262 83% 58% / 0.02) 0px, transparent 50%), radial-gradient(at 0% 50%, hsl(142 71% 45% / 0.02) 0px, transparent 50%)",
      },
      animation: {
        "fade-in": "fadeIn 0.5s cubic-bezier(0.16, 1, 0.3, 1)",
        "fade-in-up": "fadeInUp 0.6s cubic-bezier(0.16, 1, 0.3, 1)",
        "fade-in-down": "fadeInDown 0.5s cubic-bezier(0.16, 1, 0.3, 1)",
        "slide-up": "slideUp 0.5s cubic-bezier(0.16, 1, 0.3, 1)",
        "slide-down": "slideDown 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
        "slide-in-right": "slideInRight 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
        "slide-in-left": "slideInLeft 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
        "scale-in": "scaleIn 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
        "scale-in-sm": "scaleInSm 0.2s cubic-bezier(0.16, 1, 0.3, 1)",
        shimmer: "shimmer 2s infinite",
        "pulse-slow": "pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "pulse-fast": "pulse 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "spin-slow": "spin 3s linear infinite",
        "ping-slow": "ping 2s cubic-bezier(0, 0, 0.2, 1) infinite",
        "border-glow": "borderGlow 3s ease-in-out infinite alternate",
        "breath": "breath 4s ease-in-out infinite",
        float: "float 6s ease-in-out infinite",
        "float-delayed": "float 6s ease-in-out 2s infinite",
        "grid-flow": "gridFlow 20s linear infinite",
        "particle-float": "particleFloat 8s ease-in-out infinite",
        "counter": "counter 2s ease-out forwards",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        fadeInUp: {
          "0%": { opacity: "0", transform: "translateY(16px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        fadeInDown: {
          "0%": { opacity: "0", transform: "translateY(-12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideDown: {
          "0%": { opacity: "0", transform: "translateY(-12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideInRight: {
          "0%": { opacity: "0", transform: "translateX(16px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        slideInLeft: {
          "0%": { opacity: "0", transform: "translateX(-16px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        scaleIn: {
          "0%": { opacity: "0", transform: "scale(0.97)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        scaleInSm: {
          "0%": { opacity: "0", transform: "scale(0.98)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        shimmer: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
        breath: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.7" },
        },
        borderGlow: {
          "0%": { borderColor: "hsl(var(--primary) / 0.08)" },
          "100%": { borderColor: "hsl(var(--primary) / 0.2)" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-6px)" },
        },
        gridFlow: {
          "0%": { transform: "translate(0, 0)" },
          "100%": { transform: "translate(24px, 24px)" },
        },
        particleFloat: {
          "0%, 100%": { transform: "translateY(0) translateX(0)", opacity: "0.4" },
          "25%": { transform: "translateY(-12px) translateX(6px)", opacity: "0.6" },
          "50%": { transform: "translateY(-6px) translateX(-3px)", opacity: "0.5" },
          "75%": { transform: "translateY(-14px) translateX(8px)", opacity: "0.55" },
        },
        counter: {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      backdropBlur: {
        xs: "2px",
      },
      transitionDuration: {
        fast: "150ms",
        normal: "250ms",
        slow: "400ms",
        slower: "600ms",
      },
      transitionTimingFunction: {
        spring: "cubic-bezier(0.34, 1.56, 0.64, 1)",
        "out-expo": "cubic-bezier(0.16, 1, 0.3, 1)",
        "in-out-expo": "cubic-bezier(0.87, 0, 0.13, 1)",
      },
      spacing: {
        18: "4.5rem",
        88: "22rem",
        112: "28rem",
        128: "32rem",
      },
      maxWidth: {
        "8xl": "88rem",
        "9xl": "96rem",
      },
      zIndex: {
        60: "60",
        70: "70",
        80: "80",
        90: "90",
        100: "100",
      },
    },
  },
  plugins: [
    require("tailwindcss-animate"),
    function ({ addUtilities }) {
      addUtilities({
        ".text-balance": { "text-wrap": "balance" },
        ".glass-panel": {
          background: "rgba(255, 255, 255, 0.8)",
          "backdrop-filter": "blur(20px) saturate(180%)",
          border: "1px solid rgba(0, 0, 0, 0.06)",
          "box-shadow": "0 4px 24px -4px rgba(0, 0, 0, 0.06)",
        },
        ".glass-card": {
          background: "rgba(255, 255, 255, 0.9)",
          "backdrop-filter": "blur(24px) saturate(200%)",
          border: "1px solid rgba(0, 0, 0, 0.06)",
          "box-shadow": "0 4px 16px -4px rgba(0, 0, 0, 0.06)",
        },
        ".glass-card-elevated": {
          background: "rgba(255, 255, 255, 1)",
          "backdrop-filter": "blur(32px) saturate(200%)",
          border: "1px solid rgba(0, 0, 0, 0.06)",
          "box-shadow": "0 8px 24px -8px rgba(0, 0, 0, 0.08), inset 0 1px 0 0 rgba(255,255,255,1)",
        },
        ".glass-border": {
          border: "1px solid rgba(0, 0, 0, 0.06)",
        },
        ".bg-grid": {
          "background-image":
            "radial-gradient(circle, hsl(var(--border) / 0.5) 1px, transparent 1px)",
          "background-size": "24px 24px",
        },
        ".bg-grid-fine": {
          "background-image":
            "radial-gradient(circle, hsl(var(--border) / 0.3) 0.5px, transparent 0.5px)",
          "background-size": "16px 16px",
        },
        ".bg-grid-lines": {
          "background-image":
            "linear-gradient(hsl(var(--border) / 0.3) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--border) / 0.3) 1px, transparent 1px)",
          "background-size": "32px 32px",
        },
        ".bg-noise": {
          "background-image": "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.015'/%3E%3C/svg%3E\")",
          "background-repeat": "repeat",
          "background-size": "128px 128px",
        },
        ".border-gradient-cyan": {
          border: "1px solid transparent",
          "background-clip": "padding-box",
          "background-image": "linear-gradient(hsl(var(--surface-elevated)), hsl(var(--surface-elevated))), linear-gradient(135deg, hsl(var(--primary) / 0.15), transparent 50%)",
          "background-origin": "border-box",
        },
        ".stagger-1": { animationDelay: "0.1s" },
        ".stagger-2": { animationDelay: "0.2s" },
        ".stagger-3": { animationDelay: "0.3s" },
        ".stagger-4": { animationDelay: "0.4s" },
        ".stagger-5": { animationDelay: "0.5s" },
        ".stagger-6": { animationDelay: "0.6s" },
        ".line-clamp-2": {
          overflow: "hidden",
          display: "-webkit-box",
          "-webkit-box-orient": "vertical",
          "-webkit-line-clamp": "2",
        },
        ".line-clamp-3": {
          overflow: "hidden",
          display: "-webkit-box",
          "-webkit-box-orient": "vertical",
          "-webkit-line-clamp": "3",
        },
      });
    },
  ],
};

module.exports = config;
