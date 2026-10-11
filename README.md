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
