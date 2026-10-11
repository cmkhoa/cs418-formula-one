# Exploratory Data Analysis

The code and plots are in `eda.ipynb`. This analysis uses the three CSV files in `sample_data/`. They are only small samples, so these are observations from the sample, not conclusions about an entire F1 season.

## 1. Dataset profiles

| File | Shape | Types / missing values | Notes |
| --- | --- | --- | --- |
| `qualifying.csv` | 10 rows, 9 columns | 6 integer columns, 3 time-string columns; no CSV nulls | All rows are from `raceId` 18. Qualifying positions go from 1 to 10. |
| `results.csv` | 10 rows, 18 columns | Numeric columns plus 5 string columns; no CSV nulls | Some fields use `\N` instead of an actual missing value. |
| `driver_standings.csv` | 10 rows, 7 columns | 6 integer columns and 1 float column; no CSV nulls | Most rows are from race 18, but two are from race 19. |

The notebook prints the shape, `info()` output, null counts, and `describe()` output for each file.

## 2. Data issues

| Issue | Count | What we did |
| --- | ---: | --- |
| `\N` in the results file | 5 rows, 12 cells | Left the original CSV alone. In the notebook, `\N` is changed to missing values in an analysis copy. |
| `milliseconds` read as text | 5 rows affected by `\N` | Converted it to numeric in the analysis copy. |
| Race time formats do not match | 5 non-missing values | Left it alone for now. One value is a total race time and the others are time gaps. |
| Grid and qualifying rank differ | 1 of 6 matched rows | Kept both fields because a penalty or other change may explain it. |
| Incomplete joins | 6 qualifying/results matches; 8 results/standings matches | Used inner joins and showed the join sizes. |
| Exact duplicates | 0 | No rows removed. |

## 7. OpenF1 API exploration

OpenF1 has 18 endpoints. Historical data is free, needs no key, and comes as JSON or CSV. The free tier allows 3 requests/second and 30 requests/minute. Endpoint details are from the API docs; plot findings are from `eda.ipynb`.

## Endpoints

| Topic | Endpoint | What it provides |
| --- | --- | --- |
| Calendar | `meetings`, `sessions` | Race weekends and their sessions, with circuit, country, dates, cancelled flag |
| Drivers / teams | `drivers`, `championship_teams` (beta) | Driver name and number, `team_name` per session; team points and position |
| Results / positions | `session_result`, `starting_grid`, `position` | Final results with DNF/DNS/DSQ, grid positions, in-race position changes over time |
| Pit stops | `pit`, `stints` | Lap, `lane_duration`, `stop_duration`; tyre compound and stint laps |
| Weather | `weather` | Air and track temperature, humidity, wind, rainfall, updated every minute per session |
| Race control | `race_control` | Flags, safety car, session status, incident messages |

## Join keys

- `meeting_key` (weekend) → `session_key` (qualifying, race, etc.) → `driver_number`.
- Driver-level endpoints join on `session_key` + `driver_number`. Teams come from `drivers.team_name`, because `pit` has no team column.
- `weather` and `race_control` join on `session_key`, then align by `date` or `lap_number`.
- `circuit_key` links the same circuit across years.
- There is no `raceId`, so linking to the Kaggle data means matching on year, circuit and date.

## Data-quality issues

- Coverage starts in 2023**, so OpenF1 cannot cover our full 2015–2026 window.
- `stop_duration` only exists from the 2024 US GP.** Earlier stops only have `lane_duration`, which is not comparable.
- `driver_number` is per season**, so never join on it without `session_key`.
- `team_name` is free text**, so rebrands may split a team. Check before grouping.
- `position` is a time series.** Use `session_result` for final results.
- Mixed types:** `session_result.duration` is an array in qualifying, and `gap_to_leader` can be `+N LAP(S)`.
- Deprecated fields:** `pit_duration` and `country_code` go away at the end of 2026.
- Sparse or beta data:** `team_radio` is mostly empty in 2026, `overtakes` is incomplete, and championship endpoints are beta.

## Exploratory plots

The notebook plots sessions per season, pit stop coverage per race (including the share with `stop_duration`), track temperature and rainfall per race, and safety car and red flag counts per race.

Findings: _fill in after running._

Takeaway: OpenF1 works for 2023+ pit-stop, weather and race-event analysis, but not the full 2015–2026 window.

## 3. Distributions

The notebook includes plots for qualifying position, classified finishing position, fastest-lap speed, and positions gained/lost from qualifying.

- Qualifying and finishing position both cover ranks 1–10 once in this sample.
- Points have a median of 3.5 and range from 0 to 10.
- Fastest-lap speed ranges from 212.97 to 218.39 km/h, with a median of 216.09 km/h.
- In the six joined qualifying/results rows, position change ranges from losing 7 places to gaining 4 places.

## 4–6. Relationships, what they show, and what to do next

| Plot | What we saw | Why it matters / next step |
| --- | --- | --- |
| Qualifying position vs. finish position | The 6 matched rows have a correlation of 0.347. Some drivers moved a lot during the race. | Qualifying may matter, but this sample is too small to say how much. Add more races and split finishers from retirements. |
| Grid position vs. finish position | Five drivers started where they qualified; one driver started much farther back. | Grid and qualifying position should be kept as separate variables. Look for penalty or race-control data. |
| Fastest-lap speed vs. finish position | Faster laps generally line up with better finishing positions in this sample (correlation −0.631). | A fastest lap is only one lap. Next, compare normal lap pace while considering tyres, traffic, and safety cars. |
| Finish position vs. driver standings | The 8 joined rows have the same finishing and standings ranks. | This makes sense for a small early-season-style sample. Add full standings data to look at changes over several races. |

These are descriptions, not evidence that one variable causes another.

## Revised questions

With the data currently available, we are exploring:

1. How does qualifying position relate to finishing position?
2. Which drivers gain or lose the most positions from qualifying or the starting grid?
3. How does fastest-lap speed relate to race outcome?
4. How do race results connect to driver standings over time?

To answer the group's broader pit-stop, circuit, weather, and regulation questions, we need the full datasets and race metadata.
