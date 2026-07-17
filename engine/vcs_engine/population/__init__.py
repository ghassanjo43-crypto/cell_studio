"""Population dynamics — many cells competing in one shared medium.

This subpackage sits *above* the single-cell engine. It does not add biology; it
orchestrates many independent single-cell simulations (each a full
``build_evolution_scenario`` with its own reproducible RNG streams), couples them
through a single shared nutrient medium, and turns each cell's ``division`` event
into a real new cell. Lineage, competition, selection, and extinction all emerge.
"""

from .population import Cell, Population, PopulationConfig

__all__ = ["Cell", "Population", "PopulationConfig"]
