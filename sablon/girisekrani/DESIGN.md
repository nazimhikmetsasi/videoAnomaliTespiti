---
name: Sentinel Control System
colors:
  surface: '#081425'
  surface-dim: '#081425'
  surface-bright: '#2f3a4c'
  surface-container-lowest: '#040e1f'
  surface-container-low: '#111c2d'
  surface-container: '#152031'
  surface-container-high: '#1f2a3c'
  surface-container-highest: '#2a3548'
  on-surface: '#d8e3fb'
  on-surface-variant: '#c6c6cd'
  inverse-surface: '#d8e3fb'
  inverse-on-surface: '#263143'
  outline: '#909097'
  outline-variant: '#45464d'
  surface-tint: '#bec6e0'
  primary: '#bec6e0'
  on-primary: '#283044'
  primary-container: '#0f172a'
  on-primary-container: '#798098'
  inverse-primary: '#565e74'
  secondary: '#adc6ff'
  on-secondary: '#002e6a'
  secondary-container: '#0566d9'
  on-secondary-container: '#e6ecff'
  tertiary: '#b7c8e1'
  on-tertiary: '#213145'
  tertiary-container: '#06182b'
  on-tertiary-container: '#728299'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#dae2fd'
  primary-fixed-dim: '#bec6e0'
  on-primary-fixed: '#131b2e'
  on-primary-fixed-variant: '#3f465c'
  secondary-fixed: '#d8e2ff'
  secondary-fixed-dim: '#adc6ff'
  on-secondary-fixed: '#001a42'
  on-secondary-fixed-variant: '#004395'
  tertiary-fixed: '#d3e4fe'
  tertiary-fixed-dim: '#b7c8e1'
  on-tertiary-fixed: '#0b1c30'
  on-tertiary-fixed-variant: '#38485d'
  background: '#081425'
  on-background: '#d8e3fb'
  surface-variant: '#2a3548'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  title-sm:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  data-mono:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 16px
  label-caps:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 16px
    letterSpacing: 0.05em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  container-padding: 24px
  grid-gutter: 12px
  sidebar-width: 280px
  event-stream-width: 320px
  stack-sm: 8px
  stack-md: 16px
---

## Brand & Style

The design system is engineered for high-stakes surveillance and analytical environments. It prioritizes rapid cognitive processing and "eyes-on-screen" endurance. The aesthetic is **Modern Corporate** with a heavy emphasis on **Information Density**. 

The UI evokes a "Control Center" atmosphere—authoritative, precise, and resilient. It utilizes a dark-mode-first approach to reduce eye strain in low-light monitoring rooms. Visual complexity is managed through a strict hierarchical grid, ensuring that while the interface is data-rich, it remains breathable and intuitive. Motion is reserved strictly for functional feedback and critical alarm states to prevent "alert fatigue."

Key characteristics:
- **Focused:** Minimal decorative elements to keep attention on video feeds.
- **Reliable:** Rigid structural alignment and systematic spacing.
- **Urgent:** Clear semantic signaling for anomaly detection.

## Colors

The palette is optimized for dark environments (Control Center vibe). 

