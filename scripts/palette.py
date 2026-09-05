"""The site's two data colours, in one place.

Chemical vs rapid HPF is the only categorical distinction this project draws,
and it was drawn in four different pairs: matplotlib's defaults in the figures,
a pair of tailwind hexes in two builders, and the site's own tokens in the CSS.
Same two groups, four looks.

These are the validated pair -- both modes pass the lightness band, the chroma
floor, colour-vision separation and contrast against their surface. The old dark
steps failed the lightness band in both slots, which is why the site's cards
glowed against the dark ground.

Figures render on white, so they take the light steps; the CSS carries both.
"""

CHEM = "#eb6834"        # light surface
HPF = "#2a78d6"
CHEM_DARK = "#d95926"   # dark surface
HPF_DARK = "#3987e5"

PREP_COLOR = {"Chemical": CHEM, "Rapid HPF": HPF}
PREP_COLORS = PREP_COLOR        # some scripts imported it under this name
