"""Reproduce every number and figure in the README narrative analysis."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/cs418-matplotlib")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import mannwhitneyu

from pipeline_utils import write_json


SEED = 418
BOOTSTRAPS = 20_000
BLUE = "#2F6B9A"
ORANGE = "#D97706"
LIGHT_BLUE = "#9CC4DF"
GRAY = "#6B7280"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/pit_stops_2023_2025.csv"),
    )
    parser.add_argument("--figure-dir", type=Path, default=Path("figures"))
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("metadata/narrative_results.json"),
    )
    return parser.parse_args()


def percentile_interval(values: np.ndarray) -> list[float]:
    return [float(value) for value in np.quantile(values, [0.025, 0.975])]


def build_team_races(data: pd.DataFrame) -> pd.DataFrame:
    driver_results = data[
        [
            "event_id",
            "constructor_ref",
            "driverId",
            "race_points",
            "race_grid_position",
        ]
    ].drop_duplicates(["event_id", "driverId"])
    team_results = (
        driver_results.groupby(["event_id", "constructor_ref"], as_index=False)
        .agg(
            team_points=("race_points", "sum"),
            mean_grid=("race_grid_position", "mean"),
        )
    )
    group_columns = [
        "event_id",
        "year",
        "round",
        "race_name",
        "circuit_ref",
        "constructor_ref",
        "canonical_team_name",
    ]
    stops = (
        data.groupby(group_columns, as_index=False)
        .agg(
            best_stop=("dhl_stop_seconds", "min"),
            median_stop=("dhl_stop_seconds", "median"),
            stop_count=("stop_id", "size"),
        )
    )
    return stops.merge(
        team_results,
        on=["event_id", "constructor_ref"],
        how="left",
        validate="one_to_one",
    )


def fastest_team_bootstrap(
    team_races: pd.DataFrame, rng: np.random.Generator
) -> tuple[float, float, float, list[float]]:
    sufficient_statistics = []
    for _, group in team_races.groupby("event_id"):
        fastest = group["best_stop"] == group["best_stop"].min()
        sufficient_statistics.append(
            [
                group.loc[fastest, "team_points"].sum(),
                fastest.sum(),
                group.loc[~fastest, "team_points"].sum(),
                (~fastest).sum(),
            ]
        )
    stats = np.asarray(sufficient_statistics, dtype=float)
    sampled = stats[
        rng.integers(0, len(stats), size=(BOOTSTRAPS, len(stats)))
    ].sum(axis=1)
    boot_differences = sampled[:, 0] / sampled[:, 1] - sampled[:, 2] / sampled[:, 3]
    fastest_mean = stats[:, 0].sum() / stats[:, 1].sum()
    other_mean = stats[:, 2].sum() / stats[:, 3].sum()
    return (
        float(fastest_mean),
        float(other_mean),
        float(fastest_mean - other_mean),
        percentile_interval(boot_differences),
    )


def clustered_model(team_races: pd.DataFrame, maximum_stop: float | None) -> dict[str, Any]:
    model_data = team_races.dropna(subset=["mean_grid"]).copy()
    if maximum_stop is not None:
        model_data = model_data[model_data["best_stop"] <= maximum_stop]
    model = smf.ols(
        "team_points ~ best_stop + mean_grid + C(event_id) + C(constructor_ref)",
        model_data,
    ).fit(cov_type="cluster", cov_kwds={"groups": model_data["event_id"]})
    return {
        "rows": int(model.nobs),
        "best_stop_coefficient_points_per_second": float(model.params["best_stop"]),
        "confidence_interval_95": [
            float(value) for value in model.conf_int().loc["best_stop"]
        ],
        "p_value": float(model.pvalues["best_stop"]),
        "controls": "mean starting-grid position, event fixed effects, and team fixed effects",
    }


def event_year_bootstrap(
    event_medians: pd.DataFrame, rng: np.random.Generator
) -> tuple[float, float, float, list[float]]:
    first = event_medians.loc[event_medians["year"] == 2023, "median_stop"].to_numpy()
    last = event_medians.loc[event_medians["year"] == 2025, "median_stop"].to_numpy()
    boot_first = np.median(
        first[rng.integers(0, len(first), size=(BOOTSTRAPS, len(first)))], axis=1
    )
    boot_last = np.median(
        last[rng.integers(0, len(last), size=(BOOTSTRAPS, len(last)))], axis=1
    )
    first_median = float(np.median(first))
    last_median = float(np.median(last))
    return (
        first_median,
        last_median,
        last_median - first_median,
        percentile_interval(boot_last - boot_first),
    )


def paired_bootstrap(
    differences: np.ndarray, rng: np.random.Generator
) -> tuple[float, list[float]]:
    boot = np.median(
        differences[
            rng.integers(
                0, len(differences), size=(BOOTSTRAPS, len(differences))
            )
        ],
        axis=1,
    )
    return float(np.median(differences)), percentile_interval(boot)


def style_axis(axis: plt.Axes) -> None:
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.grid(axis="y", color="#E5E7EB", linewidth=0.8)
    axis.set_axisbelow(True)


def figure_points_by_rank(team_races: pd.DataFrame, output: Path) -> None:
    plot_data = team_races.copy()
    plot_data["pit_rank"] = plot_data.groupby("event_id")["best_stop"].rank(
        method="min"
    )
    rng = np.random.default_rng(SEED)
    jitter = rng.normal(0, 0.07, len(plot_data))
    means = plot_data.groupby("pit_rank", as_index=False)["team_points"].mean()

    figure, axis = plt.subplots(figsize=(9, 5.4))
    axis.scatter(
        plot_data["pit_rank"] + jitter,
        plot_data["team_points"],
        s=16,
        alpha=0.17,
        color=GRAY,
        edgecolors="none",
        label="Team-race",
    )
    axis.plot(
        means["pit_rank"],
        means["team_points"],
        color=BLUE,
        marker="o",
        linewidth=2.4,
        markersize=6,
        label="Mean team points",
    )
    axis.set_title(
        "Teams with the fastest stop usually scored more race points",
        loc="left",
        fontsize=14,
        fontweight="bold",
    )
    axis.set_xlabel("Rank of the team's fastest stop within the race (1 = fastest)")
    axis.set_ylabel("Team points in the race")
    axis.set_xticks(range(1, 11))
    axis.set_xlim(0.5, 10.5)
    axis.set_ylim(bottom=0)
    axis.legend(frameon=False, loc="upper right")
    style_axis(axis)
    figure.tight_layout()
    figure.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(figure)


def figure_team_trends(team_years: pd.DataFrame, output: Path) -> None:
    figure, axis = plt.subplots(figsize=(9, 5.8))
    colors = plt.get_cmap("tab10").colors
    for index, (team, group) in enumerate(team_years.groupby("canonical_team_name")):
        group = group.sort_values("year")
        axis.plot(
            group["year"],
            group["typical_stop"],
            marker="o",
            linewidth=2,
            markersize=5,
            color=colors[index % len(colors)],
            label=team,
        )
    axis.set_title(
        "Seven of eight continuously named teams were faster in 2025 than 2023",
        loc="left",
        fontsize=14,
        fontweight="bold",
    )
    axis.set_xlabel("Season")
    axis.set_ylabel("Typical race-level median stop (seconds)")
    axis.set_xticks([2023, 2024, 2025])
    axis.legend(frameon=False, ncol=2, fontsize=9, loc="upper right")
    style_axis(axis)
    figure.tight_layout()
    figure.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(figure)


def figure_rain_comparison(event_medians: pd.DataFrame, output: Path) -> None:
    dry = event_medians.loc[~event_medians["rain"], "median_stop"].to_numpy()
    wet = event_medians.loc[event_medians["rain"], "median_stop"].to_numpy()
    rng = np.random.default_rng(SEED)
    figure, axis = plt.subplots(figsize=(8, 5.4))
    box = axis.boxplot(
        [dry, wet],
        positions=[0, 1],
        widths=0.48,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": "#111827", "linewidth": 2},
        boxprops={"linewidth": 1.2},
        whiskerprops={"linewidth": 1.2},
        capprops={"linewidth": 1.2},
    )
    box["boxes"][0].set_facecolor("#D1D5DB")
    box["boxes"][1].set_facecolor(LIGHT_BLUE)
    for position, values, color in [(0, dry, GRAY), (1, wet, BLUE)]:
        axis.scatter(
            position + rng.normal(0, 0.055, len(values)),
            values,
            color=color,
            alpha=0.72,
            s=28,
            edgecolors="white",
            linewidths=0.4,
        )
    axis.set_title(
        "Race-level rain flags did not separate typical stop times",
        loc="left",
        fontsize=14,
        fontweight="bold",
    )
    axis.set_xticks([0, 1], [f"No rain\n(n={len(dry)})", f"Rain recorded\n(n={len(wet)})"])
    axis.set_ylabel("Median stationary stop time in the race (seconds)")
    axis.set_xlabel("")
    style_axis(axis)
    figure.tight_layout()
    figure.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    args = parse_args()
    args.figure_dir.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(args.input)
    if len(data) != 2225 or data["stop_id"].nunique() != len(data):
        raise ValueError("Narrative analysis requires the audited 2,225-row final dataset")

    rng = np.random.default_rng(SEED)
    team_races = build_team_races(data)
    fastest_mean, other_mean, points_gap, points_gap_ci = fastest_team_bootstrap(
        team_races, rng
    )
    full_model = clustered_model(team_races, maximum_stop=None)
    typical_stop_model = clustered_model(team_races, maximum_stop=4.0)

    event_medians = (
        data.groupby(
            ["event_id", "year", "race_name", "circuit_ref"], as_index=False
        )
        .agg(
            median_stop=("dhl_stop_seconds", "median"),
            rain=("openf1_any_rain", "first"),
        )
    )
    event_medians["rain"] = (
        event_medians["rain"].astype(str).str.casefold().eq("true")
    )
    first_median, last_median, year_change, year_change_ci = event_year_bootstrap(
        event_medians, rng
    )

    common_circuits = (
        event_medians[event_medians["year"].isin([2023, 2025])]
        .pivot_table(index="circuit_ref", columns="year", values="median_stop")
        .dropna()
    )
    circuit_change, circuit_change_ci = paired_bootstrap(
        (common_circuits[2025] - common_circuits[2023]).to_numpy(), rng
    )

    continuous_teams = set(
        team_races.loc[team_races["year"] == 2023, "constructor_ref"]
    )
    for year in (2024, 2025):
        continuous_teams &= set(
            team_races.loc[team_races["year"] == year, "constructor_ref"]
        )
    team_years = (
        team_races[team_races["constructor_ref"].isin(continuous_teams)]
        .groupby(
            ["year", "constructor_ref", "canonical_team_name"], as_index=False
        )
        .agg(typical_stop=("median_stop", "median"))
    )
    team_wide = team_years.pivot(
        index=["constructor_ref", "canonical_team_name"],
        columns="year",
        values="typical_stop",
    )
    team_wide["change_2025_minus_2023"] = team_wide[2025] - team_wide[2023]
    teams_improved = int((team_wide["change_2025_minus_2023"] < 0).sum())
    largest_improvement_key = team_wide["change_2025_minus_2023"].idxmin()
    largest_improvement = float(
        team_wide.loc[largest_improvement_key, "change_2025_minus_2023"]
    )
    mercedes_pairs = (
        team_races[
            (team_races["constructor_ref"] == "mercedes")
            & team_races["year"].isin([2023, 2025])
        ]
        .pivot_table(index="circuit_ref", columns="year", values="median_stop")
        .dropna()
    )
    mercedes_change, mercedes_change_ci = paired_bootstrap(
        (mercedes_pairs[2025] - mercedes_pairs[2023]).to_numpy(), rng
    )

    dry = event_medians.loc[~event_medians["rain"], "median_stop"]
    wet = event_medians.loc[event_medians["rain"], "median_stop"]
    rain_test = mannwhitneyu(wet, dry, alternative="two-sided")
    rain_model = smf.ols(
        "median_stop ~ rain + C(year)", event_medians
    ).fit(cov_type="HC3")
    rain_key = "rain[T.True]"
    mixed_circuit_differences = []
    for _, group in event_medians.groupby("circuit_ref"):
        if group["rain"].nunique() == 2:
            mixed_circuit_differences.append(
                group.loc[group["rain"], "median_stop"].mean()
                - group.loc[~group["rain"], "median_stop"].mean()
            )
    mixed_differences = np.asarray(mixed_circuit_differences)
    within_circuit_boot = np.mean(
        mixed_differences[
            rng.integers(
                0,
                len(mixed_differences),
                size=(BOOTSTRAPS, len(mixed_differences)),
            )
        ],
        axis=1,
    )

    figure_points_by_rank(team_races, args.figure_dir / "finding-points-by-pit-rank.png")
    figure_team_trends(team_years, args.figure_dir / "finding-team-improvement.png")
    figure_rain_comparison(event_medians, args.figure_dir / "finding-rain.png")

    results = {
        "input": args.input.as_posix(),
        "random_seed": SEED,
        "bootstrap_resamples": BOOTSTRAPS,
        "finding_1_points_and_fast_stops": {
            "team_races": len(team_races),
            "events": team_races["event_id"].nunique(),
            "mean_points_fastest_stop_team": fastest_mean,
            "mean_points_other_teams": other_mean,
            "difference_points": points_gap,
            "event_cluster_bootstrap_confidence_interval_95": points_gap_ci,
            "adjusted_full_sample_model": full_model,
            "sensitivity_best_stop_at_most_4_seconds": typical_stop_model,
        },
        "finding_2_change_over_time": {
            "event_median_2023_seconds": first_median,
            "event_median_2025_seconds": last_median,
            "change_2025_minus_2023_seconds": year_change,
            "independent_event_bootstrap_confidence_interval_95": year_change_ci,
            "continuous_teams": len(continuous_teams),
            "continuous_teams_with_lower_2025_typical_stop": teams_improved,
            "largest_improvement_team": largest_improvement_key[1],
            "largest_improvement_seconds": largest_improvement,
            "common_circuit_count": len(common_circuits),
            "common_circuit_median_change_seconds": circuit_change,
            "common_circuit_bootstrap_confidence_interval_95": circuit_change_ci,
            "mercedes_common_circuit_count": len(mercedes_pairs),
            "mercedes_common_circuit_median_change_seconds": mercedes_change,
            "mercedes_common_circuit_bootstrap_confidence_interval_95": mercedes_change_ci,
            "team_year_typical_stop_seconds": [
                {
                    "year": int(row.year),
                    "team": row.canonical_team_name,
                    "seconds": float(row.typical_stop),
                }
                for row in team_years.itertuples()
            ],
        },
        "finding_3_rain": {
            "dry_events": len(dry),
            "rain_events": len(wet),
            "dry_event_median_seconds": float(dry.median()),
            "rain_event_median_seconds": float(wet.median()),
            "mann_whitney_u": float(rain_test.statistic),
            "mann_whitney_p_value": float(rain_test.pvalue),
            "year_adjusted_rain_difference_seconds": float(
                rain_model.params[rain_key]
            ),
            "year_adjusted_confidence_interval_95": [
                float(value) for value in rain_model.conf_int().loc[rain_key]
            ],
            "year_adjusted_p_value": float(rain_model.pvalues[rain_key]),
            "circuits_observed_in_both_conditions": len(mixed_differences),
            "mean_within_circuit_rain_difference_seconds": float(
                mixed_differences.mean()
            ),
            "within_circuit_bootstrap_confidence_interval_95": percentile_interval(
                within_circuit_boot
            ),
        },
        "analyses_not_used": {
            "driver_level_outcome_model": (
                "Left out because race outcomes repeat across a driver's multiple stops; "
                "the team-race aggregation answers the project question without pseudoreplication."
            ),
            "openf1_stationary_duration_comparison": (
                "Left out because OpenF1 stop_duration is missing for 1,376 of 2,225 final rows."
            ),
            "fastf1_model": (
                "Left out because saved FastF1 lap context covers only 99 stops in three races."
            ),
        },
        "figures": [
            "figures/finding-points-by-pit-rank.png",
            "figures/finding-team-improvement.png",
            "figures/finding-rain.png",
        ],
    }
    write_json(args.results, results)
    print(f"Narrative figures written to {args.figure_dir}")
    print(f"Narrative results written to {args.results}")
    print(f"Fastest-stop points gap: {points_gap:.2f} points")
    print(f"2025 minus 2023 event median: {year_change:.3f} seconds")
    print(
        "Year-adjusted rain difference: "
        f"{rain_model.params[rain_key]:.3f} seconds"
    )


if __name__ == "__main__":
    main()
