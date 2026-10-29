# cs418-formula-one

CS418 Intro to Data Science Project on F1

## Group Members

- Neha Kamat
- Rahul Gowda
- Shanmukh Cherbrolu
- Michael Cao

## Current Questions

- Does having the fastest pit stops in a season or race lead to better finishing positions or more points?
- Which teams improved their pit-stop times over a season, and did their standings change too?
- Do pit-stop times differ by circuit or era?
- How does qualifying position relate to finishing position?
- Which drivers gain or lose the most places compared with where they qualified?

## Sources

### Main sources

- [FastF1 API](https://docs.fastf1.dev/)
- [Kaggle F1 Race Dataset](https://www.kaggle.com/datasets/jtrotman/formula-1-race-data)
- [OpenF1](https://openf1.org/)

### Side sources

- [DHL Fastest Pit Stop Award](https://inmotion.dhl/en/formula-1/fastest-pit-stop-award)
- [formula1-datasets](https://github.com/toUpperCase78/formula1-datasets)

## Data shape

The larger source dataset has related tables for races, results, lap times, drivers, teams, and circuits. The repository currently includes small samples for qualifying, results, and driver standings.

## Exploratory analysis

`eda.ipynb` contains our exploratory work, and `EDA.md` summarizes it. The notebook checks shapes, types, missing values, and summary statistics before making a few basic plots.

We found no exact duplicates or CSV nulls. The main issue is that `results.csv` uses `\N` in 5 rows (12 cells), so the notebook changes those values to missing only in an analysis copy. We also found one grid/qualifying mismatch and incomplete joins between the sample files.

The plots look at qualifying vs. finish position, grid vs. finish position, fastest-lap speed vs. finish position, and results vs. standings. Since the files only have 10 rows each, these are just starting observations. We need the full data before making claims about teams, circuits, pit stops, weather, or rule changes.

## Data documentation

Our full data documentation is in [`DATASHEET.md`](DATASHEET.md). It includes the datasheets, research-question scope, codebook, rebuilding recipe, access and reuse notes, and discussion of the people represented by the data.

- **DHL Fastest Pit Stop Award data:** [official DHL page](https://inmotion.dhl/en/formula-1/fastest-pit-stop-award), accessed through the [`Jordan-Soria/PitStops`](https://github.com/Jordan-Soria/PitStops) mirror. No license is stated for the mirror or the underlying tables.
- **OpenF1:** [OpenF1 API](https://openf1.org/docs/). OpenF1 permits historical access for educational, research, personal-learning, and non-commercial fan projects, but does not claim ownership of the underlying Formula One data.
- **Formula 1 Race Data:** [Kaggle/Ergast-derived dataset](https://www.kaggle.com/datasets/jtrotman/formula-1-race-data). The exact Kaggle license was not recorded in the repository and must be checked on the dataset page before redistribution.
- **FastF1:** [FastF1](https://docs.fastf1.dev/) is used as a one-race exploratory and validation source. Its software is MIT-licensed; that license does not automatically cover the underlying timing data.

The biggest limitation is that the repository does not yet contain a finished join between pit stops and race outcomes. The saved DHL data cover only the 2023 Bahrain Grand Prix, while the broader OpenF1 and FastF1 pulls are not stored as versioned data files, so we cannot yet make season-wide or causal claims.
