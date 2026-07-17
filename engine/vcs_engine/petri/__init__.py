"""The Digital Petri Dish — a spatial, agent-based lab culture.

This subpackage is a **new capability layered on top of** the engine's ideas (the
same reaction–diffusion maths as ``biology.spatial`` and the same heritable
genotype/mutation concept), not a rewrite of the single-cell kernel. Thousands of
lightweight cell agents live on a 2D grid, take up a diffusing nutrient locally,
grow, divide into neighbouring sites, mutate, signal to neighbours, and die — so
colony expansion, biofilm fronts, nutrient-limited cores, clone competition,
founder effects, and colony extinction all emerge. Everything is vectorised with
NumPy so a dish of thousands of cells steps quickly and stays reproducible.
"""

from .dish import PetriConfig, PetriDish

__all__ = ["PetriConfig", "PetriDish"]
