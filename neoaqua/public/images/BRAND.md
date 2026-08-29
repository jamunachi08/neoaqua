# NeoAqua — app identity

These assets identify **the application**. The product brand that names your
finished goods is a separate, configurable thing (NeoAqua Settings → Brand) and
changing it does not change these.

## The mark

A water droplet whose lower third is filled with deep water, the surface drawn
as a single wave crest. Legible down to 32 px; below that the wave softens but
the droplet silhouette still reads.

## Files

| File | Use |
|---|---|
| `neoaqua-logo.svg` | The app icon. Referenced by `app_logo_url` in hooks.py. Transparent background. |
| `neoaqua-app-tile.svg` | Rounded-square tile for favicons, mobile home screens, app stores. |
| `neoaqua-icon-mono.svg` | Single colour, inherits `currentColor`. For print, watermarks, embossing, one-colour output. |
| `neoaqua-wordmark.svg` | Horizontal lockup: mark + NeoAqua + BOTTLED WATER. Letterheads, documents, headers. |
| `neoaqua-wordmark-ar.svg` | The same with نيو أكوا beneath. |
| `neoaqua-icon-512.png` / `-192.png` | Raster tiles. |
| `neoaqua-icon-64.png` / `neoaqua-favicon-32.png` | Small raster. |

## Palette

| Role | Hex | Where |
|---|---|---|
| Sky | `#5CC8F5` | Top of the droplet gradient |
| Primary | `#1B98E0` | The brand blue — buttons, links, chart accents |
| Deep water | `#1478B4` | Upper half of the water gradient |
| Navy | `#13293D` | Headings, the base of both gradients |
| Mist | `#E8F4FB` | Panel and highlight backgrounds |
| Muted | `#7A8B99` | The BOTTLED WATER line, secondary text |

These are the same values the app already uses in `neoaqua.bundle.css` and in
the generated documents, so nothing needs re-theming.

## Using it

Minimum clear space around the mark is half its width. Do not stretch it, recolour
the droplet outside the palette, or place the gradient version on a mid-blue
background — use `neoaqua-icon-mono.svg` there instead.

The wordmark sets type in a system stack (Segoe UI, Inter, Helvetica Neue, Arial).
That keeps the file small and editable, at the cost of rendering slightly
differently across platforms. If you need it pixel-identical everywhere — a
printed carton, say — have the type converted to outlines by a designer first.

## Arabic

`neoaqua-wordmark-ar.svg` stores نيو أكوا in logical order and relies on the
renderer to shape and join it. Browsers do this correctly. Some PDF engines,
including older wkhtmltopdf builds, do not. **Check it in your own browser and
in a generated PDF before using it on anything customer-facing**, and if the
letters appear disconnected or reversed, have that line converted to outlines.
