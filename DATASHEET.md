# Data Documentation: Formula One Pit Stops

This document explains the data we currently have, where it came from, and what it can and cannot support. Our project is about Formula One pit stops, especially whether faster stops are connected to race results and whether teams improve during a season. The repository is still at the exploratory stage, so this datasheet separates data that is actually saved in the repository from data that the notebooks download when they run.

## Quick summary

| Dataset | Role in this project | Data currently saved in the repo | Coverage of the saved data | Main limitation |
| --- | --- | --- | --- | --- |
| DHL Fastest Pit Stop Award, through `Jordan-Soria/PitStops` | Primary pit-stop dataset | 52 Bahrain 2023 stops and 10 team standings rows | One race and one season standings table | The GitHub mirror does not state a license, and its extraction method is not documented in detail |
| OpenF1 | Primary supporting source | No API response is saved; the notebook contains download code | Code requests 2023–2026 races | Results can change when the API is rerun, and stationary `stop_duration` begins only at the 2024 United States GP |
| Kaggle Formula 1 Race Data (Ergast-derived) | Secondary race-results source | Three 10-row samples | Mostly race 18 in the samples | The samples are too small and are not yet joined to the pit-stop data |
| FastF1 | Exploratory and validation source | No returned data is saved; notebook output describes the 2023 Bahrain GP | One race | One race cannot support season-level conclusions |

The biggest overall limitation is that we have **not yet built a single joined analysis table connecting pit stops to race results**. The current notebooks explore the sources separately. Any statement below about relationships between pit-stop time and finishing position is therefore a research goal, not a result.

---

## 1. Datasheets for the primary datasets

### 1.1 DHL Fastest Pit Stop Award data

#### Motivation

DHL created the Fastest Pit Stop Award in 2015 to recognize the teamwork and performance of Formula One pit crews. DHL describes pit stops as an example of how Formula One is a team sport and says the award recognizes people whose work contributes to a driver's success. This purpose comes from the [official DHL award page](https://inmotion.dhl/en/formula-1/fastest-pit-stop-award).

