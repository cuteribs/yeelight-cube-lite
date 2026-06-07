# Advanced Color & Brightness Calibration

> [!WARNING]
> This document is for **developers** working on the integration internals. The
> parameters below are low-level tuning knobs for the on-device color and
> brightness pipeline. They are **not** exposed through any user-facing card or
> entity, and most users never need them. Nothing here is required for normal
> use of the lamp.

The `set_color_calibration` service lets you adjust the color/brightness
correction pipeline **at runtime** so you can dial in values against a real
lamp without restarting Home Assistant. Changes are applied immediately but are
**not persisted** — once you find values you like, copy them into the code
defaults in [`light.py`](../light.py) so they survive a restart.

All current values are also published on the light entity as
`calib_*` attributes, so a tuning UI can read back the live state.

---

## Why correction is needed

The Cube Lite's LEDs do not behave like an sRGB computer monitor:

- **Different LED efficiencies.** The green LED is the most efficient and the
  blue LED the least, so a "neutral" RGB value such as white can look greenish,
  and blues/purples can look washed out.
- **Non-linearity at low duty cycle.** At very low effective brightness (low PWM
  duty), the LEDs become non-linear and hues drift — dim colors lose saturation
  or shift toward a different hue.
- **Coarse hardware dimming.** The lamp's own brightness register is relatively
  coarse, so dimming purely in hardware feels steppy.

The pipeline addresses these with three independent stages, applied in this
order after color effects:

```
color effects → brightness darken (+ per-channel floors)
              → System 1 (low-bright gamma)
              → System 2 (per-channel gain) → encode & send
```

The dashboard preview is never affected — it always shows the original intended
colors. Only the data sent to the physical lamp is corrected.

---

## System 1 — Low-brightness gamma correction

Implemented in `_apply_color_correction()`. Applies a per-channel inverse-gamma
boost that fades in only at low **effective** brightness (where effective =
`hardware_brightness × (100 − darken) / 100`). Above `hw_threshold` it is fully
off; at/below `hw_full` it is fully on, blending linearly in between. It also
blends between a hue-preserving uniform scale and a per-channel scale via
`channel_balance`.

| Field | Default | Range | Description |
| :-- | :-- | :-- | :-- |
| `gamma_r` | `0.85` | 0.1–1.0 | Red inverse gamma. Lower = stronger low-brightness boost. `1.0` = no change |
| `gamma_g` | `0.75` | 0.1–1.0 | Green inverse gamma. Lower than red because the green LED is stronger |
| `gamma_b` | `0.62` | 0.1–1.0 | Blue inverse gamma. Usually the strongest correction so dim blues don't go grayish |
| `hw_threshold` | `50` | 10–100 | Hardware brightness % **above** which correction is fully off |
| `hw_full` | `10` | 1–50 | Hardware brightness % at/below which correction is fully on (100%) |
| `channel_balance` | `0.7` | 0.0–1.0 | Blend: `0` = uniform luminance scale (hue-safe, no blue fix), `1` = pure per-channel (best blue/purple accuracy, may shift hue). `0.7` favors per-channel |

---

## System 2 — Per-channel gain (monitor matching)

Implemented in `_apply_color_accuracy()`, toggled by `set_color_accuracy`
(default **on**). A linear multiplier per channel that compensates for the LED
color imbalance vs. a monitor. The correction **fades with brightness**: full
strength at HA brightness 255, fading to neutral (no correction) near
brightness 1, so it never fights System 1 at the dim end.

| Field | Default | Range | Description |
| :-- | :-- | :-- | :-- |
| `gain_r` | `1.00` | 0.5–1.5 | Red channel multiplier. `1.00` = no scaling |
| `gain_g` | `1.00` | 0.5–1.5 | Green channel multiplier. Lower than `1.0` reduces the green cast in whites/yellows |
| `gain_b` | `1.00` | 0.5–1.5 | Blue channel multiplier. Lower than `1.0` deepens blues/purples |

> [!NOTE]
> **The code default for all three gains is `1.00`, which makes System 2 a
> no-op out of the box.** The function and the docstring describe a tuned
> profile (e.g. `gain_g ≈ 0.87`, `gain_b ≈ 0.72`) as a *starting point* for the
> kind of green/blue reduction these LEDs typically need, but those values are
> not currently applied as defaults. Tune them against your own unit before
> committing new defaults.

---

## System 3 — Unified brightness curve

Implemented in `_calculate_brightness_values()`. The single user brightness
slider (1–100%) drives **two smooth power curves at once**, each spanning the
whole range, so there is no breaking point where the dimming behaviour switches
character. With `p = user_brightness / 255` (0 → 1):

- **Hardware brightness** follows
  `hardware_keep = hw_floor + (1 − hw_floor) · p^hw_curve`. With `hw_curve < 1`
  the hardware rises quickly at the bottom then flattens near 100%, keeping the
  bright end smooth (the Yeelight hardware register is coarse near the top).
- **RGB darkening** follows `darken% = darken_floor · (1 − p^darken_curve)`.
  With `darken_curve > 1` most of the darkening happens in the upper range, so
  colors stay rich until the slider is dimmed well down.

