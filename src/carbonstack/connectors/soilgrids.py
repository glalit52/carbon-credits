"""SoilGrids: a soil prior for anywhere, and why it is only a prior.

ISRIC's SoilGrids 2.0 predicts soil properties at 250 m globally, with a
quantile range for each. It is the right answer to three questions and the
wrong answer to one:

* **Right:** what clay fraction does RothC start from before a core is pulled;
  roughly what SOC stock is the sampling design stratifying; where should the
  strata boundaries go.
* **Wrong:** what is the baseline stock for crediting. VM0042 requires
  measured cores. A 250 m modelled pixel that averages a paddy, a bund and a
  road is not a baseline, and `SoilPrior.as_baseline()` refuses to pretend
  it is.

Units are converted with the response's own `d_factor` rather than constants
copied from documentation, so a change in how ISRIC encodes a layer moves
the number visibly instead of silently by a factor of ten.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..soil import SoilCore, SoilLayer
from .base import ConnectorUnavailable, Snapshot, Transport

SOILGRIDS_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
DEPTHS = ("0-5cm", "5-15cm", "15-30cm")
PROPERTIES = ("clay", "soc", "bdod", "cfvo")

# After dividing by d_factor: clay %, soc g/kg, bdod g/cm3, cfvo vol %.


@dataclass(frozen=True)
class GridLayer:
    top_cm: float
    bottom_cm: float
    clay_pct: float
    soc_g_kg: float
    bulk_density_g_cm3: float
    coarse_vol_frac: float
    soc_g_kg_q05: float | None = None
    soc_g_kg_q95: float | None = None


@dataclass
class SoilPrior:
    """A modelled profile at a point. Useful, and not evidence."""

    lat: float
    lon: float
    layers: list[GridLayer]
    provenance: list[dict] = field(default_factory=list)

    @property
    def depth_cm(self) -> float:
        return max(l.bottom_cm for l in self.layers)

    def _weighted(self, attr: str) -> float:
        total = math.fsum(l.bottom_cm - l.top_cm for l in self.layers)
        return math.fsum(getattr(l, attr) * (l.bottom_cm - l.top_cm) for l in self.layers) / total

    @property
    def clay_pct(self) -> float:
        """Thickness-weighted clay over the profile. RothC's one soil input."""
        return self._weighted("clay_pct")

    def _core(self, which: str = "mean") -> SoilCore:
        layers = []
        for l in self.layers:
            soc = {"mean": l.soc_g_kg, "q05": l.soc_g_kg_q05,
                   "q95": l.soc_g_kg_q95}[which]
            if soc is None:
                raise ValueError(f"no {which} quantile in this prior")
            layers.append(SoilLayer(l.top_cm, l.bottom_cm, soc / 10.0,
                                    l.bulk_density_g_cm3,
                                    min(0.95, l.coarse_vol_frac)))
        return SoilCore(plot_id="soilgrids", sampled_on=None,
                        lab_reference="SoilGrids 2.0 (modelled)", layers=layers)

    def soc_t_ha(self) -> float:
        return self._core().soc_t_ha()

    def soc_interval_t_ha(self) -> tuple[float, float] | None:
        """The 90% prediction interval, when the quantiles were requested.

        Usually wide -- often a factor of two -- and that width is the
        argument for pulling cores before anything else.
        """
        try:
            return self._core("q05").soc_t_ha(), self._core("q95").soc_t_ha()
        except ValueError:
            return None

    def as_baseline(self):
        raise ValueError(
            "SoilGrids is a 250 m modelled prior, not a measured baseline: "
            "VM0042 and the Gold Standard SOC framework both require cores. "
            "Use it to stratify and to initialise a model, never to credit.")

    def to_dict(self) -> dict:
        interval = self.soc_interval_t_ha()
        return {
            "lat": self.lat, "lon": self.lon, "depth_cm": self.depth_cm,
            "clay_pct": round(self.clay_pct, 2),
            "soc_t_ha": round(self.soc_t_ha(), 2),
            "soc_interval_t_ha": [round(v, 2) for v in interval] if interval else None,
            "layers": [l.__dict__ for l in self.layers],
            "provenance": self.provenance,
            "status": "prior -- not a crediting baseline",
        }


def soilgrids(transport: Transport, lat: float, lon: float) -> SoilPrior:
    params = {"lat": f"{lat:.5f}", "lon": f"{lon:.5f}",
              "property": list(PROPERTIES), "depth": list(DEPTHS),
              "value": ["mean", "Q0.05", "Q0.95"]}
    snap = transport.fetch("soilgrids", SOILGRIDS_URL, params)
    return parse_soilgrids(snap, lat, lon)


def parse_soilgrids(snap: Snapshot, lat: float, lon: float) -> SoilPrior:
    data = snap.json()
    try:
        layers = data["properties"]["layers"]
    except (KeyError, TypeError) as exc:
        raise ConnectorUnavailable("soilgrids", f"unexpected response shape ({exc})") from exc

    # values[(property, label)] = {"mean": .., "Q0.05": .., ...} in target units
    values: dict[tuple[str, str], dict[str, float | None]] = {}
    ranges: dict[str, tuple[float, float]] = {}
    for layer in layers:
        name = layer.get("name")
        if name not in PROPERTIES:
            continue
        d_factor = float((layer.get("unit_measure") or {}).get("d_factor") or 1)
        for depth in layer.get("depths", []):
            label = depth.get("label")
            rng = depth.get("range") or {}
            ranges[label] = (float(rng.get("top_depth", 0)), float(rng.get("bottom_depth", 0)))
            values[(name, label)] = {
                k: (None if v is None else float(v) / d_factor)
                for k, v in (depth.get("values") or {}).items()
            }

    out = []
    for label in DEPTHS:
        got = {p: values.get((p, label), {}) for p in PROPERTIES}
        mean = {p: got[p].get("mean") for p in PROPERTIES}
        if any(mean[p] is None for p in ("clay", "soc", "bdod")):
            # Water bodies, built-up land and the oceans come back null.
            raise ConnectorUnavailable(
                "soilgrids", f"no prediction for {label} at {lat:.4f},{lon:.4f}",
                "the point may be water or built-up; move it inside the field")
        top, bottom = ranges[label]
        out.append(GridLayer(
            top, bottom,
            clay_pct=mean["clay"],
            soc_g_kg=mean["soc"],
            bulk_density_g_cm3=mean["bdod"],
            coarse_vol_frac=(mean["cfvo"] or 0.0) / 100.0,
            soc_g_kg_q05=got["soc"].get("Q0.05"),
            soc_g_kg_q95=got["soc"].get("Q0.95"),
        ))
    return SoilPrior(lat, lon, out, [snap.provenance()])
