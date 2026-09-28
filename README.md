# cs418-formula-one
CS418 Intro to Data Science Project on F1

## Group Members:
- Neha Kamat
- Rahul Gowda
- Shanmukh Cherbrolu
- Michael Cao

## Current Questions:
- Does having the fastest pit stops in a season (or at a race) translate into better finishing positions or more points?
- Which teams improved their pit stop times over a season, and did that match their standings changes?
- Do pit stop times differ by circuit, or by era (2015 to 2026)?
- Are pit stop times getting faster over time, and how did rule changes affect them?
- How much does the 2026 regs change the order compared to previous reg changes?
- How does a driver's qualifying position predict their finishing position and how does this vary across circuits and weather conditions?
- Which drivers consistently gain or lose the most positions relative to where they qualify?
- What distinguishes high-performing F1 drivers, and how does that change depending on the performance metrics used?

## Sources:
### Main sources
- [FastF1 API](https://docs.fastf1.dev/): Main source of data, contains race data from 1950s-present
- [Kaggle F1 Race Dataset](https://www.kaggle.com/datasets/jtrotman/formula-1-race-data): secondary, more details race progression lap by lap
- https://openf1.org/
### Side source
- [DHL Fastest Pitstop API](https://inmotion.dhl/en/formula-1/fastest-pit-stop-award): data for pitstop times, requires reddit community's reverse engineering of API
- https://github.com/toUpperCase78/formula1-datasets

## Datashape
- The dataset contains 14 CSV files with different shapes, including 1,172 rows × 18 columns for races, 27,568 rows × 18 columns for race results, and 883,003 rows × 6 columns for lap times. Each file represents a different aspect of Formula 1, such as drivers, teams, circuits, and race performance, and the tables are connected through shared IDs.
