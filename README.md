# ⚽ Touchline IQ

### Beyond the Score. Into the Game.

Touchline IQ is an interactive football intelligence platform designed to help fans explore matches beyond the final score. It combines match simulations, event-driven analytics, tactical insights, match statistics, and highlights in one interactive interface.

Built with Python and Streamlit, Touchline IQ transforms football match events into accessible, structured insights for exploring what happens during a game and why it matters.

---

## 🎯 The Problem

Traditional football scoreboards tell fans what happened, but they don't always help explain how a match unfolded.

Fans may want to explore questions such as:

* How did a match develop over its 90 minutes?
* Which events shaped the final result?
* How did passing, shots, recoveries, and turnovers influence the game?
* What can match events reveal about a team's performance?
* How can match information be presented to fans with different levels of tactical knowledge?

Touchline IQ aims to bridge the gap between following the score and understanding the game.

## 💡 Our Solution

Touchline IQ provides an interactive match centre where users can explore live simulations and completed matches through multiple perspectives.

### Key Features

**1. Interactive Live Match Centre**

* Explore simulated matches as they progress.
* Play, pause, and navigate through match timelines.
* Review match events and statistics at different points in the game.
* Inspect historical match states without revealing future events.

**2. Event-Driven Match Analytics**

* Calculate match metrics from structured event data.
* Explore goals, shots, passes, successful passes, recoveries, and turnovers.
* Examine match patterns and performance indicators.
* Keep displayed results grounded in the underlying event history.

**3. Match Highlights**

* Explore important events from completed matches.
* Browse highlights derived from match event histories.
* Search and filter the highlight library.

**4. Four Interactive Match-Centre Tabs**

Both live and completed matches provide four dedicated views:

* **Overview:** Match score, statistics, event summaries, and insights.
* **Highlights:** Important events from the selected match.
* **Player Stats:** Player-related statistics derived from match data.
* **Commentary:** Event-based descriptions of the match.

Live views respect the selected historical timestamp, while completed matches use their full event histories.

**5. Multiple Match Scenarios**

* Two independent simulated live matches.
* Ten completed fictional matches.
* Distinct match histories and scoring scenarios.
* Stable match identities and scores derived from explicit goal events.

**6. Interactive Interface**

A Streamlit interface with a consistent purple-and-lime visual theme makes match information accessible through an organised, interactive experience.

---

## 🛠️ Technology Stack

| Technology | Purpose                                 |
| ---------- | --------------------------------------- |
| Python     | Core application logic and analytics    |
| Streamlit  | Interactive web interface               |
| Pandas     | Structured data processing              |
| Plotly     | Interactive visualisations, where used  |
| GitHub     | Source-code hosting and version control |

The application uses a deterministic synthetic match-data pipeline. This allows match scenarios to be explored reproducibly without depending on a live football-data API.

*Microsoft Foundry Local is being explored as a potential local AI integration; it is not claimed as an implemented application feature in this version.*

## 🧠 How It Works

Touchline IQ follows an event-driven architecture:

1. **Generate or load match events:** Create structured match-event histories.
2. **Validate event data:** Check that events follow the expected schema.
3. **Calculate analytics:** Derive match statistics from the underlying events.
4. **Identify patterns:** Analyse supported sequences and match developments.
5. **Present insights:** Display the resulting information through the match centre.
6. **Respect match state:** Filter live information according to the selected timestamp and use the full event history for completed matches.

This design keeps the displayed statistics connected to the underlying data instead of treating the scoreboard and analytics as independent sources of truth.

## 🚀 Getting Started

### Prerequisites

* Python 3.11 or a compatible Python version.
* pip.
* A web browser.

### Installation

Clone the repository:

```bash
git clone https://github.com/vedmahajan-code/touchline-iq.git
cd touchline-iq
```

Create a virtual environment:

**Windows**

```bash
python -m venv .venv
.venv\Scripts\activate
```

**macOS/Linux**

```bash
python -m venv .venv
source .venv/bin/activate
```

Install the required dependencies:

```bash
pip install streamlit pandas plotly
```

Run the application:

```bash
streamlit run app.py
```

Streamlit should provide a local URL that you can open in your browser.

**Note:** These are basic setup instructions. If the project uses additional dependencies, install them as well. A complete, verified `requirements.txt` should be used once the project's dependencies have been confirmed.

## 🧪 Testing

The project includes automated tests covering areas such as:

* Match-centre interface behaviour.
* Live and completed match views.
* Historical event filtering.
* Match-specific statistics and commentary.
* Separation of independent match histories.
* Synthetic-data pipeline behaviour.

During development, the test suite reported **22 passing tests** following the restoration of the four match-centre tabs.

This result reflects the local development test run; the test suite should be rerun against the final repository version.

## 🔒 Data and Scope

Touchline IQ uses fictional match scenarios and synthetic event histories for its current match-centre experience.

The project is designed to demonstrate interactive football analytics without requiring a live match-data provider.

Its insights are based on the information available in the selected match. The application should not present unsupported events or statistics as facts.

## 🗺️ Future Improvements

Potential future developments include:

* Local AI-powered match explanations.
* Distinct explanation styles for casual fans and tactical analysts.
* Evidence-linked answers grounded in the selected match's event history.
* Expanded tactical-pattern analysis.
* Additional visualisations and match-comparison tools.
* Improved automated testing and deployment.

These are planned directions, not claims that every feature is already implemented.

## 👨‍💻 Project Information

**Project:** Touchline IQ
**Tagline:** Beyond the Score. Into the Game.
**Category:** Football Analytics / Sports Technology
**Interface:** Streamlit
**Language:** Python

**Repository:**
https://github.com/vedmahajan-code/touchline-iq

---

*Touchline IQ — turning football events into football understanding.*
