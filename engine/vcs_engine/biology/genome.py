"""Genome configuration for stochastic gene expression.

A genome here is a small set of genes, each with transcription/translation and
decay rate constants. One gene may be flagged as the **replication initiator**:
its protein product gates DNA replication, coupling gene expression to the cell
cycle. This is a deliberately coarse abstraction of real regulation, sufficient to
make replication (and therefore division) *emerge* from expression dynamics rather
than from a timer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .naming import TARGETS, mrna_var, protein_var


@dataclass(frozen=True)
class GeneSpec:
    """A single gene: expression kinetics plus optional regulatory role.

    Rates are per hour. Transcription is scaled at run time by the cell's mass
    relative to a reference (a larger cell has more machinery) and by the gene's
    heritable expression factor (which mutations alter).

    A gene may **regulate** one cell-level phenotype target: its protein product
    up- or down-modulates that target's realized value (a minimal gene-regulatory
    network), so expression dynamics feed back into transport/membrane/replication/
    metabolism.

    Args:
        name: Gene identifier.
        k_transcription: mRNA synthesis rate at reference mass (molecules/h).
        k_translation: Protein synthesis rate per mRNA (molecules/mRNA/h).
        mrna_decay: First-order mRNA degradation rate (1/h).
        protein_decay: First-order protein degradation rate (1/h).
        is_initiator: If true, this gene's protein gates DNA replication.
        initiator_threshold: Protein count above which replication may initiate.
        regulates: Phenotype target this gene regulates, or ``None``. One of
            ``naming.TARGETS``.
        regulation_mode: ``"activate"`` or ``"repress"``.
        regulation_strength: Maximum fractional effect (0 disables regulation).
        regulation_k: Hill half-saturation protein count.
    """

    name: str
    k_transcription: float = 40.0
    k_translation: float = 20.0
    mrna_decay: float = 5.0
    protein_decay: float = 0.5
    is_initiator: bool = False
    initiator_threshold: float = 20.0
    regulates: Optional[str] = None
    regulation_mode: str = "activate"
    regulation_strength: float = 0.0
    regulation_k: float = 40.0

    def __post_init__(self) -> None:
        if self.regulates is not None and self.regulates not in TARGETS:
            raise ValueError(f"regulates must be one of {TARGETS} or None")
        if self.regulation_mode not in ("activate", "repress"):
            raise ValueError("regulation_mode must be 'activate' or 'repress'")

    @property
    def mrna_var(self) -> str:
        return mrna_var(self.name)

    @property
    def protein_var(self) -> str:
        return protein_var(self.name)


@dataclass
class GenomeConfig:
    """A genome: a set of genes plus the mass reference for expression scaling.

    Args:
        genes: The genes to express.
        reference_mass: Biomass (gDW) at which the configured rates apply.
    """

    genes: list[GeneSpec]
    reference_mass: float = 1.0

    def __post_init__(self) -> None:
        names = [g.name for g in self.genes]
        if len(names) != len(set(names)):
            raise ValueError("gene names must be unique")
        if sum(1 for g in self.genes if g.is_initiator) > 1:
            raise ValueError("at most one gene may be the replication initiator")
        if self.reference_mass <= 0.0:
            raise ValueError("reference_mass must be positive")

    @property
    def initiator(self) -> Optional[GeneSpec]:
        """The initiator gene, or ``None`` if the genome has none."""
        for gene in self.genes:
            if gene.is_initiator:
                return gene
        return None

    def regulators_of(self, target: str) -> list[GeneSpec]:
        """Genes that regulate ``target`` with non-zero strength."""
        return [
            g for g in self.genes
            if g.regulates == target and g.regulation_strength != 0.0
        ]
