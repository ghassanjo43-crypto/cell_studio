"""The Petri dish: a vectorised spatial agent model of a lab culture.

State
-----
* ``nutrient`` — an ``(H, W)`` field (mmol/site) that diffuses each tick (explicit
  finite-difference Laplacian with zero-flux/reflective boundaries — the same scheme
  as ``biology.spatial``, in 2D).
* ``occupant`` — an ``(H, W)`` grid holding the cell index at each site, or ``-1``.
  One cell per site: this is what makes competition **local** (interior cells deplete
  their neighbourhood) and gives colonies **fronts** (only edge cells find empty
  neighbours to divide into).
* Cell agents — parallel NumPy arrays (position, clone/founder id, two heritable
  genotype factors, mass, energy/ATP, generation, accumulated mutations, a local
  signalling level, alive flag, starvation counter).

Each tick, vectorised over the living cells: diffuse → sense local nutrient and
neighbour density → take up nutrient (Michaelis–Menten × genotype) → spend
maintenance (raised by crowding, a contact-inhibition signal) → grow on the surplus
→ starve/die in depleted cores → divide into an empty neighbour (mutating the
daughter). Founder clones compete for space and nutrient; weak colonies go extinct.

Determinism: a single seeded ``numpy`` generator drives mutation, division order, and
daughter placement, so a whole dish run is reproducible and checkpoint/restore
continues it bit-for-bit.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

import numpy as np


@dataclass
class PetriConfig:
    """Configuration for a Digital Petri Dish run."""

    seed: int = 0
    width: int = 80
    height: int = 80
    initial_cells: int = 8  # founder clones
    nutrient_init: float = 1.0  # mmol per site
    nutrient_pattern: str = "gradient"  # uniform | gradient | patches (heterogeneity)
    diffusion_alpha: float = 0.18  # < 0.25 for 2D explicit stability
    feed_rate: float = 0.0  # uniform inflow (mmol/site/time); 0 = closed dish
    vmax: float = 8.0
    km: float = 0.4
    yield_factor: float = 0.9  # energy per mmol taken up
    maintenance: float = 0.35  # energy per unit mass per time
    growth_efficiency: float = 0.55  # mass gained per unit surplus energy
    division_mass: float = 1.0
    energy_cap: float = 5.0
    death_steps: int = 12  # consecutive starving steps before death
    mutation_rate: float = 0.6  # Poisson mean mutations per division
    mutation_sigma: float = 0.25
    signal_gain: float = 3.0  # how fast the crowding signal tracks neighbour density
    heatmap_size: int = 40  # coarse resolution of the heat maps
    frame_cell_cap: int = 4000  # max cells serialised into a frame

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("grid dimensions must be positive")
        if not 0.0 < self.diffusion_alpha < 0.25:
            raise ValueError("diffusion_alpha must be in (0, 0.25) for stability")
        if self.initial_cells < 1:
            raise ValueError("need at least one founder cell")


class PetriDish:
    """A spatial colony culture on a 2D grid (thousands of cell agents)."""

    def __init__(self, config: PetriConfig) -> None:
        self.config = config
        self.rng = np.random.default_rng(config.seed)
        self.step_index = 0
        self.time = 0.0
        H, W = config.height, config.width
        self.capacity = H * W
        self.n_clones = config.initial_cells

        self.nutrient = self._initial_nutrient()
        self.occupant = np.full((H, W), -1, dtype=np.int32)

        # Cell agent arrays (index into these is a stable cell id).
        cap = self.capacity
        self.cx = np.zeros(cap, dtype=np.int32)
        self.cy = np.zeros(cap, dtype=np.int32)
        self.clone = np.zeros(cap, dtype=np.int32)
        self.gtrans = np.ones(cap, dtype=np.float64)  # transport genotype factor
        self.gyield = np.ones(cap, dtype=np.float64)  # yield genotype factor
        self.mass = np.zeros(cap, dtype=np.float64)
        self.energy = np.zeros(cap, dtype=np.float64)
        self.generation = np.zeros(cap, dtype=np.int32)
        self.mutations = np.zeros(cap, dtype=np.int32)
        self.signal = np.zeros(cap, dtype=np.float64)
        self.alive = np.zeros(cap, dtype=bool)
        self.starve = np.zeros(cap, dtype=np.int32)

        self.n_slots = 0  # high-water number of used slots
        self._free: list[int] = []  # reusable slots from dead cells
        self.born = 0
        self.died = 0
        self._events: list[dict[str, Any]] = []
        self._prev_clone_counts = np.zeros(self.n_clones, dtype=np.int64)
        self._dominant_announced = False
        self._confluent_announced = False
        self._extinct_announced = False

        self._seed_founders()
        self._prev_clone_counts = self._clone_counts()

    # --------------------------------------------------------------- setup
    def _initial_nutrient(self) -> np.ndarray:
        c = self.config
        H, W = c.height, c.width
        base = float(c.nutrient_init)
        if c.nutrient_pattern == "uniform":
            return np.full((H, W), base, dtype=np.float64)
        if c.nutrient_pattern == "gradient":
            ramp = np.linspace(0.35, 1.0, W)[None, :]
            return (base * np.broadcast_to(ramp, (H, W))).astype(np.float64).copy()
        if c.nutrient_pattern == "patches":
            field = np.full((H, W), base * 0.3, dtype=np.float64)
            ys, xs = np.mgrid[0:H, 0:W]
            for _ in range(5):
                cyc = self.rng.integers(0, H)
                cxc = self.rng.integers(0, W)
                r2 = ((ys - cyc) ** 2 + (xs - cxc) ** 2) / (2 * (min(H, W) / 6) ** 2)
                field += base * np.exp(-r2)
            return field
        raise ValueError(f"unknown nutrient_pattern {c.nutrient_pattern!r}")

    def _seed_founders(self) -> None:
        c = self.config
        H, W = c.height, c.width
        # Scatter founders on a coarse lattice near the centre so colonies have room.
        n = c.initial_cells
        cols = int(np.ceil(np.sqrt(n)))
        spacing_x = max(1, W // (cols + 1))
        spacing_y = max(1, H // (cols + 1))
        placed = 0
        for i in range(n):
            gx = ((i % cols) + 1) * spacing_x
            gy = ((i // cols) + 1) * spacing_y
            gx = int(np.clip(gx, 0, W - 1))
            gy = int(np.clip(gy, 0, H - 1))
            if self.occupant[gy, gx] >= 0:
                continue
            self._place_cell(gy, gx, clone=i, gtrans=1.0, gyield=1.0,
                             mass=c.division_mass * 0.5, energy=1.0, generation=0, mutations=0)
            placed += 1
            self._emit("colony_founded", {"clone": i, "x": gx, "y": gy})
        if placed == 0:  # pathological tiny grid
            self._place_cell(0, 0, clone=0, gtrans=1.0, gyield=1.0,
                             mass=c.division_mass * 0.5, energy=1.0, generation=0, mutations=0)

    def _alloc_slot(self) -> Optional[int]:
        if self._free:
            return self._free.pop()
        if self.n_slots < self.capacity:
            j = self.n_slots
            self.n_slots += 1
            return j
        return None

    def _place_cell(self, y: int, x: int, *, clone: int, gtrans: float, gyield: float,
                    mass: float, energy: float, generation: int, mutations: int) -> Optional[int]:
        j = self._alloc_slot()
        if j is None:
            return None
        self.cy[j] = y
        self.cx[j] = x
        self.clone[j] = clone
        self.gtrans[j] = gtrans
        self.gyield[j] = gyield
        self.mass[j] = mass
        self.energy[j] = energy
        self.generation[j] = generation
        self.mutations[j] = mutations
        self.signal[j] = 0.0
        self.starve[j] = 0
        self.alive[j] = True
        self.occupant[y, x] = j
        return j

    # ---------------------------------------------------------------- step
    def _diffuse(self) -> None:
        n = self.nutrient
        p = np.pad(n, 1, mode="edge")  # zero-flux (reflective) boundaries
        lap = p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:] - 4.0 * n
        n += self.config.diffusion_alpha * lap
        if self.config.feed_rate:
            n += self.config.feed_rate * self._dt
        np.clip(n, 0.0, None, out=n)

    def _neighbour_counts(self) -> np.ndarray:
        occ = (self.occupant >= 0).astype(np.float64)
        p = np.pad(occ, 1)
        return (
            p[:-2, :-2] + p[:-2, 1:-1] + p[:-2, 2:]
            + p[1:-1, :-2] + p[1:-1, 2:]
            + p[2:, :-2] + p[2:, 1:-1] + p[2:, 2:]
        )

    def step(self, dt: float) -> None:
        """Advance the whole dish by one macro-step of size ``dt``."""
        self._dt = dt
        c = self.config
        self.step_index += 1
        self.time += dt

        self._diffuse()

        idx = np.flatnonzero(self.alive[: self.n_slots])
        if idx.size == 0:
            self._check_events()
            return

        ys = self.cy[idx]
        xs = self.cx[idx]
        local_n = self.nutrient[ys, xs]

        # Local signalling / cell–cell communication: track neighbour density.
        neigh = self._neighbour_counts()
        density = neigh[ys, xs] / 8.0
        self.signal[idx] = np.clip(self.signal[idx] + (c.signal_gain * density - self.signal[idx]) * dt, 0.0, 1.0)

        # Michaelis–Menten uptake (× transport genotype), capped by what's on the site.
        uptake = c.vmax * self.gtrans[idx] * (local_n / (c.km + local_n)) * self.mass[idx] * dt
        uptake = np.minimum(uptake, local_n)  # sites are unique per cell → safe
        self.nutrient[ys, xs] -= uptake

        gain = uptake * c.yield_factor * self.gyield[idx]
        # Crowding raises maintenance (contact inhibition via the local signal).
        cost = c.maintenance * self.mass[idx] * dt * (1.0 + 0.6 * self.signal[idx])
        net = gain - cost
        self.energy[idx] = np.clip(self.energy[idx] + net, 0.0, c.energy_cap)
        self.mass[idx] += c.growth_efficiency * np.maximum(net, 0.0)

        starving = net < 0.0
        self.starve[idx] = np.where(starving, self.starve[idx] + 1, 0)

        dead_local = self.starve[idx] >= c.death_steps
        for di in idx[dead_local]:
            self._kill(int(di))

        # Division: big enough, not just-killed, and has an empty neighbour.
        can_divide = (self.mass[idx] >= c.division_mass) & (~dead_local)
        candidates = idx[can_divide]
        if candidates.size:
            self.rng.shuffle(candidates)
            for ci in candidates:
                self._divide(int(ci))

        self._check_events()

    def _kill(self, i: int) -> None:
        if not self.alive[i]:
            return
        self.alive[i] = False
        self.occupant[self.cy[i], self.cx[i]] = -1
        self._free.append(i)
        self.died += 1

    def _empty_neighbour(self, y: int, x: int) -> Optional[tuple[int, int]]:
        H, W = self.config.height, self.config.width
        options: list[tuple[int, int]] = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                ny, nx = y + dy, x + dx
                if 0 <= ny < H and 0 <= nx < W and self.occupant[ny, nx] < 0:
                    options.append((ny, nx))
        if not options:
            return None
        return options[int(self.rng.integers(len(options)))]

    def _divide(self, i: int) -> None:
        spot = self._empty_neighbour(int(self.cy[i]), int(self.cx[i]))
        if spot is None:
            return  # packed interior → cannot divide (colony fronts emerge)
        ny, nx = spot
        # Mutate the daughter's genotype.
        gtrans = float(self.gtrans[i])
        gyield = float(self.gyield[i])
        n_mut = int(self.rng.poisson(self.config.mutation_rate))
        for _ in range(n_mut):
            factor = float(np.exp(self.rng.normal(0.0, self.config.mutation_sigma)))
            if self.rng.random() < 0.5:
                gtrans = float(np.clip(gtrans * factor, 0.1, 10.0))
            else:
                gyield = float(np.clip(gyield * factor, 0.1, 10.0))

        half_mass = float(self.mass[i]) * 0.5
        half_energy = float(self.energy[i]) * 0.5
        j = self._place_cell(
            ny, nx, clone=int(self.clone[i]), gtrans=gtrans, gyield=gyield,
            mass=half_mass, energy=half_energy,
            generation=int(self.generation[i]) + 1,
            mutations=int(self.mutations[i]) + n_mut,
        )
        if j is None:
            return  # at capacity
        self.mass[i] = half_mass
        self.energy[i] = half_energy
        self.born += 1

    # -------------------------------------------------------------- events
    def _clone_counts(self) -> np.ndarray:
        live = self.alive[: self.n_slots]
        if not live.any():
            return np.zeros(self.n_clones, dtype=np.int64)
        return np.bincount(self.clone[: self.n_slots][live], minlength=self.n_clones).astype(np.int64)

    def _check_events(self) -> None:
        counts = self._clone_counts()
        total = int(counts.sum())
        # Colony extinction: a clone that was alive is now gone.
        gone = np.flatnonzero((self._prev_clone_counts > 0) & (counts == 0))
        for clone in gone:
            self._emit("colony_extinct", {"clone": int(clone)})
        self._prev_clone_counts = counts

        if total == 0:
            if not self._extinct_announced and self.step_index > 0:
                self._extinct_announced = True
                self._emit("population_extinct", {"died": self.died})
            return

        # Biofilm confluence: most of the dish is occupied.
        occ_frac = total / float(self.capacity)
        if not self._confluent_announced and occ_frac >= 0.8:
            self._confluent_announced = True
            self._emit("biofilm_confluent", {"occupancy": round(occ_frac, 3)})

        # Clone dominance (founder effect / competitive win).
        dominant = int(counts.argmax())
        if not self._dominant_announced and counts[dominant] >= 0.5 * total:
            self._dominant_announced = True
            self._emit("clone_dominant", {"clone": dominant, "fraction": round(counts[dominant] / total, 3)})

    def _emit(self, kind: str, data: dict[str, Any]) -> None:
        self._events.append({"step": self.step_index, "time": self.time, "type": kind, "data": data})

    # ------------------------------------------------------------- readouts
    @property
    def metadata(self) -> dict[str, Any]:
        if self.is_extinct:
            return {"lifecycle.status": "EXTINCT"}
        return {}

    @property
    def is_extinct(self) -> bool:
        return self.step_index > 0 and not self.alive[: self.n_slots].any()

    @property
    def events(self) -> list[dict[str, Any]]:
        return self._events

    def _block_dims(self) -> tuple[int, int, int, int]:
        """Block size and coarse (rows, cols) for the heat maps — ``heatmap_size`` is
        an *upper bound* on the coarse resolution (ceil-division block sizing)."""
        hm = self.config.heatmap_size
        H, W = self.config.height, self.config.width
        by = max(1, -(-H // hm))  # ceil(H / hm)
        bx = max(1, -(-W // hm))
        return by, bx, H // by, W // bx

    def _coarse(self, grid: np.ndarray) -> np.ndarray:
        """Block-mean a full-resolution grid down to the heat-map resolution."""
        by, bx, rows, cols = self._block_dims()
        g = grid[: rows * by, : cols * bx]
        coarse: np.ndarray = g.reshape(rows, by, cols, bx).mean(axis=(1, 3))
        return coarse

    def _heatmaps(self, idx: np.ndarray) -> dict[str, list[float]]:
        by, bx, rows, cols = self._block_dims()
        pop = np.zeros((rows, cols), dtype=np.float64)
        mut = np.zeros((rows, cols), dtype=np.float64)
        atp = np.zeros((rows, cols), dtype=np.float64)
        if idx.size:
            biny = np.clip(self.cy[idx] // by, 0, rows - 1)
            binx = np.clip(self.cx[idx] // bx, 0, cols - 1)
            flat = biny * cols + binx
            np.add.at(pop.reshape(-1), flat, 1.0)
            np.add.at(mut.reshape(-1), flat, self.mutations[idx].astype(np.float64))
            np.add.at(atp.reshape(-1), flat, self.energy[idx])
            with np.errstate(invalid="ignore", divide="ignore"):
                mut = np.where(pop > 0, mut / np.maximum(pop, 1), 0.0)
                atp = np.where(pop > 0, atp / np.maximum(pop, 1), 0.0)
        nutrient = self._coarse(self.nutrient)
        return {
            "population": pop.ravel().round(3).tolist(),
            "nutrient": nutrient.ravel().round(4).tolist(),
            "mutation": mut.ravel().round(3).tolist(),
            "atp": atp.ravel().round(4).tolist(),
        }

    def _clone_map(self, idx: np.ndarray) -> list[int]:
        by, bx, rows, cols = self._block_dims()
        result = np.full(rows * cols, -1, dtype=np.int64)
        if idx.size:
            biny = np.clip(self.cy[idx] // by, 0, rows - 1)
            binx = np.clip(self.cx[idx] // bx, 0, cols - 1)
            flat = biny * cols + binx
            key = flat * self.n_clones + self.clone[idx]
            counts = np.bincount(key, minlength=rows * cols * self.n_clones).reshape(rows * cols, self.n_clones)
            has = counts.sum(axis=1) > 0
            dominant = counts.argmax(axis=1)
            result[has] = dominant[has]
        return result.tolist()

    def summary(self) -> dict[str, Any]:
        """A compact, renderer-friendly snapshot: stats + heat maps + a cell sample."""
        c = self.config
        idx = np.flatnonzero(self.alive[: self.n_slots])
        counts = self._clone_counts()
        total = int(counts.sum())
        dominant = int(counts.argmax()) if total else -1
        colonies = int((counts > 0).sum())
        # Cap the cell list sent to the renderer (near-LOD instanced view).
        sample = idx[: c.frame_cell_cap]
        cells = {
            "x": self.cx[sample].tolist(),
            "y": self.cy[sample].tolist(),
            "clone": self.clone[sample].tolist(),
            "energy": self.energy[sample].round(3).tolist(),
            "mut": self.mutations[sample].tolist(),
            "count": int(sample.size),
            "cap": c.frame_cell_cap,
        }
        return {
            "step": self.step_index,
            "alive": total,
            "dead": self.died,
            "born": self.born,
            "died": self.died,
            "colonies": colonies,
            "n_clones": self.n_clones,
            "dominant_clone": dominant,
            "dominant_fraction": (counts[dominant] / total) if total else 0.0,
            "generations": int(self.generation[idx].max()) if idx.size else 0,
            "occupancy": round(total / float(self.capacity), 4),
            "total_nutrient": float(round(self.nutrient.sum(), 3)),
            "mean_genotype": {
                "transport": float(self.gtrans[idx].mean()) if idx.size else 1.0,
                "yield": float(self.gyield[idx].mean()) if idx.size else 1.0,
            },
            "grid": [c.height, c.width],
            "hm_size": [self._block_dims()[2], self._block_dims()[3]],
            "heatmaps": self._heatmaps(idx),
            "clone_map": self._clone_map(idx),
            "cells": cells,
        }

    # ----------------------------------------------------------- checkpoint
    def create_checkpoint(self) -> dict[str, Any]:
        return {
            "config": asdict(self.config),
            "step_index": self.step_index,
            "time": self.time,
            "n_slots": self.n_slots,
            "free": list(self._free),
            "born": self.born,
            "died": self.died,
            "rng": self.rng.bit_generator.state,
            "nutrient": self.nutrient.tolist(),
            "occupant": self.occupant.tolist(),
            "prev_clone_counts": self._prev_clone_counts.tolist(),
            "flags": [self._dominant_announced, self._confluent_announced, self._extinct_announced],
            "events": list(self._events),
            "arrays": {
                name: getattr(self, name)[: self.n_slots].tolist()
                for name in ("cx", "cy", "clone", "gtrans", "gyield", "mass",
                             "energy", "generation", "mutations", "signal", "alive", "starve")
            },
        }

    def restore_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        self.step_index = int(checkpoint["step_index"])
        self.time = float(checkpoint["time"])
        self.n_slots = int(checkpoint["n_slots"])
        self._free = list(checkpoint["free"])
        self.born = int(checkpoint["born"])
        self.died = int(checkpoint["died"])
        self.rng.bit_generator.state = checkpoint["rng"]
        self.nutrient = np.array(checkpoint["nutrient"], dtype=np.float64)
        self.occupant = np.array(checkpoint["occupant"], dtype=np.int32)
        self._prev_clone_counts = np.array(checkpoint["prev_clone_counts"], dtype=np.int64)
        self._dominant_announced, self._confluent_announced, self._extinct_announced = checkpoint["flags"]
        self._events = list(checkpoint["events"])
        n = self.n_slots
        dtypes = {
            "cx": np.int32, "cy": np.int32, "clone": np.int32, "gtrans": np.float64,
            "gyield": np.float64, "mass": np.float64, "energy": np.float64,
            "generation": np.int32, "mutations": np.int32, "signal": np.float64,
            "alive": bool, "starve": np.int32,
        }
        for name, dtype in dtypes.items():
            arr = getattr(self, name)
            arr[:n] = np.array(checkpoint["arrays"][name], dtype=dtype)