- **Primary Backgrounds:** Use Deep Charcoal (#0F172A) for the main canvas and Navy (#1E293B) for elevated surfaces like sidebars and cards.
- **Accent:** A professional "Action Blue" (#3B82F6) is used for primary interactions, selection states, and focus indicators.
- **Semantic Logic:**
    - **Yellow (Pre-alarm):** Indicates suspicious behavior or potential anomalies.
    - **Red (Confirmed Alarm):** Indicates a high-priority security breach or confirmed incident.
    - **Green (Normal):** System health and active camera streams.
    - **Gray (Inactive):** Offline devices or archived data.
- **Contrast:** All text/background combinations must meet WCAG AA standards. Ensure red and yellow alerts have high-contrast text (usually black or deep navy) for maximum legibility.

## Typography

This design system uses a dual-font strategy:
1. **Inter:** Used for all UI labels, navigation, and body text. Its high x-height ensures readability at small sizes in dense tables.
2. **JetBrains Mono:** Used for timestamps, coordinates, frame rates, and numerical data. Monospaced fonts prevent layout shifts when numbers change rapidly in real-time streams.

**Language Support:** Full Turkish (Türkçe) support is required. Ensure character sets include `ç, ğ, ı, ö, ş, ü, İ`.

**Usage Guidelines:**
- Use `data-mono` for any dynamic sensor data or clock displays.
- Use `label-caps` for table headers and section titles in the sidebar.
- Maintain a minimum of 12px for body text to ensure accessibility in high-pressure scenarios.

## Layout & Spacing

The layout follows a **Fixed-Fluid Hybrid** model optimized for ultra-wide monitors and standard 1080p control screens.

- **Sidebar:** Fixed at 280px. Contains hierarchical navigation (Bölge > Kamera).
- **Event Stream:** A right-aligned vertical feed (320px) for real-time alerts.
- **Main Canvas:** Fluid grid for camera feeds. It supports 1x1, 2x2, 3x3, and 1+5 (one large, five small) layouts.
- **Grid Gutter:** A tight 12px gutter maximizes screen real estate for video feeds.
- **Breakpoints:**
    - Desktop (Standard): 1280px+
    - Wide Control Center: 1920px+
    - Ultra-Wide: 2560px+ (Layout expands to allow additional event columns).

Spacing follows a 4px base unit to allow for surgical precision in data-heavy components.

## Elevation & Depth

Depth is conveyed through **Tonal Layering** rather than heavy shadows, minimizing visual noise.

- **Level 0 (Base):** Deep Charcoal (#0F172A) for the application background.
- **Level 1 (Surface):** Navy (#1E293B) for sidebar, top bar, and container cards.
- **Level 2 (Active/Floating):** Lighter Navy (#334155) for tooltips, dropdowns, and modals.
- **Outlines:** Use 1px solid borders (#334155) for all containers. This creates a crisp, technical look without the blur of shadows.
- **Interaction:** Hover states on list items should use a subtle background highlight (#1E293B -> #334155) and a 2px vertical blue accent on the left edge.

## Shapes

The design system utilizes a **Soft (0.25rem)** roundedness level to maintain a professional, technical appearance while avoiding the "aggression" of sharp 90-degree corners.

- **Components (Buttons, Inputs, Cards):** 4px (0.25rem) radius.
- **Video Feeds:** 4px radius. 
- **Status Indicators (Pills):** Fully rounded (Pill-shaped) to distinguish them from interactive buttons.
- **Selection Rings:** 2px offset with a 2px stroke to ensure focus states are visible over complex video content.

## Components

### Video Camera Grid
The core component. Each cell includes:
- Overlay for Camera Name and Status (Top-left).
- Real-time Analytics Overlay (Bounding boxes for detected objects).
- Action Bar on hover (Record, PTZ Control, Snapshot).
- **Alarm State:** A 4px pulsing internal border (Red or Yellow).

### Event Stream Cards
- **Header:** Timestamp (Mono) and Priority Icon.
- **Content:** Short description (e.g., "Sınır İhlali" / "Border Breach").
- **Thumbnail:** A low-res snapshot of the trigger frame.
- **Action:** "İncele" (Examine) button in professional blue.

### Data Tables
- Condensed height (32px rows).
- Skeleton states use a subtle navy pulse animation.
- Sortable headers with `label-caps` styling.

### Status Indicators
- **Online:** Green dot + "Aktif" text.
- **Offline:** Gray dot + "Devre Dışı" text.
- **Alarm Confirmed:** Red flashing icon + "ONAYLANDI" text.

### Sidebar Navigation
- Multi-level accordion for "Bölgeler" (Zones).
- Integration of small sparklines next to zone names to show activity trends.

### Inputs & Controls
- **Dark Inputs:** Deep navy backgrounds with 1px borders.
- **Search:** Specifically optimized for Turkish character search (case-insensitive "İ/i" handling).