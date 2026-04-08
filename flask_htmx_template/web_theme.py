"""Web theme generator."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from materialyoucolor.dynamiccolor.dynamic_scheme import DynamicScheme
from materialyoucolor.dynamiccolor.material_dynamic_colors import MaterialDynamicColors
from materialyoucolor.dynamiccolor.variant import Variant
from materialyoucolor.hct.hct import Hct
from materialyoucolor.utils.color_utils import argb_from_rgb, hex_from_argb

from flask_htmx_template.models.base import BaseEnum

if TYPE_CHECKING:
    from collections.abc import Callable

HexColor = str


class Mood(BaseEnum):
    """Color palette mood options."""

    MONOCHROME = 1
    NEUTRAL = 2
    TONAL_SPOT = 3
    VIBRANT = 4
    EXPRESSIVE = 5
    FIDELITY = 6
    CONTENT = 7
    RAINBOW = 8
    FRUIT_SALAD = 9


DEFAULT_SWATCH = "#3f6837"
DEFAULT_MOOD = Mood.TONAL_SPOT


class FixedColors(TypedDict):
    """Fixed color scheme definition."""

    primary_fixed: HexColor
    on_primary_fixed: HexColor
    primary_fixed_dim: HexColor
    on_primary_fixed_variant: HexColor

    secondary_fixed: HexColor
    on_secondary_fixed: HexColor
    secondary_fixed_dim: HexColor
    on_secondary_fixed_variant: HexColor

    tertiary_fixed: HexColor
    on_tertiary_fixed: HexColor
    tertiary_fixed_dim: HexColor
    on_tertiary_fixed_variant: HexColor

    white: HexColor
    black: HexColor


class Colors(TypedDict):
    """Color scheme definition."""

    primary: HexColor
    on_primary: HexColor
    primary_container: HexColor
    on_primary_container: HexColor
    inverse_primary: HexColor

    secondary: HexColor
    on_secondary: HexColor
    secondary_container: HexColor
    on_secondary_container: HexColor

    tertiary: HexColor
    on_tertiary: HexColor
    tertiary_container: HexColor
    on_tertiary_container: HexColor

    error: HexColor
    on_error: HexColor
    error_container: HexColor
    on_error_container: HexColor

    surface: HexColor
    on_surface: HexColor
    surface_dim: HexColor
    surface_bright: HexColor
    surface_variant: HexColor
    on_surface_variant: HexColor

    inverse_surface: HexColor
    inverse_on_surface: HexColor

    surface_container_lowest: HexColor
    surface_container_low: HexColor
    surface_container: HexColor
    surface_container_high: HexColor
    surface_container_highest: HexColor

    outline: HexColor
    outline_variant: HexColor

    shadow: HexColor
    scrim: HexColor


class Theme(TypedDict):
    """Web theme definition."""

    fixed: FixedColors
    light: Colors
    dark: Colors


def _argb_from_hex(hex_color: str) -> int:
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return argb_from_rgb(r, g, b)


def _to_hex(argb: int) -> HexColor:
    return hex_from_argb(argb)[:7].lower()


def _make_colors(get: Callable[[str], HexColor]) -> Colors:
    return {
        "primary": get("primary"),
        "on_primary": get("onPrimary"),
        "primary_container": get("primaryContainer"),
        "on_primary_container": get("onPrimaryContainer"),
        "inverse_primary": get("inversePrimary"),
        "secondary": get("secondary"),
        "on_secondary": get("onSecondary"),
        "secondary_container": get("secondaryContainer"),
        "on_secondary_container": get("onSecondaryContainer"),
        "tertiary": get("tertiary"),
        "on_tertiary": get("onTertiary"),
        "tertiary_container": get("tertiaryContainer"),
        "on_tertiary_container": get("onTertiaryContainer"),
        "error": get("error"),
        "on_error": get("onError"),
        "error_container": get("errorContainer"),
        "on_error_container": get("onErrorContainer"),
        "surface": get("surface"),
        "on_surface": get("onSurface"),
        "surface_dim": get("surfaceDim"),
        "surface_bright": get("surfaceBright"),
        "surface_variant": get("surfaceVariant"),
        "on_surface_variant": get("onSurfaceVariant"),
        "inverse_surface": get("inverseSurface"),
        "inverse_on_surface": get("inverseOnSurface"),
        "surface_container_lowest": get("surfaceContainerLowest"),
        "surface_container_low": get("surfaceContainerLow"),
        "surface_container": get("surfaceContainer"),
        "surface_container_high": get("surfaceContainerHigh"),
        "surface_container_highest": get("surfaceContainerHighest"),
        "outline": get("outline"),
        "outline_variant": get("outlineVariant"),
        "shadow": get("shadow"),
        "scrim": get("scrim"),
    }


def _make_fixed(get: Callable[[str], HexColor]) -> FixedColors:
    return {
        "primary_fixed": get("primaryFixed"),
        "on_primary_fixed": get("onPrimaryFixed"),
        "primary_fixed_dim": get("primaryFixedDim"),
        "on_primary_fixed_variant": get("onPrimaryFixedVariant"),
        "secondary_fixed": get("secondaryFixed"),
        "on_secondary_fixed": get("onSecondaryFixed"),
        "secondary_fixed_dim": get("secondaryFixedDim"),
        "on_secondary_fixed_variant": get("onSecondaryFixedVariant"),
        "tertiary_fixed": get("tertiaryFixed"),
        "on_tertiary_fixed": get("onTertiaryFixed"),
        "tertiary_fixed_dim": get("tertiaryFixedDim"),
        "on_tertiary_fixed_variant": get("onTertiaryFixedVariant"),
        "white": "#fff",
        "black": "#000",
    }


def generate(swatch: HexColor, mood: Mood = DEFAULT_MOOD) -> Theme:
    """Generate a theme from a swatch color.

    Args:
        swatch: Color to generate a theme around
        mood: Scheme variant controlling how secondary/tertiary hues are derived

    Returns:
        Theme

    """
    hct = Hct.from_int(_argb_from_hex(swatch))
    v = Variant[mood.name.upper()]
    mdc = MaterialDynamicColors()
    scheme_light = DynamicScheme(hct, v, 0.0, is_dark=False)
    scheme_dark = DynamicScheme(hct, v, 0.0, is_dark=True)

    def get_light(name: str) -> HexColor:
        return _to_hex(getattr(mdc, name).get_argb(scheme_light))

    def get_dark(name: str) -> HexColor:
        return _to_hex(getattr(mdc, name).get_argb(scheme_dark))

    return {
        "fixed": _make_fixed(get_light),
        "light": _make_colors(get_light),
        "dark": _make_colors(get_dark),
    }