At `p = 0` the lamp sits at `hw_floor%` hardware with `darken_floor%` darkening
(the dim night level); at `p = 1` it is `100%` hardware with `0%` darkening
(full output). The perceived output is the product of the two curves —
`hardware_keep × (1 − darken%/100)` — which is smooth and monotonic end to end.

| Field | Default | Range | Description |
| :-- | :-- | :-- | :-- |
| `hw_floor` | `1` | 1–100 | Hardware brightness % at the very bottom of the slider (0% user brightness) |
| `darken_floor` | `97` | 0–100 | RGB darkening % at the bottom of the slider. `97` means pixels are multiplied by `0.03` at minimum. Lower retains more per-pixel color precision when very dim |
| `hw_curve` | `0.5` | 0.1–3.0 | Exponent shaping the hardware-brightness rise. `< 1` lifts the low end and flattens the top; `> 1` does the opposite |
| `darken_curve` | `2.0` | 0.1–4.0 | Exponent shaping the darkening. `> 1` keeps colors rich high up and concentrates dimming low down; `< 1` darkens earlier |

### Per-channel floors

The darken stage (`_apply_final_brightness()`) never drives a lit channel all
the way to `0` — it clamps each non-zero channel to a minimum value so very dim
colors stay lit and the right hue instead of dropping out. Because the red,
green and blue LEDs reach their reliable minimum at different drive levels
(blue typically needs the highest floor), the minimum is **per channel**.

| Field | Default | Range | Description |
| :-- | :-- | :-- | :-- |
| `floor_r` | `1` | 1–32 | Lowest value a lit **red** channel is clamped to after darkening |
| `floor_g` | `1` | 1–32 | Lowest value a lit **green** channel is clamped to |
| `floor_b` | `1` | 1–32 | Lowest value a lit **blue** channel is clamped to. Often the highest, so dim blues don't disappear |

> [!NOTE]
> Floors apply only to channels that are already non-zero — a channel set to
> `0` stays off. They are published as `calib_floor_r/g/b` attributes and set
> via the `floor_r/g/b` keys of `set_color_calibration`.

### Shaping the low end

Because the eye responds non-linearly, a large part of the bottom of the slider
can look almost identically dim, so small slider moves near the bottom appear to
do little. Unlike the old dual-range model there is no transition point to
cross — both curves are continuous — so the levers are smooth: lower
`darken_floor` (brighter minimum), lower `hw_curve` (lifts the low range), or
lower `darken_curve` (darkens earlier so the mid feels brighter). The in-card
calibration **wizard** automates finding these values empirically against your
unit.

---

## Tuning workflow

1. Load the internal calibration card (development build only — see below) and
   point it at your lamp entity.
2. Either drag the raw sliders or run the guided **wizard**. The wizard takes
   exclusive control of the lamp (so automations can't disturb the test) and
   walks you through, in order:
   1. **Channel floors** — find the lowest level each of red/green/blue is still
      lit and the right color, with a zoom to refine → `floor_r/g/b`.
   2. **Brightness curve** — set the minimum, then even out a dim→bright ramp
      with no fade-to-grey → `darken_floor`, `hw_curve`, `darken_curve`.
   3. **White balance** (green, then blue) → `gain_g`, `gain_b`.
   4. **Color check** — flood each primary/secondary and nudge what looks wrong;
      full brightness tunes `gain_*`, dim tunes `gamma_*` (gamma is capped so
      colors stay saturated).
   5. **Verify** and **Summary** — confirm, then copy the numbers.
3. Each change calls `set_color_calibration` and re-renders immediately.
4. When satisfied, use **Copy Values** (or the wizard summary) and paste the
   numbers into the corresponding constants/defaults in
   [`light.py`](../light.py):
   - System 1 → `self._calib_gamma_*`, `_calib_hw_*`, `_calib_channel_balance`
   - System 2 → `self._calib_gain_*`
   - System 3 → the `HW_FLOOR_PERCENT`, `DARKEN_FLOOR_PERCENT`,
     `HW_CURVE_EXPONENT`, and `DARKEN_CURVE_EXPONENT` class constants (and the
     matching `_calib_*` initializers).
   - Per-channel floors → `self._calib_floor_r/g/b`.

### Calling the service directly

```yaml
action: yeelight_cube.set_color_calibration
data:
  # System 1 — gamma curve
  gamma_r: 0.85
  gamma_g: 0.75
  gamma_b: 0.62
  hw_threshold: 50
  hw_full: 10
  channel_balance: 0.7
  # System 2 — gain
  gain_r: 1.00
  gain_g: 1.00
  gain_b: 1.00
  # System 3 — unified brightness curve
  hw_floor: 1
  darken_floor: 97
  hw_curve: 0.5
  darken_curve: 2.0
  # Per-channel darken floors
  floor_r: 1
  floor_g: 1
  floor_b: 1
  entity_id: light.cubelite_192_168_4_102
```

All fields are optional — only the keys you pass are updated.

---

## The internal calibration card

The tuning UI (`yeelight-cube-calibration-card.js`, type
`yeelight-cube-calibration-card`) is a **development-only** card and is excluded
from the published repository. It is auto-registered as a Lovelace resource only
when the JS file is present on disk, so production installs never see it.
