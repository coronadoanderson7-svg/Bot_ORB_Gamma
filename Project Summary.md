Project Summary
The objective of this project is to develop an algorithmic trading engine designed to operate in the 0DTE (Zero Days to Expiration) options market. The system follows a structured, multi-stage workflow to identify and execute high-probability trades.
Core Processes: 

Opening Range Identification: Define the initial price range during the opening period.
Breakout Detection: Monitor and detect valid breakouts from the established opening range.
Gamma Exposure (GEX) Analysis: Calculate and incorporate GEX metrics to enhance trade selection.
Trade Execution: Systematically open and close positions based on signal confirmation.


Stage 1: Opening Range Identification
The goal is to define the initial price range during the first 30 minutes of the market session.

Step 1: IB API Communication Flow (High-Level)

Step,API Client Action (You Send),TWS/IB Gateway Action (You Receive)
Setup,"1. Connect to TWS/IB Gateway (e.g., eClient.connect(...)).","2. Connection established (e.g., eWrapper.connectionTime(...) is called)."
Contract,"3. Define the contract for your ticker (e.g., Contract object: symbol, secType, exchange, currency).","No immediate response, this is local."
Request Data,"4. Send the historical data request (e.g., eClient.reqHistoricalData(...)).","5. Data received in bars (e.g., eWrapper.historicalData(...) is called repeatedly for each bar)."
Data Received,,"6. End of data stream (e.g., eWrapper.historicalDataEnd(...) is called to signal completion)."
Cleanup,"7. Disconnect (e.g., eClient.disconnect()).",Connection is closed.

Step 2: Request Parameters (First 30 Minutes)

contract: The ticker of interest (e.g., AAPL).
endDateTime: Set to the current date and 30 minutes after market open (e.g., 09:30:00 EST + 30 mins).
durationStr: Set to '30 min' to define the historical data window.
barSizeSetting: Set to '1 min' resolution to accurately capture high/low.
whatToShow: Use 'TRADES' for open, high, low, close, and volume.
useRTH: Set to 1 (True) to ignore pre-market data

Step 3: Calculating Levels

Store Bar Data: Collect High and Low prices for every 1-minute bar received.
Filter/Validate: Ensure bars strictly fall within the market open window (no pre-market).
Find Range: Once historicalDataEnd is received:
HIGH_LEVEL: The maximum value of all collected High prices.
LOW_LEVEL: The minimum value of all collected Low prices.


Stage 2: Breakout Detection
Monitor real-time data to detect clean breakouts from the established range.

Step 1: Real-Time Data Flow
Setup: Ensure the TWS/Gateway connection is active.
Request Data: Send a request using eClient.reqRealTimeBars(...). Receive data via eWrapper.realtimeBar(...) every time a bar closes.
Processing: Client-side code aggregates 5-second bars into 5-minute candles and applies logic.
Cleanup: Cancel the subscription using eClient.cancelRealTimeBars(...) when finished.

Step 2: Breakout Calculation Conditions

Let the 5-minute candle consist of: $C_{High}$, $C_{Low}$, $C_{Open}$, and $C_{Close}$.

High Breakout (Bullish Signal):
Direction: Must be a bullish candle ($C_{Close} > C_{Open}$)
Clean Break: The entire body must be above the level ($C_{Low} > HIGH\_LEVEL$)

Low Breakout (Bearish Signal):
Direction: Must be a bearish candle ($C_{Close} < C_{Open}$)
Clean Break: The entire body must be below the level ($C_{High} < LOW\_LEVEL$)

Signal Result:

If High Breakout is true: BULLISH.
If Low Breakout is true: BEARISH.
Otherwise: NO SIGNAL.



Stage 3: Gamma Exposure (GEX) Analysis
Identify the strike with the largest gamma magnitude to enhance trade selection.

Step 1: Data Gathering

Option Parameters: Use reqSecDefOptParams to get valid expirations and strikes.
Filter & Build: Identify the 0DTE date and build Contract objects for all Call and Put strikes.
Request Option Data: Use reqMktData (Generic Ticks 100 or 101/28) to receive Gamma (via tickOptionComputation) and Open Interest.

Step 2: GEX Calculation

Calculate GEX for every Call and Put at each strike (K)
$$GEX_{i} = Gamma_{i} \times Open Interest_{i} \times Multiplier (100) \times sign$$

Directional Sign: Call GEX is positive (+); Put GEX is negative (-).
Total GEX per Strike: $GEX_{Strike} = GEX_{Call} + GEX_{Put}$.

Output: Highest_Gamma_Strike = Strike price with the largest absolute value $|GEX_{Strike}|.

Stage 4: Trade Execution

Systematically open/close positions based on Signal and Gamma outputs.

Part 1: Open Trade (Conditional Entry) 


Get ATM: Find the At-The-Money strike closest to current Spot_Price.
Define Contract: Build the 0DTE Call/Put Option_Contract.
Bullish Check: IF (Signal is BULLISH) AND (Highest_Gamma_Strike > Spot_Price) → Long Call.
Bearish Check: IF (Signal is BEARISH) AND (Highest_Gamma_Strike < Spot_Price) → Short Put.
Entry Price: Request Mid Price for the option to set $P_{entry}$.
Exit Levels:
    Take Profit ($P_{TP}$): $P_{entry} \times (1 + 0.20)$.
    Stop Loss ($P_{SL}$): $P_{entry} \times (1 - 0.30)$.

Part 2: Bracket Order Submission

Order Type,IB API Action,Description
Parent (Entry),Limit Order (BUY) at Pentry​. Set transmit = False.,Main order to establish the position.
Child 1 (TP),Limit Order (SELL) at PTP​. Set transmit = False.,Sells position for a 20% gain.
Child 2 (SL),Stop Order (SELL) at PSL​. Set transmit = True.,Sells for 30% loss. Sending True triggers the whole group.

Part 3: Close Trade (Automatic Management) 

The Bracket Order (OCA Group) manages the exit automatically:

If $P_{TP}$ hits: Limit Order fills, Stop Loss is automatically cancelled.
If $P_{SL}$ hits: Stop Order triggers and fills, Profit Taker is automatically cancelled.

