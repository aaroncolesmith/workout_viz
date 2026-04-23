# Design System Specification: The High-Performance Monolith

## 1. Overview & Creative North Star
The Creative North Star for this design system is **"The High-Performance Monolith."** 

This system rejects the cluttered, "gamified" aesthetic typical of fitness apps in favor of a silent, authoritative companion. It is inspired by architectural brutalism and high-end horology—focusing on precision, weight, and light. To achieve an "expensive" feel, the UI moves away from standard grids. We utilize **intentional asymmetry**, where large typography offsets dense data visualizations, and **high-contrast scale**, placing massive display numbers next to micro-labeling. The experience should feel less like a mobile app and more like a custom-calibrated instrument.

## 2. Colors & Tonal Depth
The palette is strictly monochromatic to maintain focus on the user’s performance data. Color is a reward, not a decoration.

### The "No-Line" Rule
Standard 1px borders are prohibited for sectioning. They create visual noise that cheapens the interface. Boundaries must be defined through **Background Color Shifts**. For example, a card component using `surface_container_highest` should sit directly on a `surface` background. The eye should perceive the edge through the shift in value, not a stroke.

### Surface Hierarchy & Nesting
The UI is treated as a series of physical layers. Use the following hierarchy to define importance:
*   **Base:** `surface` (#131313) – The foundation.
*   **Sectioning:** `surface_container_low` (#1c1b1b) – For secondary content blocks.
*   **Interaction:** `surface_container_high` (#2a2a2a) – For clickable elements and cards.
*   **Emphasis:** `surface_bright` (#393939) – To draw immediate focus to a specific metric.

### Glass & Gradient Rule
To prevent the UI from feeling flat, use **Glassmorphism** for floating elements (e.g., sticky headers or navigation bars). Use `surface` with 70% opacity and a `20px` backdrop blur. 
*   **Signature Textures:** For primary CTAs, use a subtle linear gradient from `primary` (#ffffff) to `primary_container` (#d4d4d4) at a 45-degree angle. This provides a metallic, tactile "soul" to the button that flat white cannot achieve.

## 3. Typography
The typography strategy relies on the interplay between the geometric strength of **Manrope** and the technical clarity of **Inter**.

*   **Display & Headline (Manrope):** Used for "Hero Metrics" (e.g., Heart Rate, Total Weight). The tracking should be tightened (-2%) for large displays to create a solid, "expensive" block of text.
*   **Body & Labels (Inter):** Used for technical data, instructions, and secondary info. Increase tracking (+3%) on `label-sm` to ensure legibility during high-intensity movement.
*   **Editorial Contrast:** A screen should ideally feature a massive `display-lg` metric juxtaposed with a tiny `label-md` description. This scale gap is what creates the "premium" feel.

## 4. Elevation & Depth
In this system, depth is a function of light and layering, not artificial shadows.

*   **The Layering Principle:** Achieve lift by "stacking." A `surface_container_lowest` (#0e0e0e) input field should be nested within a `surface_container` (#201f1f) card. This creates a "recessed" or "pressed" look common in luxury car dashboards.
*   **Ambient Shadows:** If an element must float (e.g., a modal), use a shadow with a blur of `40px` and an opacity of 6% using the `on_surface` color. It should feel like an ambient occlusion, not a "drop shadow."
*   **The Ghost Border:** If accessibility requires a container boundary, use the `outline_variant` (#474747) at **15% opacity**. This creates a "whisper" of a line that guides the eye without interrupting the monochromatic flow.

## 5. Components

### Buttons
*   **Primary:** Solid `primary` (#ffffff) with `on_primary` (#1a1c1c) text. Use `xl` (0.75rem) roundedness for a modern, architectural feel.
*   **Secondary:** Ghost style. No background. Use the "Ghost Border" (15% opacity `outline_variant`). 
*   **Interaction:** On press, primary buttons should shift to `primary_container` (#d4d4d4).

### Data Visualization (The Accent Exception)
The `tertiary` (#62ff96) color is reserved exclusively for "Success" or "Live" data (e.g., an active heart rate zone). `error` (#ffb4ab) is reserved for "Strain" or "Warning." All other chart elements (axes, grids) must use `outline` (#919191).

### Lists & Cards
*   **No Dividers:** Explicitly forbid 1px lines between list items. Use a `16px` vertical gap (Spacing Scale) or alternate background tints (`surface_container_low` vs `surface_container`).
*   **Progress Indicators:** Use thin (2px) tracks. The background track should be `surface_container_highest`, and the active indicator should be `primary`.

### Input Fields
*   **Style:** Minimalist. No bottom line. Use `surface_container_lowest` with a subtle `sm` (0.125rem) corner radius. Labeling should use `label-sm` in `on_surface_variant` (#c6c6c6), positioned above the field, never inside as a placeholder.

## 6. Do's and Don'ts

### Do
*   **Do** use extreme white space. If you think there is enough padding, add 8px more.
*   **Do** use "Manrope" for all numbers. Numbers are the star of this app.
*   **Do** use subtle backdrop blurs on any element that overlays data.

### Don't
*   **Don't** use pure black (#000000) for backgrounds. Use `surface` (#131313) to allow for depth layering.
*   **Don't** use icons with fills. Use `1.5px` or `1px` thin-stroke geometric outlines only.
*   **Don't** use standard "Material" or "Human Interface" default elevations. Everything must be tonally derived.
*   **Don't** use emojis. They break the professional, "luxury instrument" vibe.

---
*Document Version: 1.0.0*
*Editorial Direction: Senior UI/UX Director*