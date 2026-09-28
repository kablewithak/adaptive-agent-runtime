from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from adaptive_runtime.evaluation.benchmark_program import (
    R4_CASE_COUNT,
    R4_TEMPLATE_COUNT,
    BenchmarkPartition,
    HarbourDeskFailureFamily,
)


class AuthoringContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class AuthoringTemplate(AuthoringContract):
    template_id: str = Field(min_length=1, max_length=100)
    family: HarbourDeskFailureFamily
    partition: BenchmarkPartition
    mechanism_key: str | None = Field(default=None, max_length=120)
    challenge_statement: str | None = Field(default=None, max_length=500)
    evidence_requirements: tuple[str, ...] = ()
    perturbation_axes: tuple[str, ...] = ()
    anti_shortcut_constraints: tuple[str, ...] = ()
    instance_ids: tuple[str, ...] = Field(min_length=5, max_length=5)
    sealed: bool = False

    @model_validator(mode="after")
    def validate_template(self) -> AuthoringTemplate:
        if len(set(self.instance_ids)) != 5:
            raise ValueError("template instance IDs must be unique")
        for case_id in self.instance_ids:
            if not (len(case_id) == 7 and case_id.startswith("hdb-") and case_id[4:].isdigit()):
                raise ValueError("public case IDs must use opaque hdb-NNN identities")

        if self.partition is BenchmarkPartition.LOCKED:
            if not self.sealed:
                raise ValueError("locked template slots must remain sealed")
            if self.mechanism_key is not None or self.challenge_statement is not None:
                raise ValueError("locked mechanisms must not be development-visible")
            if (
                self.evidence_requirements
                or self.perturbation_axes
                or self.anti_shortcut_constraints
            ):
                raise ValueError("locked authoring detail must remain sealed")
        else:
            if self.sealed:
                raise ValueError("development and validation templates must be explicit")
            if self.mechanism_key is None or self.challenge_statement is None:
                raise ValueError("materializable templates require a mechanism and challenge")
            if not self.evidence_requirements:
                raise ValueError("materializable templates require evidence requirements")
            if len(self.perturbation_axes) < 2:
                raise ValueError("materializable templates require perturbation axes")
            if len(self.anti_shortcut_constraints) < 2:
                raise ValueError("materializable templates require anti-shortcut constraints")
        return self


class AuthoringCatalog(AuthoringContract):
    schema_version: Literal["harbourdesk-r4-template-catalog-v2"] = (
        "harbourdesk-r4-template-catalog-v2"
    )
    exact_locked_fixture_material_sealed: bool = True
    templates: tuple[AuthoringTemplate, ...] = Field(
        min_length=R4_TEMPLATE_COUNT,
        max_length=R4_TEMPLATE_COUNT,
    )

    @model_validator(mode="after")
    def validate_catalog(self) -> AuthoringCatalog:
        if len({item.template_id for item in self.templates}) != R4_TEMPLATE_COUNT:
            raise ValueError("template IDs must be unique")

        explicit_mechanisms = tuple(
            item.mechanism_key
            for item in self.templates
            if item.partition is not BenchmarkPartition.LOCKED
        )
        if len(explicit_mechanisms) != 24 or len(set(explicit_mechanisms)) != 24:
            raise ValueError("24 development/validation mechanisms must be unique")

        case_ids = tuple(case_id for item in self.templates for case_id in item.instance_ids)
        if len(case_ids) != R4_CASE_COUNT or len(set(case_ids)) != R4_CASE_COUNT:
            raise ValueError("catalog must contain exactly 180 unique public case IDs")

        partitions = Counter(item.partition for item in self.templates)
        if partitions != Counter(
            {
                BenchmarkPartition.DEVELOPMENT: 18,
                BenchmarkPartition.VALIDATION: 6,
                BenchmarkPartition.LOCKED: 12,
            }
        ):
            raise ValueError("template partition counts must be 18/6/12")

        for family in HarbourDeskFailureFamily:
            items = tuple(item for item in self.templates if item.family is family)
            if len(items) != 6:
                raise ValueError("each family requires exactly six template slots")
            if Counter(item.partition for item in items) != Counter(
                {
                    BenchmarkPartition.DEVELOPMENT: 3,
                    BenchmarkPartition.VALIDATION: 1,
                    BenchmarkPartition.LOCKED: 2,
                }
            ):
                raise ValueError("each family requires 3 development, 1 validation, 2 locked slots")

        if not self.exact_locked_fixture_material_sealed:
            raise ValueError("exact locked fixture material must remain sealed")
        return self


def load_r4_template_catalog(repo_root: Path) -> AuthoringCatalog:
    path = repo_root / "benchmarks" / "harbourdesk" / "r4" / "template_catalog_v2.json"
    return AuthoringCatalog.model_validate_json(path.read_text(encoding="utf-8"))
