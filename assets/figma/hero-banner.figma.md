# Figma Specification: Hero Banner

## Purpose
Product hero banner for the AegisNex README and website landing page.

## Canvas
- Frame: 1200 × 600 px
- Background: Dark (#0A0E14) with subtle grid overlay

## Layout

### Background
- Color: `#0A0E14`
- Subtle grid pattern: 48px squares, 0.5px lines at `rgba(255,255,255,0.03)`
- Radial gradient glow: centered at 50% 20%, 600px diameter, `radial-gradient(circle, rgba(80,70,228,0.08), transparent 70%)`

### Logo Area (Center)
- Position: Center, Y: 120–280
- Icon: Shield/hexagon icon with embedded "A" character
- Icon size: 80 × 80 px
- Icon color: Primary gradient (#5046E4 → #7C73FF)
- Behind icon: 120px diameter soft glow ring (opacity 0.15)

### Typography

**Product Name:**
- Text: "AegisNex"
- Font: Inter, 56px, Bold (700)
- Color: `#FFFFFF`
- Letter-spacing: -0.03em
- Position: Below icon, centered

**Tagline:**
- Text: "Open-source infrastructure observability, AI-driven incident response, and autonomous remediation."
- Font: Inter, 18px, Regular (400)
- Color: `rgba(255,255,255,0.6)`
- Max width: 680px
- Position: Below name, centered

### Badge Row
- Position: Y: 440
- Arrangement: Center, 8px gap between badges
- Each badge: rounded rectangle (4px radius), 24px height, auto-width
- Badge colors: varied per technology (Python blue, FastAPI teal, Next.js black, etc.)
- Badge text: white, 12px, medium weight

### Decorative Elements
- Subtle network node lines in background corners (opacity 0.03)
- 2 floating accent dots (8px diameter) at random positions

## Export
- Format: PNG (lossless)
- Also export @2x for retina displays (2400 × 1200 px)
