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