We do not download the tables directly from DHL. Our notebook uses the [`Jordan-Soria/PitStops`](https://github.com/Jordan-Soria/PitStops) GitHub mirror. The related [`f1pits` documentation](https://github.com/Jordan-Soria/f1pits) says that its race-level data were extracted from the DHL website. José Jordán-Soria created the mirror and package. Funding for the extraction and mirror is **not documented by the publisher**. DHL funds and presents the award, but the funding arrangement for the data publication is also **not documented by the publisher**.

#### Composition

One row in a race file represents one ranked pit stop by one driver in one Grand Prix. Its fields are rank, team, driver, stationary stop time, lap, and DHL award points. One row in the championship file represents one team's season standing and accumulated DHL points.

The repository holds:

- [`sample_data/dhl_pitstops_2023_r01_bahrain.tsv`](sample_data/dhl_pitstops_2023_r01_bahrain.tsv): 52 rows × 6 columns, covering the 2023 Bahrain Grand Prix.
- [`sample_data/dhl_pitstop_champ_2023.tsv`](sample_data/dhl_pitstop_champ_2023.tsv): 10 rows × 3 columns, covering the 2023 team standings.

The Bahrain file contains all 52 entries shown in the mirrored race table, ranked 1 through 52. It includes 20 drivers and 10 teams. Stop times range from 2.22 to 42.57 seconds. The file has no empty cells or exact duplicate rows. A lap value of 0 appears in the file; neither DHL nor the mirror documents what that value means, so we should not reinterpret it as missing or as a normal race lap.

The `f1pits` documentation says its pit-stop data begin in 2018 and that sprint stops are not included. It also explains that only the top ten stops receive points and that a driver's later top-ten stop receives zero points. The saved Bahrain file is one race, not a random sample, but the publisher does not clearly document whether every stop in every mirrored race file is guaranteed to be present. For that reason, we cannot claim complete historical coverage without checking every race against another source.

#### Collection process

The mirror's documentation says the tables were extracted from the DHL website. It does not explain the scraper, the original endpoint, validation steps, or whether any entries were manually corrected. Those details are **not documented by the publisher**. The data concern public sporting performances by named drivers and teams. The pit-crew members doing the work are not named. Individual consent is **not documented by the publisher**.

#### Preprocessing

The publisher's preprocessing is **not documented** beyond saying that the data were extracted from DHL. The mirrored files are tab-separated text even though the upstream filenames use `.csv`. They also contain extra whitespace in headers and values. Our `read_dhl` function in [`eda.ipynb`](eda.ipynb) strips that whitespace and converts rank, time, lap, and points to numeric values. The original sample files remain unchanged.

#### Uses

The `f1pits` package is intended for retrieving and visualizing pit-stop performance. In our project, the data can describe which recorded stops were fastest, compare recorded team times, and track DHL award points.

This source should not be used by itself to claim that a fast stop causes a good race result. It also should not be treated as a measure of each crew member's individual ability, a complete description of race strategy, or a complete record of all pit-lane time. The recorded time is stationary stop time, not necessarily the driver's total time lost entering and leaving the pit lane.

#### Distribution

The mirror is distributed as plain-text files on GitHub. We accessed it through the GitHub API and raw-file URLs in [`eda.ipynb`](eda.ipynb). The repository does not state a license. Therefore, we cannot assume that the mirrored files or our republished processed copy can be freely redistributed. The original DHL page also does not give a reusable-data license on the award page. We can share our code and small samples already in this course repository, but broader redistribution requires clarification from the rights holders.

#### Maintenance

The mirror is maintained by José Jordán-Soria. The notebook checks annual folders from 2018 through 2026, but it does not save the returned file list or the mirror's commit hash. Updates can be detected through the GitHub commit history. There is no documented update schedule or guarantee of long-term maintenance.

### 1.2 OpenF1

#### Motivation

[OpenF1](https://openf1.org/) describes itself as an independent, community-driven project whose goal is to make Formula One data open and accessible. Sponsors help cover server costs. It is not an official Formula One or FIA service.

#### Composition

OpenF1 is an API rather than one fixed table. The endpoints used in our notebook have different units of observation:

- `sessions`: one row per track session.
- `pit`: one row per car's trip through the pit lane.
- `weather`: one weather reading within a session.
- `race_control`: one race-control event or message.

The [OpenF1 documentation](https://openf1.org/docs/) says historical data are available from 2023 onward. The notebook requests all sessions for 2023–2026, keeps non-cancelled races, and then requests pit, weather, and race-control rows for each race. However, the API responses and printed row counts are not saved in the repository. Their current sizes are therefore **not reproducible from the repository alone**.

OpenF1 documents `lane_duration` as total time in the pit lane and `stop_duration` as stationary time. It also states that `stop_duration` is available only from the 2024 United States Grand Prix onward. That missing period is structural, not evidence that earlier cars did not stop. OpenF1 does not include seasons before 2023.

#### Collection process

OpenF1 says that it provides real-time and historical timing data, but its public documentation does not fully describe the original collection hardware, its complete validation process, or every transformation from the Formula One timing stream. Those details are **not documented by the publisher**. The API records public sporting activity by named drivers and teams. Driver consent for this independent republication is **not documented by the publisher**.

#### Preprocessing

OpenF1 returns already structured JSON or CSV. Any publisher-side cleaning beyond the documented field definitions is **not documented by the publisher**. Our notebook converts each JSON response into a pandas dataframe, adds a readable race `label`, and derives a Boolean `rain` field from `rainfall > 0`. It does not alter the API's source data.

#### Uses

OpenF1 is suitable for educational and research projects involving pit-lane duration, weather, race control, sessions, and other timing information from 2023 onward. Its own site says it is intended for educational purposes, personal learning, research, and non-commercial fan engagement.

It should not be used for analysis before 2023. `lane_duration` and `stop_duration` should not be treated as the same measure. We also should not compare stationary stop time across the full 2023–2026 period because that field begins late in 2024. OpenF1 is unofficial, so it should not be treated as an official FIA timing record.

#### Distribution

Historical data are available without authentication from `https://api.openf1.org/v1` in JSON or CSV. The free tier is limited to 3 requests per second and 30 requests per minute. OpenF1 says credit is appreciated but not required, and limits its stated intended uses to education, learning, research, and non-commercial fan engagement. It also says that it does not claim ownership of Formula One data, trademarks, or broadcasts. Because this is not a conventional open-data license for the underlying records, we will share our analysis code but will not claim ownership of or unrestricted reuse rights over an OpenF1 data export.

#### Maintenance

OpenF1 is an active community project. The documentation can change, fields can be deprecated, and current-season records can be updated. For example, `pit_duration` is marked deprecated and scheduled for removal after 2026. A future user should record the retrieval date, API parameters, and returned row counts each time the notebook is run. Our documentation was checked on October 28, 2026.

### 1.3 Secondary and validation sources

#### Kaggle Formula 1 Race Data

The repository's three CSV samples come from the Kaggle dataset [`jtrotman/formula-1-race-data`](https://www.kaggle.com/datasets/jtrotman/formula-1-race-data), which is an Ergast-derived relational dataset. In our project, these files supply qualifying positions, race results, and standings rather than pit-stop measurements. The repository contains only 10 rows from each table. The full data are downloaded by [`data_acquisition.ipynb`](data_acquisition.ipynb) but are not committed.

The notebook's saved output reports full-table shapes of 11,298 qualifying rows, 27,568 result rows, and 35,695 driver-standing rows at the time it was run. Since the downloaded version and files are not saved, these figures describe that run and not a permanent version. Publisher funding, the exact collection process, and consent are **not documented by the publisher** in the materials saved here. The Kaggle page's exact license could not be verified from the repository, so we do not claim a license for it.

#### FastF1

[FastF1](https://docs.fastf1.dev/) is an unofficial Python package for Formula One timing and telemetry. We use it only to inspect the 2023 Bahrain race and to compare its 52 recorded pit-in laps with the 52 rows in the DHL mirror. The notebook reports 1,056 lap rows, 20 qualifying rows, and 161 weather rows. FastF1's software and documentation are MIT-licensed, but that license does not automatically grant rights to the underlying Formula One timing data. Its publisher-side transformations beyond documented fields are not fully described in our repository.

## 2. Scope of the research questions

Here, the **target population** is what we would like to make a claim about, the **access frame** is what the available sources let us reach, and the **sample** is what we actually analyze.

| Research question | Target population | Access frame | Current sample | What is missing and what that limits |
| --- | --- | --- | --- | --- |
| Does having faster pit stops in a race or season relate to better finishing positions or more points? | All driver-race entries and teams in Formula One World Championship races | Pit stops listed by the DHL mirror plus race results available from the Kaggle/Ergast-derived tables | 52 DHL stops from 2023 Bahrain; 10 sampled result rows that are not yet joined to those stops | The two samples are not aligned or joined. We cannot yet estimate the relationship, and an observational join would show association rather than causation. |
| Which teams improve their pit-stop times during a season, and do their standings change too? | All teams competing across complete Formula One seasons | DHL race tables available from 2018 onward and their season standings | One 2023 race table and the 10-row 2023 DHL team standings file saved in the repo | One race cannot measure improvement. Team rebranding and lineup changes also make comparisons across seasons difficult. |
| Do pit-stop times differ by circuit or era? | All pit stops at all Formula One championship circuits and seasons | DHL mirror from 2018 onward; OpenF1 from 2023 onward | One circuit in the saved DHL sample; no saved OpenF1 response | Earlier eras, many circuits, and changes in timing definitions are missing. We cannot generalize beyond Bahrain 2023 from the committed file. |
| How do weather and race interruptions relate to pit stops? | All Formula One race sessions and stops | OpenF1 weather, race-control, and pit endpoints from 2023 onward | Download code exists, but no API extract is saved | We cannot reproduce a numerical result until the responses are saved. Weather readings and race-control events also need a documented time- or lap-based alignment to stops. |

The access frames are not probability samples. They are convenience records created for sports timing and awards. This means missing races or stops may be systematic rather than random.

## 3. Codebook

The codebook includes every raw or derived column currently used by [`eda.ipynb`](eda.ipynb) for pit-stop analysis and its supporting race-outcome plots. API ranges marked “depends on API run” cannot be calculated without saving the response.

### DHL race and championship tables

| Column | Type | Units | Meaning | Range or allowed values in saved sample | Missing-value coding | Origin |
| --- | --- | --- | --- | --- | --- | --- |
| `Pos.` | integer | rank | Rank of the stop by stationary time, where 1 is fastest | 1–52 in Bahrain; 1–10 in standings | Empty cell becomes `NaN` | Raw DHL mirror; numeric conversion in `read_dhl` |
| `Team` | string | none | Team name | 10 team names | Empty string/`NaN` | Raw DHL mirror |
| `Driver` | string | none | Driver surname | 20 drivers in Bahrain | Empty string/`NaN` | Raw DHL mirror |
| `Time (sec)` | float | seconds | Stationary pit-stop time | 2.22–42.57 | Empty or nonnumeric value becomes `NaN` | Raw DHL mirror; numeric conversion in `read_dhl` |
| `Lap` | integer | lap number | Race lap associated with the stop; sprints excluded | 0–54; meaning of 0 is undocumented | Empty or nonnumeric value becomes `NaN` | Raw DHL mirror; numeric conversion in `read_dhl` |
| `Points` | integer | DHL award points | Points assigned for the ranked stop or accumulated by a team | Race: 0, 1, 2, 4, 6, 8, 10, 12, 15, 18, 25; standings: 14–543 | Empty or nonnumeric value becomes `NaN` | Raw DHL mirror; numeric conversion in `read_dhl` |
| `year` | integer | calendar year | Season parsed from folder name | 2018–2026 in download loop | None after a successful parse | Derived in `eda.ipynb` |
| `round` | integer | race round | Leading number parsed from filename | Depends on downloaded file | None after a successful parse | Derived in `eda.ipynb` |
| `file` | string | none | Source filename | Depends on downloaded file | None | Derived in `eda.ipynb` |

### OpenF1 fields used

| Column | Type | Units | Meaning | Range or allowed values | Missing-value coding | Origin |
| --- | --- | --- | --- | --- | --- | --- |
| `session_key` | integer | none | OpenF1 identifier for a session | Depends on API run | JSON `null` | OpenF1 `sessions`, `pit`, `weather`, and `race_control` |
| `meeting_key` | integer | none | OpenF1 identifier for a race weekend | Depends on API run | JSON `null` | OpenF1 API |
| `year` | integer | year | Season of the session | 2023–2026 in our query | JSON `null` | `sessions` |
| `session_name` | string | none | Session name | Filtered to `Race` | JSON `null` | `sessions` |
| `is_cancelled` | Boolean | none | Whether the session was cancelled | `True` or `False`; only `False` retained | JSON `null` | `sessions` |
| `circuit_short_name` | string | none | Short circuit name | Depends on API run | JSON `null` | `sessions` |
| `driver_number` | integer | car number | Driver's racing number for that season | Depends on API run | JSON `null` | `pit` |
| `lap_number` | integer | lap number | Lap of the pit-lane visit or race-control event | 1 or greater when present | JSON `null` | `pit` and `race_control` |
| `lane_duration` | float | seconds | Total time spent in the pit lane | Nonnegative; depends on API run | JSON `null` | `pit` |
| `stop_duration` | float | seconds | Stationary time in the pit box | Available only from 2024 US GP onward | JSON `null` | `pit` |
| `rainfall` | numeric/Boolean | indicator | Whether rain was recorded | 0/1 or false/true | JSON `null` | `weather` |
| `track_temperature` | float | degrees Celsius | Track temperature at the reading time | Depends on API run | JSON `null` | `weather` |
| `category` | string | none | Type of race-control event | Includes `SafetyCar` | JSON `null` | `race_control` |
| `flag` | string | none | Flag named in a race-control record | Includes `RED` | JSON `null` | `race_control` |
| `label` | string | none | Readable race label made from year and circuit | Example: `2023 Bahrain` | None if inputs exist | Derived in `eda.ipynb`: `year + circuit_short_name` |
| `rain` | Boolean | none | Whether `rainfall` is greater than zero | `True` or `False` | Missing if `rainfall` is missing | Derived in `eda.ipynb` |

### FastF1 validation fields used

| Column | Type | Units | Meaning | Range or allowed values in the Bahrain run | Missing-value coding | Origin |
| --- | --- | --- | --- | --- | --- | --- |
| `Driver` | string | none | Driver abbreviation | 20 drivers | `NaN` | FastF1 laps |
| `Stint` | float | stint number | Sequential tyre stint | Positive numbers | `NaN` | FastF1 laps |
| `LapNumber` | float | lap number | Driver's lap number | 1 through race distance | `NaN` | FastF1 laps |
| `LapTime` | timedelta | time | Recorded lap duration | Timedelta values | `NaT`; saved notebook output reports 1 missing | FastF1 laps |
| `LapTimeSeconds` | float | seconds | `LapTime` converted to seconds | Depends on valid lap times | `NaN` when `LapTime` is missing | Derived in `eda.ipynb` |
| `PitInTime` | timedelta | session time | Time at which a lap enters the pits | Present on 52 laps | `NaT` on non-pit-in laps | FastF1 laps |
| `PitOutTime` | timedelta | session time | Time at which a lap exits the pits | Present on 50 laps | `NaT` on non-pit-out laps | FastF1 laps |
| `IsAccurate` | Boolean | none | FastF1 timing-quality flag | `True` or `False` | None reported | FastF1 laps |
| `TrackStatus` | string | status code | Track condition code | Clean-lap filter keeps only `1` | Empty/`NaN` if absent | FastF1 laps |
| `Compound` | string | none | Tyre compound | `SOFT`, `MEDIUM`, `HARD` in this race | `NaN` | FastF1 laps |
| `TyreLife` | float | laps | Age of tyre set | 1–24 reported in `EDA.md` | `NaN` | FastF1 laps |
| `Laps` | integer | laps | Count of rows in each driver/stint group | Positive integer | None after grouping | Derived `stint_lengths` table in `fastf1_exploration.ipynb` |

### Race-results fields used

| Column | Type | Units | Meaning | Range or values in saved sample | Missing-value coding | Origin |
| --- | --- | --- | --- | --- | --- | --- |
| `raceId` | integer | none | Race key | 18–19 across the samples | None | Kaggle/Ergast-derived files |
| `driverId` | integer | none | Driver key | Integer IDs | None | Raw |
| `constructorId` | integer | none | Team key | Integer IDs | None | Raw |
| `position` in qualifying | integer | rank | Qualifying position | 1–10 | None | `qualifying.csv` |
| `grid` | integer | rank | Starting-grid position | 1–18 | None in saved sample | `results.csv` |
| `positionOrder` | integer | rank | Race finishing order including nonfinishers | 1–10 | None | `results.csv` |
| `points` | float | championship points | Race or cumulative standings points | Results: 0–10; standings: 1–14 | None | Results/standings files |
| `laps` | integer | laps | Race laps completed | 43–58 | None | `results.csv` |
| `milliseconds` | string | milliseconds | Race time, with `\N` used upstream for missing | Mixed numeric text and `\N` | Literal `\N` | `results.csv` |
| `milliseconds_numeric` | float | milliseconds | Numeric conversion of `milliseconds` | Valid numeric values or missing | `NaN` after coercion | Derived in `eda.ipynb` |
| `fastestLapSpeed` | float | km/h | Average speed on the driver's fastest lap | 212.974–218.385 | Literal `\N` upstream / `NaN` after cleaning | `results.csv` |
| `position` in standings | integer | rank | Driver championship position after the race | 1–8 | None | `driver_standings.csv` |
| `position_change` | integer | places | Qualifying position minus finishing order; positive means places gained | -7 to 4 among six matched rows | Missing if no join match | Derived in `eda.ipynb` |

## 4. Reproducible recipe

The repository currently produces several exploratory dataframes, not one final analysis dataframe. These are the steps the code actually performs.

1. Run [`data_acquisition.ipynb`](data_acquisition.ipynb) to download `jtrotman/formula-1-race-data` with `kagglehub`. The notebook then expects the qualifying, results, and driver-standings files under `data/`. The copy from the Kaggle cache into `data/` is not automated, so this is a current reproducibility gap.
2. In [`eda.ipynb`](eda.ipynb), load the three 10-row CSV files from `sample_data/`. These committed samples allow the early race-result checks to run without the full Kaggle download.
3. Check shapes, data types, missing values, summary statistics, and exact duplicates. No exact duplicate rows are found in the three samples.
4. In the results analysis copy, replace literal `\N` values with `pd.NA` and convert `milliseconds` to `milliseconds_numeric` with `pd.to_numeric(errors="coerce")`. The source CSV is not edited.
5. Join qualifying to results with an inner join on `raceId`, `driverId`, and `constructorId`. Of 10 qualifying and 10 result rows, **6 match, 4 qualifying rows do not match, and 4 result rows do not match**.
6. Derive `position_change = position_qual - positionOrder` for the six matched rows.
7. Join results to driver standings with an inner join on `raceId` and `driverId`. Of 10 result and 10 standings rows, **8 match, 2 result rows do not match, and 2 standings rows do not match**.
8. For OpenF1, call `sessions` for 2023, 2024, 2025, and 2026. Keep rows where `session_name == "Race"` and `is_cancelled == False`. Add `label = year + circuit_short_name`.
9. For each retained OpenF1 race, request `pit`, `weather`, and `race_control` using `session_key`. The helper waits 2.1 seconds between calls and retries HTTP 429 responses. Add `rain = rainfall > 0`. The responses are not saved, so row counts must be recorded during the next successful run.
10. For FastF1, load the 2023 Bahrain race and qualifying sessions with telemetry disabled. Copy laps, race results, weather, and qualifying results into dataframes.
11. Derive `LapTimeSeconds`. Create `clean_laps` by keeping rows where `IsAccurate` is true, `TrackStatus == "1"`, pit-in and pit-out times are missing, and lap time is present. The notebook reports 889 of 1,056 laps retained.
12. Load the two committed DHL TSV samples with `read_dhl`. Use tab separation, strip whitespace, and convert `Pos.`, `Time (sec)`, `Lap`, and `Points` to numeric types. No rows are dropped from the saved Bahrain sample.
13. For the broader DHL coverage check, list `.csv` files in the mirror's 2018–2026 year folders, download them to `dhl_cache/`, parse year and round from their paths, and combine them. Malformed rows are skipped only after a strict parse raises an error. The cache and combined dataframe are not committed.
14. **No join currently connects DHL or OpenF1 pit stops to the Kaggle race results.** Therefore, there are no honest matched/unmatched counts for that planned join. Before the final analysis, we need to define a stable race key (season, round/circuit, and date), a driver/team name crosswalk, save the joined table, and report both matched and unmatched counts.

---

## 5. Access, reuse, and FAIR checklist

| Dataset | Findable: persistent source | Accessible: version/date | Interoperable: format and identifiers | Reusable: license or terms and our decision |
| --- | --- | --- | --- | --- |
| DHL mirror | [`Jordan-Soria/PitStops`](https://github.com/Jordan-Soria/PitStops); official [DHL award page](https://inmotion.dhl/en/formula-1/fastest-pit-stop-award) | Accessed October 28, 2026; exact mirror commit was not recorded | Tab-separated text; team and driver names are free text; year/round come from paths | No license is stated for the mirror or table data. We will not claim unrestricted redistribution rights for a processed full copy. |
| OpenF1 | [API documentation](https://openf1.org/docs/) and base URL `https://api.openf1.org/v1` | Documentation checked October 28, 2026; live query results are not versioned | JSON or CSV; uses `meeting_key`, `session_key`, and `driver_number` | Stated for education, learning, research, and non-commercial fan use; no ownership claim over underlying F1 data. Share code and citation, not a claim of ownership over an export. |
| Kaggle/Ergast-derived data | [Kaggle dataset](https://www.kaggle.com/datasets/jtrotman/formula-1-race-data) | Download notebook output reflects the version available when it was run; exact access date/version not saved | CSV relational tables with race, driver, and constructor IDs | Exact dataset license was not verifiable from the repository. Reuse must follow the license shown on the Kaggle page at download time. |
| FastF1 | [FastF1 documentation](https://docs.fastf1.dev/) and [GitHub repository](https://github.com/theOehrly/Fast-F1) | Notebook output reports FastF1 3.8.3; Bahrain 2023 sessions | Python/pandas objects with documented lap and session fields | FastF1 code/docs are MIT; underlying timing-data rights are separate and not documented as MIT. Share code, not a claim that the timing data are ours. |

---

## 6. People, representation, and possible harm

These datasets describe people even though they are mostly performance records. Drivers are named directly. Pit crews are represented indirectly through team-level stop times, while individual crew members are left unnamed. Engineers, strategists, reserve drivers, mechanics outside the active stop crew, and other workers who affect performance are mostly invisible.

This creates a representation problem: a team's stop time can look like a direct measure of worker quality even though it also depends on equipment, pit-lane traffic, the driver's positioning, damage, penalties, safety procedures, and strategy. Slow or unusual stops may be necessary and should not automatically be treated as mistakes. Retirements and missing records can also make certain drivers or teams appear worse if context is ignored.

The data cover Formula One, an unusually well-funded and internationally visible racing series. They do not represent pit crews in Formula 2, Formula 3, women's racing series, regional series, or less-funded motorsport. Findings should not be generalized to those groups.

Using the CARE principles as a lens:

- **Collective benefit:** The project can help fans and students understand teamwork and strategy, but it should not be used to rank or target individual workers.
- **Authority to control:** Teams, drivers, and crews did not contribute to this student project or control our interpretation. The publishers do not document consent for this reuse.
- **Responsibility:** We need to explain timing definitions, missing periods, and race context instead of reducing a team to one number.
- **Ethics:** Results should remain descriptive. We should avoid claims about competence, employment decisions, or blame based only on pit-stop rankings.

No Indigenous identity or community data are recorded in these tables. Still, CARE is useful because it reminds us that publicly visible performance data concern real people and organizations, not just rows in a dataframe.

---

## References

- Timnit Gebru et al., [“Datasheets for Datasets”](https://doi.org/10.1145/3458723), 2021.
- Sam Lau, Joey Gonzalez, and Deb Nolan, [*Learning Data Science*, Chapter 2](https://learningds.org/ch/02/data_scope_intro.html).
- Mark D. Wilkinson et al., [“The FAIR Guiding Principles”](https://doi.org/10.1038/sdata.2016.18), 2016.
- Stephanie Russo Carroll et al., [“The CARE Principles for Indigenous Data Governance”](https://doi.org/10.5334/dsj-2020-043), 2020.
- Shannon E. Ellis and Jeffrey T. Leek, [“How to Share Data for Collaboration”](https://doi.org/10.1080/00031305.2017.1375987), 2018.
- [DHL Fastest Pit Stop Award](https://inmotion.dhl/en/formula-1/fastest-pit-stop-award).
- [`f1pits` documentation](https://github.com/Jordan-Soria/f1pits).
- [OpenF1 API documentation](https://openf1.org/docs/).
- [FastF1 documentation](https://docs.fastf1.dev/).
